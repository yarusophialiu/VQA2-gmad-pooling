"""Score local lossless chunks for gMAD, keeping a separate, signed manifest.

Uses CVVDP video mode, standard_fhd, bilinear full-screen resizing and frame
repetition on a common 120 Hz axis. Does not enable motion/SPEM extensions.
"""
import argparse
import csv
import gc
import hashlib
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration',
        '-of', 'json', str(path)], text=True))['streams'][0]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--cvvdp-root', type=Path, help='Use this local CVVDP checkout rather than the default import')
    parser.add_argument('--scene', default='bistro')
    parser.add_argument('--shot', default='bistro_path2_seg3_1')
    parser.add_argument('--heights', type=int, nargs='+', default=[360, 480])
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--gpu-mem', type=float, default=4)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--reuse-root', type=Path, help='Reuse compatible signed scores from a previous run')
    args = parser.parse_args()
    if args.cvvdp_root:
        sys.path.insert(0, str(args.cvvdp_root.resolve()))
    import pycvvdp
    import torch
    from extract_gmad_frame_scores import extract
    from per_frame_quality import cvvdp_per_frame_jod
    torch.set_num_threads(4)
    metric = pycvvdp.cvvdp(display_name='standard_fhd', device=torch.device(args.device), gpu_mem=args.gpu_mem, quiet=True)
    source_dir = args.source_root / args.scene / args.shot
    shot = f'{args.scene}/{args.shot}'
    out_dir = args.output_root / shot
    jobs = []
    for chunk in (1, 2, 3):
        ref = source_dir / 'references' / f'ref_chunk{chunk}_lossless_hevc.mp4'
        info = probe(ref)
        assert int(info['nb_frames']) == 180 and Fraction(info['r_frame_rate']) == 120, (ref, info)
        for height in args.heights:
            for fps in (30, 60, 120):
                test = source_dir / 'videos' / f'chunk{chunk}_{height}p{fps}_lossless_hevc.mp4'
                test_info = probe(test)
                assert test_info['height'] == height and Fraction(test_info['r_frame_rate']) == fps
                assert int(test_info['nb_frames']) == fps * 1.5 and abs(float(test_info['duration']) - 1.5) <= 1 / fps + 1e-6
                jobs.append((chunk, height, fps, test.resolve(), ref.resolve()))
    if args.limit is not None:
        jobs = jobs[:args.limit]
    for folder in ('features', 'native', 'frames', 'references'):
        (out_dir / folder).mkdir(parents=True, exist_ok=True)
    implementation = Path(pycvvdp.__file__).parent
    pipeline = dict(display='standard_fhd', full_screen_resize='bilinear', temporal_resample_fps=120,
                    temporal_padding='replicate', metric_version=metric.version,
                    cvvdp_root=str(implementation), metric_sha256=digest(implementation / 'cvvdp_metric.py'),
                    parameters_sha256=digest(metric.parameters_file),
                    display_models_sha256=digest(implementation / 'vvdp_data/display_models.json'),
                    video_source_sha256=digest(implementation / 'video_source_file.py'),
                    exporter_sha256=digest(Path(__file__).with_name('per_frame_quality.py')),
                    gpu_mem=args.gpu_mem, device=args.device, torch_version=torch.__version__)
    write_json(args.output_root / 'scoring_config.json', pipeline)
    records, normalized = [], {}
    for number, (chunk, height, fps, test, original_ref) in enumerate(jobs, 1):
        if original_ref not in normalized:
            ref = original_ref
            info = probe(ref)
            if Fraction(info['avg_frame_rate']) != 120 or abs(float(info['duration']) - 1.5) > 1e-6:
                # chunk1 has all 180 frames but lacks the final packet duration.
                # Preserve its pixels; normalize only timestamps in a separate copy.
                ref = out_dir / 'references' / original_ref.name
                source_metadata = ref.with_suffix('.source.json')
                signature = dict(source=str(original_ref), sha256=digest(original_ref), fps=120, frames=180)
                if args.reuse_root:
                    previous_ref = args.reuse_root / shot / 'references' / original_ref.name
                    previous_metadata = previous_ref.with_suffix('.source.json')
                    if previous_ref.is_file() and previous_metadata.is_file() and json.loads(previous_metadata.read_text()) == signature:
                        ref = previous_ref
                        source_metadata = previous_metadata
                if not (ref.is_file() and source_metadata.is_file()
                        and json.loads(source_metadata.read_text()) == signature):
                    print(f'Normalize reference timestamps: {original_ref.name}', flush=True)
                    temporary = ref.with_suffix('.partial.mp4')
                    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                                    '-threads', '2', '-i', str(original_ref), '-vf', 'setpts=N/(120*TB)',
                                    '-fps_mode', 'passthrough', '-an', '-c:v', 'libx265', '-preset', 'ultrafast',
                                    '-x265-params', 'lossless=1:pools=6:frame-threads=2:log-level=error',
                                    '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', str(temporary)], check=True)
                    temporary.replace(ref)
                    write_json(source_metadata, signature)
                normalized_info = probe(ref)
                assert Fraction(normalized_info['avg_frame_rate']) == 120 and int(normalized_info['nb_frames']) == 180
                assert abs(float(normalized_info['duration']) - 1.5) < 1e-6
            normalized[original_ref] = ref.resolve()
        ref = normalized[original_ref]
        stem = test.stem
        features = out_dir / 'features' / f'{stem}_fmap.json'
        native = out_dir / 'native' / f'{stem}_native.csv'
        frames = out_dir / 'frames' / f'{stem}_frames.csv'
        cache_metadata = features.with_suffix('.scoring.json')
        signature = dict(pipeline=pipeline, test_sha256=digest(test), reference_sha256=digest(ref))
        if args.reuse_root and not cache_metadata.is_file():
            previous_dir = args.reuse_root / shot
            previous_features = previous_dir / 'features' / features.name
            previous_cache = previous_features.with_suffix('.scoring.json')
            copies = [(previous_features, features), (previous_cache, cache_metadata),
                      (previous_dir / 'native' / native.name, native),
                      (previous_dir / 'frames' / frames.name, frames),
                      (previous_dir / 'frames' / frames.with_suffix('.metadata.json').name, frames.with_suffix('.metadata.json'))]
            if (all(source.is_file() for source, _ in copies)
                    and json.loads(previous_cache.read_text()) == signature):
                for source, destination in copies:
                    shutil.copyfile(source, destination)
        reusable = (cache_metadata.is_file() and features.is_file() and native.is_file() and frames.is_file()
                    and frames.with_suffix('.metadata.json').is_file()
                    and json.loads(cache_metadata.read_text()) == signature)
        print(f'[{number}/{len(jobs)}] {"Reuse" if reusable else "CVVDP"} {test.name}', flush=True)
        if reusable:
            with native.open(newline='') as stream:
                jod = float(next(csv.DictReader(stream))['cvvdp'])
            metadata = json.loads(frames.with_suffix('.metadata.json').read_text())
        else:
            scoring_test = test
            test_info = probe(test)
            if Fraction(test_info['avg_frame_rate']) != fps or abs(float(test_info['duration']) - 1.5) > 1e-6:
                if fps == 120 and digest(test) == digest(original_ref):
                    scoring_test = ref
                else:
                    normalized_dir = out_dir / 'normalized_inputs'
                    normalized_dir.mkdir(exist_ok=True)
                    scoring_test = normalized_dir / test.name
                    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                                    '-threads', '2', '-i', str(test), '-vf', f'setpts=N/({fps}*TB)',
                                    '-fps_mode', 'passthrough', '-an', '-c:v', 'libx265', '-preset', 'medium',
                                    '-x265-params', 'lossless=1:pools=6:frame-threads=2:log-level=error',
                                    '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', str(scoring_test)], check=True)
            with torch.no_grad():
                video = pycvvdp.video_source_temp_resample_file(
                    str(scoring_test), str(ref), display_photometry=metric.display_photometry,
                    full_screen_resize='bilinear', resize_resolution=[1920, 1080], max_fps=120)
                assert video.get_frames_per_second() == 120 and video.get_video_size()[2] == 180
                quality, stats = metric.predict_video_source(video)
                jod = float(quality)
                assert stats['N_frames'] == 180 and stats['frames_per_second'] == 120
                metric.write_features_to_json(stats, str(features))
                with native.open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=['test', 'reference', 'cvvdp'])
                    writer.writeheader()
                    writer.writerow(dict(test=str(test), reference=str(ref), cvvdp=jod))
                metadata = extract(features, frames, jod, metric, cvvdp_per_frame_jod, duration_s=1.5)
                assert metadata['exported_frames'] == 180 and metadata['usable_for_design']
                write_json(cache_metadata, signature)
                del video, quality, stats
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        record = dict(scene=args.scene, shot=shot, chunk=chunk, height=height, fps=fps,
                      test=test.as_posix(), reference=ref.as_posix(), original_reference=original_ref.as_posix(),
                      native_jod=jod, frames_csv=frames.resolve().as_posix(),
                      source_frames=metadata['source_frames'], usable_for_design=metadata['usable_for_design'])
        records.append(record)
        write_json(args.output_root / 'manifest.json', records)
        print(f'  JOD={jod:.6f}; 180 video-mode frame proxies saved.', flush=True)
    print(f'Complete: {len(records)} scored chunks. Manifest: {args.output_root / "manifest.json"}', flush=True)


if __name__ == '__main__':
    main()
