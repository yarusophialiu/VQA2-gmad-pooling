"""Generate lossless resolution/FPS variants and score each 1.5 s chunk on iridium.

The source is dataset-reference-chunks/*/*/{lossless_hevc,4000}/ref_chunkN.mp4.
The remote ``4000`` directory contains the same lossless reference files as the
locally renamed ``lossless_hevc`` directory; it is not a 4 Mbps test source.
All new test variants are HEVC lossless, so the only intended changes are
spatial downsampling and/or temporal downsampling.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pycvvdp

from extract_gmad_frame_scores import extract


SOURCE_ROOT = Path("/local/scratch-2/yl962/VQA/VQA_Postprocess_Dataset/dataset-reference-chunks")
FULL_REFERENCE_ROOT = Path("/local/scratch-2/yl962/VQA/VQA_over_time/dataset-1080p-4mbps-full")
OUTPUT_ROOT = Path("/local/scratch-2/yl962/VQA2/results/gmad_frame_scores/lossless_spatiotemporal_chunks")
HELPER_DIR = Path("/local/scratch-2/yl962/VQA2/metric_calibration_pooling")
CONDITIONS = [(height, fps) for height in (720, 1080) for fps in (30, 60, 120)]
DEFAULT_SCENES = ("bistro", "gallery", "makeway", "school", "sibenik")


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate,nb_frames", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)["streams"][0]


def references(root: Path, scenes: set[str]) -> list[tuple[Path, Path]]:
    found = []
    for shot in sorted(root.glob("*/*")):
        if not shot.is_dir():
            continue
        if shot.parent.name not in scenes:
            continue
        source_dir = next((shot / name for name in ("lossless_hevc", "4000") if (shot / name).is_dir()), None)
        if source_dir is None:
            continue
        for index in (1, 2, 3):
            ref = source_dir / f"ref_chunk{index}.mp4"
            if not ref.is_file():
                raise FileNotFoundError(ref)
            found.append((ref, shot.relative_to(root)))
    if not found:
        raise FileNotFoundError(f"No reference chunks found under {root}")
    return found


def native_jod(path: Path) -> float:
    with path.open(newline="") as stream:
        records = list(csv.DictReader(stream))
    if len(records) != 1:
        raise ValueError(f"Expected one CVVDP result in {path}")
    return float(next(value for key, value in records[0].items() if key.strip() == "cvvdp"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--full-reference-root", type=Path, default=FULL_REFERENCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--scenes", nargs="+", default=DEFAULT_SCENES)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, help="Run only the first N conditions, for a pilot")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    jobs = [(source_ref, shot, height, fps) for source_ref, shot in references(args.source_root, set(args.scenes))
            for height, fps in CONDITIONS]
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        jobs = jobs[:args.limit]
    if not args.dry_run:
        sys.path.insert(0, str(HELPER_DIR))
        from per_frame_quality import cvvdp_per_frame_jod
        metric = pycvvdp.cvvdp(display_name="standard_fhd", device=args.device)
    cvvdp = Path(sys.executable).with_name("cvvdp")
    manifest = []
    for number, (source_ref, shot, height, fps) in enumerate(jobs, 1):
        chunk = int(re.fullmatch(r"ref_chunk([123])", source_ref.stem).group(1))
        output_dir = args.output_root / shot
        full_ref = args.full_reference_root / shot / "4000" / "reference_8000_start_0_120_1080.mp4"
        ref = output_dir / "references" / f"ref_chunk{chunk}_lossless_hevc.mp4"
        stem = f"chunk{chunk}_{height}p{fps}_lossless_hevc"
        test = output_dir / "videos" / f"{stem}.mp4"
        features = output_dir / "features" / f"{stem}_fmap.json"
        native = output_dir / "native" / f"{stem}_native.csv"
        frames = output_dir / "frames" / f"{stem}_frames.csv"
        if args.dry_run:
            print(f"[{number}/{len(jobs)}] {test} VS {ref} (from {full_ref}; existing {source_ref})")
            continue
        full_info = probe(full_ref)
        if (int(full_info["width"]), int(full_info["height"])) != (1920, 1080) or abs(float(Fraction(full_info["avg_frame_rate"])) - 120) > 0.1:
            raise ValueError(f"Unexpected full reference format: {full_ref}: {full_info}")
        if int(full_info["nb_frames"]) < 540:
            raise ValueError(f"Full reference has fewer than 540 frames: {full_ref}")
        if not ref.is_file() or int(probe(ref).get("nb_frames", 0)) != 180:
            ref.parent.mkdir(parents=True, exist_ok=True)
            start = (chunk - 1) * 180
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(full_ref),
                 "-vf", f"trim=start_frame={start}:end_frame={start + 180},setpts=N/(120*TB)",
                 "-fps_mode", "passthrough",
                 "-an", "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "lossless=1",
                 "-pix_fmt", "yuv420p", str(ref)], check=True,
            )
        if int(probe(ref)["nb_frames"]) != 180:
            raise ValueError(f"Rebuilt reference is not 180 frames: {ref}")
        if (height, fps) == (1080, 120):
            test.parent.mkdir(parents=True, exist_ok=True)
            if not test.is_symlink() or test.resolve() != ref.resolve():
                test.unlink(missing_ok=True)
                test.symlink_to(ref)
        elif not test.is_file() or int(probe(test).get("nb_frames", 0)) != round(fps * 1.5):
            test.parent.mkdir(parents=True, exist_ok=True)
            filter_chain = f"fps={fps}" + (f",scale=-2:{height}:flags=bicubic" if height != 1080 else "")
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ref),
                 "-vf", filter_chain, "-an", "-frames:v", str(round(fps * 1.5)),
                 "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "lossless=1",
                 "-pix_fmt", "yuv420p", str(test)], check=True,
            )
        if not features.is_file() or not native.is_file():
            features.parent.mkdir(parents=True, exist_ok=True)
            native.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [str(cvvdp), "--test", str(test), "--ref", str(ref), "--device", args.device,
                 "--display", "standard_fhd", "--full-screen-resize", "bilinear",
                 "--temp-resample", "120", "--features", "--output-dir", str(features.parent),
                 "--result", str(native)], check=True,
            )
        jod = native_jod(native)
        if not frames.is_file():
            info = extract(features, frames, jod, metric, cvvdp_per_frame_jod, duration_s=1.5)
        else:
            info = json.loads(frames.with_suffix(".metadata.json").read_text())
        item = {"scene": shot.parts[0], "shot": str(shot), "chunk": chunk,
                "height": height, "fps": fps, "test": str(test), "reference": str(ref),
                "native_jod": jod, "frames_csv": str(frames),
                "source_frames": info["source_frames"],
                "usable_for_design": info["usable_for_design"]}
        manifest.append(item)
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"[{number}/{len(jobs)}] {shot} chunk{chunk} {height}p{fps}: "
              f"JOD={jod:.5f}, frames={info['exported_frames']}, usable={info['usable_for_design']}", flush=True)
    print(f"Completed {len(manifest)} conditions: {args.output_root / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
