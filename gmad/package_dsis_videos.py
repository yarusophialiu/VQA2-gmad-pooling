"""Copy only the video chunks a DSIS recipe list plays, for running the experiment on another machine.

Files keep their path relative to VQA2-dataset. Two forms:
  folder (default): <output>/VQA2-dataset/...; copy that folder next to
      VQA2-gmad-pooling on the other machine (merging with any existing one).
  --zip-per-scene: <output>/<scene>.zip, each holding VQA2-dataset/... for one
      scene; extract every zip into the folder that contains VQA2-gmad-pooling.
run_dsis_gmad_480p1080p.m finds the files there even though the recipes hold
this machine's absolute paths.

    python package_dsis_videos.py --output E:/dsis_package
    python package_dsis_videos.py --output E:/dsis_package --zip-per-scene
    python package_dsis_videos.py --dry-run
Rerunning skips files (or complete zips) already written.
"""
import argparse
import csv
import json
import re
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
VERSION_A = (WORKSPACE / 'VQA2-gmad-pooling' / 'results' / 'gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted'
             / 'selection_all_scenes' / 'video_recipes.json')


def relative(path):
    match = re.search(r'[\\/]VQA2-dataset[\\/](.*)$', path)
    assert match, f'Not under VQA2-dataset: {path}'
    return Path(match.group(1))


def played_files(recipes):
    """Chunks the player opens, with their scene: each reference chunk, and test chunks except 1080p120 (shown from the reference)."""
    files = {}
    for r in recipes:
        scene = r['scene'].split('__')[0]
        for c in range(3):
            files[r['source_references'][c]] = scene
            if r[f'chunk{c + 1}'] != '1080p120':
                files[r['source_videos'][c]] = scene
    return files


def write_list(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'bytes'])
        writer.writeheader()
        writer.writerows(rows)


def copy_folder(output, sources):
    root = output / 'VQA2-dataset'
    root.mkdir(parents=True, exist_ok=True)
    pending = [(s, r) for s, r, _ in sources
               if not ((root / r).is_file() and (root / r).stat().st_size == s.stat().st_size)]
    need = sum(s.stat().st_size for s, _ in pending)
    free = shutil.disk_usage(root).free
    assert free > need, f'Need {need / 1e9:.2f} GB on {root}, only {free / 1e9:.2f} GB free'
    for number, (source, rel) in enumerate(pending, 1):
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.partial')
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
        print(f'[{number}/{len(pending)}] {rel.as_posix()}', flush=True)
    rows = []
    for source, rel, _ in sources:
        size = (root / rel).stat().st_size
        assert size == source.stat().st_size, f'Size mismatch after copy: {rel}'
        rows.append(dict(path=rel.as_posix(), bytes=size))
    write_list(output / 'dsis_package_files.csv', rows)
    print(f'Done: {len(rows)} files under {root}; {len(sources) - len(pending)} were already there.')


def zip_scenes(output, sources):
    """One stored (uncompressed) zip per scene; lossless HEVC does not compress further."""
    output.mkdir(parents=True, exist_ok=True)
    by_scene = defaultdict(list)
    for source, rel, scene in sources:
        by_scene[scene].append((source, 'VQA2-dataset/' + rel.as_posix()))
    for number, (scene, items) in enumerate(sorted(by_scene.items()), 1):
        archive = output / f'{scene}.zip'
        expected = {name: source.stat().st_size for source, name in items}
        if archive.is_file():
            with zipfile.ZipFile(archive) as existing:
                if {i.filename: i.file_size for i in existing.infolist()} == expected:
                    print(f'[{number}/{len(by_scene)}] {archive.name}: already complete', flush=True)
                    continue
        need = sum(expected.values())
        free = shutil.disk_usage(output).free
        assert free > need, f'Need {need / 1e9:.2f} GB on {output}, only {free / 1e9:.2f} GB free'
        temporary = archive.with_name(archive.name + '.partial')
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
            for source, name in sorted(items, key=lambda item: item[1]):
                bundle.write(source, name)
        with zipfile.ZipFile(temporary) as bundle:
            bad = bundle.testzip()
            assert bad is None, f'CRC check failed for {bad} in {temporary}'
            assert {i.filename: i.file_size for i in bundle.infolist()} == expected, f'Incomplete {temporary}'
        temporary.replace(archive)
        write_list(output / f'{scene}_files.csv', [dict(path=n, bytes=b) for n, b in sorted(expected.items())])
        print(f'[{number}/{len(by_scene)}] {archive.name}: {len(items)} files, {need / 1e9:.2f} GB, CRC checked', flush=True)
    print(f'Done: {len(by_scene)} scene zips in {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--recipes', type=Path, nargs='+', default=[VERSION_A], help='Default: Version A recipes')
    parser.add_argument('--output', type=Path, help='Package folder, e.g. on an external drive')
    parser.add_argument('--zip-per-scene', action='store_true', help='Write one zip per scene instead of a folder')
    parser.add_argument('--dry-run', action='store_true', help='List the size per scene only')
    args = parser.parse_args()
    if not args.dry_run and args.output is None:
        parser.error('--output is required unless --dry-run')
    files = {}
    for path in args.recipes:
        files.update(played_files(json.loads(path.read_text())))
    sources = []
    for f, scene in sorted(files.items()):
        source = Path(f)
        if not source.is_file():
            source = WORKSPACE / 'VQA2-dataset' / relative(f)
        assert source.is_file(), f'Missing on this machine: {f}'
        sources.append((source, relative(f), scene))
    total = sum(s.stat().st_size for s, _, _ in sources)
    print(f'{len(sources)} files, {total / 1e9:.2f} GB from {len(args.recipes)} recipe list(s)')
    if args.dry_run:
        sizes = defaultdict(lambda: [0, 0])
        for source, _, scene in sources:
            sizes[scene][0] += 1
            sizes[scene][1] += source.stat().st_size
        for scene, (count, size) in sorted(sizes.items()):
            print(f'  {scene:10s} {count:3d} files {size / 1e9:6.2f} GB')
        return
    if args.zip_per_scene:
        zip_scenes(args.output, sources)
    else:
        copy_folder(args.output, sources)


if __name__ == '__main__':
    main()
