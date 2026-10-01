"""Score all six fixed conditions per scene on iridium for gMAD candidate construction.

Uses full 4.5 s test and reference videos, ColorVideoVDP video mode with a
common 120 fps axis, then exports 540 frame scores for each condition.
The run is resumable: existing features and score CSVs are reused.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import pycvvdp

from extract_gmad_frame_scores import extract


DATA_ROOT = Path("/local/scratch-2/yl962/VQA/VQA_over_time/dataset-1080p-4mbps-full")
OUTPUT_ROOT = Path("/local/scratch-2/yl962/VQA2/results/gmad_frame_scores/fixed_4mbps")
HELPER_DIR = Path("/local/scratch-2/yl962/VQA2/metric_calibration_pooling")


def read_jod(path: Path) -> float:
    with path.open(newline="") as stream:
        records = list(csv.DictReader(stream))
    if len(records) != 1:
        raise ValueError(f"Expected one ColorVideoVDP result in {path}, got {len(records)}")
    return float(next(value for key, value in records[0].items() if key.strip() == "cvvdp"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N conditions, for a pilot")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    videos = sorted(args.data_root.rglob("4000_start_0_*_*.mp4"))
    if not videos:
        raise SystemExit(f"No fixed videos found under {args.data_root}")
    if args.limit is not None:
        videos = videos[: args.limit]
    sys.path.insert(0, str(HELPER_DIR))
    from per_frame_quality import cvvdp_per_frame_jod

    metric = pycvvdp.cvvdp(display_name="standard_fhd", device=args.device)
    cvvdp = Path(sys.executable).with_name("cvvdp")
    manifest = []
    for i, video in enumerate(videos, start=1):
        relative = video.relative_to(args.data_root)
        reference = video.parent / "reference_8000_start_0_120_1080.mp4"
        if not reference.is_file():
            raise FileNotFoundError(reference)
        out_dir = args.output_root / relative.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        features = out_dir / f"{video.stem}_fmap.json"
        native_csv = out_dir / f"{video.stem}_native.csv"
        frame_csv = out_dir / f"{video.stem}_frames.csv"
        if not (features.is_file() and native_csv.is_file()):
            command = [
                str(cvvdp), "--test", str(video), "--ref", str(reference),
                "--device", args.device, "--display", "standard_fhd",
                "--full-screen-resize", "bilinear", "--temp-resample", "120",
                "--features", "--output-dir", str(out_dir), "--result", str(native_csv),
            ]
            print(f"[{i}/{len(videos)}] ColorVideoVDP {relative}", flush=True)
            subprocess.run(command, check=True)
        else:
            print(f"[{i}/{len(videos)}] Reusing ColorVideoVDP features {relative}", flush=True)

        native_jod = read_jod(native_csv)
        if not frame_csv.is_file():
            info = extract(features, frame_csv, native_jod, metric, cvvdp_per_frame_jod)
        else:
            metadata_path = frame_csv.with_suffix(".metadata.json")
            info = json.loads(metadata_path.read_text())
            info.setdefault("exported_frames", min(info["source_frames"], info["design_frames"]))
            info.setdefault("missing_design_frames", max(0, info["design_frames"] - info["source_frames"]))
            info.setdefault("usable_for_4p5s_design", info["missing_design_frames"] == 0)
            metadata_path.write_text(json.dumps(info, indent=2) + "\n")
        manifest.append({
            "test": str(video), "reference": str(reference),
            "native_jod": native_jod, "frames_csv": str(frame_csv),
            "source_frames": info["source_frames"],
            "usable_for_4p5s_design": info["usable_for_4p5s_design"],
            "missing_design_frames": info["missing_design_frames"],
            "excluded_trailing_frames": info["excluded_trailing_frames"],
        })
        print(
            f"  JOD={native_jod:.5f}; {info['exported_frames']} frame scores saved; "
            f"usable_for_4p5s_design={info['usable_for_4p5s_design']}",
            flush=True,
        )

    manifest_path = args.output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Completed {len(manifest)} conditions: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
