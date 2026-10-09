"""Encode three reference chunks as 360p/480p HEVC lossless at 30/60/120 fps.

Uses exact sizes 640x360 and 854x480 with bicubic spatial downsampling and
FFmpeg fps temporal sampling. Source chunk durations are preserved to the
nearest whole frame at each target frame rate. One terminal frame is cloned
before sampling, then trimmed to the expected frame count, to retain the last
source frame even when its original packet duration is missing.
"""
import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_frames,duration,sample_aspect_ratio',
        '-of', 'json', str(path)], text=True))['streams'][0]


def validate(path, width, height, fps, frames):
    info = probe(path)
    if not (info['codec_name'] == 'hevc' and info['pix_fmt'] == 'yuv420p'
            and (info['width'], info['height']) == (width, height)
            and Fraction(info['avg_frame_rate']) == fps
            and int(info['nb_frames']) == frames
            and abs(float(info['duration']) - frames / fps) < 1e-6
            and info['sample_aspect_ratio'] == '1:1'):
        raise ValueError(f'Unexpected output format: {path}: {info}')
    # Decode every output frame to catch damaged or incomplete bitstreams.
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror',
                    '-threads', '2', '-i', str(path), '-map', '0:v:0',
                    '-an', '-f', 'null', '-'], check=True)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True,
                        help='Directory containing ref_chunk1/2/3.mp4 or ref_chunkN_lossless_hevc.mp4')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=6)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--replace', action='store_true', help='Replace the 18 named 360p/480p outputs')
    parser.add_argument('--expected-source-frames', type=int,
                        help='Require this frame count in each source (180 for 1.5 s gMAD chunks)')
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('--threads must be positive')
    sources = []
    for chunk in (1, 2, 3):
        source = next((args.source_dir / name for name in
                       (f'ref_chunk{chunk}.mp4', f'ref_chunk{chunk}_lossless_hevc.mp4')
                       if (args.source_dir / name).is_file()), None)
        if source is None:
            parser.error(f'Missing reference chunk {chunk}: {args.source_dir}')
        info = probe(source)
        if info['pix_fmt'] != 'yuv420p' or Fraction(info['r_frame_rate']) != 120:
            parser.error(f'Expected 120 fps yuv420p reference: {source}: {info}')
        if args.expected_source_frames is not None and int(info['nb_frames']) != args.expected_source_frames:
            parser.error(f'Expected {args.expected_source_frames} source frames: {source}: {info}')
        sources.append((chunk, source.resolve(), info))
    jobs = [(chunk, source, info, width, height, fps)
            for chunk, source, info in sources
            for width, height in ((640, 360), (854, 480))
            for fps in (30, 60, 120)]
    # Never overwrite unrelated files already present in the target folder.
    for chunk, _, _, _, height, fps in jobs:
        target = args.output / f'chunk{chunk}_{height}p{fps}_lossless_hevc.mp4'
        if target.exists() and not args.replace:
            parser.error(f'Output already exists; refusing to overwrite: {target}')
    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for number, (chunk, source, source_info, width, height, fps) in enumerate(jobs, 1):
        target = args.output / f'chunk{chunk}_{height}p{fps}_lossless_hevc.mp4'
        temporary = target.with_suffix('.partial.mp4')
        frame_fraction = Fraction(int(source_info['nb_frames']) * fps) / Fraction(source_info['r_frame_rate'])
        expected_frames = (2 * frame_fraction.numerator + frame_fraction.denominator) // (2 * frame_fraction.denominator)
        filters = (f"setpts=N/({source_info['r_frame_rate']}*TB),"
                   'tpad=stop_mode=clone:stop=1,'
                   f'fps={fps}:start_time=0:round=near,'
                   f'trim=end_frame={expected_frames},setpts=N/({fps}*TB),'
                   f'scale={width}:{height}:flags=bicubic,setsar=1')
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n',
                   '-threads', '2', '-i', str(source), '-map', '0:v:0', '-an',
                   '-vf', filters, '-fps_mode', 'passthrough',
                   '-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params',
                   f'lossless=1:pools={args.threads}:frame-threads=2:log-level=error',
                   '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', '-movflags', '+faststart', str(temporary)]
        print(f'[{number}/{len(jobs)}] {target.name}: {width}x{height}, {fps} fps, '
              f'{expected_frames} frames, {expected_frames / fps:.6f} s', flush=True)
        if args.dry_run:
            continue
        subprocess.run(command, check=True)
        output_info = validate(temporary, width, height, fps, expected_frames)
        temporary.replace(target)
        records.append(dict(chunk=chunk, source=str(source), source_probe=source_info,
                            output=str(target.resolve()), probe=output_info,
                            spatial_filter='bicubic', temporal_filter=filters,
                            lossless=True, encoder='libx265', command=command))
        manifest = dict(source_directory=str(args.source_dir.resolve()),
                        requested_resolutions=[[640, 360], [854, 480]], fps=[30, 60, 120],
                        completed_videos=len(records), videos=records)
        (args.output / 'low_resolution_encode_manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if not args.dry_run:
        print(f'Complete: {len(records)} verified HEVC lossless videos.', flush=True)


if __name__ == '__main__':
    main()
