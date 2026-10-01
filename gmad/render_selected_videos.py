"""Render selected recipes on iridium, or locally after downloading source videos.

Example:
  python render_selected_videos.py --recipes pilot_video_recipes.json --output /path/to/pilot_videos

Use --dataset-root to relocate the lossless_spatiotemporal_chunks source directory.
This creates display-ready 1920x1080/120 fps lossless videos. Full-video CVVDP
validation remains a separate step; frame-score concatenation is only screening.
"""
import argparse
import json
import subprocess
from pathlib import Path


def probe(path):
    data=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height,avg_frame_rate,nb_frames','-of','json',str(path)],text=True)
    return json.loads(data)['streams'][0]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recipes',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dataset-root',type=Path)
    p.add_argument('--limit',type=int)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    recipes=json.loads(args.recipes.read_text())
    if args.limit is not None:recipes=recipes[:args.limit]
    for n,r in enumerate(recipes,1):
        sources=[]
        for source in r['source_videos']:
            path=Path(source)
            if args.dataset_root:
                path=args.dataset_root / source.split('/lossless_spatiotemporal_chunks/',1)[1]
            if not path.is_file():raise FileNotFoundError(path)
            sources.append(path)
        target=args.output/r['output_name']
        expected=dict(width=1920,height=1080,avg_frame_rate='120/1',nb_frames='540')
        if target.is_file() and probe(target)==expected:
            print(f'[{n}/{len(recipes)}] Reuse {target}',flush=True);continue
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y']
        for source in sources:cmd+=['-i',str(source)]
        filters=[f'[{i}:v]setpts=PTS-STARTPTS,scale=1920:1080:flags=bilinear,fps=120,'
                 f'trim=end_frame=180,setpts=N/(120*TB),setsar=1[v{i}]' for i in range(3)]
        filters+=['[v0][v1][v2]concat=n=3:v=1:a=0[out]']
        cmd+=['-filter_complex',';'.join(filters),'-map','[out]','-an','-r','120',
              '-c:v','libx265','-preset','ultrafast','-x265-params','lossless=1',
              '-pix_fmt','yuv420p',str(target)]
        print(f'[{n}/{len(recipes)}] {r["candidate_id"]}',flush=True)
        if args.dry_run:print(cmd);continue
        args.output.mkdir(parents=True,exist_ok=True)
        subprocess.run(cmd,check=True)
        actual=probe(target)
        if actual!=expected:raise ValueError(f'Unexpected output: {target}: {actual}')
    print('Complete. Recompute full-video CVVDP before locking final experimental stimuli.')


if __name__=='__main__':main()
