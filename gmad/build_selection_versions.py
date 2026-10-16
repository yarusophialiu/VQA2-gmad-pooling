"""Build two experiment-sized pair selections from a shot-grouped gMAD run.

Version A (all_scenes): K pairs from every scene, spread across its shots,
with every pair labelled by predicted perceptibility.
Version B (subset_scenes): only the scenes whose gMAD pairs have the largest
predicted differences, more pairs per scene, excluding likely-imperceptible pairs.

Perceptibility is a model-based screen, not a human threshold: max_model_gap
is the largest |delta JOD| between the two videos over all pooling rules.
1 JOD corresponds to 75% of observers preferring the better video; 0.5 JOD is
close to chance. Within a scene, pairs are chosen greedily to cover new
(defender, attacker, quality bin) cells first, then by normalized attack gap,
taking shots in turn so that every shot contributes.
"""
import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def perceptibility(gap, low, high):
    return ('likely_imperceptible' if gap < low else
            'possibly_imperceptible' if gap < high else 'likely_perceptible')


def choose(pairs, count):
    """Greedy cell coverage within one scene, taking its shots in turn."""
    by_shot = defaultdict(list)
    for p in pairs:
        by_shot[p['shot']].append(p)
    picks, covered, taken = [], set(), defaultdict(int)
    while len(picks) < count and any(by_shot.values()):
        shot = min((s for s in by_shot if by_shot[s]), key=lambda s: (taken[s], s))
        best = max(by_shot[shot], key=lambda p: (len(p['cells'] - covered), p['max_attack_gap_normalized'], p['pair_id']))
        by_shot[shot].remove(best)
        covered |= best['cells']
        taken[shot] += 1
        picks.append(best)
    return picks


def export(out, picks, recipes, description):
    out.mkdir(parents=True, exist_ok=True)
    rows = [{k: v for k, v in p.items() if k != 'cells'} for p in picks]
    write_csv(out / 'pairs.csv', rows)
    ids = {p[key] for p in picks for key in ('video_a', 'video_b')}
    (out / 'video_recipes.json').write_text(
        json.dumps([recipes[i] for i in sorted(ids)], indent=2) + '\n', encoding='utf-8')
    labels = defaultdict(int)
    for p in picks:
        labels[p['perceptibility']] += 1
    per_scene = defaultdict(int)
    for p in picks:
        per_scene[p['scene']] += 1
    summary = dict(description=description, pairs=len(picks), videos=len(ids),
                   scenes=dict(sorted(per_scene.items())), perceptibility=dict(sorted(labels.items())))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gmad-dir', type=Path, required=True, help='run_selection.py --group-by shot output')
    parser.add_argument('--pairs-per-scene', type=int, default=10, help='Version A pairs per scene')
    parser.add_argument('--subset-scenes', type=int, default=5, help='Version B number of scenes')
    parser.add_argument('--subset-pairs-per-scene', type=int, default=25)
    parser.add_argument('--scenes', nargs='+', help='Version B scenes, overriding the ranking')
    parser.add_argument('--imperceptible-jod', type=float, default=0.5)
    parser.add_argument('--perceptible-jod', type=float, default=1.0)
    args = parser.parse_args()
    root = args.gmad_dir
    config = json.loads((root / 'config.json').read_text())
    assert config['content_group_policy'].startswith('full shot path'), 'Run run_selection.py with --group-by shot'
    rules = config['rules']
    predictions = {r['candidate_id']: [float(r[name]) for name in rules] for r in read_csv(root / 'predictions.csv')}
    recipes = {r['candidate_id']: r for r in json.loads((root / 'selected_video_recipes.json').read_text())}
    cells, attack = defaultdict(set), defaultdict(float)
    for t in read_csv(root / 'attack_tasks.csv'):
        if t['status'] == 'selected':
            cells[t['pair_id']].add((config['representative'][t['defender']],
                                     config['representative'][t['attacker']], t['quality_bin']))
            attack[t['pair_id']] = max(attack[t['pair_id']], float(t['attack_gap_normalized']))
    pairs = []
    for p in read_csv(root / 'gmad_pairs.csv'):
        a, b = predictions[p['video_a']], predictions[p['video_b']]
        gaps = [abs(x - y) for x, y in zip(a, b)]
        mean = rules.index('mean')
        gap = max(gaps)
        pairs.append(dict(pair_id=p['pair_id'], scene=p['scene'].split('__')[0], shot=p['scene'].replace('__', '/', 1),
                          video_a=p['video_a'], video_b=p['video_b'],
                          settings_a=p['settings_a'], settings_b=p['settings_b'],
                          gmad_task_count=int(p['gmad_task_count']),
                          mean_jod_a=round(a[mean], 4), mean_jod_b=round(b[mean], 4),
                          mean_rule_gap=round(gaps[mean], 4), median_model_gap=round(statistics.median(gaps), 4),
                          max_model_gap=round(gap, 4),
                          max_gap_rule=rules[gaps.index(gap)],
                          max_attack_gap_normalized=round(attack[p['pair_id']], 4),
                          perceptibility=perceptibility(gap, args.imperceptible_jod, args.perceptible_jod),
                          cells=cells[p['pair_id']]))
    by_scene = defaultdict(list)
    for p in pairs:
        by_scene[p['scene']].append(p)
    ranking = []
    for scene, items in sorted(by_scene.items()):
        gaps = [p['max_model_gap'] for p in items]
        ranking.append(dict(scene=scene, shots=len({p['shot'] for p in items}), gmad_pairs=len(items),
                            median_max_model_gap=round(statistics.median(gaps), 4),
                            share_likely_perceptible=round(sum(p['perceptibility'] == 'likely_perceptible' for p in items) / len(items), 4),
                            share_likely_imperceptible=round(sum(p['perceptibility'] == 'likely_imperceptible' for p in items) / len(items), 4)))
    ranking.sort(key=lambda r: (-r['median_max_model_gap'], r['scene']))
    for rank, row in enumerate(ranking, 1):
        row['rank'] = rank
    write_csv(root / 'scene_ranking.csv', ranking)
    write_csv(root / 'pair_perceptibility.csv', [{k: v for k, v in p.items() if k != 'cells'} for p in pairs])

    version_a = [p for scene in sorted(by_scene) for p in choose(by_scene[scene], args.pairs_per_scene)]
    summary_a = export(root / 'selection_all_scenes', version_a, recipes,
                       f'{args.pairs_per_scene} pairs per scene from all scenes; perceptibility labelled, none excluded')
    subset = args.scenes or [r['scene'] for r in ranking[:args.subset_scenes]]
    assert set(subset) <= set(by_scene), f'Unknown scenes: {set(subset) - set(by_scene)}'
    version_b = [p for scene in subset for p in choose(
        [p for p in by_scene[scene] if p['perceptibility'] != 'likely_imperceptible'], args.subset_pairs_per_scene)]
    summary_b = export(root / 'selection_subset_scenes', version_b, recipes,
                       f'{args.subset_pairs_per_scene} pairs per scene from {", ".join(subset)}; likely-imperceptible pairs excluded')
    print(json.dumps(dict(scene_ranking=ranking, all_scenes=summary_a, subset_scenes=summary_b), indent=2))


if __name__ == '__main__':
    main()
