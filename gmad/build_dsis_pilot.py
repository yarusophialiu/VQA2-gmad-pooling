"""Select the DSIS pilot: 5-12 shots (references), each with all of its videos.

Every Version A video belongs to a gMAD pair within its shot, so taking whole
shots keeps every gMAD pair complete. Several shots of one scene are allowed.
Candidates are sets of SHOTS shots outside EXCLUDE with <= MAX_VIDEOS videos
(sized for ~40 min at ~20 s per trial) whose videos, by CVVDP DSIS level
(4.5 s combined JOD), cover levels 1-5 with >= MIN_LEVEL1 level-1 videos, from
>= MIN_SCENES scenes that each span >= MIN_SPAN levels. Among them it keeps the
one with the most level-5 videos, then the fewest level-2 + level-3 videos,
then more scenes, then fewer videos.

Writes results/dsis_pilot/: pilot_recipes.json (for run_dsis_pilot.m),
pilot_videos.csv (with CVVDP scores) and pilot_pairs.csv (gMAD pairs).
"""
import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / 'results' / 'gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted' / 'selection_all_scenes'
SCORES = ROOT / 'results' / 'cvvdp_combined_version_a' / 'combined_jod_dsis.csv'
OUTPUT = ROOT / 'results' / 'dsis_pilot'
MAX_VIDEOS = 110       # ~20 s per trial incl. rating and loading -> ~37 min, plus breaks
SHOTS = range(5, 13)   # number of references
EXCLUDE = {'school', 'bistro', 'sibenik', 'gallery'}   # scenes kept out of the pilot
MIN_LEVEL1 = 10        # level 1 is the scarcest level
MIN_SCENES = 8
MIN_SPAN = 3           # levels each scene must cover (fox and rogue reach 3 at most)


def scene_of(shot):
    return shot.split('__')[0]


def main():
    with SCORES.open(newline='') as stream:
        scores = {row['candidate_id']: row for row in csv.DictReader(stream)}
    levels = defaultdict(lambda: [0] * 5)
    for row in scores.values():
        levels[row['shot']][int(row['dsis_level']) - 1] += 1
    shots = [s for s in sorted(levels) if scene_of(s) not in EXCLUDE]
    size = {s: sum(levels[s]) for s in shots}
    covered = {s: {i for i in range(5) if levels[s][i]} for s in shots}

    best, best_key, searched = None, None, 0
    for k in SHOTS:
        for chosen in itertools.combinations(shots, k):
            if sum(size[s] for s in chosen) > MAX_VIDEOS:
                continue
            searched += 1
            counts = [sum(levels[s][i] for s in chosen) for i in range(5)]
            if min(counts) == 0 or counts[0] < MIN_LEVEL1:
                continue
            spans = defaultdict(set)
            for s in chosen:
                spans[scene_of(s)] |= covered[s]
            widths = [len(v) for v in spans.values()]
            if len(spans) < MIN_SCENES or min(widths) < MIN_SPAN:
                continue
            key = (counts[4], -(counts[1] + counts[2]), len(spans), -sum(counts))
            if best_key is None or key > best_key:
                best, best_key = chosen, key

    recipes = [r for r in json.loads((SELECTION / 'video_recipes.json').read_text()) if r['scene'] in best]
    with (SELECTION / 'pairs.csv').open(newline='') as stream:
        pairs = [p for p in csv.DictReader(stream) if p['video_a'].rsplit('__', 1)[0] in best]
    ids = {r['candidate_id'] for r in recipes}
    assert all(p['video_a'] in ids and p['video_b'] in ids for p in pairs), 'incomplete gMAD pair'

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'pilot_recipes.json').write_text(json.dumps(recipes, indent=1) + '\n')
    with (OUTPUT / 'pilot_videos.csv').open('w', newline='') as stream:
        fields = ['candidate_id', 'scene', 'shot', 'chunk1', 'chunk2', 'chunk3', 'combined_jod', 'dsis_level', 'dsis_label']
        writer = csv.DictWriter(stream, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(sorted((scores[i] for i in ids), key=lambda r: (r['shot'], -float(r['combined_jod']))))
    with (OUTPUT / 'pilot_pairs.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)

    counts = [sum(levels[s][i] for s in best) for i in range(5)]
    print(f'{len(best)} references from {len({scene_of(s) for s in best})} scenes, {len(recipes)} videos, {len(pairs)} gMAD pairs '
          f'(searched {searched} shot sets)')
    print('DSIS level 1-5 counts:', counts)
    for scene in sorted({scene_of(s) for s in best}):
        members = [s for s in best if scene_of(s) == scene]
        span = sorted({i + 1 for s in members for i in covered[s]})
        print(f'  {scene:10s} levels {",".join(map(str, span)):9s}  '
              + ', '.join(f'{s.split("__")[1]} {levels[s]}' for s in members))
    print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
