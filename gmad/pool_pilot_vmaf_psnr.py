"""Apply every temporal pooling rule to the per-frame VMAF and PSNR-Y of the DSIS pilot videos.

Reads results/dsis_pilot/vmaf_psnr/frames/<candidate_id>.csv (from score_pilot_vmaf_psnr.py)
and pools each 540-frame series with run_selection.predict, i.e. with the same
time-converted parameters as the CVVDP predictions. The input offset is chosen
per metric as in run_selection (shift so the minimum frame value is >= 1).

PSNR-Y is pooled in the MSE domain, not in dB: each frame's PSNR is converted back to
MSE = 255^2 / 10^(PSNR/10), the rules pool -MSE (higher = better, as they expect),
and the pooled MSE is converted to dB once. For the mean rule this is the PSNR of the
mean MSE. Averaging dB instead lets frames identical to the reference (libvmaf caps
them at 60 dB, e.g. 1 frame in 4 of a 1080p30 chunk) inflate the score by an amount
that depends only on the cap.

Writes results/dsis_pilot/vmaf_psnr/predictions_vmaf.csv and predictions_psnr_y.csv
(candidate_id + one column per rule). Needs torch (e.g. the anaconda base Python).
"""
import numpy as np
import pandas as pd
import torch

from run_selection import RULES, ROOT, predict

FRAMES = ROOT / 'results' / 'dsis_pilot' / 'vmaf_psnr'
METRICS = ['vmaf', 'psnr_y']
PEAK = 255.   # 8-bit, as in libvmaf's psnr feature


def main():
    torch.set_num_threads(1)
    means = pd.read_csv(FRAMES / 'pilot_vmaf_psnr.csv').set_index('candidate_id')
    ids = means.index.tolist()
    frames = {c: pd.read_csv(FRAMES / 'frames' / f'{c}.csv') for c in ids}
    for metric in METRICS:
        q = [frames[c][metric].to_numpy(float) for c in ids]
        if metric == 'psnr_y':
            q = [-PEAK ** 2 / 10 ** (row / 10) for row in q]   # -MSE
        offset = max(0., 1. - min(float(row.min()) for row in q))
        pred = pd.DataFrame(predict(q, offset), columns=RULES)
        if metric == 'psnr_y':
            assert (pred < 0).all().all(), 'pooled MSE must stay positive'
            pred = 10 * np.log10(PEAK ** 2 / -pred)
            expected = [10 * np.log10(PEAK ** 2 / -row.mean()) for row in q]
        else:
            expected = means[f'mean_{metric}']
        assert np.allclose(pred['mean'], expected, atol=1e-3), metric
        pred.insert(0, 'candidate_id', ids)
        pred.to_csv(FRAMES / f'predictions_{metric}.csv', index=False)
        print(f'{metric}: offset {offset:g}, wrote {FRAMES / f"predictions_{metric}.csv"}')


if __name__ == '__main__':
    main()
