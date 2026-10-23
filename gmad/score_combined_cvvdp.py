"""Score each gMAD-selected video as one 4.5 s clip (chunk1+chunk2+chunk3) with CVVDP.

Same pipeline as run_local_chunk_scores.py (video mode, standard_fhd, bilinear
full-screen resize to 1920x1080, frame repetition on a 120 Hz axis, replicate
temporal padding), but the three chunks are joined in memory, so temporal
filtering runs across chunk boundaries and one JOD covers the whole stimulus
seen in the DSIS experiment. 1080p120 test chunks use the reference file, as the
experiment does.

Writes <output>/combined_jod.csv (one row per video, appended as it goes, so a
rerun resumes) and <output>/frames/<candidate_id>.csv (540 video-mode per-frame
JOD proxies). Then maps JOD to the 1-5 DSIS scale, see dsis_category().

Example:
  python gmad/score_combined_cvvdp.py --cvvdp-root <ColorVideoVDP checkout>
"""
import argparse
import csv
import gc
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SELECTION = ROOT / 'results' / 'gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted' / 'selection_all_scenes'
CHUNK_FRAMES = 180   # 1.5 s at 120 Hz
FIELDS = ['candidate_id', 'scene', 'shot', 'chunk1', 'chunk2', 'chunk3', 'combined_jod',
          'mean_chunk_jod', 'frames', 'seconds']

# DSIS level for a CVVDP JOD: 1-JOD-wide bins anchored at the reference (JOD 10).
# Within 0.5 JOD of the reference is treated as imperceptible.
DSIS_BINS = [(9.5, 5, 'Excellent - Imperceptible'),
             (8.5, 4, 'Good - Perceptible, but not annoying'),
             (7.5, 3, 'Fair - Slightly annoying'),
             (6.5, 2, 'Poor - Annoying'),
             (float('-inf'), 1, 'Bad - Very annoying')]


def dsis_category(jod):
    for lower, level, label in DSIS_BINS:
        if jod >= lower:
            return level, label


def local_path(path):
    """Recipes store Windows paths; find the same file under this workspace's VQA2-dataset."""
    relative = re.search(r'[\\/]VQA2-dataset[\\/](.*)$', path).group(1).replace('\\', '/')
    local = WORKSPACE / 'VQA2-dataset' / relative
    assert local.is_file(), f'Missing {local}'
    return local


def make_combined_source(pycvvdp, tests, refs, display_photometry):
    """Join three 1.5 s chunk sources into one 540-frame source, opened one chunk at a time."""

    from pycvvdp.video_source import video_source

    class combined_source(video_source):
        def __init__(self):
            self.current, self.index = None, -1

        def _chunk(self, frame):
            index = frame // CHUNK_FRAMES
            if index != self.index:
                self.current = pycvvdp.video_source_temp_resample_file(
                    str(tests[index]), str(refs[index]), display_photometry=display_photometry,
                    full_screen_resize='bilinear', resize_resolution=[1920, 1080])
                assert self.current.get_frames_per_second() == 120, tests[index]
                assert tuple(self.current.get_video_size()) == (1080, 1920, CHUNK_FRAMES), tests[index]
                self.index = index
            return self.current, frame % CHUNK_FRAMES

        def get_video_size(self):
            return (1080, 1920, 3 * CHUNK_FRAMES)

        def get_frames_per_second(self):
            return 120

        def get_test_frame(self, frame, device, colorspace):
            source, local = self._chunk(frame)
            return source.get_test_frame(local, device=device, colorspace=colorspace)

        def get_reference_frame(self, frame, device, colorspace):
            source, local = self._chunk(frame)
            return source.get_reference_frame(local, device=device, colorspace=colorspace)

    return combined_source()


def earlier_chunk_means():
    """Mean of the three per-chunk JODs used for the gMAD selection, from pairs.csv."""
    means = {}
    with (SELECTION / 'pairs.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            means[row['video_a']] = float(row['mean_jod_a'])
            means[row['video_b']] = float(row['mean_jod_b'])
    return means


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--recipes', type=Path, default=SELECTION / 'video_recipes.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / 'cvvdp_combined_version_a')
    parser.add_argument('--cvvdp-root', type=Path, help='ColorVideoVDP checkout to import instead of the installed pycvvdp')
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--gpu-mem', type=float, default=4)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.cvvdp_root:
        sys.path.insert(0, str(args.cvvdp_root.resolve()))
    import pycvvdp
    import torch
    sys.path.insert(0, str(ROOT))
    from per_frame_quality import cvvdp_per_frame_jod

    # The earlier chunk scores capped temporal resampling at 120 Hz; with 30/60/120 fps
    # tests against a 120 fps reference the resampling rate is 120 Hz either way.
    pycvvdp.video_source_temp_resample_file.max_fps = 120
    torch.set_num_threads(4)
    metric = pycvvdp.cvvdp(display_name='standard_fhd', device=torch.device(args.device),
                           gpu_mem=args.gpu_mem, quiet=True)
    recipes = json.loads(args.recipes.read_text())[:args.limit]
    means = earlier_chunk_means()

    (args.output / 'frames').mkdir(parents=True, exist_ok=True)
    table = args.output / 'combined_jod.csv'
    done = set()
    if table.is_file():
        with table.open(newline='') as stream:
            done = {row['candidate_id'] for row in csv.DictReader(stream)}
    else:
        with table.open('w', newline='') as stream:
            csv.DictWriter(stream, FIELDS).writeheader()
    (args.output / 'scoring_config.json').write_text(json.dumps(dict(
        display='standard_fhd', full_screen_resize='bilinear', resize_resolution=[1920, 1080],
        temporal_resample_fps=120, temporal_padding=metric.temp_padding, metric_version=metric.version,
        cvvdp_root=str(Path(pycvvdp.__file__).parent), torch_version=torch.__version__,
        chunks_joined_in_memory=True, frames=3 * CHUNK_FRAMES, dsis_bins=DSIS_BINS[:-1]), indent=2) + '\n')

    for number, recipe in enumerate(recipes, 1):
        cid = recipe['candidate_id']
        if cid in done:
            continue
        labels = [recipe[f'chunk{c}'] for c in (1, 2, 3)]
        refs = [local_path(p) for p in recipe['source_references']]
        tests = [ref if label == '1080p120' else local_path(p)
                 for label, p, ref in zip(labels, recipe['source_videos'], refs)]
        start = time.time()
        with torch.no_grad():
            source = make_combined_source(pycvvdp, tests, refs, metric.display_photometry)
            quality, stats = metric.predict_video_source(source)
            jod = float(quality)
            assert stats['N_frames'] == 3 * CHUNK_FRAMES and stats['frames_per_second'] == 120
            frames = cvvdp_per_frame_jod(metric, stats, jod)
        with (args.output / 'frames' / f'{cid}.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['frame', 'chunk', 'time_s', 'jod_proxy'])
            for f, value in enumerate(frames):
                writer.writerow([f + 1, f // CHUNK_FRAMES + 1, f'{f / 120:.6f}', f'{value:.6f}'])
        row = dict(candidate_id=cid, scene=recipe['scene'].split('__')[0], shot=recipe['scene'],
                   chunk1=labels[0], chunk2=labels[1], chunk3=labels[2], combined_jod=f'{jod:.6f}',
                   mean_chunk_jod=f'{means[cid]:.4f}' if cid in means else '', frames=len(frames),
                   seconds=f'{time.time() - start:.1f}')
        with table.open('a', newline='') as stream:
            csv.DictWriter(stream, FIELDS).writerow(row)
        print(f'[{number}/{len(recipes)}] {cid}: JOD {jod:.4f} ({row["seconds"]} s)', flush=True)
        del source, quality, stats
        gc.collect()
        torch.cuda.empty_cache()

    write_categories(table, args.output / 'combined_jod_dsis.csv')


def write_categories(table, destination):
    with table.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    counts = {}
    for row in rows:
        level, label = dsis_category(float(row['combined_jod']))
        row['dsis_level'], row['dsis_label'] = level, label
        counts[level] = counts.get(level, 0) + 1
    rows.sort(key=lambda r: (r['scene'], r['shot'], -float(r['combined_jod'])))
    with destination.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, FIELDS + ['dsis_level', 'dsis_label'])
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} videos -> {destination}')
    for lower, level, label in DSIS_BINS:
        print(f'  {level} {label:38s} JOD >= {lower:5.1f}: {counts.get(level, 0)}')


if __name__ == '__main__':
    main()
