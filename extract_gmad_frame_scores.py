"""Convert a ColorVideoVDP --features JSON into a frame quality CSV.

Run with the same pycvvdp version and display model used to produce the
feature JSON. This uses VQA2's existing per_frame_quality.py implementation,
which validates that temporal pooling of the frame-domain response reproduces
the official full-video JOD.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pycvvdp


def load_features(path: Path) -> dict:
    data = json.loads(path.read_text())
    names = [key for key in data if re.fullmatch(r"t\d+_b\d+", key)]
    if not names:
        raise ValueError(f"No per-frame channel/band features in {path}")
    channels = max(int(re.match(r"t(\d+)_", key).group(1)) for key in names) + 1
    bands = max(int(re.search(r"_b(\d+)$", key).group(1)) for key in names) + 1
    frames = int(data["N_frames"])
    expected = {f"t{c}_b{b}" for c in range(channels) for b in range(bands)}
    if set(names) != expected:
        raise ValueError(f"Incomplete channel/band grid in {path}")
    q = np.empty((1, channels, frames, bands), dtype=np.float32)
    for c in range(channels):
        for b in range(bands):
            series = np.asarray(data[f"t{c}_b{b}"], dtype=np.float32)
            if series.shape != (1, frames):
                raise ValueError(f"Unexpected t{c}_b{b} shape {series.shape}")
            q[0, c, :, b] = series[0]
    return {"Q_per_ch": q, "frames_per_second": float(data["frames_per_second"])}


def extract(
    feature_path: Path,
    output_path: Path,
    full_video_jod: float,
    metric,
    per_frame_function,
    duration_s: float = 4.5,
) -> dict:
    stats = load_features(feature_path)
    scores = np.asarray(per_frame_function(metric, stats, full_video_jod), dtype=float)
    fps = stats["frames_per_second"]
    if not math.isclose(fps, 120.0, abs_tol=1e-6):
        raise ValueError(f"Expected common 120 fps axis, got {fps}")
    design_frames = round(fps * duration_s)
    if not np.isfinite(scores).all():
        raise ValueError(f"Non-finite frame scores in {feature_path}")
    exported_frames = min(len(scores), design_frames)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frame_index", "time_s", "jod_frame_proxy"])
        for i, value in enumerate(scores[:exported_frames]):
            writer.writerow([i, f"{i / fps:.9f}", f"{value:.9f}"])

    metadata = {
        "feature_json": str(feature_path),
        "full_video_jod": full_video_jod,
        "fps": fps,
        "source_frames": len(scores),
        "design_duration_s": duration_s,
        "design_frames": design_frames,
        "exported_frames": exported_frames,
        "missing_design_frames": max(0, design_frames - len(scores)),
        "usable_for_design": len(scores) >= design_frames,
        "excluded_trailing_frames": max(0, len(scores) - design_frames),
        "score": "JOD-like per-frame proxy from video-mode Q_per_ch, before temporal pooling",
        "display": "standard_fhd",
    }
    if math.isclose(duration_s, 4.5):
        metadata["usable_for_4p5s_design"] = metadata["usable_for_design"]
    output_path.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("features", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("full_video_jod", type=float)
    parser.add_argument("--helper-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--duration", type=float, default=4.5, help="Expected video duration in seconds")
    args = parser.parse_args()
    sys.path.insert(0, str(args.helper_dir))
    from per_frame_quality import cvvdp_per_frame_jod

    metric = pycvvdp.cvvdp(display_name="standard_fhd", device=args.device)
    metadata = extract(args.features, args.output, args.full_video_jod, metric, cvvdp_per_frame_jod, args.duration)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
