"""Analyse the DSIS pilot ratings in results/dsis_pilot/ratings/.

No subject rejection (too few participants): MOS = plain mean of the 1-5 scores.
Unrated trials (a session stopped early) are blank rows and are dropped.
Reports rater agreement, how well CVVDP and each temporal pooling rule predict
MOS, and gMAD aggressiveness / resistance per rule (Ma et al., TPAMI 2020),
with q = (MOS of the attacker's high video - MOS of its low video) / 4.

Writes results/dsis_pilot/analysis/: video_mos.csv, subjects.csv, rules.csv,
scene_srcc.csv (SRCC per predictor and scene), gmad_tasks.csv and gmad_rules.csv. (Too few tasks per rule pair for a
Thurstone global ranking, so per-rule means are reported instead.)

Run with a Python that has numpy, scipy and pandas (e.g. ../VQA2/.venv).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'results' / 'dsis_pilot'
GMAD = ROOT / 'results' / 'gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted'
OUTPUT = PILOT / 'analysis'
SPLITS = 2000
rng = np.random.default_rng(0)


def corr(x, y):
    keep = x.notna() & y.notna()
    x, y = x[keep], y[keep]
    return stats.spearmanr(x, y)[0], stats.pearsonr(x, y)[0], stats.kendalltau(x, y)[0]


def fisher_mean(values, weights=None):
    """Average correlations in Fisher-z space; NaN (constant input) entries are skipped."""
    values = np.asarray(values, float)
    weights = np.ones_like(values) if weights is None else np.asarray(weights, float)
    keep = np.isfinite(values)
    z = np.arctanh(np.clip(values[keep], -0.999, 0.999))
    return np.tanh(np.average(z, weights=weights[keep]))


def main():
    ratings = pd.concat([pd.read_csv(p) for p in sorted((PILOT / 'ratings').glob('*_ratings.csv'))])
    ratings = ratings.dropna(subset=['score'])
    videos = pd.read_csv(PILOT / 'pilot_videos.csv')
    predictions = pd.read_csv(GMAD / 'predictions.csv', encoding='utf-8-sig')
    rules = [c for c in predictions.columns if c != 'candidate_id']

    # MOS without subject rejection
    table = ratings.pivot(index='candidate_id', columns='subject', values='score')
    n = table.notna().sum(axis=1)
    mos = pd.DataFrame({'mos': table.mean(axis=1), 'std': table.std(axis=1), 'n': n})
    mos['ci95'] = stats.t.ppf(0.975, n - 1) * mos['std'] / np.sqrt(n)
    df = videos.merge(mos, left_on='candidate_id', right_index=True).merge(predictions, on='candidate_id')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT / 'video_mos.csv', index=False)

    subjects = table.columns
    print('Ratings per subject:', table.notna().sum().to_dict())
    print(f'{len(subjects)} subjects, {len(table)} videos, {int(n.min())}-{int(n.max())} ratings per video, '
          f'{len(ratings)} ratings')
    print(f'MOS range {mos.mos.min():.2f}-{mos.mos.max():.2f}, mean per-video std {mos["std"].mean():.2f}, '
          f'mean 95% CI half-width {mos.ci95.mean():.2f}')
    print('Skipped samples (ref/test) total:', int(ratings.reference_skipped_samples.sum()),
          int(ratings.test_skipped_samples.sum()))
    print('Score histogram:', ratings.score.value_counts().sort_index().to_dict())

    # Per subject: bias, agreement with leave-one-out MOS, behaviour
    rows = []
    for s in subjects:
        others = table.drop(columns=s).mean(axis=1)
        srcc, plcc, _ = corr(table[s], others)
        r = ratings[ratings.subject == s]
        rows.append({'subject': s, 'ratings': int(table[s].notna().sum()), 'mean_score': table[s].mean(), 'bias_vs_others': (table[s] - others).mean(),
                     'mad_vs_others': (table[s] - others).abs().mean(), 'srcc_loo': srcc, 'plcc_loo': plcc,
                     'replay_rate': (r.replays > 0).mean(), 'median_rating_time_s': r.rating_time_s.median()})
    subj = pd.DataFrame(rows)
    subj.to_csv(OUTPUT / 'subjects.csv', index=False)
    print('\nPer subject:\n' + subj.round(3).to_string(index=False))

    # Split-half reliability (3 vs 4 raters), Spearman-Brown corrected to the full panel
    halves = []
    for _ in range(SPLITS):
        order = rng.permutation(subjects)
        a, b = table[order[:len(order) // 2]].mean(axis=1), table[order[len(order) // 2:]].mean(axis=1)
        halves.append([stats.spearmanr(a, b)[0], stats.pearsonr(a, b)[0]])
    z = np.arctanh(np.array(halves)).mean(axis=0)
    half = np.tanh(z)
    full = 2 * half / (1 + half)
    print(f'\nSplit-half SRCC {half[0]:.3f} / PLCC {half[1]:.3f}; Spearman-Brown ceiling '
          f'SRCC {full[0]:.3f} / PLCC {full[1]:.3f}')

    # Predictors vs MOS: CVVDP on the full video, its DSIS level, and every pooling rule
    rows = []
    for column in ['combined_jod', 'dsis_level'] + rules:
        srcc, plcc, krcc = corr(df[column], df['mos'])
        boot = [stats.spearmanr(*df.iloc[i][[column, 'mos']].T.values)[0]
                for i in rng.integers(0, len(df), (1000, len(df)))]
        rows.append({'predictor': column, 'srcc': srcc, 'srcc_lo': np.percentile(boot, 2.5),
                     'srcc_hi': np.percentile(boot, 97.5), 'plcc': plcc, 'krcc': krcc})
    pred = pd.DataFrame(rows)

    # Per scene: SRCC of each predictor against MOS over all of the scene's videos (every shot kept),
    # then the Fisher-z mean over scenes, equal-weighted and weighted by n - 3 (videos per scene)
    scenes = df.groupby('scene')
    sizes = scenes.size()
    per_scene = pd.DataFrame({column: {s: stats.spearmanr(g[column], g['mos'])[0] for s, g in scenes}
                              for column in pred.predictor}).T
    pred['scene_srcc_mean'] = pred.predictor.map(lambda c: fisher_mean(per_scene.loc[c]))
    pred['scene_srcc_weighted'] = pred.predictor.map(lambda c: fisher_mean(per_scene.loc[c], sizes[per_scene.columns] - 3))
    pred = pred.sort_values('srcc', ascending=False)
    pred.to_csv(OUTPUT / 'rules.csv', index=False)
    per_scene.columns = [f'{s} ({sizes[s]})' for s in per_scene.columns]
    per_scene.loc[pred.predictor].to_csv(OUTPUT / 'scene_srcc.csv', index_label='predictor')
    print('\nPredictors vs MOS (84 videos):\n' + pred.round(3).to_string(index=False))
    print('\nSRCC per scene (videos):\n' + per_scene.loc[pred.predictor].round(2).to_string())

    # gMAD: every attack task whose pair is in the pilot
    tasks = pd.read_csv(GMAD / 'attack_tasks.csv', encoding='utf-8-sig')
    pairs = pd.read_csv(PILOT / 'pilot_pairs.csv')
    tasks = tasks[tasks.pair_id.isin(pairs.pair_id)].copy()
    tasks['mos_high'] = tasks.video_high.map(mos.mos)
    tasks['mos_low'] = tasks.video_low.map(mos.mos)
    tasks['q'] = (tasks.mos_high - tasks.mos_low) / 4
    tasks.to_csv(OUTPUT / 'gmad_tasks.csv', index=False)

    pair_mos_gap = (pairs.video_a.map(mos.mos) - pairs.video_b.map(mos.mos)).abs()
    print(f'\ngMAD: {len(pairs)} pairs, {len(tasks)} attack tasks; |MOS gap| per pair median '
          f'{pair_mos_gap.median():.2f}, {int((pair_mos_gap >= 0.5).sum())} pairs >= 0.5')
    print(f'Attacker right (q > 0) in {(tasks.q > 0).mean():.0%} of tasks, wrong (q < 0) in {(tasks.q < 0).mean():.0%}')

    names = sorted(set(tasks.attacker) | set(tasks.defender))
    rows = []
    for r in names:
        att, dfd = tasks[tasks.attacker == r], tasks[tasks.defender == r]
        rows.append({'rule': r, 'tasks_as_attacker': len(att), 'aggressiveness': att.q.mean() if len(att) else np.nan,
                     'attacker_wrong_rate': (att.q < 0).mean() if len(att) else np.nan,
                     'tasks_as_defender': len(dfd),
                     'resistance': (1 - dfd.q.abs()).mean() if len(dfd) else np.nan})
    summary = pd.DataFrame(rows)

    summary = summary.sort_values('aggressiveness', ascending=False)
    summary.to_csv(OUTPUT / 'gmad_rules.csv', index=False)
    print('\ngMAD per rule (q in [-1, 1]):\n' + summary.round(3).to_string(index=False))
    print(f'\nWrote {OUTPUT}')


if __name__ == '__main__':
    main()
