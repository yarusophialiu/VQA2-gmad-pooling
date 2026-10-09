"""Video-mode CVVDP frame proxies, with checked reconstruction of native JOD.

Follow CVVDP's do_pooling_and_jods through spatial-band and channel pooling,
then map each frame's response to JOD before temporal pooling. These are
video-mode frame proxies, not independent-image CVVDP scores.
"""
import numpy as np
import torch


def cvvdp_per_frame_jod(metric, stats, full_video_jod):
    features = torch.as_tensor(stats['Q_per_ch'], device=metric.device).clone()
    if features.ndim != 4 or features.shape[0] != 1 or features.shape[2] < 2:
        raise ValueError('Expected one video: Q_per_ch[1, channel, frame, band]')
    if metric.block_channels is not None:
        raise ValueError('Channel-blocking variants are not supported by this exporter')
    channels, bands = features.shape[1], features.shape[3]
    band_weights = torch.ones((1, channels, 1, bands), device=metric.device, dtype=features.dtype)
    band_weights[:, :, 0, -1] = metric.baseband_weight[:channels]
    spatial = metric.lp_norm(features * metric.get_ch_weights(channels) * band_weights,
                             metric.beta_sch, dim=3, normalize=False)
    response = metric.lp_norm(spatial, metric.beta_tch, dim=1, normalize=False)
    recovered = metric.met2jod(metric.lp_norm(response, metric.beta_t, dim=2, normalize=True).squeeze())
    official = metric.do_pooling_and_jods(features)
    if not torch.allclose(recovered, official, atol=1e-5, rtol=1e-6):
        raise ValueError('Frame-domain response does not reproduce CVVDP temporal pooling')
    if abs(float(recovered) - float(full_video_jod)) > 1e-4:
        raise ValueError(f'Native JOD mismatch: recovered={float(recovered)}, native={full_video_jod}')
    scores = metric.met2jod(response).reshape(-1).detach().cpu().numpy()
    if not np.isfinite(scores).all():
        raise ValueError('Non-finite frame proxies')
    return scores
