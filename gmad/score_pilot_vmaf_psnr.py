"""Per-frame VMAF and PSNR for every DSIS pilot video (results/dsis_pilot/pilot_recipes.json).

Same stimulus as score_combined_cvvdp.py: each test chunk is bilinear-resized
full screen to 1920x1080 and frame-repeated onto a 120 Hz axis, the three
chunks are joined into one 540-frame clip and compared with the shot's three
1080p120 reference chunks. 1080p120 test chunks use the reference file, as the
experiment does (so their PSNR is libvmaf's 8-bit cap of 60 dB).

Scores come from ffmpeg's libvmaf on the native 8-bit YUV 4:2:0 frames:
VMAF model vmaf_v0.6.1 (built into ffmpeg) and libvmaf's psnr feature (Y, Cb, Cr).

Writes <output>/frames/<candidate_id>.csv (540 rows: frame, chunk, vmaf,
psnr_y, psnr_cb, psnr_cr) and <output>/pilot_vmaf_psnr.csv (one row per video,
mean of the per-frame scores). Videos with a finished frames CSV are skipped,
so a rerun resumes.

Example:
  python gmad/score_pilot_vmaf_psnr.py --ffmpeg C:/ffmpeg-.../bin/ffmpeg.exe
"""
import argparse
import csv
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PILOT = ROOT / 'results' / 'dsis_pilot'
CHUNK_FRAMES = 180   # 1.5 s at 120 Hz
METRICS = ['vmaf', 'psnr_y', 'psnr_cb', 'psnr_cr']


def local_path(path):
    """Recipes store Windows paths; find the same file under this workspace's VQA2-dataset."""
    relative = re.search(r'[\\/]VQA2-dataset[\\/](.*)$', path).group(1).replace('\\', '/')
    local = WORKSPACE / 'VQA2-dataset' / relative
    assert local.is_file(), f'Missing {local}'
    return local


def filter_graph(fps):
    """Test chunks: repeat frames onto 120 Hz, resize to 1080p; join both sides; score."""
    parts = []
    for c in range(3):
        step = 120 // fps[c]
        parts.append(f'[{c}:v]settb=1/120,setpts=N*{step},fps=120,scale=1920:1080:flags=bilinear,'
                     f'trim=end_frame={CHUNK_FRAMES},setpts=PTS-STARTPTS,format=yuv420p[t{c}]')
        parts.append(f'[{c + 3}:v]trim=end_frame={CHUNK_FRAMES},setpts=PTS-STARTPTS,format=yuv420p[r{c}]')
    parts.append('[t0][t1][t2]concat=n=3:v=1:a=0[test]')
    parts.append('[r0][r1][r2]concat=n=3:v=1:a=0[ref]')
    parts.append('[test][ref]libvmaf=model=version=vmaf_v0.6.1:feature=name=psnr:'
                 'log_fmt=json:log_path=vmaf.json:n_threads=8')
    return ';'.join(parts)


def score(ffmpeg, recipe):
    labels = [recipe[f'chunk{c + 1}'] for c in range(3)]
    refs = [local_path(p) for p in recipe['source_references']]
    tests = [refs[c] if labels[c] == '1080p120' else local_path(recipe['source_videos'][c]) for c in range(3)]
    fps = [int(re.fullmatch(r'(\d+)p(\d+)', label).group(2)) for label in labels]
    with tempfile.TemporaryDirectory() as temp_dir:
        cmd = [ffmpeg, '-hide_banner', '-v', 'error']
        for path in tests + refs:
            cmd += ['-i', str(path)]
        cmd += ['-lavfi', filter_graph(fps), '-f', 'null', '-']
        # log_path is relative so the Windows drive colon never reaches the filter parser.
        subprocess.run(cmd, cwd=temp_dir, check=True)
        frames = json.loads((Path(temp_dir) / 'vmaf.json').read_text())['frames']
    assert len(frames) == 3 * CHUNK_FRAMES, f"{recipe['candidate_id']}: {len(frames)} frames"
    return [{'frame': f['frameNum'], 'chunk': f['frameNum'] // CHUNK_FRAMES + 1,
             **{m: f['metrics'][m] for m in METRICS}} for f in frames]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ffmpeg', default='C:/ffmpeg-2023-12-18-git-be8a4f80b9-essentials_build/bin/ffmpeg.exe',
                        help='ffmpeg built with libvmaf')
    parser.add_argument('--recipes', type=Path, default=PILOT / 'pilot_recipes.json')
    parser.add_argument('--output', type=Path, default=PILOT / 'vmaf_psnr')
    args = parser.parse_args()

    recipes = json.loads(args.recipes.read_text())
    frame_dir = args.output / 'frames'
    frame_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for i, recipe in enumerate(recipes, 1):
        cid = recipe['candidate_id']
        frame_file = frame_dir / f'{cid}.csv'
        if frame_file.is_file():
            with open(frame_file, newline='') as f:
                rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
        else:
            rows = score(args.ffmpeg, recipe)
            with open(frame_file.with_suffix('.tmp'), 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['frame', 'chunk'] + METRICS)
                writer.writeheader()
                writer.writerows(rows)
            frame_file.with_suffix('.tmp').replace(frame_file)
        means = {m: sum(r[m] for r in rows) / len(rows) for m in METRICS}
        summary.append({'candidate_id': cid, 'scene': recipe['scene'],
                        **{f'chunk{c}': recipe[f'chunk{c}'] for c in (1, 2, 3)},
                        **{f'mean_{m}': round(v, 4) for m, v in means.items()}})
        print(f'[{i}/{len(recipes)}] {cid}: VMAF {means["vmaf"]:.2f}  PSNR-Y {means["psnr_y"]:.2f} dB', flush=True)

    with open(args.output / 'pilot_vmaf_psnr.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(f'Wrote {args.output / "pilot_vmaf_psnr.csv"} and {len(summary)} per-frame CSVs in {frame_dir}')


if __name__ == '__main__':
    main()
