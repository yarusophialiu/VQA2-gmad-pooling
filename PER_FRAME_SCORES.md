# How per-frame scores are computed

ColorVideoVDP (CVVDP) gives one JOD for a whole video. The temporal pooling
rules we compare need one score **per frame**. We get these by running CVVDP once
in **video mode** and stopping its pooling one step early, *before* the frames are
pooled over time. Each frame's pooled response is converted to JOD with CVVDP's
own mapping.

These are **video-mode frame proxies**, not image-mode CVVDP scores for each frame.
The code: [`per_frame_quality.py`](per_frame_quality.py) (`cvvdp_per_frame_jod`).

## 1. Run CVVDP once on the video

Test and reference are loaded with
`pycvvdp.video_source_temp_resample_file(test, ref, full_screen_resize='bilinear', resize_resolution=[1920, 1080])`
and scored with `metric.predict_video_source(...)`, display model `standard_fhd`.

- Both videos are resized to 1920×1080 (bilinear) and put on a common 120 Hz axis
  by frame repetition: a 30 fps frame is shown for 4 refreshes, 60 fps for 2, the
  same as on the experiment display.
- CVVDP splits each frame into 4 channels (`t0`–`t3`: achromatic sustained, red–green,
  yellow–violet, achromatic transient) and 8 spatial bands (`b0`–`b7`; `b7` is the
  baseband). The sustained/transient channels come from temporal filters over
  neighbouring frames, so each frame's values already carry motion and flicker
  information.
- Besides the JOD, CVVDP returns the per-frame features `Q_per_ch[video, channel, frame, band]`.
  These are the distortion responses before any pooling, and are saved as `--features` JSON
  (`t<channel>_b<band>` arrays).

## 2. Pool space and channels, but not time

CVVDP's own pooling (`do_pooling_and_jods`) has three steps, each an Lp norm:

| Step | Over | Exponent | Formula |
|---|---|---|---|
| 1 | spatial bands *b* | β_sch = 4 | Q_sc[c,f] = ( Σ_b ( w_c · w_cb · Q[c,f,b] )⁴ )^¼ |
| 2 | channels *c* | β_tch = 4 | Q_tc[f] = ( Σ_c Q_sc[c,f]⁴ )^¼ |
| 3 | frames *f* | β_t = 2, normalised | Q = ( (1/N) Σ_f Q_tc[f]² )^½ |

followed by the JOD mapping `met2jod`:

```
JOD(Q) = 10 − a · Q^e            for Q > 0.1     (a = 0.04396, e = 0.9302)
JOD(Q) = 10 − a · 0.1^(e−1) · Q   for Q ≤ 0.1     (linear near 0)
```

Channel weights w_c are 1 for the achromatic and both chromatic channels and
0.808 for the transient channel. The band weight w_cb is 1, except for the
baseband, which has a per-channel weight (0.0036, 1.66, 4.12, 25.3).

**The per-frame score is `JOD(Q_tc[f])`.** We run steps 1 and 2 exactly as CVVDP does,
skip step 3, and convert each frame's response with `met2jod`. A frame with no
visible difference scores 10. Strongly distorted frames can score below 0,
because the mapping is not clamped.

## 3. Check against CVVDP's own score

Before saving, `cvvdp_per_frame_jod` rebuilds the full-video JOD from the
per-frame responses (step 3, then `met2jod`). It compares the result with
(a) CVVDP's `do_pooling_and_jods` on the same features and (b) the JOD returned by
`predict_video_source`. If either differs (tolerance 1e-5 / 1e-4), it raises an
error and nothing is written. So the per-frame scores always reproduce CVVDP's
official score, and the check fails as soon as a CVVDP version pools differently.
Channel-blocking variants (`block_channels`) are rejected.

## Things to keep in mind

- **Context-dependent.** The temporal filters look at neighbouring frames, so the
  same frame can score differently in a different clip, and differently from
  CVVDP's image mode.
- **The mean of the per-frame JODs is not the clip's JOD.** CVVDP takes the L2 mean
  of the *responses* and converts that to JOD. Because JOD is non-linear in Q and
  the L2 mean weighs bad frames more, averaging per-frame JODs gives a higher
  (milder) value.
- **First frames.** Temporal padding is `replicate`: before frame 1 the filters see
  copies of frame 1, so the transient channel starts from a static history.
- **Frame index and time.** Scores are on the 120 Hz axis (frame *i* at *i*/120 s),
  regardless of the test video's native frame rate.

## Where the scores come from

| Use | Scored unit | Script | Output |
|---|---|---|---|
| gMAD selection | each 1.5 s chunk separately (180 frames) | [`run_local_chunk_scores.py`](run_local_chunk_scores.py), [`run_iridium_lossless_chunks.py`](run_iridium_lossless_chunks.py) → [`extract_gmad_frame_scores.py`](extract_gmad_frame_scores.py) | `<shot>/frames/chunkN_<res><fps>_lossless_hevc_frames.csv` (`frame_index, time_s, jod_frame_proxy`) + `.metadata.json` |
| DSIS stimuli as seen | whole 4.5 s video, 3 chunks joined (540 frames) | [`gmad/score_combined_cvvdp.py`](gmad/score_combined_cvvdp.py) | `results/cvvdp_combined_version_a/frames/<candidate_id>.csv` (`frame, chunk, time_s, jod_proxy`) |

**Chunk scores (gMAD selection).** Each chunk is scored against its own reference
chunk. A 4.5 s candidate's sequence is then the three 180-frame sequences laid end to
end. The temporal filters restart at every chunk boundary, so the change between
chunks is not seen by CVVDP. Candidate sequences were pooled with the gMAD rules
(time policy `converted`, negative-score frames dropped; see the README).

**Combined scores (DSIS stimuli).** The three chunks are joined in memory into one
540-frame source, so the temporal filters run across chunk boundaries. The video is
scored as participants see it. 1080p120 test chunks use the reference file, as the
experiment does. Over the 239 Version A videos, the combined JOD is on average
0.44 JOD lower than the mean of the three chunk JODs (correlation 0.95); see
`results/cvvdp_combined_version_a/combined_jod_report.html`.

## Reproducing

- CVVDP: git checkout [`gfxdisp/ColorVideoVDP`](https://github.com/gfxdisp/ColorVideoVDP)
  at `e837f06` (metric v0.5.6), passed with `--cvvdp-root`. It reproduces the
  earlier chunk scores exactly. The PyPI `cvvdp==0.5.6` release is a different
  snapshot, so don't use it for these scores.
- Python: torch 2.6.0 + CUDA 12.4. On this machine: `~/micromamba/envs/cvvdp`, checkout in `~/toolboxes/ColorVideoVDP`.
- `video_source_temp_resample_file.max_fps` is set to 120. With 30/60/120 fps tests
  against a 120 fps reference, the resampling rate is 120 Hz either way.

```bash
~/micromamba/envs/cvvdp/bin/python gmad/score_combined_cvvdp.py --cvvdp-root ~/toolboxes/ColorVideoVDP
```
