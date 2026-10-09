"""Build a result report with CVVDP chunk scores and the new gMAD pilot list."""
import argparse
import csv
import html
import json
import shutil
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def table(headers, rows):
    esc = lambda value: html.escape(str(value))
    return '<table><thead><tr>' + ''.join(f'<th>{esc(x)}</th>' for x in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{esc(x)}</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory
    summary = json.loads((root / 'summary.json').read_text(encoding='utf-8'))
    config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    score_root = Path(config['input_root'])
    scoring = json.loads((score_root / 'scoring_config.json').read_text(encoding='utf-8'))
    chunks = json.loads((score_root / 'manifest.json').read_text(encoding='utf-8'))
    pilot = read_csv(root / 'pilot_pairs.csv')
    settings = sorted({(row['height'], row['fps']) for row in chunks})
    heights = sorted({height for height, _ in settings})
    frame_rates = sorted({fps for _, fps in settings})
    assert len(chunks) == len(settings) * 3 and summary['candidates'] == len(settings) ** 3
    assert summary['scenes'] == ['bistro']
    assert len(pilot) == summary['pilot_unique_pairs']
    quality = {(row['height'], row['fps'], row['chunk']): row['native_jod'] for row in chunks}
    widths = {360: 640, 480: 854, 720: 1280, 1080: 1920}
    quality_rows = [[f'{widths[h]} x {h}', fps] +
                    [f'{quality[h, fps, c]:.4f}' for c in (1, 2, 3)]
                    for h, fps in settings]
    resolution_title = ' / '.join(f'{height}p' for height in heights)
    resolution_sizes = ' / '.join(f'{widths[height]} x {height}' for height in heights)
    fps_title = ' / '.join(str(fps) for fps in frame_rates)
    exported = [dict(scene=row['scene'], chunk=row['chunk'], height=row['height'], fps=row['fps'],
                     native_jod=row['native_jod'], frame_proxies=row['source_frames'],
                     test=row['test'], reference=row['reference'], frames_csv=row['frames_csv']) for row in chunks]
    with (root / 'cvvdp_chunk_scores.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(exported[0]))
        writer.writeheader()
        writer.writerows(exported)
    shutil.copyfile(score_root / 'scoring_config.json', root / 'cvvdp_scoring_config.json')
    pilot_rows = [[row['pair_id'], row['settings_a'], row['settings_b'], row['roles'], row['gmad_task_count']]
                  for row in pilot]
    equivalent = defaultdict(list)
    for name, representative in config['representative'].items():
        equivalent[representative].append(name)
    equivalent_rows = [[' = '.join(names)] for names in equivalent.values() if len(names) > 1]
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bistro {resolution_title} - CVVDP and gMAD results</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;background:#f4f7fa;color:#193342;margin:0}}
main{{max-width:1200px;margin:auto;padding:28px}}section{{background:white;border:1px solid #d6e0e5;border-radius:10px;padding:22px;margin:20px 0}}
h1{{line-height:1.3}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #d6e0e5}}th{{background:#eaf3f5}}a{{color:#08777b}}
.scroll{{overflow:auto}}input{{font:inherit;padding:9px;max-width:100%;width:400px}}.stats{{font-size:20px}}code{{overflow-wrap:anywhere}}</style>
<main><h1>Bistro {resolution_title}: CVVDP and gMAD</h1>
<p>{len(chunks)} lossless HEVC chunks: {resolution_sizes}, at {fps_title} fps.
Every chunk lasts 1.5 seconds; three chunks form one 4.5-second candidate.
Each chunk has {len(settings)} settings; this run includes all combinations of the listed resolutions and frame rates.</p>
<section><h2>Result counts</h2><p class="stats">{summary['candidates']} candidates ·
{summary['attack_tasks']} attack tasks · {summary['gmad_unique_pairs']} distinct gMAD pairs ·
{summary['pilot_unique_pairs']} pilot pairs · {summary['pilot_unique_videos']} pilot videos</p>
{table(['Task status', 'Count'], sorted(summary['task_status'].items()))}</section>
<section><h2>CVVDP chunk scores</h2>
<p>CVVDP model {html.escape(str(scoring['metric_version']))}, <code>standard_fhd</code>, bilinear full-screen resize to 1920 x 1080,
common 120 Hz axis with repeated frames. Video-mode processing retains temporal filtering.
Each chunk exports 180 frame proxies; their underlying response reproduces the native CVVDP JOD after temporal pooling.</p>
{table(['Source resolution', 'Source fps', 'Chunk 1 JOD', 'Chunk 2 JOD', 'Chunk 3 JOD'], quality_rows)}
<p><a href="cvvdp_chunk_scores.csv">CVVDP scores and file paths</a> · <a href="cvvdp_scoring_config.json">CVVDP version, settings and hashes</a></p></section>
<section><h2>gMAD settings</h2><p>{summary['rules']} pooling rules; {summary['effective_rules']} distinct predictions.
K={config['bins']}; defender gap cap = min({config['epsilon_cap']}, {config['epsilon_fraction']*100:g}% of defender p95-p5).
Minimum attacker gap = {config['min_attack_fraction']*100:g}% of attacker p95-p5.
Negative frame proxies are skipped; the input offset is {config['common_input_offset']}.
This input contains {summary['negative_input_samples']} negative proxies.</p>
<p>Time windows retain the original study durations: 4 seconds = 480 frames, 5 seconds = 600 frames at 120 Hz.
Seed: {config['seed']}. Equivalent predictions:</p>{table(['Equivalent rules'], equivalent_rows)}</section>
<section><h2>Pilot pair list</h2><p>Up to ten gMAD pairs plus random and diagnostic pairs.
A/B are list labels; no subjective preference data have been collected.</p>
<input id="search" type="search" placeholder="Search pair ID, settings or purpose" aria-label="Filter pilot pairs">
<div class="scroll" id="pilot">{table(['Pair ID', 'Video A: three settings', 'Video B: three settings', 'Purpose', 'Linked gMAD tasks'], pilot_rows)}</div></section>
<section><h2>Result files</h2><p><a href="pilot_pairs.csv">Pilot pairs CSV</a> ·
<a href="gmad_pairs.csv">All gMAD pairs CSV</a> · <a href="attack_tasks.csv">Attack tasks</a> ·
<a href="predictions.csv">Candidate predictions</a> · <a href="pilot_video_recipes.json">Pilot assembly recipes</a> ·
<a href="input_audit.csv">Chunk input audit</a> · <a href="negative_frames.csv">Negative frame records</a> ·
<a href="config.json">gMAD settings and input hashes</a> · <a href="report.html">Chinese report</a></p>
<p>These are screening results from concatenated chunk-score sequences. Complete assembled-video CVVDP checks at transitions remain separate.</p></section>
</main><script>document.getElementById('search').oninput = event => {{
const query = event.target.value.toLowerCase();
document.querySelectorAll('#pilot tbody tr').forEach(row => {{row.hidden = !row.textContent.toLowerCase().includes(query);}});
}};</script></html>'''
    target = root / 'report_en.html'
    target.write_text(page, encoding='utf-8', newline='\n')
    print(f'Created {target.resolve()}')


if __name__ == '__main__':
    main()
