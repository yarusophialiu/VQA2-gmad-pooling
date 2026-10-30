"""Generate the test chunks listed in a recipe file from its lossless reference chunks.

Same encoding as VQA2-dataset/encode_steam_lossless_chunks.py: the ffmpeg fps filter
keeps every (120/fps)-th frame (CVVDP repeats each one back onto the 120 Hz axis),
then a bicubic scale to the target height, HEVC lossless (libx265 lossless=1, yuv420p).
1080p120 tests are symlinks to the reference. Only files the recipes list are made.

Example:
  python gmad/encode_pilot_test_chunks.py --recipes results/dsis_pilot/pilot_recipes.json \
      --dataset-root /anfs/gfxdisp/yl962/temporal-pooling-metric/dataset-reference-chunks
"""
import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from score_combined_cvvdp import local_path


def probe(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
         'stream=width,height,avg_frame_rate,nb_frames,pix_fmt', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True)
    return json.loads(result.stdout)['streams'][0]


def encode(ref, test, height, fps):
    if (height, fps) == (1080, 120):
        target = os.path.relpath(ref, test.parent)
        if not (test.is_symlink() and os.readlink(test) == target):
            test.parent.mkdir(parents=True, exist_ok=True)
            test.unlink(missing_ok=True)
            test.symlink_to(target)
        return 'symlink'
    frames = round(fps * 1.5)
    if test.is_file() and int(probe(test).get('nb_frames', 0)) == frames:
        return 'exists'
    test.parent.mkdir(parents=True, exist_ok=True)
    partial = test.with_name(test.stem + '.partial.mp4')
    filter_chain = f'fps={fps}' + (f',scale=-2:{height}:flags=bicubic' if height != 1080 else '')
    subprocess.run(
        ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(ref),
         '-vf', filter_chain, '-an', '-frames:v', str(frames),
         '-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', 'lossless=1:log-level=error',
         '-pix_fmt', 'yuv420p', str(partial)], check=True)
    info = probe(partial)
    if (int(info['nb_frames']), int(info['height']), info['avg_frame_rate']) != (frames, height, f'{fps}/1'):
        raise ValueError(f'Unexpected output {partial}: {info}')
    partial.rename(test)
    return 'encoded'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--recipes', type=Path, required=True)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    jobs = {}
    for recipe in json.loads(args.recipes.read_text()):
        for video, reference in zip(recipe['source_videos'], recipe['source_references']):
            height, fps = map(int, re.search(r'chunk\d_(\d+)p(\d+)_lossless_hevc\.mp4$', video).groups())
            test, ref = local_path(video, args.dataset_root), local_path(reference, args.dataset_root)
            assert ref.is_file(), f'Missing reference {ref}'
            assert jobs.setdefault(test, (ref, test, height, fps))[0] == ref, test
    print(f'{len(jobs)} test chunks')
    if args.dry_run:
        for ref, test, height, fps in jobs.values():
            print(f'{ref} -> {test}')
        return
    counts = {}
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(encode, *job): test for test, job in sorted(jobs.items())}
        for number, future in enumerate(as_completed(futures), 1):
            status = future.result()
            counts[status] = counts.get(status, 0) + 1
            print(f'[{number}/{len(jobs)}] {futures[future].relative_to(args.dataset_root)}: {status}', flush=True)
    print(counts)


if __name__ == '__main__':
    main()
