"""Render the two pair selections of a shot-grouped gMAD run as one HTML report (zh or en)."""
import argparse
import csv
import html
import json
from pathlib import Path

KINDS = {'likely_perceptible': 'ok', 'possibly_imperceptible': 'warn', 'likely_imperceptible': 'bad'}

TEXT = {
    'zh': dict(
        labels={'likely_perceptible': '可察觉', 'possibly_imperceptible': '可能看不出', 'likely_imperceptible': '很可能看不出'},
        fonts='family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+SC:wght@400;600&family=Noto+Serif+SC:wght@600',
        display='"Noto Serif SC", "Songti SC", "SimSun", serif',
        body='"Noto Sans SC", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif',
        title='多场景 gMAD 选择',
        shown='显示 ${shown} / ${rows.length} 对', all='全部', scene='场景', label='可察觉性',
        panel='{title}：<b>{pairs} 对、{videos} 个视频</b>，{scenes} 个场景。{counts}。',
        columns=['Shot', '视频 A（chunk 1 / 2 / 3）', '视频 B', 'A 均值 JOD', 'B 均值 JOD',
                 '中位分差', '最大分差', '最大分差模型', 'gMAD 任务', '可察觉性'],
        rank_columns=['排名', '场景', 'Shot', 'gMAD 对', '分差中位数 (JOD)', '可察觉', '很可能看不出', '版本'],
        version_a='A 版', version_b='B 版（{scenes}）', in_version='B 版', joiner='、', negative='{shot}（{n} 帧）',
        tabs=['A 版 · 每个场景都选', 'B 版 · 部分场景'],
        eyebrow='gMAD · 480p/720p/1080p × 30/60/120 fps · 按 shot 分组',
        h1='多场景 gMAD 选择：两个实验版本',
        lede='{shots} 个 shot 在同一套本地 CVVDP 打分（standard_fhd，120 Hz）上按 shot 分组跑 gMAD，参数与 bistro 那次相同；'
             '再从全部 gMAD 视频对中筛出两个实验规模的版本：A 版每个场景都选，B 版只选部分场景。',
        figures=['shot（{scenes} 个场景）', '候选视频（每 shot 729）', 'gMAD 视频对', '涉及的不同视频', 'A 版视频对', 'B 版视频对'],
        figures_label='总体数字',
        method='怎么选的',
        gmad_note='每个 shot 单独成组，拼出 9³ = 729 个三段视频（每段 1.5 s）。{rules} 种 temporal pooling 规则两两作为防守者/攻击者，'
                  '在 {bins} 个质量档里找"防守者认为几乎一样、攻击者认为差最多"的视频对。负的逐帧分数跳过，时间参数按 120 Hz 换算。',
        label_title='可察觉性标注',
        label_intro='对每一对取 15 个模型预测分差里最大的 |ΔJOD|：',
        label_items=['最大分差 &lt; 0.5 JOD，接近随机猜', '0.5–1 JOD', '≥ 1 JOD（约 75% 的人能选对）'],
        label_outro='只有所有模型都认为差别小，才会被标为看不出，所以这是保守的初筛，不是人眼阈值。',
        versions_title='两个版本',
        version_items=['<b>A 版</b>：每个场景 10 对，多 shot 场景轮流取；先覆盖新的"防守模型/攻击模型/质量档"组合，再按攻击分差排序；可察觉性只标注，不排除。',
                       '<b>B 版</b>：按场景的分差中位数排名取前 5 个场景，每个 25 对，排除"很可能看不出"的视频对。'],
        ranking='场景排名',
        ranking_lede='"分差中位数"是该场景所有 gMAD 视频对最大模型分差的中位数，B 版按它取前 5。左侧蓝线标出的是 B 版选中的场景。',
        caveat_title='B 版前两名可能被高估',
        caveat='这次输入里有 {negatives} 个负的逐帧分数，来自 {negative_text} 的 30/60 fps chunk，说明那几帧质量掉得很厉害；'
               '它们按 bistro 的做法被跳过了。worst-window、percentile 这类模型对瞬间下降很敏感，所以 sibenik、gallery 排名靠前，'
               '可能有一部分来自几帧异常。想要更稳的 B 版，可以手动指定场景，例如 <code>--scenes forza spiderman heros3 ratchet lego</code>。',
        pairs='视频对',
        legend=['三段色块 = 每个 chunk 的 分辨率·帧率：', 'JOD 是 mean pooling 的预测；分差是两段视频在 15 个模型下的 |ΔJOD|。'],
        files='文件',
        files_lede='都在 <code>VQA2-gmad-pooling/results/{folder}/</code> 下：',
        file_items=['<code>selection_all_scenes/</code>、<code>selection_subset_scenes/</code>：各自的 <code>pairs.csv</code>、'
                    '<code>video_recipes.json</code>（播放器可直接读）、<code>summary.json</code>',
                    '<code>pair_perceptibility.csv</code>：全部 {gmad_pairs} 对的分差和标注；<code>scene_ranking.csv</code>：场景排名',
                    '重新生成：<code>build_selection_versions.py --gmad-dir …</code>（可调每场景对数、B 版场景、阈值），再运行本报告脚本']),
    'en': dict(
        labels={'likely_perceptible': 'Perceptible', 'possibly_imperceptible': 'Possibly imperceptible',
                'likely_imperceptible': 'Likely imperceptible'},
        fonts='family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,600',
        display='"Source Serif 4", Georgia, serif',
        body='"IBM Plex Sans", "Segoe UI", system-ui, sans-serif',
        title='Multi-scene gMAD Selection',
        shown='Showing ${shown} of ${rows.length} pairs', all='All', scene='Scene', label='Perceptibility',
        panel='{title}: <b>{pairs} pairs, {videos} videos</b> from {scenes} scenes. {counts}.',
        columns=['Shot', 'Video A (chunk 1 / 2 / 3)', 'Video B', 'A mean JOD', 'B mean JOD',
                 'Median gap', 'Max gap', 'Max-gap rule', 'gMAD tasks', 'Perceptibility'],
        rank_columns=['Rank', 'Scene', 'Shots', 'gMAD pairs', 'Median gap (JOD)', 'Perceptible', 'Likely imperceptible', 'Version'],
        version_a='Version A', version_b='Version B ({scenes})', in_version='Version B', joiner=', ', negative='{shot} ({n} frames)',
        tabs=['Version A · every scene', 'Version B · selected scenes'],
        eyebrow='gMAD · 480p/720p/1080p × 30/60/120 fps · grouped by shot',
        h1='Multi-scene gMAD selection: two experiment versions',
        lede='gMAD was run on {shots} shots, one content group per shot, using a single local CVVDP scoring setup '
             '(standard_fhd, 120 Hz) and the same parameters as the bistro run. Two experiment-sized versions were then '
             'drawn from all gMAD pairs: Version A covers every scene, Version B covers a subset of scenes.',
        figures=['shots ({scenes} scenes)', 'candidate videos (729 per shot)', 'gMAD pairs', 'distinct videos in those pairs',
                 'pairs in Version A', 'pairs in Version B'],
        figures_label='Overall figures',
        method='Method',
        gmad_note='Each shot is its own group, giving 9³ = 729 three-chunk videos (1.5 s per chunk). The {rules} temporal '
                  'pooling rules take turns as defender and attacker; within each of {bins} quality bins, gMAD finds the pair '
                  'the defender rates as nearly equal and the attacker rates as most different. Negative per-frame scores are '
                  'skipped and time constants are converted to 120 Hz.',
        label_title='Perceptibility label',
        label_intro='For each pair, take the largest |ΔJOD| across the 15 pooling models:',
        label_items=['max gap &lt; 0.5 JOD, close to chance', '0.5–1 JOD', '≥ 1 JOD (about 75% of observers pick the better video)'],
        label_outro='A pair is flagged as imperceptible only when every model predicts a small difference, so this is a '
                    'conservative model-based screen, not a human threshold.',
        versions_title='Two versions',
        version_items=['<b>Version A</b>: 10 pairs per scene, taking shots in turn. Pairs that cover a new (defender, attacker, '
                       'quality bin) cell come first, then larger normalized attack gaps. Perceptibility is labelled, not used to exclude pairs.',
                       '<b>Version B</b>: the top 5 scenes by median max gap, 25 pairs each, excluding likely-imperceptible pairs.'],
        ranking='Scene ranking',
        ranking_lede='Median gap is the median, over all gMAD pairs of a scene, of each pair\'s largest model gap. Version B '
                     'takes the top 5. Rows with a blue left edge are the scenes in Version B.',
        caveat_title='The top two Version B scenes may be overrated',
        caveat='The input contains {negatives} negative per-frame scores, from the 30/60 fps chunks of {negative_text}. These '
               'frames show sharp quality drops and were skipped, as in the bistro run. Worst-window and percentile pooling react '
               'strongly to brief drops, so part of the high ranking of sibenik and gallery may come from a few outlier frames. '
               'For a more robust Version B, pass the scenes explicitly, for example '
               '<code>--scenes forza spiderman heros3 ratchet lego</code>.',
        pairs='Pairs',
        legend=['The three blocks show each chunk\'s resolution·frame rate:',
                'JOD is the mean-pooling prediction; gaps are |ΔJOD| between the two videos under the 15 models.'],
        files='Files',
        files_lede='All under <code>VQA2-gmad-pooling/results/{folder}/</code>:',
        file_items=['<code>selection_all_scenes/</code> and <code>selection_subset_scenes/</code>: each has <code>pairs.csv</code>, '
                    '<code>video_recipes.json</code> (readable by the players) and <code>summary.json</code>',
                    '<code>pair_perceptibility.csv</code>: gaps and labels for all {gmad_pairs} pairs; '
                    '<code>scene_ranking.csv</code>: the scene ranking',
                    'To regenerate: <code>build_selection_versions.py --gmad-dir …</code> (pairs per scene, Version B scenes and '
                    'thresholds are arguments), then this report script']),
}

STYLE = """
/* Layout: one reading column; data tables scroll inside their own frames. */
:root {
  --bg: #f6f7f9; --surface: #ffffff; --fg: #1c2430; --muted: #5d6878; --line: #dde2ea;
  --accent: #2c5d8a; --accent-soft: #e3ecf5;
  --fps30: #d9e4ef; --fps60: #9fbad6; --fps120: #2c5d8a; --fps-ink: #1c2430; --fps-ink-strong: #ffffff;
  --ok: #2f7d4f; --ok-soft: #e2f1e8; --warn: #9a6a12; --warn-soft: #f6ecd6; --bad: #b23b3b; --bad-soft: #f7e1e1;
  --display: __DISPLAY__;
  --body: __BODY__;
  --mono: "IBM Plex Mono", ui-monospace, "Consolas", monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12161c; --surface: #1a2029; --fg: #e3e8ef; --muted: #9aa5b4; --line: #2c3542;
  --accent: #8db5dc; --accent-soft: #1f3247;
  --fps30: #263445; --fps60: #3d5d80; --fps120: #8db5dc; --fps-ink: #e3e8ef; --fps-ink-strong: #12161c;
  --ok: #79c695; --ok-soft: #1c3326; --warn: #e0b45c; --warn-soft: #3a2f17; --bad: #ec8b8b; --bad-soft: #3d2121;
  color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #12161c; --surface: #1a2029; --fg: #e3e8ef; --muted: #9aa5b4; --line: #2c3542;
  --accent: #8db5dc; --accent-soft: #1f3247;
  --fps30: #263445; --fps60: #3d5d80; --fps120: #8db5dc; --fps-ink: #e3e8ef; --fps-ink-strong: #12161c;
  --ok: #79c695; --ok-soft: #1c3326; --warn: #e0b45c; --warn-soft: #3a2f17; --bad: #ec8b8b; --bad-soft: #3d2121;
  color-scheme: dark }
body { background: var(--bg); color: var(--fg); font: 15px/1.65 var(--body); }
.page { max-width: 1120px; margin: 0 auto; padding-inline: 20px; padding-block: 40px 64px; display: grid; gap: 44px; }
h1, h2 { font-family: var(--display); font-weight: 600; text-wrap: balance; margin: 0; }
h1 { font-size: 2rem; line-height: 1.25; }
h2 { font-size: 1.35rem; }
h3 { font-size: 1rem; margin: 0; }
p { margin: 0; max-width: 68ch; }
section { display: grid; gap: 16px; min-width: 0; }
.eyebrow { font: 600 .75rem var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.lede { color: var(--muted); }
.figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1px; background: var(--line); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.figure { background: var(--surface); padding: 14px 16px; display: grid; gap: 2px; }
.figure b { font: 600 1.5rem var(--mono); font-variant-numeric: tabular-nums; }
.figure span { color: var(--muted); font-size: .85rem; }
.notes { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.note { display: grid; gap: 6px; align-content: start; }
.note p, .note li { color: var(--muted); font-size: .92rem; }
.note ul { margin: 0; padding-left: 1.2em; display: grid; gap: 4px; }
.caveat { border-left: 3px solid var(--warn); background: var(--warn-soft); padding: 12px 16px; border-radius: 0 6px 6px 0; display: grid; gap: 6px; }
.caveat p { color: var(--fg); font-size: .92rem; }
.frame { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: .88rem; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font: 600 .74rem var(--mono); letter-spacing: .05em; text-transform: uppercase; color: var(--muted); background: var(--bg); position: sticky; top: 0; }
tbody tr:last-child td { border-bottom: 0; }
td.num { font-family: var(--mono); font-variant-numeric: tabular-nums; text-align: right; }
th.num { text-align: right; }
tr.chosen td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.bar { display: flex; align-items: center; gap: 8px; min-width: 180px; }
.bar i { display: block; height: 8px; border-radius: 2px; background: var(--accent); }
.bar b { font: 500 .85rem var(--mono); font-variant-numeric: tabular-nums; }
.strip { display: inline-grid; grid-template-columns: repeat(3, auto); gap: 2px; font: 500 .78rem var(--mono); }
.strip span { padding: 2px 6px; border-radius: 3px; color: var(--fps-ink); }
.strip .f30 { background: var(--fps30); }
.strip .f60 { background: var(--fps60); }
.strip .f120 { background: var(--fps120); color: var(--fps-ink-strong); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: .78rem; font-weight: 600; }
.badge.ok { color: var(--ok); background: var(--ok-soft); }
.badge.warn { color: var(--warn); background: var(--warn-soft); }
.badge.bad { color: var(--bad); background: var(--bad-soft); }
.legend { display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center; color: var(--muted); font-size: .85rem; }
.tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.tabs button { font: 600 .92rem var(--body); padding: 8px 16px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: var(--fg); cursor: pointer; }
.tabs button[aria-selected="true"] { background: var(--accent); border-color: var(--accent); color: var(--surface); }
.tabs button:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.controls { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; }
.controls label { display: flex; gap: 8px; align-items: center; color: var(--muted); font-size: .88rem; }
select { font: inherit; padding: 4px 8px; border-radius: 4px; border: 1px solid var(--line); background: var(--surface); color: var(--fg); }
.count { font: 500 .85rem var(--mono); color: var(--muted); }
.panel { display: grid; gap: 14px; }
.panel .frame { max-height: 70vh; overflow: auto; }
code { font: .85em var(--mono); background: var(--accent-soft); padding: 1px 5px; border-radius: 3px; overflow-wrap: anywhere; }
.files { display: grid; gap: 6px; margin: 0; padding-left: 1.2em; color: var(--muted); font-size: .9rem; }
@media (max-width: 560px) { h1 { font-size: 1.6rem; } .page { padding-block: 28px 48px; } }
"""

SCRIPT = """
const tabs = document.querySelectorAll('.tabs button');
tabs.forEach(tab => tab.addEventListener('click', () => {
  tabs.forEach(t => t.setAttribute('aria-selected', String(t === tab)));
  document.querySelectorAll('.panel').forEach(p => { p.hidden = p.id !== tab.dataset.panel; });
}));
document.querySelectorAll('.panel').forEach(panel => {
  const scene = panel.querySelector('.f-scene'), label = panel.querySelector('.f-label');
  const rows = panel.querySelectorAll('tbody tr'), count = panel.querySelector('.count');
  const apply = () => {
    let shown = 0;
    rows.forEach(r => {
      const ok = (!scene.value || r.dataset.scene === scene.value) && (!label.value || r.dataset.label === label.value);
      r.hidden = !ok; if (ok) shown++;
    });
    count.textContent = `__SHOWN__`;
  };
  scene.addEventListener('change', apply); label.addEventListener('change', apply); apply();
});
"""


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def strip(settings):
    cells = []
    for part in settings.split(' / '):
        height, fps = part.split('p')
        cells.append(f'<span class="f{fps}" title="{part}">{height}·{fps}</span>')
    return f'<span class="strip">{"".join(cells)}</span>'


def badge(label, t):
    return f'<span class="badge {KINDS[label]}">{t["labels"][label]}</span>'


def table(columns, numeric, body):
    head = ''.join(f'<th class="num">{c}</th>' if i in numeric else f'<th>{c}</th>' for i, c in enumerate(columns))
    return f'<div class="frame"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def pair_panel(panel_id, title, summary, rows, hidden, t):
    scenes = sorted({r['scene'] for r in rows})
    options = ''.join(f'<option value="{s}">{s}</option>' for s in scenes)
    label_options = ''.join(f'<option value="{k}">{v}</option>' for k, v in t['labels'].items())
    body = []
    for r in rows:
        body.append(
            f'<tr data-scene="{r["scene"]}" data-label="{r["perceptibility"]}">'
            f'<td>{r["shot"]}</td><td>{strip(r["settings_a"])}</td><td>{strip(r["settings_b"])}</td>'
            f'<td class="num">{float(r["mean_jod_a"]):.2f}</td><td class="num">{float(r["mean_jod_b"]):.2f}</td>'
            f'<td class="num">{float(r["median_model_gap"]):.2f}</td>'
            f'<td class="num">{float(r["max_model_gap"]):.2f}</td><td>{html.escape(r["max_gap_rule"])}</td>'
            f'<td class="num">{r["gmad_task_count"]}</td><td>{badge(r["perceptibility"], t)}</td></tr>')
    counts = ' · '.join(f'{t["labels"][k]} {v}' for k, v in summary['perceptibility'].items())
    lede = t['panel'].format(title=html.escape(title), pairs=summary['pairs'], videos=summary['videos'],
                             scenes=len(scenes), counts=counts)
    return f"""
<div class="panel" id="{panel_id}" {'hidden' if hidden else ''}>
  <p class="lede">{lede}</p>
  <div class="controls">
    <label for="{panel_id}-scene">{t['scene']} <select id="{panel_id}-scene" class="f-scene"><option value="">{t['all']}</option>{options}</select></label>
    <label for="{panel_id}-label">{t['label']} <select id="{panel_id}-label" class="f-label"><option value="">{t['all']}</option>{label_options}</select></label>
    <span class="count"></span>
  </div>
  {table(t['columns'], {3, 4, 5, 6, 8}, ''.join(body))}
</div>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gmad-dir', type=Path, required=True)
    parser.add_argument('--lang', choices=('zh', 'en'), default='zh')
    parser.add_argument('--output', type=Path, help='Default: <gmad-dir>/selection_versions[_en].html')
    args = parser.parse_args()
    root = args.gmad_dir
    t = TEXT[args.lang]
    out = args.output or root / ('selection_versions.html' if args.lang == 'zh' else 'selection_versions_en.html')
    summary = json.loads((root / 'summary.json').read_text())
    config = json.loads((root / 'config.json').read_text())
    ranking = read_csv(root / 'scene_ranking.csv')
    a_rows = read_csv(root / 'selection_all_scenes' / 'pairs.csv')
    b_rows = read_csv(root / 'selection_subset_scenes' / 'pairs.csv')
    a_sum = json.loads((root / 'selection_all_scenes' / 'summary.json').read_text())
    b_sum = json.loads((root / 'selection_subset_scenes' / 'summary.json').read_text())
    subset = set(b_sum['scenes'])
    negatives = {}
    for row in read_csv(root / 'negative_frames.csv'):
        shot = Path(row['source_csv']).parent.parent
        key = f'{shot.parent.name}/{shot.name}'
        negatives[key] = negatives.get(key, 0) + 1
    widest = max(float(r['median_max_model_gap']) for r in ranking)
    rank_rows = ''.join(
        f'<tr class="{"chosen" if r["scene"] in subset else ""}"><td class="num">{r["rank"]}</td><td>{r["scene"]}</td>'
        f'<td class="num">{r["shots"]}</td><td class="num">{int(r["gmad_pairs"]):,}</td>'
        f'<td><span class="bar"><i style="width:{float(r["median_max_model_gap"]) / widest * 120:.1f}px"></i>'
        f'<b>{float(r["median_max_model_gap"]):.2f}</b></span></td>'
        f'<td class="num">{float(r["share_likely_perceptible"]) * 100:.1f}%</td>'
        f'<td class="num">{float(r["share_likely_imperceptible"]) * 100:.1f}%</td>'
        f'<td>{t["in_version"] if r["scene"] in subset else ""}</td></tr>' for r in ranking)
    shots = len(config['candidates_per_scene'])
    gmad_pairs = f"{summary['gmad_unique_pairs']:,}"
    negative_text = t['joiner'].join(t['negative'].format(shot=s, n=n) for s, n in sorted(negatives.items()))
    figures = [shots, f"{summary['candidates']:,}", gmad_pairs, f"{summary['all_selected_videos']:,}",
               a_sum['pairs'], b_sum['pairs']]
    figure_html = ''.join(f'<div class="figure"><b>{value}</b><span>{text.format(scenes=len(ranking))}</span></div>'
                          for value, text in zip(figures, t['figures']))
    badges = [badge(k, t) for k in ('likely_imperceptible', 'possibly_imperceptible', 'likely_perceptible')]
    label_list = ''.join(f'<li>{b} {text}</li>' for b, text in zip(badges, t['label_items']))
    version_list = ''.join(f'<li>{item}</li>' for item in t['version_items'])
    file_list = ''.join(f'<li>{item.format(gmad_pairs=gmad_pairs)}</li>' for item in t['file_items'])
    tabs = (f'<div class="tabs" role="tablist">'
            f'<button type="button" role="tab" aria-selected="true" data-panel="version-a">{t["tabs"][0]}</button>'
            f'<button type="button" role="tab" aria-selected="false" data-panel="version-b">{t["tabs"][1]}</button></div>')
    panels = (pair_panel('version-a', t['version_a'], a_sum, a_rows, False, t)
              + pair_panel('version-b', t['version_b'].format(scenes=t['joiner'].join(b_sum['scenes'])), b_sum, b_rows, True, t))
    style = STYLE.replace('__DISPLAY__', t['display']).replace('__BODY__', t['body'])
    script = SCRIPT.replace('__SHOWN__', t['shown'])
    page = f"""<title>{t['title']}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{t['fonts']}&display=swap">
<style>{style}</style>
<main class="page">
  <header style="display:grid;gap:12px">
    <span class="eyebrow">{t['eyebrow']}</span>
    <h1>{t['h1']}</h1>
    <p class="lede">{t['lede'].format(shots=shots)}</p>
  </header>
  <section aria-label="{t['figures_label']}"><div class="figures">{figure_html}</div></section>
  <section>
    <h2>{t['method']}</h2>
    <div class="notes">
      <div class="note"><h3>gMAD</h3><p>{t['gmad_note'].format(rules=len(config['rules']), bins=config['bins'])}</p></div>
      <div class="note"><h3>{t['label_title']}</h3><p>{t['label_intro']}</p><ul>{label_list}</ul><p>{t['label_outro']}</p></div>
      <div class="note"><h3>{t['versions_title']}</h3><ul>{version_list}</ul></div>
    </div>
  </section>
  <section>
    <h2>{t['ranking']}</h2>
    <p class="lede">{t['ranking_lede']}</p>
    {table(t['rank_columns'], {0, 2, 3, 5, 6}, rank_rows)}
    <div class="caveat"><b>{t['caveat_title']}</b>
      <p>{t['caveat'].format(negatives=summary['negative_input_samples'], negative_text=html.escape(negative_text))}</p></div>
  </section>
  <section>
    <h2>{t['pairs']}</h2>
    <div class="legend"><span>{t['legend'][0]}</span>
      <span class="strip"><span class="f30">30 fps</span><span class="f60">60 fps</span><span class="f120">120 fps</span></span>
      <span>{t['legend'][1]}</span></div>
    {tabs}
    {panels}
  </section>
  <section>
    <h2>{t['files']}</h2>
    <p class="lede">{t['files_lede'].format(folder=root.name)}</p>
    <ul class="files">{file_list}</ul>
  </section>
</main>
<script>{script}</script>
"""
    out.write_text(page, encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
