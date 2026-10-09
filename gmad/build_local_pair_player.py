"""Build an offline A/B player and lossless H.264 copies of rendered pilot videos."""
import argparse
import csv
import html
import json
import subprocess
from pathlib import Path


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,duration',
        '-of', 'json', str(path)], text=True))['streams'][0]


def valid(path, source_info):
    if not path.is_file():
        return False
    try:
        info = probe(path)
        return info['codec_name'] == 'h264' and all(
            info[key] == source_info[key] for key in
            ('width', 'height', 'pix_fmt', 'avg_frame_rate', 'nb_frames', 'duration'))
    except (subprocess.CalledProcessError, KeyError, ValueError):
        return False


PLAYER = '''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Pilot A/B player</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#15181e;color:#edf0f5;font:16px system-ui,sans-serif}
main{max-width:1400px;margin:auto;padding:24px}h1{font-size:26px;margin:0 0 10px}
p{line-height:1.6;color:#b8c2d3}select,button{font:inherit;padding:9px 14px;border:1px solid #657083;border-radius:6px;background:#262e3b;color:#fff}
button{cursor:pointer}button:hover{background:#3c4b61}select{max-width:100%}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}
.settings{font-family:monospace;line-height:1.8;overflow-wrap:anywhere}
video{display:block;width:100%;max-width:1920px;aspect-ratio:16/9;background:#000;margin:auto}
.screen{background:#000}.screen:fullscreen{display:flex;align-items:center;justify-content:center}
.screen:fullscreen video{width:100%;height:100%;object-fit:contain}
.active{background:#3262a8}a{color:#9ac3ff}#status{min-height:25px}
</style>
<main><h1>__TITLE__ · Pilot video pairs</h1>
<p>__COUNT__ 对 · __VIDEOS__ 段视频 · 每段 4.5 秒（3 × 1.5 秒）· 1920 × 1080 / 120 fps。先选择一对，再播放 A 或 B；“A → B”按顺序播放。</p>
<div class="bar"><button id="previous">上一对</button><select id="pairs" aria-label="选择视频对"></select><button id="next">下一对</button></div>
<div id="details" class="settings"></div>
<div class="bar"><button id="a">播放 A</button><button id="b">播放 B</button><button id="both">A → B</button><button id="stop">停止</button><button id="fullscreen">全屏</button><label>格式 <select id="codec"><option value="h264">H.264 无损</option><option value="hevc">HEVC 无损</option></select></label></div>
<div class="screen" id="screen"><video id="video" controls playsinline preload="auto" muted></video></div>
<p id="status" role="status"></p><div class="bar"><a id="file-a">A 文件</a><a id="file-b">B 文件</a><a href="pair_video_paths.csv">配对文件路径 CSV</a></div>
<p>720p 内容用 bicubic 放大；30/60 fps 内容通过重复帧输出为 120 fps。H.264 与 HEVC 文件均采用无损编码。观察 120 fps 差异时，使用至少 120 Hz 的显示器并检查播放丢帧情况。这里保留 Pilot list 的 A/B 标签及顺序。</p>
</main><script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const video = $('video');
let index = 0, side = 'a', queued = null, generation = 0;
DATA.forEach((pair, i) => {
  const option = document.createElement('option');
  option.value = i; option.textContent = `${i + 1}. ${pair.pair_id} · ${pair.roles}`;
  $('pairs').append(option);
});
function file(which) { return DATA[index][`${which}_${$('codec').value}`]; }
function links() {
  for (const s of ['a', 'b']) { $('file-' + s).href = file(s); }
}
function label() {
  for (const s of ['a', 'b']) $(''+s).classList.toggle('active', s === side);
  const chunk = Math.min(3, Math.floor(video.currentTime / 1.5) + 1);
  return `${index + 1}/${DATA.length} · ${DATA[index].pair_id} · ${side.toUpperCase()} · chunk ${chunk}/3 · ${video.currentTime.toFixed(2)} / 4.50 s`;
}
function selectPair(i) {
  generation++; video.pause(); queued = null;
  index = (i + DATA.length) % DATA.length; side = 'a'; $('pairs').value = index;
  const p = DATA[index];
  $('details').textContent = `A: ${p.settings_a}\nB: ${p.settings_b}`;
  $('details').style.whiteSpace = 'pre-line';
  video.src = file('a'); links(); $('status').textContent = label();
}
async function play(which, sequence = false) {
  const request = ++generation; video.pause(); side = which; queued = sequence ? 'b' : null;
  video.src = file(which); $('status').textContent = label() + ' · 加载中';
  try { await video.play(); }
  catch (error) { if (request === generation && error.name !== 'AbortError') $('status').textContent = '无法播放：请切换格式，或通过下面的文件链接使用本地播放器打开。' + error.message; }
}
$('pairs').onchange = () => selectPair(Number($('pairs').value));
$('previous').onclick = () => selectPair(index - 1); $('next').onclick = () => selectPair(index + 1);
$('a').onclick = () => play('a'); $('b').onclick = () => play('b'); $('both').onclick = () => play('a', true);
$('stop').onclick = () => { generation++; queued = null; video.pause(); video.currentTime = 0; $('status').textContent = label(); };
$('codec').onchange = () => selectPair(index);
$('fullscreen').onclick = () => $('screen').requestFullscreen().catch(error => { $('status').textContent = error.message; });
video.ontimeupdate = () => { $('status').textContent = label(); };
video.onended = () => {
  if (queued) { const next = queued; queued = null; play(next); }
  else {
    const quality = video.getVideoPlaybackQuality ? video.getVideoPlaybackQuality() : null;
    $('status').textContent = label() + (quality ? ` · 播放丢帧 ${quality.droppedVideoFrames}/${quality.totalVideoFrames}` : ' · 播放结束');
  }
};
video.onerror = () => { queued = null; $('status').textContent = '当前格式无法解码。请切换格式，或点击文件链接用本地播放器打开。'; };
selectPair(0);
</script></html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--pair-list', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    with args.pair_list.open(encoding='utf-8-sig', newline='') as stream:
        pairs = list(csv.DictReader(stream))
    if not pairs:
        parser.error('Empty pair list')
    if args.threads < 1:
        parser.error('--threads must be positive')
    manifest = json.loads((args.directory / 'render_manifest.json').read_text())
    originals = {row['candidate_id']: Path(row['output']) for row in manifest['videos']}
    ids = sorted({row[key] for row in pairs for key in ('video_a', 'video_b')})
    missing = set(ids) - originals.keys()
    if missing:
        parser.error(f'Missing rendered videos: {sorted(missing)}')
    browser_dir = args.directory / 'h264_lossless'
    browser_dir.mkdir(exist_ok=True)
    for n, candidate in enumerate(ids, 1):
        source = originals[candidate]
        source_info = probe(source)
        target = browser_dir / source.name
        signature = dict(source=str(source.resolve()), size=source.stat().st_size,
                         mtime_ns=source.stat().st_mtime_ns, encoder='libx264', crf=0,
                         preset='veryfast', pixel_format='yuv420p')
        metadata = target.with_suffix('.render.json')
        if (metadata.is_file() and json.loads(metadata.read_text()).get('signature') == signature
                and valid(target, source_info)):
            print(f'[{n}/{len(ids)}] Reuse H.264 {candidate}', flush=True)
            continue
        temporary = target.with_suffix('.partial.mp4')
        print(f'[{n}/{len(ids)}] Lossless H.264 {candidate}', flush=True)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-threads', '2', '-i', str(source), '-map', '0:v:0', '-an',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '0',
                        '-threads', str(args.threads), '-pix_fmt', 'yuv420p',
                        '-fps_mode', 'passthrough', '-movflags', '+faststart', str(temporary)], check=True)
        if not valid(temporary, source_info):
            raise ValueError(f'Invalid browser copy: {temporary}')
        temporary.replace(target)
        metadata.write_text(json.dumps(dict(signature=signature, probe=probe(target)), indent=2) + '\n')
    data = []
    for row in pairs:
        record = {key: row[key] for key in ('pair_id', 'roles', 'settings_a', 'settings_b')}
        for side in ('a', 'b'):
            source = originals[row[f'video_{side}']]
            record[f'{side}_hevc'] = source.relative_to(args.directory.resolve()).as_posix()
            record[f'{side}_h264'] = 'h264_lossless/' + source.name
        data.append(record)
    title = ', '.join(sorted({row['scene'] for row in pairs}))
    page = PLAYER.replace('__TITLE__', html.escape(title)).replace('__COUNT__', str(len(pairs)))
    page = page.replace('__VIDEOS__', str(len(ids))).replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    target = args.directory / 'play_pairs.html'
    target.write_text(page, encoding='utf-8')
    print(f'Player: {target.resolve()}', flush=True)


if __name__ == '__main__':
    main()
