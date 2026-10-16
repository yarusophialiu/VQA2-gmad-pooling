"""Encode local lossless resolution/FPS variants of dataset-reference-chunks.

Local counterpart of the encoding half of run_iridium_lossless_chunks.py.
Source: <root>/<scene>/<shot>/lossless_hevc/ref_chunkN.mp4 (1920x1080, 120 fps,
180 frames), or references/ref_chunkN_lossless_hevc.mp4 for shots copied from
iridium without lossless_hevc. Writes, next to it, the layout run_local_chunk_scores.py reads:
  <shot>/references/ref_chunkN_lossless_hevc.mp4      (hard link to the source)
  <shot>/videos/chunkN_<H>p<FPS>_lossless_hevc.mp4    (HEVC lossless)
1080p120 is the reference itself (hard link). All other variants change only
spatial (bicubic) and/or temporal (frame dropping) sampling.
"""
import argparse
import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent.parent / 'VQA2-dataset' / 'dataset-reference-chunks'
WIDTHS = {480: 854, 720: 1280, 1080: 1920}
DEFAULT_SCENES = ('forza', 'lego', 'ratchet', 'spiderman')
MIN_FREE_GB = 2.0


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=width,height,avg_frame_rate,nb_frames,duration', '-of', 'json', str(path)], text=True))['streams'][0]


def valid(path, width, height, fps):
    if not path.is_file():
        return False
    info = probe(path)
    return ((int(info['width']), int(info['height'])) == (width, height)
            and Fraction(info['avg_frame_rate']) == fps and int(info.get('nb_frames', 0)) == round(fps * 1.5)
            and abs(float(info['duration']) - 1.5) <= 1 / fps + 1e-6)


def link(source, destination):
    if destination.is_file() and os.path.samefile(source, destination):
        return
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=SOURCE_ROOT)
    parser.add_argument('--scenes', nargs='+', default=DEFAULT_SCENES)
    parser.add_argument('--heights', type=int, nargs='+', default=[480, 720, 1080])
    parser.add_argument('--fps', type=int, nargs='+', default=[30, 60, 120])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    shots = [shot for scene in args.scenes for shot in sorted((args.root / scene).iterdir())
             if (shot / 'lossless_hevc').is_dir() or (shot / 'references').is_dir()]
    assert shots, f'No shots for {args.scenes} under {args.root}'
    for shot in shots:
        for chunk in (1, 2, 3):
            ref = shot / 'references' / f'ref_chunk{chunk}_lossless_hevc.mp4'
            source = shot / 'lossless_hevc' / f'ref_chunk{chunk}.mp4'
            if not source.is_file():
                source = ref
            assert valid(source, 1920, 1080, 120), f'Unexpected source format: {source}'
            if not args.dry_run and source != ref:
                ref.parent.mkdir(exist_ok=True)
                link(source, ref)
            for height in args.heights:
                for fps in args.fps:
                    test = shot / 'videos' / f'chunk{chunk}_{height}p{fps}_lossless_hevc.mp4'
                    name = f'{shot.parent.name}/{shot.name} {test.name}'
                    if args.dry_run:
                        print(f'{test} <- {source}')
                        continue
                    test.parent.mkdir(exist_ok=True)
                    if (height, fps) == (1080, 120):
                        link(source, test)
                        continue
                    if valid(test, WIDTHS[height], height, fps):
                        print(f'Exists {name}', flush=True)
                        continue
                    free_gb = shutil.disk_usage(shot).free / 1e9
                    if free_gb < MIN_FREE_GB:
                        raise SystemExit(f'Stopped: only {free_gb:.1f} GB free before {name}')
                    filter_chain = f'fps={fps}' + (f',scale={WIDTHS[height]}:{height}:flags=bicubic' if height != 1080 else '')
                    temporary = test.with_suffix('.partial.mp4')
                    subprocess.run(
                        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                         '-vf', filter_chain, '-an', '-frames:v', str(round(fps * 1.5)),
                         '-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', 'lossless=1:log-level=error',
                         '-pix_fmt', 'yuv420p', str(temporary)], check=True)
                    temporary.replace(test)
                    assert valid(test, WIDTHS[height], height, fps), f'Bad encode: {test}'
                    print(f'Encoded {name} ({test.stat().st_size / 1e6:.0f} MB)', flush=True)
    print(f'Complete: {len(shots)} shots under {args.root}', flush=True)


if __name__ == '__main__':
    main()
