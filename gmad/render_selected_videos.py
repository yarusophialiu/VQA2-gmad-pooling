"""Render selected recipes on iridium, or locally after downloading source videos.

Example:
  python render_selected_videos.py --recipes pilot_video_recipes.json --output /path/to/pilot_videos

Use --dataset-root to relocate the lossless_spatiotemporal_chunks source directory.
This uses bicubic scaling and frame duplication to create 1920x1080/120 fps
lossless videos. Normalized chunks are cached, then concatenated without
re-encoding. Full-video CVVDP
validation remains a separate step; frame-score concatenation is only screening.
"""
import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path


def probe(path):
    data=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration',
        '-of','json',str(path)],text=True)
    return json.loads(data)['streams'][0]


def valid_output(path, frames):
    if not path.is_file():
        return False
    try:
        info=probe(path)
        return (info['codec_name']=='hevc' and info['pix_fmt']=='yuv420p'
                and info['width']==1920 and info['height']==1080
                and info['avg_frame_rate']=='120/1' and int(info['nb_frames'])==frames
                and abs(float(info['duration'])-frames/120)<1e-6)
    except (subprocess.CalledProcessError, KeyError, ValueError):
        return False


def reusable(path, signature, frames):
    metadata=path.with_suffix('.render.json')
    if not metadata.is_file():
        return False
    try:
        return json.loads(metadata.read_text())['signature']==signature and valid_output(path,frames)
    except (KeyError, ValueError):
        return False


def finish(temporary, target, signature, frames):
    if not valid_output(temporary,frames):
        raise ValueError(f'Unexpected video format: {temporary}: {probe(temporary)}')
    temporary.replace(target)
    target.with_suffix('.render.json').write_text(
        json.dumps(dict(signature=signature,probe=probe(target)),indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipes',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dataset-root',type=Path)
    p.add_argument('--pair-list',type=Path,help='Filter recipes to the videos named in a pair CSV')
    p.add_argument('--role',help='With --pair-list, keep only pairs having this role, e.g. gmad_pilot')
    p.add_argument('--threads',type=int,default=4,help='x265 worker threads for chunk normalization')
    p.add_argument('--limit',type=int)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if args.threads<1:p.error('--threads must be positive')
    if args.role and not args.pair_list:p.error('--role requires --pair-list')
    recipes=json.loads(args.recipes.read_text())
    pairs=[]
    if args.pair_list:
        with args.pair_list.open(encoding='utf-8-sig',newline='') as stream:
            pairs=list(csv.DictReader(stream))
        if args.role:pairs=[row for row in pairs if args.role in row.get('roles','').split(';')]
        ids={row[key] for row in pairs for key in ('video_a','video_b')}
        missing=ids-{row['candidate_id'] for row in recipes}
        if missing:raise ValueError(f'Missing recipes: {sorted(missing)}')
        recipes=[row for row in recipes if row['candidate_id'] in ids]
    if args.limit is not None:recipes=recipes[:args.limit]
    if not recipes:p.error('No videos selected')
    # Resolve every input before creating any output.
    resolved={}
    for recipe in recipes:
        sources=[]
        for source in recipe['source_videos']:
            path=Path(source)
            if args.dataset_root:
                path=args.dataset_root / source.split('/lossless_spatiotemporal_chunks/',1)[1]
            if not path.is_file():raise FileNotFoundError(path)
            sources.append(path.resolve())
        if len(sources)!=3:raise ValueError('Each video requires exactly three chunks')
        resolved[recipe['candidate_id']]=sources
    pipeline=dict(spatial_filter='bicubic',temporal_filter='reset native frame timestamps; '
                  'tpad one native frame; fps=120:start_time=0:round=near; trim 180 frames',
                  width=1920,height=1080,fps=120,chunk_frames=180,video_frames=540,
                  encoder='libx265',lossless=True,pixel_format='yuv420p',version=2)
    cache=args.output/'normalized_chunks'
    normalized={}
    signatures={}
    records=[]
    if not args.dry_run:cache.mkdir(parents=True,exist_ok=True)
    for n,r in enumerate(recipes,1):
        sources=resolved[r['candidate_id']]
        target=args.output/r['output_name']
        chunks=[]
        for source in sources:
            if source not in normalized:
                info=probe(source)
                fps=info['r_frame_rate']
                if (fps not in ('30/1','60/1','120/1') or info['height'] not in (720,1080)
                        or abs(float(info['duration'])-1.5)>1/int(fps.split('/')[0])+1e-6
                        or int(info['nb_frames'])!=int(fps.split('/')[0])*1.5):
                    raise ValueError(f'Unexpected source chunk: {source}: {info}')
                stat=source.stat()
                source_fps=int(fps.split('/')[0])
                signature=dict(pipeline=pipeline,source=str(source),size=stat.st_size,mtime_ns=stat.st_mtime_ns,
                               source_fps=source_fps)
                key=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:16]
                chunk=cache/f'{source.stem}_{key}.mp4'
                temporary=chunk.with_suffix('.partial.mp4')
                if not reusable(chunk,signature,180):
                    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','2','-i',str(source),
                         '-vf',f'setpts=N/({source_fps}*TB),tpad=stop_mode=clone:stop=1,'
                         'scale=1920:1080:flags=bicubic,'
                         'fps=120:start_time=0:round=near,trim=end_frame=180,setpts=N/(120*TB),setsar=1',
                         '-an','-fps_mode','passthrough','-c:v','libx265','-preset','ultrafast',
                         '-x265-params',f'lossless=1:pools={args.threads}:frame-threads=2:log-level=error',
                         '-pix_fmt','yuv420p','-tag:v','hvc1',str(temporary)]
                    print(f'Normalize {source}',flush=True)
                    if args.dry_run:print(cmd)
                    else:
                        subprocess.run(cmd,check=True)
                        finish(temporary,chunk,signature,180)
                normalized[source]=chunk
                signatures[source]=signature
            chunks.append(normalized[source])
        signature=dict(pipeline=pipeline,sources=[signatures[source] for source in sources])
        if reusable(target,signature,540):
            print(f'[{n}/{len(recipes)}] Reuse {target}',flush=True)
        else:
            listing=target.with_suffix('.concat.txt')
            temporary=target.with_suffix('.partial.mp4')
            cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),
                 '-map','0:v:0','-c:v','copy','-an','-tag:v','hvc1','-movflags','+faststart',str(temporary)]
            print(f'[{n}/{len(recipes)}] Assemble {r["candidate_id"]}',flush=True)
            if args.dry_run:print(cmd)
            else:
                listing.write_text(''.join("file '"+str(path.resolve()).replace("'","'\\''")+"'\n" for path in chunks))
                try:
                    subprocess.run(cmd,check=True)
                    finish(temporary,target,signature,540)
                finally:
                    listing.unlink(missing_ok=True)
        records.append(dict(candidate_id=r['candidate_id'],output=str(target.resolve()),
                            sources=[str(path) for path in sources],normalized_chunks=[str(path.resolve()) for path in chunks]))
    if not args.dry_run:
        manifest=dict(pipeline=pipeline,recipe_file=str(args.recipes.resolve()),
                      pair_list=str(args.pair_list.resolve()) if args.pair_list else None,
                      role=args.role,video_count=len(records),videos=records)
        (args.output/'render_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if pairs:
            by_id={r['candidate_id']:r['output'] for r in records}
            with (args.output/'pair_video_paths.csv').open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=['pair_id','scene','video_a','video_b','path_a','path_b','roles'])
                writer.writeheader()
                for row in pairs:
                    if row['video_a'] in by_id and row['video_b'] in by_id:
                        writer.writerow({key:row.get(key,'') for key in ('pair_id','scene','video_a','video_b','roles')} |
                                        dict(path_a=by_id[row['video_a']],path_b=by_id[row['video_b']]))
    print('Complete. Recompute full-video CVVDP before locking final experimental stimuli.')


if __name__=='__main__':main()
