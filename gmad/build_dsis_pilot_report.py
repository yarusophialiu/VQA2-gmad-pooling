"""Build a self-contained HTML report: temporal pooling rules vs DSIS pilot MOS.

Reads results/dsis_pilot/analysis/ (written by analyze_dsis_pilot.py) and writes
results/dsis_pilot/analysis/pooling_vs_mos.html with three charts: the per-scene
SRCC averages (equal-weighted and weighted by n - 3) per rule, a rule x scene SRCC
strip plot and heatmap, and per-scene scatter plots of the chosen rule's score
against MOS. Also writes pooling_vs_mos_en.html, the same page in English.
"""
import json

import pandas as pd

from analyze_dsis_pilot import OUTPUT, GMAD

PREDICTORS = ['combined_jod'] + [c for c in pd.read_csv(GMAD / 'predictions.csv', encoding='utf-8-sig',
                                                         nrows=0).columns if c != 'candidate_id']
LABELS = {'combined_jod': 'CVVDP 整段 JOD（参照）'}
LABELS_EN = {'combined_jod': 'CVVDP full-clip JOD (reference)'}
# Rules whose predictions coincide on every pilot video are drawn once, named together.
SAME = {'mean': ['last_frames_mean', 'cumulative_quality'], 'median': ['kth_percentile']}


def english(page):
    """English page: translate the Chinese strings."""
    for zh, en in EN:
        assert zh in page, zh
        page = page.replace(zh, en)
    return page


def main():
    rules = pd.read_csv(OUTPUT / 'rules.csv').set_index('predictor')
    scene_srcc = pd.read_csv(OUTPUT / 'scene_srcc.csv', index_col='predictor')
    videos = pd.read_csv(OUTPUT / 'video_mos.csv')
    hidden = {r for group in SAME.values() for r in group}
    shown = [p for p in PREDICTORS if p not in hidden]
    scenes = [c.split(' (')[0] for c in scene_srcc.columns]
    sizes = videos.groupby('scene').size()

    data = {
        'rules': [{'key': p,
                   'label': LABELS.get(p, ' = '.join([p] + SAME.get(p, []))),
                   'equal': rules.loc[p, 'scene_srcc_mean'],
                   'weighted': rules.loc[p, 'scene_srcc_weighted'],
                   'pooled': rules.loc[p, 'srcc'],
                   'scenes': [None if pd.isna(v) else v for v in scene_srcc.loc[p]]} for p in shown],
        'scenes': [{'name': s, 'n': int(sizes[s]), 'weight': int(sizes[s]) - 3,
                    'shots': sorted(videos.loc[videos.scene == s, 'shot'].unique().tolist())} for s in scenes],
        'videos': [{'id': r.candidate_id, 'scene': r.scene, 'shot': r.shot, 'mos': r.mos, 'ci': r.ci95,
                    'n': int(r.n), 'chunks': f'{r.chunk1} / {r.chunk2} / {r.chunk3}',
                    'scores': {p: getattr(r, p) for p in shown}} for r in videos.itertuples()],
    }
    page = PAGE.replace('__DATA__', json.dumps(data, ensure_ascii=False))
    (OUTPUT / 'pooling_vs_mos.html').write_text(page)
    for rule in data['rules']:
        rule['label'] = LABELS_EN.get(rule['key'], rule['label'])
    (OUTPUT / 'pooling_vs_mos_en.html').write_text(english(PAGE).replace('__DATA__', json.dumps(data)))
    print(f'Wrote {OUTPUT / "pooling_vs_mos.html"} and {OUTPUT / "pooling_vs_mos_en.html"}')


PAGE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pooling 规则 vs MOS</title>
<style>
:root {
  color-scheme: light;
  --surface-0: #f6f5f2; --surface-1: #fcfcfb; --grid: #e4e3de; --axis: #b9b8b1;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #77766f;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --pooled: #9a9992;
  --series-4: #eda100; --series-5: #e87ba4; --series-6: #008300; --series-7: #6250d6; --series-8: #e34948;
  --highlight: #f0efec;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --grid: #2c2c2a; --axis: #4a4a46;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #96958c;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --pooled: #6f6e68;
    --series-4: #c98500; --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-8: #e66767;
    --highlight: #262624;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --grid: #2c2c2a; --axis: #4a4a46;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #96958c;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --pooled: #6f6e68;
    --series-4: #c98500; --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-8: #e66767;
  --highlight: #262624;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.55 system-ui, -apple-system, "PingFang SC", "Helvetica Neue", sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 6px; }
h2 { font-size: 17px; margin: 0 0 4px; }
p { margin: 0 0 10px; color: var(--text-secondary); }
.card { background: var(--surface-1); border-radius: 12px; padding: 20px; margin-top: 20px; }
.lead { max-width: 820px; }
.legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: var(--text-secondary); margin: 8px 0 4px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.key { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.key.tick { width: 2px; height: 12px; border-radius: 1px; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
svg text { fill: var(--text-secondary); font-size: 12px; }
svg .label { fill: var(--text-primary); }
svg .muted { fill: var(--text-muted); font-size: 11px; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
.row-hit { fill: transparent; }
.row-hit.hover, .row-hit.on { fill: var(--highlight); }
.controls { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 8px 0 12px; }
select { font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--axis);
  background: var(--surface-1); color: var(--text-primary); }
.panels { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px; }
.panel h3 { font-size: 14px; margin: 0; }
.panel .sub { font-size: 12px; color: var(--text-muted); margin: 0 0 2px; }
.scroll { overflow-x: auto; }
.legend button { font: inherit; color: inherit; background: none; border: 1px solid transparent; border-radius: 999px;
  padding: 2px 8px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.legend button.on { border-color: var(--axis); color: var(--text-primary); }
.strip-dot { transition: opacity .15s; }
#tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--grid); border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.5;
  box-shadow: 0 4px 16px rgba(0,0,0,.12); opacity: 0; transition: opacity .1s; max-width: 320px; z-index: 10; }
#tip b { font-weight: 600; }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--text-secondary); }
table { border-collapse: collapse; font-size: 12px; margin-top: 8px; width: 100%; }
th, td { padding: 4px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
</style>
</head>
<body>
<main>
<h1>Pooling 规则 vs 人眼 MOS（DSIS pilot）</h1>
<p class="lead">7 名被试，84 个视频，8 个场景，未剔除任何被试。每个场景内：把该场景全部视频（所有 shot 合在一起）按 MOS 和按规则分数各排一次名次，求 Spearman 相关（SRCC）。
8 个场景的 SRCC 在 Fisher z 空间平均：<b>等权</b> = 每个场景一份；<b>加权</b> = 权重为视频数 − 3，视频多的场景说了算。</p>

<section class="card">
<h2>1. 各规则的场景平均 SRCC</h2>
<p>按加权排序。小场景（heros3、ratchet 各 5 个视频）会把等权平均抬高，建议以加权为准。点击一行，下面的散点图切换到该规则。</p>
<div class="legend">
  <span><i class="key" style="background:var(--series-1)"></i>场景加权</span>
  <span><i class="key" style="background:var(--series-2)"></i>场景等权</span>
  <span><i class="key tick" style="background:var(--pooled)"></i>84 个视频混在一起（参照）</span>
</div>
<div id="dots"></div>
</section>

<section class="card">
<h2>2. 每个场景、每个规则的 SRCC</h2>
<p>上图：横轴是规则（按加权排序），每个点是一个场景在该规则下的 SRCC。每个场景在每列里的左右位置固定，点击图例可以单独看一个场景。</p>
<div class="legend" id="strip-legend"></div>
<div class="scroll"><div id="strip"></div></div>
<p class="muted" style="font-size:12px">* mean 同 last_frames_mean、cumulative_quality；median 同 kth_percentile（这批视频上分数完全一样）。</p>
<p style="margin-top:18px">下图：同样的数值做成热力图，颜色越深相关越高。列名下面是该场景的视频数；视频越少，这一格越不可信。</p>
<div class="scroll"><div id="heat"></div></div>
</section>

<section class="card">
<h2>3. 每个场景：规则分数 vs MOS</h2>
<p>每个点是一个视频，竖线是 MOS 的 95% 置信区间，颜色区分同一场景里的不同 shot。横轴是规则给出的 JOD，各场景范围不同。</p>
<div class="controls"><label for="pick">规则</label><select id="pick"></select></div>
<div class="panels" id="panels"></div>
</section>

<section class="card">
<h2>数据表</h2>
<details><summary>展开全部数值</summary><div class="scroll" id="table"></div></details>
</section>
</main>
<div id="tip" role="tooltip"></div>
<script>
const DATA = __DATA__;
const NS = 'http://www.w3.org/2000/svg';
const f2 = v => v == null ? '—' : v.toFixed(2);
const tip = document.getElementById('tip');
let current = DATA.rules.slice().sort((a, b) => b.weighted - a.weighted)[0].key;

function el(name, attrs, parent, text) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function showTip(evt, html) {
  tip.innerHTML = html; tip.style.opacity = 1;
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > innerWidth - 8) x = evt.clientX - w - pad;
  if (y + h > innerHeight - 8) y = evt.clientY - h - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip() { tip.style.opacity = 0; }
function bindTip(node, html) {
  node.addEventListener('mousemove', e => showTip(e, html));
  node.addEventListener('mouseleave', hideTip);
}

// 1. Dot plot: weighted / equal / pooled SRCC per rule
function drawDots() {
  const rules = DATA.rules.slice().sort((a, b) => b.weighted - a.weighted);
  const row = 30, left = 300, right = 30, top = 24, width = 900;
  const height = top + row * rules.length + 8;
  const lo = 0.2, hi = 0.9, x = v => left + (v - lo) / (hi - lo) * (width - left - right);
  const box = document.getElementById('dots'); box.innerHTML = '';
  const svg = el('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': '各规则场景平均 SRCC'}, box);
  for (let t = 0.2; t <= 0.901; t += 0.1) {
    el('line', {x1: x(t), x2: x(t), y1: top - 6, y2: height - 4, class: 'grid'}, svg);
    el('text', {x: x(t), y: top - 10, 'text-anchor': 'middle'}, svg, t.toFixed(1));
  }
  rules.forEach((r, i) => {
    const y = top + i * row + row / 2;
    const band = el('rect', {x: 0, y: y - row / 2, width, height: row, rx: 6,
      class: 'row-hit' + (r.key === current ? ' on' : ''), 'pointer-events': 'none'}, svg);
    el('text', {x: left - 14, y: y + 4, 'text-anchor': 'end', class: 'label'}, svg, r.label);
    const a = Math.min(r.equal, r.weighted), b = Math.max(r.equal, r.weighted);
    el('line', {x1: x(a), x2: x(b), y1: y, y2: y, stroke: 'var(--axis)', 'stroke-width': 2}, svg);
    el('line', {x1: x(r.pooled), x2: x(r.pooled), y1: y - 7, y2: y + 7, stroke: 'var(--pooled)',
      'stroke-width': 2, 'stroke-linecap': 'round'}, svg);
    el('circle', {cx: x(r.equal), cy: y, r: 5, fill: 'var(--series-2)', stroke: 'var(--surface-1)', 'stroke-width': 2}, svg);
    el('circle', {cx: x(r.weighted), cy: y, r: 5, fill: 'var(--series-1)', stroke: 'var(--surface-1)', 'stroke-width': 2}, svg);
    if (i < 3) el('text', {x: x(Math.min(r.equal, r.weighted, r.pooled)) - 12, y: y + 4, 'text-anchor': 'end', class: 'muted'}, svg,
      `加权 ${f2(r.weighted)} · 等权 ${f2(r.equal)}`);
    // Transparent hit area on top of the marks; it lights the band underneath.
    const hit = el('rect', {x: 0, y: y - row / 2, width, height: row, fill: 'transparent', style: 'cursor:pointer'}, svg);
    hit.addEventListener('mouseenter', () => band.classList.add('hover'));
    hit.addEventListener('mouseleave', () => band.classList.remove('hover'));
    hit.addEventListener('click', () => select(r.key));
    bindTip(hit, `<b>${r.label}</b><br>场景加权 ${f2(r.weighted)}<br>场景等权 ${f2(r.equal)}<br>84 个视频混在一起 ${f2(r.pooled)}`);
  });
}


// 2a. Strip plot: x = rule, y = SRCC, one colour (and one fixed offset) per scene
let focusScene = null;
function drawStrip() {
  const rules = DATA.rules.slice().sort((a, b) => b.weighted - a.weighted);
  const scenes = DATA.scenes, colors = scenes.map((_, j) => `var(--series-${j + 1})`);
  const left = 110, right = 12, top = 26, bottom = 120, col = 64;
  const width = left + col * rules.length + right, height = 380;
  const lo = 0, hi = 1, Y = v => top + (hi - v) / (hi - lo) * (height - top - bottom);
  const legend = document.getElementById('strip-legend'); legend.innerHTML = '';
  scenes.forEach((s, j) => {
    const b = document.createElement('button');
    b.className = focusScene === j ? 'on' : '';
    b.innerHTML = `<i class="key" style="background:${colors[j]}"></i>${s.name}（${s.n}）`;
    b.addEventListener('click', () => { focusScene = focusScene === j ? null : j; drawStrip(); });
    legend.appendChild(b);
  });
  const box = document.getElementById('strip'); box.innerHTML = '';
  const svg = el('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': '每个场景每个规则的 SRCC 点图',
    style: `min-width:${width}px`}, box);
  for (let t = 0; t <= 1.001; t += 0.2) {
    el('line', {x1: left, x2: width - right, y1: Y(t), y2: Y(t), class: 'grid'}, svg);
    el('text', {x: left - 8, y: Y(t) + 4, 'text-anchor': 'end'}, svg, t.toFixed(1));
  }
  el('text', {x: left - 8, y: 10, 'text-anchor': 'end', class: 'muted'}, svg, 'SRCC');
  const offset = j => (j - (scenes.length - 1) / 2) * (col - 16) / (scenes.length - 1);
  rules.forEach((r, i) => {
    const cx = left + i * col + col / 2;
    const short = r.label.split(' = ')[0].replace(/（参照）| \(reference\)/, '') + (r.label.includes(' = ') ? ' *' : '');
    const lab = el('text', {x: cx, y: height - bottom + 16, 'text-anchor': 'end', class: 'label',
      transform: `rotate(-40 ${cx} ${height - bottom + 16})`}, svg, short);
    lab.style.fontSize = '11px';
  });
  // Connect each scene's points so one scene can be followed across rules when focused.
  scenes.forEach((s, j) => {
    if (focusScene !== j) return;
    const pts = rules.map((r, i) => r.scenes[j] == null ? null : [left + i * col + col / 2 + offset(j), Y(r.scenes[j])]).filter(Boolean);
    el('polyline', {points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: colors[j], 'stroke-width': 2,
      'stroke-linejoin': 'round', opacity: 0.6}, svg);
  });
  rules.forEach((r, i) => {
    const cx = left + i * col + col / 2;
    r.scenes.forEach((v, j) => {
      if (v == null) return;
      const g = el('g', {class: 'strip-dot', opacity: focusScene == null || focusScene === j ? 1 : 0.12}, svg);
      el('circle', {cx: cx + offset(j), cy: Y(v), r: 9, fill: 'transparent'}, g);
      el('circle', {cx: cx + offset(j), cy: Y(v), r: 4, fill: colors[j], stroke: 'var(--surface-1)', 'stroke-width': 1.5}, g);
      bindTip(g, `<b>${scenes[j].name}</b>（${scenes[j].n} 个视频）<br>${r.label}<br>SRCC ${f2(v)}`);
    });
  });
}

// 2b. Heatmap: rule x scene SRCC
function drawHeat() {
  const rules = DATA.rules.slice().sort((a, b) => b.weighted - a.weighted);
  const left = 300, cw = 76, ch = 26, top = 40, width = left + cw * DATA.scenes.length + 8;
  const height = top + ch * rules.length + 4;
  const box = document.getElementById('heat'); box.innerHTML = '';
  const svg = el('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': '每个场景每个规则的 SRCC',
    style: `min-width:${width}px`}, box);
  const ramp = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6',
                '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'];
  const color = v => ramp[Math.max(0, Math.min(ramp.length - 1, Math.round(v * (ramp.length - 1))))];
  DATA.scenes.forEach((s, j) => {
    el('text', {x: left + j * cw + cw / 2, y: top - 22, 'text-anchor': 'middle', class: 'label'}, svg, s.name);
    el('text', {x: left + j * cw + cw / 2, y: top - 8, 'text-anchor': 'middle', class: 'muted'}, svg, `${s.n} 个视频`);
  });
  rules.forEach((r, i) => {
    const y = top + i * ch;
    el('text', {x: left - 14, y: y + ch / 2 + 4, 'text-anchor': 'end', class: 'label'}, svg, r.label);
    r.scenes.forEach((v, j) => {
      const g = el('g', {style: 'cursor:pointer'}, svg);
      el('rect', {x: left + j * cw + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3,
        fill: v == null ? 'var(--grid)' : color(Math.max(0, v))}, g);
      const dark = v != null && v >= 0.55;
      el('text', {x: left + j * cw + cw / 2, y: y + ch / 2 + 4, 'text-anchor': 'middle',
        style: `fill:${dark ? '#ffffff' : '#0b0b0b'};font-size:11px`}, g, f2(v));
      g.addEventListener('click', () => select(r.key));
      bindTip(g, `<b>${r.label}</b> · ${DATA.scenes[j].name}<br>SRCC ${f2(v)}（${DATA.scenes[j].n} 个视频，加权权重 ${DATA.scenes[j].weight}）`);
    });
  });
}

// 3. Small multiples: chosen rule's score vs MOS, one panel per scene
function drawPanels() {
  const rule = DATA.rules.find(r => r.key === current);
  const box = document.getElementById('panels'); box.innerHTML = '';
  const shotColor = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)'];
  DATA.scenes.forEach((s, j) => {
    const vids = DATA.videos.filter(v => v.scene === s.name);
    const div = document.createElement('div'); div.className = 'panel'; box.appendChild(div);
    div.innerHTML = `<h3>${s.name} · SRCC ${f2(rule.scenes[j])}</h3><p class="sub">${s.n} 个视频 · ` +
      s.shots.map((sh, k) => `<i class="key" style="background:${shotColor[k]}"></i> shot ${sh.split('_').pop()}`).join('　') + '</p>';
    const W = 260, H = 218, L = 34, R = 10, T = 22, B = 30;
    const xs = vids.map(v => v.scores[current]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    const padX = Math.max(0.15, (x1 - x0) * 0.08); x0 -= padX; x1 += padX;
    const X = v => L + (v - x0) / (x1 - x0) * (W - L - R), Y = v => T + (5 - v) / 4 * (H - T - B);
    const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${s.name} ${rule.label} vs MOS`}, div);
    for (let m = 1; m <= 5; m++) {
      el('line', {x1: L, x2: W - R, y1: Y(m), y2: Y(m), class: 'grid'}, svg);
      el('text', {x: L - 8, y: Y(m) + 4, 'text-anchor': 'end'}, svg, m);
    }
    const step = niceStep((x1 - x0) / 4);
    for (let t = Math.ceil(x0 / step) * step; t <= x1; t += step)
      el('text', {x: X(t), y: H - B + 16, 'text-anchor': 'middle'}, svg, +t.toFixed(2));
    el('text', {x: W - R, y: H - 2, 'text-anchor': 'end', class: 'muted'}, svg, '规则分数 (JOD)');
    el('text', {x: 2, y: 10, class: 'muted'}, svg, 'MOS');
    vids.forEach(v => {
      const c = shotColor[s.shots.indexOf(v.shot)];
      const cx = X(v.scores[current]);
      el('line', {x1: cx, x2: cx, y1: Y(Math.min(5, v.mos + v.ci)), y2: Y(Math.max(1, v.mos - v.ci)),
        stroke: c, 'stroke-width': 1.5, opacity: 0.45}, svg);
    });
    vids.forEach(v => {
      const c = shotColor[s.shots.indexOf(v.shot)];
      const g = el('g', {}, svg);
      el('circle', {cx: X(v.scores[current]), cy: Y(v.mos), r: 10, fill: 'transparent'}, g);
      el('circle', {cx: X(v.scores[current]), cy: Y(v.mos), r: 4.5, fill: c, stroke: 'var(--surface-1)', 'stroke-width': 2}, g);
      bindTip(g, `<b>${v.chunks}</b><br>${v.shot.split('__')[1]}<br>MOS ${f2(v.mos)} ± ${f2(v.ci)}（${v.n} 人）<br>${rule.label}: ${f2(v.scores[current])}`);
    });
  });
}
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
  return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
}

function drawTable() {
  const rules = DATA.rules.slice().sort((a, b) => b.weighted - a.weighted);
  let h = '<table><tr><th>规则</th><th>场景加权</th><th>场景等权</th><th>84 个混合</th>' +
    DATA.scenes.map(s => `<th>${s.name} (${s.n})</th>`).join('') + '</tr>';
  rules.forEach(r => {
    h += `<tr><td>${r.label}</td><td>${f2(r.weighted)}</td><td>${f2(r.equal)}</td><td>${f2(r.pooled)}</td>` +
      r.scenes.map(v => `<td>${f2(v)}</td>`).join('') + '</tr>';
  });
  document.getElementById('table').innerHTML = h + '</table>';
}

function select(key) {
  current = key;
  const pick = document.getElementById('pick');
  if (pick) pick.value = key;
  drawDots();
  if (document.getElementById('panels')) drawPanels();
}

const pick = document.getElementById('pick');
if (pick) {
  DATA.rules.slice().sort((a, b) => b.weighted - a.weighted).forEach(r => {
    const o = document.createElement('option'); o.value = r.key; o.textContent = r.label; pick.appendChild(o);
  });
  pick.addEventListener('change', () => select(pick.value));
}
drawStrip(); drawHeat(); drawTable(); select(current);
</script>
</body>
</html>
"""

EN = [
    ('<html lang="zh">', '<html lang="en">'),
    ('<title>Pooling 规则 vs MOS</title>', '<title>Pooling Rules vs MOS</title>'),
    ('<h1>Pooling 规则 vs 人眼 MOS（DSIS pilot）</h1>', '<h1>Temporal pooling rules vs MOS (DSIS pilot)</h1>'),
    ('7 名被试，84 个视频，8 个场景，未剔除任何被试。每个场景内：把该场景全部视频（所有 shot 合在一起）按 MOS 和按规则分数各排一次名次，求 Spearman 相关（SRCC）。\n'
     '8 个场景的 SRCC 在 Fisher z 空间平均：<b>等权</b> = 每个场景一份；<b>加权</b> = 权重为视频数 − 3，视频多的场景说了算。',
     '7 participants, 84 videos, 8 scenes; no participant was rejected. Within each scene, all of its videos (every shot together) '
     'are ranked by MOS and by the rule\'s score, and the Spearman correlation (SRCC) between the two rankings is computed. '
     'The 8 scene SRCCs are averaged in Fisher z space: <b>equal-weighted</b> gives every scene the same weight; '
     '<b>weighted</b> uses n − 3 (number of videos minus 3), so scenes with more videos count more.'),
    ('<h2>1. 各规则的场景平均 SRCC</h2>', '<h2>1. Scene-averaged SRCC per rule</h2>'),
    ('<p>按加权排序。小场景（heros3、ratchet 各 5 个视频）会把等权平均抬高，建议以加权为准。点击一行，下面的散点图切换到该规则。</p>',
     '<p>Sorted by the weighted average. Small scenes (heros3 and ratchet, 5 videos each) inflate the equal-weighted average, '
     'so the weighted average is the one to read. Click a row to show that rule in the scatter plots below.</p>'),
    ('></i>场景加权</span>', '></i>Scene average, weighted (n − 3)</span>'),
    ('></i>场景等权</span>', '></i>Scene average, equal weights</span>'),
    ('></i>84 个视频混在一起（参照）</span>', '></i>All 84 videos pooled (reference)</span>'),
    ('<h2>2. 每个场景、每个规则的 SRCC</h2>', '<h2>2. SRCC per scene and rule</h2>'),
    ('<p>上图：横轴是规则（按加权排序），每个点是一个场景在该规则下的 SRCC。每个场景在每列里的左右位置固定，点击图例可以单独看一个场景。</p>',
     '<p>Top: rules on the x-axis (sorted by the weighted average); each dot is one scene\'s SRCC for that rule. '
     'Each scene keeps the same horizontal offset within every column. Click a scene in the legend to isolate it.</p>'),
    ('* mean 同 last_frames_mean、cumulative_quality；median 同 kth_percentile（这批视频上分数完全一样）。',
     '* mean is identical to last_frames_mean and cumulative_quality, and median to kth_percentile, on these videos.'),
    ('<p style="margin-top:18px">下图：同样的数值做成热力图，颜色越深相关越高。列名下面是该场景的视频数；视频越少，这一格越不可信。</p>',
     '<p style="margin-top:18px">Bottom: the same values as a heatmap; darker means higher correlation. Under each scene is its '
     'number of videos; the fewer the videos, the less reliable the cell.</p>'),
    ('<h2>3. 每个场景：规则分数 vs MOS</h2>', '<h2>3. Per scene: rule score vs MOS</h2>'),
    ('<p>每个点是一个视频，竖线是 MOS 的 95% 置信区间，颜色区分同一场景里的不同 shot。横轴是规则给出的 JOD，各场景范围不同。</p>',
     '<p>Each dot is one video; the vertical line is the 95% confidence interval of its MOS, and colour marks the shot '
     'within the scene. The x-axis is the JOD the rule gives; its range differs between scenes.</p>'),
    ('<label for="pick">规则</label>', '<label for="pick">Rule</label>'),
    ('<p class="sub">${s.n} 个视频 · `', '<p class="sub">${s.n} videos · `'),
    (".join('　')", ".join(' &nbsp; ')"),
    ("'规则分数 (JOD)'", "'Rule score (JOD)'"),
    ('MOS ${f2(v.mos)} ± ${f2(v.ci)}（${v.n} 人）', 'MOS ${f2(v.mos)} ± ${f2(v.ci)} (${v.n} raters)'),
    ('<h2>数据表</h2>', '<h2>Data table</h2>'),
    ('<summary>展开全部数值</summary>', '<summary>Show all values</summary>'),
    ("'aria-label': '各规则场景平均 SRCC'", "'aria-label': 'Scene-averaged SRCC per rule'"),
    ('`加权 ${f2(r.weighted)} · 等权 ${f2(r.equal)}`', '`weighted ${f2(r.weighted)} · equal ${f2(r.equal)}`'),
    ('<br>场景加权 ${f2(r.weighted)}<br>场景等权 ${f2(r.equal)}<br>84 个视频混在一起 ${f2(r.pooled)}',
     '<br>Weighted ${f2(r.weighted)}<br>Equal weights ${f2(r.equal)}<br>All 84 pooled ${f2(r.pooled)}'),
    ('${s.name}（${s.n}）`', '${s.name} (${s.n})`'),
    ("'aria-label': '每个场景每个规则的 SRCC 点图'", "'aria-label': 'SRCC per scene and rule, dot plot'"),
    ('`<b>${scenes[j].name}</b>（${scenes[j].n} 个视频）<br>', '`<b>${scenes[j].name}</b> (${scenes[j].n} videos)<br>'),
    ("'aria-label': '每个场景每个规则的 SRCC'", "'aria-label': 'SRCC per scene and rule, heatmap'"),
    ('`${s.n} 个视频`', '`${s.n} videos`'),
    ('SRCC ${f2(v)}（${DATA.scenes[j].n} 个视频，加权权重 ${DATA.scenes[j].weight}）',
     'SRCC ${f2(v)} (${DATA.scenes[j].n} videos, weight ${DATA.scenes[j].weight})'),
    ("'<table><tr><th>规则</th><th>场景加权</th><th>场景等权</th><th>84 个混合</th>'",
     "'<table><tr><th>Rule</th><th>Weighted</th><th>Equal weights</th><th>All 84 pooled</th>'"),
]

if __name__ == '__main__':
    main()
