"""Build a self-contained HTML report of the combined (4.5 s) CVVDP scores.

Reads <results>/combined_jod_dsis.csv and scoring_config.json written by
score_combined_cvvdp.py and writes <results>/combined_jod_report.html.
"""
import argparse
import csv
import html
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEVELS = {5: 'Excellent', 4: 'Good', 3: 'Fair', 2: 'Poor', 1: 'Bad'}
LONG = {5: 'Imperceptible', 4: 'Perceptible, but not annoying', 3: 'Slightly annoying',
        2: 'Annoying', 1: 'Very annoying'}
BINS = {5: 'JOD ≥ 9.5', 4: '8.5 – 9.5', 3: '7.5 – 8.5', 2: '6.5 – 7.5', 1: '< 6.5'}


def esc(text):
    return html.escape(str(text), quote=True)


def right_rounded(x, y, w, h, r=4):
    """Bar whose data end (right) is rounded and whose baseline end is square."""
    r = min(r, w / 2, h / 2)
    return (f'M{x:.1f},{y:.1f}H{x + w - r:.1f}Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}'
            f'V{y + h - r:.1f}Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f}H{x:.1f}Z')


def level_bars(counts, total):
    """Horizontal bars: videos per DSIS level, best level on top."""
    width, row, left, right = 640, 34, 150, 70
    plot = width - left - right
    peak = max(counts.values())
    parts = [f'<svg viewBox="0 0 {width} {row * 5 + 8}" role="img" aria-label="Videos per DSIS level">']
    for i, level in enumerate((5, 4, 3, 2, 1)):
        y = 4 + i * row
        w = max(2, plot * counts[level] / peak)
        tip = f'Level {level} – {LEVELS[level]}|{counts[level]} videos ({100 * counts[level] / total:.0f}%)|{BINS[level]}'
        parts.append(f'<text x="{left - 12}" y="{y + row / 2 + 4}" class="tick" text-anchor="end">'
                     f'{level}  {LEVELS[level]}</text>')
        parts.append(f'<path d="{right_rounded(left, y + 7, w, row - 14)}" fill="var(--level-{level})"/>')
        parts.append(f'<text x="{left + w + 8}" y="{y + row / 2 + 4}" class="value">{counts[level]}</text>')
        parts.append(f'<rect x="0" y="{y}" width="{width}" height="{row}" class="hit" data-tip="{esc(tip)}"/>')
    parts.append(f'<line x1="{left}" x2="{left}" y1="0" y2="{row * 5 + 8}" class="axis"/>')
    parts.append('</svg>')
    return ''.join(parts)


def scene_stacks(rows):
    """One stacked bar per scene: how many of its videos fall in each level."""
    scenes = sorted({r['scene'] for r in rows})
    counts = {s: Counter(int(r['dsis_level']) for r in rows if r['scene'] == s) for s in scenes}
    width, row, left, right, top = 640, 28, 96, 40, 22
    peak = max(sum(c.values()) for c in counts.values())
    plot = width - left - right
    height = top + row * len(scenes) + 4
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="DSIS levels per scene">']
    for tick in range(0, peak + 1, 5):
        x = left + plot * tick / peak
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top - 4}" y2="{height}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{top - 9}" class="tick" text-anchor="middle">{tick}</text>')
    for i, scene in enumerate(scenes):
        y = top + i * row + 6
        h = row - 12
        x = left
        present = [lv for lv in (1, 2, 3, 4, 5) if counts[scene][lv]]
        parts.append(f'<text x="{left - 10}" y="{y + h / 2 + 4}" class="tick" text-anchor="end">{esc(scene)}</text>')
        total = sum(counts[scene].values())
        for level in present:
            n = counts[scene][level]
            w = plot * n / peak
            draw = w - 2 if level != present[-1] else w   # 2px surface gap between segments
            shape = (right_rounded(x, y, draw, h) if level == present[-1]
                     else f'M{x:.1f},{y:.1f}h{draw:.1f}v{h}h{-draw:.1f}Z')
            tip = f'{scene}|Level {level} – {LEVELS[level]}: {n} of {total} videos'
            parts.append(f'<path d="{shape}" fill="var(--level-{level})"/>')
            parts.append(f'<rect x="{x:.1f}" y="{y - 4}" width="{w:.1f}" height="{h + 8}" class="hit" data-tip="{esc(tip)}"/>')
            x += w
        parts.append(f'<text x="{x + 6:.1f}" y="{y + h / 2 + 4}" class="muted">{total}</text>')
    parts.append(f'<line x1="{left}" x2="{left}" y1="{top - 4}" y2="{height}" class="axis"/>')
    parts.append('</svg>')
    return ''.join(parts)


def scatter(rows):
    """Combined 4.5 s JOD against the mean of the three chunk JODs used for gMAD."""
    points = [(float(r['mean_chunk_jod']), float(r['combined_jod']), r) for r in rows if r['mean_chunk_jod']]
    lo, hi = 4.5, 10.0
    width, height, left, bottom, top, right = 640, 440, 52, 44, 12, 16
    pw, ph = width - left - right, height - top - bottom

    def sx(v):
        return left + pw * (v - lo) / (hi - lo)

    def sy(v):
        return top + ph * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Combined JOD against mean chunk JOD">']
    for tick in (5, 6, 7, 8, 9, 10):
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{sy(tick):.1f}" y2="{sy(tick):.1f}" class="grid"/>')
        parts.append(f'<line x1="{sx(tick):.1f}" x2="{sx(tick):.1f}" y1="{top}" y2="{top + ph}" class="grid"/>')
        parts.append(f'<text x="{left - 8}" y="{sy(tick) + 4:.1f}" class="tick" text-anchor="end">{tick}</text>')
        parts.append(f'<text x="{sx(tick):.1f}" y="{top + ph + 18}" class="tick" text-anchor="middle">{tick}</text>')
    parts.append(f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" class="ref"/>')
    parts.append(f'<text x="{sx(9.15):.1f}" y="{sy(9.55):.1f}" class="muted" text-anchor="end">same score</text>')
    for mean, combined, r in points:
        tip = (f'{r["candidate_id"]}|Combined JOD {combined:.2f} · mean chunk JOD {mean:.2f}'
               f'|Difference {combined - mean:+.2f}')
        parts.append(f'<circle cx="{sx(mean):.1f}" cy="{sy(combined):.1f}" r="4" class="dot"/>')
        parts.append(f'<circle cx="{sx(mean):.1f}" cy="{sy(combined):.1f}" r="9" class="hit" data-tip="{esc(tip)}"/>')
    parts.append(f'<line x1="{left}" x2="{width - right}" y1="{top + ph}" y2="{top + ph}" class="axis"/>')
    parts.append(f'<line x1="{left}" x2="{left}" y1="{top}" y2="{top + ph}" class="axis"/>')
    parts.append(f'<text x="{left + pw / 2}" y="{height - 6}" class="label" text-anchor="middle">'
                 'Mean of the three 1.5 s chunk JODs (gMAD selection)</text>')
    parts.append(f'<text transform="translate(14 {top + ph / 2}) rotate(-90)" class="label" text-anchor="middle">'
                 'Combined 4.5 s JOD</text>')
    parts.append('</svg>')
    return ''.join(parts)


def table(rows):
    body = []
    for r in sorted(rows, key=lambda r: (r['scene'], r['shot'], -float(r['combined_jod']))):
        level = int(r['dsis_level'])
        combined = float(r['combined_jod'])
        mean = float(r['mean_chunk_jod']) if r['mean_chunk_jod'] else None
        diff = f'{combined - mean:+.2f}' if mean is not None else ''
        shot = r['shot'].split('__', 1)[1]
        body.append(
            f'<tr data-scene="{esc(r["scene"])}">'
            f'<td>{esc(r["scene"])}</td><td>{esc(shot)}</td>'
            f'<td>{esc(r["chunk1"])}</td><td>{esc(r["chunk2"])}</td><td>{esc(r["chunk3"])}</td>'
            f'<td class="num" data-v="{combined}">{combined:.3f}</td>'
            f'<td class="num" data-v="{mean if mean is not None else ""}">{"" if mean is None else f"{mean:.3f}"}</td>'
            f'<td class="num" data-v="{diff}">{diff}</td>'
            f'<td data-v="{level}"><span class="chip" style="background:var(--level-{level})"></span>'
            f'{level} {LEVELS[level]}</td></tr>')
    return ''.join(body)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CVVDP DSIS Scores</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --series-1: #2a78d6;
  --level-1: #86b6ef; --level-2: #5598e7; --level-3: #2a78d6; --level-4: #1c5cab; --level-5: #104281;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --series-1: #3987e5;
    --level-1: #184f95; --level-2: #256abf; --level-3: #3987e5; --level-4: #6da7ec; --level-5: #b7d3f6;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --series-1: #3987e5;
  --level-1: #184f95; --level-2: #256abf; --level-3: #3987e5; --level-4: #6da7ec; --level-5: #b7d3f6;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1000px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 6px; }
h2 { font-size: 18px; margin: 36px 0 6px; }
p, li { color: var(--ink-2); }
.lede { margin: 0 0 20px; max-width: 70ch; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 20px 0; }
.tile, .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.tile { padding: 14px 16px; }
.tile .k { color: var(--ink-2); font-size: 13px; }
.tile .v { font-size: 26px; font-weight: 600; }
.card { padding: 16px; overflow-x: auto; }
svg { display: block; width: 100%; height: auto; max-width: 760px; font-size: 12px; }
.tick { fill: var(--ink-2); font-variant-numeric: tabular-nums; }
.value { fill: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
.muted { fill: var(--muted); }
.label { fill: var(--ink-2); font-size: 13px; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
.ref { stroke: var(--muted); stroke-width: 1.5; stroke-dasharray: 4 4; }
.dot { fill: var(--series-1); fill-opacity: 0.75; stroke: var(--surface); stroke-width: 2; }
.hit { fill: transparent; cursor: default; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 0 0 10px; font-size: 13px; color: var(--ink-2); }
.chip { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--grid); text-align: left; white-space: nowrap; }
th { color: var(--ink-2); font-weight: 600; cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--surface); }
th[aria-sort="ascending"]::after { content: " ▲"; }
th[aria-sort="descending"]::after { content: " ▼"; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 0 0 12px; }
select, input { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; padding: 5px 8px; }
.bins td:first-child { font-weight: 600; }
#tip { position: fixed; pointer-events: none; display: none; background: var(--surface); color: var(--ink);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 13px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15); max-width: 360px; z-index: 10; }
#tip b { display: block; margin-bottom: 2px; }
#tip span { display: block; color: var(--ink-2); }
code { font-size: 13px; }
</style>
</head>
<body>
<main>
<h1>CVVDP scores for the DSIS experiment</h1>
<p class="lede">Each of the __N__ gMAD-selected videos in Version A was scored with ColorVideoVDP as one
4.5&nbsp;s clip (chunk&nbsp;1 + chunk&nbsp;2 + chunk&nbsp;3), as participants see it, against its shot's
1080p120 reference. Each JOD is then mapped to the five-level DSIS impairment scale.</p>

<div class="tiles">
  <div class="tile"><div class="k">Videos scored</div><div class="v">__N__</div></div>
  <div class="tile"><div class="k">Scenes / shots</div><div class="v">__SCENES__ / __SHOTS__</div></div>
  <div class="tile"><div class="k">JOD range</div><div class="v">__MIN__ – __MAX__</div></div>
  <div class="tile"><div class="k">Median JOD</div><div class="v">__MEDIAN__</div></div>
</div>

<h2>DSIS levels</h2>
<p>CVVDP has no official DSIS mapping. Bins are 1&nbsp;JOD wide, counted down from the reference (JOD&nbsp;10);
1&nbsp;JOD is the difference that 75% of viewers would notice when choosing the better of two clips, so within
0.5&nbsp;JOD of the reference is treated as imperceptible.</p>
<div class="card">
<table class="bins">
<thead><tr><th>Level</th><th>DSIS label</th><th>JOD</th><th style="text-align:right">Videos</th></tr></thead>
<tbody>__BINS__</tbody>
</table>
</div>
<div class="card" style="margin-top:12px">__LEVELBARS__</div>

<h2>Levels per scene</h2>
<p>How many of each scene's videos fall in each level. Fox and school are mostly mild; forza, gallery and
sibenik hold most of the level&nbsp;1 videos.</p>
<div class="card">
<div class="legend">__LEGEND__</div>
__STACKS__
</div>

<h2>Combined score against the gMAD chunk mean</h2>
<p>The gMAD selection used the mean of the three per-chunk JODs. The 4.5&nbsp;s score ranks the videos almost
the same way (correlation __CORR__) but is __MEANDIFF__&nbsp;JOD lower on average (up to __MAXDIFF__), probably
because CVVDP now also sees the quality changes between chunks. Points below the dashed line scored lower
as one clip.</p>
<div class="card">__SCATTER__</div>

<h2>All videos</h2>
<div class="controls">
  <label>Scene <select id="scene"><option value="">All scenes</option>__OPTIONS__</select></label>
  <span id="count" class="muted"></span>
</div>
<div class="card" style="max-height:640px; overflow:auto; padding:0">
<table id="videos">
<thead><tr><th>Scene</th><th>Shot</th><th>Chunk 1</th><th>Chunk 2</th><th>Chunk 3</th>
<th class="num">Combined JOD</th><th class="num">Mean chunk JOD</th>
<th class="num">Difference</th><th>DSIS level</th></tr></thead>
<tbody>__ROWS__</tbody>
</table>
</div>

<h2>Method</h2>
<ul>
<li>ColorVideoVDP v__VERSION__ (git <code>e837f06</code>), video mode, display model <code>standard_fhd</code>,
torch __TORCH__. It reproduces the earlier per-chunk scores exactly.</li>
<li>Test and reference are resized to 1920×1080 (bilinear) and resampled to 120&nbsp;Hz by frame repetition,
giving 540 frames per clip; temporal padding <code>__PADDING__</code>.</li>
<li>The three 1.5&nbsp;s chunks are joined in memory, so temporal filtering runs across chunk boundaries.
1080p120 test chunks use the reference file, as the experiment does.</li>
<li>Per-frame JOD proxies (540 per video) are in <code>frames/</code>; the scores are in
<code>combined_jod_dsis.csv</code>. Built by <code>gmad/score_combined_cvvdp.py</code> and
<code>gmad/build_combined_jod_report.py</code>.</li>
</ul>
</main>
<div id="tip"></div>
<script>
const tip = document.getElementById('tip');
document.addEventListener('mousemove', e => {
  const target = e.target.closest('[data-tip]');
  if (!target) { tip.style.display = 'none'; return; }
  const [head, ...lines] = target.dataset.tip.split('|');
  tip.innerHTML = '';
  const b = document.createElement('b'); b.textContent = head; tip.appendChild(b);
  for (const line of lines) { const s = document.createElement('span'); s.textContent = line; tip.appendChild(s); }
  tip.style.display = 'block';
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = e.clientY + 14 + tip.offsetHeight > window.innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
});
const tbody = document.querySelector('#videos tbody');
const headers = [...document.querySelectorAll('#videos th')];
headers.forEach((th, col) => th.addEventListener('click', () => {
  const descending = th.getAttribute('aria-sort') !== 'descending';
  headers.forEach(h => h.removeAttribute('aria-sort'));
  th.setAttribute('aria-sort', descending ? 'descending' : 'ascending');
  const key = row => { const cell = row.cells[col]; const v = cell.dataset.v;
    return v !== undefined && v !== '' ? parseFloat(v) : cell.textContent; };
  const rows = [...tbody.rows].sort((a, b) => {
    const ka = key(a), kb = key(b);
    const order = typeof ka === 'number' && typeof kb === 'number' ? ka - kb : String(ka).localeCompare(String(kb));
    return descending ? -order : order;
  });
  rows.forEach(r => tbody.appendChild(r));
}));
const sceneSelect = document.getElementById('scene');
const count = document.getElementById('count');
function filter() {
  let shown = 0;
  for (const row of tbody.rows) {
    const visible = !sceneSelect.value || row.dataset.scene === sceneSelect.value;
    row.style.display = visible ? '' : 'none'; shown += visible;
  }
  count.textContent = shown + ' videos';
}
sceneSelect.addEventListener('change', filter);
filter();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'results' / 'cvvdp_combined_version_a')
    args = parser.parse_args()
    with (args.results / 'combined_jod_dsis.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    config = json.loads((args.results / 'scoring_config.json').read_text())
    jods = [float(r['combined_jod']) for r in rows]
    paired = [(float(r['combined_jod']), float(r['mean_chunk_jod'])) for r in rows if r['mean_chunk_jod']]
    diffs = [c - m for c, m in paired]
    counts = Counter(int(r['dsis_level']) for r in rows)
    bins = ''.join(f'<tr><td><span class="chip" style="background:var(--level-{lv})"></span>{lv}</td>'
                   f'<td>{LEVELS[lv]} – {LONG[lv]}</td><td>{BINS[lv]}</td>'
                   f'<td class="num">{counts[lv]}</td></tr>' for lv in (5, 4, 3, 2, 1))
    legend = ''.join(f'<span><span class="chip" style="background:var(--level-{lv})"></span>'
                     f'{lv} {LEVELS[lv]}</span>' for lv in (1, 2, 3, 4, 5))
    scenes = sorted({r['scene'] for r in rows})
    values = {
        '__N__': str(len(rows)), '__SCENES__': str(len(scenes)), '__SHOTS__': str(len({r['shot'] for r in rows})),
        '__MIN__': f'{min(jods):.2f}', '__MAX__': f'{max(jods):.2f}', '__MEDIAN__': f'{statistics.median(jods):.2f}',
        '__BINS__': bins, '__LEVELBARS__': level_bars(counts, len(rows)), '__LEGEND__': legend,
        '__STACKS__': scene_stacks(rows), '__SCATTER__': scatter(rows),
        '__CORR__': f'{statistics.correlation([c for c, _ in paired], [m for _, m in paired]):.2f}',
        '__MEANDIFF__': f'{-statistics.mean(diffs):.2f}', '__MAXDIFF__': f'{-min(diffs):.2f}',
        '__OPTIONS__': ''.join(f'<option>{esc(s)}</option>' for s in scenes), '__ROWS__': table(rows),
        '__VERSION__': esc(config['metric_version']), '__TORCH__': esc(config['torch_version']),
        '__PADDING__': esc(config['temporal_padding']),
    }
    page = PAGE
    for key, value in values.items():
        page = page.replace(key, value)
    destination = args.results / 'combined_jod_report.html'
    destination.write_text(page, encoding='utf-8')
    print(f'Wrote {destination}')


if __name__ == '__main__':
    main()
