"""Tune temporal pooling parameters on one pilot scene (makeway), test on the rest.

For each predictor (per-frame CVVDP JOD proxy, VMAF, PSNR-Y over the 540-frame
4.5 s pilot videos) and each pooling rule with parameters, a grid search picks
the parameters with the highest SRCC against MOS on the tuning scene (ties: higher
PLCC, then the grid point closest to the default). The tuned and default
parameters are then compared on the other pilot videos: pooled SRCC/PLCC over
all held-out videos, the Fisher-z mean of per-scene SRCC, and a paired
bootstrap of the SRCC gain.

Defaults are the time-converted values of the gMAD run (config.json). The rules
are NumPy copies of temporal_pooling_snapshot.py (checked against it at start-up).
mean, median and vqpooling_temporal have no parameters; cumulative_quality's
50/60 s windows reduce to the mean at 4.5 s, so it is left out.

Inputs: results/cvvdp_combined_version_a/frames/<id>.csv (jod_proxy),
results/dsis_pilot/vmaf_psnr/frames/<id>.csv, results/dsis_pilot/analysis/video_mos.csv.
Writes results/dsis_pilot/analysis/tuning_<scene>/: grid.csv (every grid point's
tuning-scene SRCC/PLCC), best_params.csv and test_results.csv.

Example:
  python gmad/tune_pooling_makeway.py [--scene makeway]
"""
import argparse
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'results' / 'dsis_pilot'
CVVDP_FRAMES = ROOT / 'results' / 'cvvdp_combined_version_a' / 'frames'
VMAF_FRAMES = PILOT / 'vmaf_psnr' / 'frames'
FPS = 120
BOOT = 2000
rng = np.random.default_rng(0)


# ---- NumPy copies of temporal_pooling_snapshot.py --------------------------------------------

def percentile(q, p):
    k = min(q.size, max(1, math.ceil(p / 100.0 * q.size)))
    return np.sort(q)[:k].mean()


def kth_percentile(q, k):
    return np.quantile(q, k / 100.0)


def minkowski(q, p):
    return np.mean(q ** p) ** (1.0 / p)


def exp_weighted_minkowski(q, p, tau):
    t = np.arange(1, q.size + 1)
    w = np.exp((t - q.size) / tau)
    return (np.sum(w * q ** p) / w.sum()) ** (1.0 / p)


def last_frames_mean(q, num_frames):
    return q[-min(num_frames, q.size):].mean()


def worst_window(q, window):
    window = min(window, q.size)
    c = np.concatenate([[0.0], np.cumsum(q)])
    return ((c[window:] - c[:-window]) / window).min()


def hysteresis(q, tau, alpha, fps=FPS):
    T = q.size
    n = max(1, round(tau * fps))
    weights = {}
    g = np.empty(T)
    for t in range(T):
        memory = q[0] if t == 0 else q[max(0, t - n):t].min()
        v = np.sort(q[t:min(t + n, T - 1) + 1])
        K = v.size
        if K not in weights:
            sigma = (2 * K - 1) / 12.0
            w = np.exp(-np.arange(K) ** 2 / (2 * sigma ** 2))
            weights[K] = w / w.sum()
        g[t] = alpha * (v * weights[K]).sum() + (1 - alpha) * memory
    return g.mean()


def segment_weighted(q, weights):
    w = np.asarray(weights, float)
    seg = np.array([s.mean() for s in np.array_split(q, w.size)])
    return (seg * w / w.sum()).sum()


def early_dominance(q, n_segments):
    return segment_weighted(q, [1.0] + [0.0] * (n_segments - 1))


def late_dominance(q, n_segments):
    return segment_weighted(q, [0.0] * (n_segments - 1) + [1.0])


def increasing_weights(q, n_segments):
    return segment_weighted(q, list(range(1, n_segments + 1)))


def decreasing_weights(q, n_segments):
    return segment_weighted(q, list(range(n_segments, 0, -1)))


P_GRID = [-8, -4, -2, -1, -0.5, 0.5, 1, 2, 4, 8]
SEGMENTS = [2, 3, 4, 5, 6, 9]
# rule: (function, default parameters, grid {parameter: values}); time parameters in frames at 120 Hz
RULES = {
    'percentile': (percentile, {'p': 5.0}, {'p': [1, 2, 5, 10, 20, 30, 40, 50, 75, 100]}),
    'kth_percentile': (kth_percentile, {'k': 50.0}, {'k': [1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90]}),
    'minkowski': (minkowski, {'p': 2.0}, {'p': P_GRID}),
    'exp_weighted_minkowski': (exp_weighted_minkowski, {'p': 2.0, 'tau': 480},
                               {'p': [-4, -2, -1, 1, 2, 4], 'tau': [30, 60, 120, 240, 480, 960, 1920]}),
    'last_frames_mean': (last_frames_mean, {'num_frames': 600},
                         {'num_frames': [30, 60, 90, 120, 180, 240, 300, 360, 420, 480, 540]}),
    'worst_window': (worst_window, {'window': 480}, {'window': [1, 12, 30, 60, 90, 120, 180, 240, 360, 480, 540]}),
    'hysteresis': (hysteresis, {'tau': 2.0, 'alpha': 0.8},
                   {'tau': [0.05, 0.1, 0.25, 0.5, 1.0, 2.0], 'alpha': [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]}),
    'early_dominance': (early_dominance, {'n_segments': 3}, {'n_segments': SEGMENTS}),
    'late_dominance': (late_dominance, {'n_segments': 3}, {'n_segments': SEGMENTS}),
    'increasing_weights': (increasing_weights, {'n_segments': 3}, {'n_segments': SEGMENTS}),
    'decreasing_weights': (decreasing_weights, {'n_segments': 3}, {'n_segments': SEGMENTS}),
}
UNTUNED = {'mean': np.mean, 'median': np.median}


def check_against_torch(q):
    """The NumPy rules must reproduce temporal_pooling_snapshot.py at the defaults and a few grid points."""
    import torch
    import temporal_pooling_snapshot as ref
    names = {'percentile': 'percentile_pooling', 'kth_percentile': 'kth_percentile_pooling',
             'minkowski': 'minkowski_pooling', 'exp_weighted_minkowski': 'exp_weighted_minkowski_pooling',
             'last_frames_mean': 'last_frames_mean_pooling', 'worst_window': 'worst_window_pooling',
             'hysteresis': 'hysteresis_pooling', 'early_dominance': 'early_dominance_pooling',
             'late_dominance': 'late_dominance_pooling', 'increasing_weights': 'increasing_weights_pooling',
             'decreasing_weights': 'decreasing_weights_pooling'}
    qt = torch.tensor(q, dtype=torch.float64)
    for rule, (fn, default, grid) in RULES.items():
        for params in [default, {k: v[0] for k, v in grid.items()}, {k: v[-1] for k, v in grid.items()}]:
            kwargs = dict(params, fps=FPS) if rule == 'hysteresis' else params
            want = float(getattr(ref, names[rule])(qt, **kwargs))
            got = fn(q, **params)
            assert abs(want - got) < 1e-9 * max(1, abs(want)), (rule, params, want, got)


def load_series(ids):
    series = {'cvvdp': {}, 'vmaf': {}, 'psnr_y': {}}
    for cid in ids:
        series['cvvdp'][cid] = pd.read_csv(CVVDP_FRAMES / f'{cid}.csv')['jod_proxy'].to_numpy(float)
        frames = pd.read_csv(VMAF_FRAMES / f'{cid}.csv')
        # Negative Minkowski exponents need q > 0; VMAF can reach 0 on a frame.
        series['vmaf'][cid] = np.maximum(frames['vmaf'].to_numpy(float), 1e-3)
        series['psnr_y'][cid] = frames['psnr_y'].to_numpy(float)
    for name, s in series.items():
        assert all(v.size == 540 for v in s.values()), name
    return series


def fisher_mean(values, weights=None):
    values = np.asarray(values, float)
    weights = np.ones_like(values) if weights is None else np.asarray(weights, float)
    keep = np.isfinite(values)
    return np.tanh(np.average(np.arctanh(np.clip(values[keep], -0.999, 0.999)), weights=weights[keep]))


def distance(params, default, grid):
    """Grid-index distance from the default, used only to break exact ties."""
    total = 0
    for k, v in params.items():
        values = sorted(set(grid[k]) | {default[k]})
        total += abs(values.index(v) - values.index(default[k]))
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scene', default='makeway')
    args = parser.parse_args()

    df = pd.read_csv(PILOT / 'analysis' / 'video_mos.csv')[['candidate_id', 'scene', 'mos']]
    series = load_series(df.candidate_id)
    check_against_torch(series['cvvdp'][df.candidate_id.iloc[0]])
    train = df[df.scene == args.scene]
    test = df[df.scene != args.scene]
    print(f'Tuning on {args.scene}: {len(train)} videos; testing on {len(test)} videos from '
          f'{test.scene.nunique()} scenes')

    def pooled(metric, fn, params, ids):
        return np.array([fn(series[metric][cid], **params) for cid in ids])

    scenes = [(test.scene == s).to_numpy() for s in test.scene.unique()]

    def held_out(x, y):
        """Pooled SRCC/PLCC and the Fisher-z scene average of SRCC, equal and n - 3 weighted (as the report)."""
        per_scene = [stats.spearmanr(x[m], y[m])[0] for m in scenes]
        return {'srcc': stats.spearmanr(x, y)[0], 'plcc': stats.pearsonr(x, y)[0],
                'scene_srcc': fisher_mean(per_scene),
                'scene_srcc_weighted': fisher_mean(per_scene, [m.sum() - 3 for m in scenes])}

    grid_rows, best_rows, test_rows = [], [], []
    for metric in series:
        for rule, (fn, default, grid) in RULES.items():
            points = [dict(zip(grid, values)) for values in itertools.product(*grid.values())]
            if default not in points:
                points.append(dict(default))
            scored = []
            for params in points:
                x = pooled(metric, fn, params, train.candidate_id)
                srcc = stats.spearmanr(x, train.mos)[0]
                plcc = stats.pearsonr(x, train.mos)[0] if np.ptp(x) > 0 else np.nan
                srcc, plcc = np.nan_to_num(srcc, nan=-1), np.nan_to_num(plcc, nan=-1)
                scored.append((srcc, plcc, -distance(params, default, grid), params))
                grid_rows.append({'metric': metric, 'rule': rule, 'params': params, 'train_srcc': srcc,
                                  'train_plcc': plcc, 'is_default': params == default})
            best = max(scored, key=lambda s: s[:3])
            tuned = best[3]
            train_default = next(s for s in scored if s[3] == default)
            best_rows.append({'metric': metric, 'rule': rule, 'default': default, 'tuned': tuned,
                              'train_srcc_default': train_default[0], 'train_srcc_tuned': best[0],
                              'train_plcc_default': train_default[1], 'train_plcc_tuned': best[1]})

            # Held-out scenes
            x_def = pooled(metric, fn, default, test.candidate_id)
            x_tun = pooled(metric, fn, tuned, test.candidate_id)
            y = test.mos.to_numpy()
            row = {'metric': metric, 'rule': rule, 'tuned': tuned}
            for tag, x in (('default', x_def), ('tuned', x_tun)):
                row.update({f'{k}_{tag}': v for k, v in held_out(x, y).items()})
            idx = rng.integers(0, len(y), (BOOT, len(y)))
            gain = np.array([stats.spearmanr(x_tun[i], y[i])[0] - stats.spearmanr(x_def[i], y[i])[0] for i in idx])
            row['srcc_gain'] = row['srcc_tuned'] - row['srcc_default']
            row['gain_lo'], row['gain_hi'] = np.nanpercentile(gain, [2.5, 97.5])
            test_rows.append(row)
            print(f"{metric:7s} {rule:24s} tuned {tuned}  train SRCC {train_default[0]:.3f} -> {best[0]:.3f}  "
                  f"test SRCC {row['srcc_default']:.3f} -> {row['srcc_tuned']:.3f} "
                  f"[{row['gain_lo']:+.3f}, {row['gain_hi']:+.3f}]", flush=True)

        for rule, fn in UNTUNED.items():
            x = np.array([fn(series[metric][cid]) for cid in test.candidate_id])
            test_rows.append({'metric': metric, 'rule': rule, 'tuned': {},
                              **{f'{k}_default': v for k, v in held_out(x, test.mos.to_numpy()).items()}})

    out = PILOT / 'analysis' / f'tuning_{args.scene}'
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(grid_rows).to_csv(out / 'grid.csv', index=False)
    pd.DataFrame(best_rows).to_csv(out / 'best_params.csv', index=False)
    results = pd.DataFrame(test_rows).sort_values(['metric', 'srcc_tuned'], ascending=[True, False])
    results.to_csv(out / 'test_results.csv', index=False)
    print(f'\nWrote {out}')


if __name__ == '__main__':
    main()
