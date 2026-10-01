"""Temporal pooling rules that collapse per-frame quality into one scalar.

Every quality-pooling function takes a 1-D torch tensor of per-frame quality
(higher = better) and returns a 0-d tensor. See temporal_pooling_rules.md for
the source paper, formula and parameter values of each rule.
"""

import math

import torch
import torch.nn.functional as F


def _vec(q):
    q = torch.as_tensor(q)
    if q.ndim != 1 or q.numel() == 0:
        raise ValueError("expected a non-empty 1-D tensor of per-frame values")
    return q if q.is_floating_point() else q.to(torch.get_default_dtype())


def mean_pooling(q):
    """Arithmetic mean of all frames."""
    return _vec(q).mean()


def median_pooling(q):
    """Median of all frames."""
    return torch.quantile(_vec(q), 0.5)


def percentile_pooling(q, p=5.0):
    """Mean of the lowest p% of frame scores (worst-case emphasis)."""
    q = _vec(q)
    k = min(q.numel(), max(1, math.ceil(p / 100.0 * q.numel())))
    return torch.sort(q).values[:k].mean()


def kth_percentile_pooling(q, k=50.0):
    """Value at the k-th percentile of the frame-score histogram (Rimac-Drlje)."""
    return torch.quantile(_vec(q), k / 100.0)


def minkowski_pooling(q, p=2.0):
    """(mean(q^p))^(1/p); p<0 emphasises the lowest scores when q>0."""
    return _vec(q).pow(p).mean().pow(1.0 / p)


def exp_weighted_minkowski_pooling(q, p=2.0, tau=100.0, normalize=True):
    """Minkowski sum with weights exp((t-T)/tau) that favour the latest frames."""
    q = _vec(q)
    T = q.numel()
    t = torch.arange(1, T + 1, dtype=q.dtype, device=q.device)
    w = torch.exp((t - T) / tau)
    denom = w.sum() if normalize else T
    return ((w * q.pow(p)).sum() / denom).pow(1.0 / p)


def last_frames_mean_pooling(q, num_frames=125):
    """Mean of the last num_frames frames (recency)."""
    q = _vec(q)
    return q[-min(num_frames, q.numel()):].mean()


def worst_window_pooling(q, window=100):
    """Lowest moving average over `window` consecutive frames."""
    q = _vec(q)
    window = min(window, q.numel())
    return F.avg_pool1d(q[None, None], window, stride=1).min()


def hysteresis_pooling(q, fps=25.0, tau=2.0, alpha=0.8):
    """Seshadrinathan & Bovik hysteresis: alpha*current + (1-alpha)*memory, then mean."""
    q = _vec(q)
    T = q.numel()
    n = max(1, round(tau * fps))
    weights = {}

    def gauss_weights(K):
        if K not in weights:
            sigma = (2 * K - 1) / 12.0
            k = torch.arange(K, dtype=q.dtype, device=q.device)
            w = torch.exp(-(k ** 2) / (2 * sigma ** 2))
            weights[K] = w / w.sum()
        return weights[K]

    g = []
    for t in range(T):
        memory = q[0] if t == 0 else q[max(0, t - n):t].min()
        v = torch.sort(q[t:min(t + n, T - 1) + 1]).values
        current = (v * gauss_weights(v.numel())).sum()
        g.append(alpha * current + (1 - alpha) * memory)
    return torch.stack(g).mean()


def vqpooling_temporal(q, max_iter=100):
    """Park et al. temporal VQPooling: 2-means split, high-quality group down-weighted."""
    q = _vec(q)
    lo, hi = q.min().detach(), q.max().detach()
    if lo == hi:
        return q.mean()
    for _ in range(max_iter):
        is_low = (q.detach() - lo).abs() <= (q.detach() - hi).abs()
        if is_low.all() or (~is_low).all():
            return q.mean()
        new_lo, new_hi = q.detach()[is_low].mean(), q.detach()[~is_low].mean()
        if new_lo == lo and new_hi == hi:
            break
        lo, hi = new_lo, new_hi
    low, high = q[is_low], q[~is_low]
    w = (1.0 - low.mean() / high.mean()) ** 2
    return (low.sum() + w * high.sum()) / (low.numel() + w * high.numel())


def cumulative_quality_pooling(q, fps=1.0, weights=(0.280, 0.426, 0.280, 0.014),
                               windows=(50, 60, 50, 50)):
    """Tran et al. CQM = w_last*WQ_last + w_avg*WQ_avg + w_min*WQ_min + w_max*WQ_max (windows in s)."""
    q = _vec(q)
    seg = torch.stack([s.mean() for s in torch.split(q, max(1, round(fps)))])

    def window_quality(K):
        return F.avg_pool1d(seg[None, None], min(K, seg.numel()), stride=1)[0, 0]

    w_last, w_avg, w_min, w_max = weights
    k_last, k_avg, k_min, k_max = windows
    return (w_last * window_quality(k_last)[-1]
            + w_avg * window_quality(k_avg).mean()
            + w_min * window_quality(k_min).min()
            + w_max * window_quality(k_max).max())


def hammerstein_wiener_pooling(q, b, f, beta, gamma, fps=1.0, skip=0):
    """Chen et al. HW model (sigmoid -> IIR filter -> linear); mean of predicted time-varying quality."""
    q = _vec(q)
    per_second = torch.stack([s.mean() for s in torch.split(q, max(1, round(fps)))])
    b, f, beta = (torch.as_tensor(x, dtype=q.dtype) for x in (b, f, beta))
    u = beta[2] + beta[3] / (1 + torch.exp(-(beta[0] * per_second + beta[1])))
    v = []
    for t in range(u.numel()):
        acc = sum(b[d] * u[t - d] for d in range(min(b.numel(), t + 1)))
        acc = acc + sum(f[d - 1] * v[t - d] for d in range(1, min(f.numel(), t) + 1))
        v.append(acc)
    out = gamma[0] * torch.stack(v) + gamma[1]
    return out[skip:].mean()


def segment_weighted_pooling(q, weights):
    """Split into len(weights) equal segments, average each, combine with normalised weights."""
    q = _vec(q)
    w = torch.as_tensor(weights, dtype=q.dtype, device=q.device)
    seg = torch.stack([s.mean() for s in torch.tensor_split(q, w.numel())])
    return (seg * w / w.sum()).sum()


def early_dominance_pooling(q, n_segments=2):
    """Only the first segment counts."""
    return segment_weighted_pooling(q, [1.0] + [0.0] * (n_segments - 1))


def late_dominance_pooling(q, n_segments=2):
    """Only the last segment counts."""
    return segment_weighted_pooling(q, [0.0] * (n_segments - 1) + [1.0])


def increasing_weights_pooling(q, n_segments=2):
    """Linearly increasing segment weights (1/3, 2/3 for two segments)."""
    return segment_weighted_pooling(q, list(range(1, n_segments + 1)))


def decreasing_weights_pooling(q, n_segments=2):
    """Linearly decreasing segment weights (2/3, 1/3 for two segments)."""
    return segment_weighted_pooling(q, list(range(n_segments, 0, -1)))


_FRAME_RATE_FLOOR_MODELS = {95.0: (0.025, 1.95), 90.0: (0.026, 1.74), 99.0: (0.024, 2.29)}


def frame_time_std_pooling(frame_times_ms, return_qoe=True):
    """Claypool et al.: QoE (1-5) = -0.16 * std(frame time in ms) + 4.63. Input is frame times, not quality."""
    s = _vec(frame_times_ms).std(unbiased=False)
    return -0.16 * s + 4.63 if return_qoe else s


def frame_rate_floor_pooling(frame_times_ms, target_fps, percentile=95.0, return_qoe=True):
    """Claypool et al.: frame-rate floor as % of target rate; QoE (1-5) is linear in it. Input is frame times."""
    ft = torch.quantile(_vec(frame_times_ms), percentile / 100.0)
    floor_pct = 100.0 * (1000.0 / ft) / target_fps
    if not return_qoe:
        return floor_pct
    if percentile not in _FRAME_RATE_FLOOR_MODELS:
        raise ValueError(f"QoE model only published for percentiles {sorted(_FRAME_RATE_FLOOR_MODELS)}")
    slope, intercept = _FRAME_RATE_FLOOR_MODELS[percentile]
    return slope * floor_pct + intercept


RULES = {
    "mean": mean_pooling,
    "median": median_pooling,
    "percentile": percentile_pooling,
    "kth_percentile": kth_percentile_pooling,
    "minkowski": minkowski_pooling,
    "exp_weighted_minkowski": exp_weighted_minkowski_pooling,
    "last_frames_mean": last_frames_mean_pooling,
    "worst_window": worst_window_pooling,
    "hysteresis": hysteresis_pooling,
    "vqpooling_temporal": vqpooling_temporal,
    "cumulative_quality": cumulative_quality_pooling,
    "early_dominance": early_dominance_pooling,
    "late_dominance": late_dominance_pooling,
    "increasing_weights": increasing_weights_pooling,
    "decreasing_weights": decreasing_weights_pooling,
}
