"""Build one offline HTML dashboard from the completed no-offset gMAD CSVs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "legacy"
OUTPUT = ROOT / "gmad_skip_negative_no_offset.html"
VERSIONS = [
    ("original", "原代码 100/125 帧", "gmad_selection_skip_negative_no_offset_120hz_defaults"),
    ("converted", "按原研究时间换算", "../gmad_selection_skip_negative_no_offset_time_converted"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def main() -> None:
    data = {}
    for key, title, dirname in VERSIONS:
        directory = ROOT / dirname
        summary = json.loads((directory / "summary.json").read_text())
        config = json.loads((directory / "config.json").read_text())
        assert config["negative_frame_policy"] == "skip" and config["common_input_offset"] == 0
        pairs = read_csv(directory / "gmad_pairs.csv")
        pilot = read_csv(directory / "pilot_pairs.csv")
        assert len(pairs) == summary["gmad_unique_pairs"]
        assert len(pilot) == summary["pilot_unique_pairs"] == 84
        assert summary["min_raw_score"] > 0
        data[key] = {
            "title": title,
            "dirname": dirname,
            "summary": {k: summary[k] for k in (
                "candidates", "attack_tasks", "task_status", "gmad_unique_pairs",
                "pilot_unique_pairs", "pilot_unique_videos", "min_raw_score",
                "negative_input_samples", "skipped_candidate_frame_values",
                "candidates_with_skipped_frames", "candidate_frame_count_distribution")},
            "time": {k: config["time_parameters"][k] for k in (
                "exp_tau_frames", "worst_window_frames", "last_frames")},
            "gmad": pairs,
            "pilot": pilot,
        }

    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    page = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>gMAD 新选对 · 删除负分 · 不加偏移</title>
<style>
:root{--ink:#173347;--muted:#586f7c;--teal:#087e80;--dark:#113b4d;--line:#d5e3e8;--wash:#eef8f6;--warm:#fff3db}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f7f8;color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}button,input,select{font:inherit}a{color:#086b72;text-underline-offset:2px}.shell{max-width:1280px;padding:28px 20px 70px;margin:auto}.hero{background:linear-gradient(115deg,#163a50,#087e80);color:white;border-radius:20px;padding:35px 42px}.hero h1{font-size:clamp(1.85rem,4vw,2.6rem);line-height:1.2;margin:8px 0 16px}.hero p{max-width:910px;margin:0 0 12px;color:#e3f3f2}.eyebrow{font-size:.78rem;font-weight:750;letter-spacing:.1em;text-transform:uppercase;color:#c4e5e2}.layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:20px;margin-top:20px}nav{position:sticky;top:20px;align-self:start;background:white;border:1px solid var(--line);border-radius:15px;padding:14px}nav a{display:block;text-decoration:none;padding:7px 9px;border-radius:7px}nav a:hover{background:var(--wash)}main{min-width:0}section{background:white;border:1px solid var(--line);border-radius:16px;padding:25px 28px;margin-bottom:18px}h2{font-size:1.38rem;line-height:1.3;margin:0 0 14px}h3{font-size:1.03rem;margin:18px 0 7px}p{margin:0 0 13px}.small{font-size:.88rem;color:var(--muted)}.note{background:var(--warm);border-left:4px solid #cd8d23;padding:12px 15px;border-radius:0 9px 9px 0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin:15px 0}.stat{border:1px solid #cfe5e0;background:var(--wash);border-radius:11px;padding:14px}.stat strong{display:block;font-size:1.58rem;color:#07696e;line-height:1.2}.stat span{color:var(--muted);font-size:.84rem}.switch{display:flex;gap:8px;flex-wrap:wrap;margin:15px 0}.switch button{background:white;border:1px solid #b4ced2;border-radius:9px;padding:8px 13px;color:var(--ink);cursor:pointer}.switch button[aria-pressed="true"]{background:#086f72;color:white;border-color:#086f72}.controls{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:10px;margin:15px 0}.controls label{display:block;font-size:.84rem;color:var(--muted);font-weight:700}.controls input,.controls select{display:block;width:100%;border:1px solid #b5cdd3;border-radius:8px;padding:8px 10px;background:white;color:var(--ink)}.table-wrap{overflow:auto;max-height:660px;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;min-width:790px;font-size:.88rem}th,td{text-align:left;padding:10px 11px;vertical-align:top;border-bottom:1px solid var(--line)}th{position:sticky;top:0;background:#e9f5f3;z-index:1}tr:nth-child(even) td{background:#fafdfc}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.83rem;white-space:nowrap}.settings{white-space:nowrap}.pager{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:13px 0}.pager button{border:1px solid #b4ced2;background:white;border-radius:8px;padding:5px 11px;cursor:pointer}.pager button:disabled{opacity:.45;cursor:default}.links{display:flex;flex-wrap:wrap;gap:8px}.links a{border:1px solid var(--line);border-radius:8px;padding:6px 9px;text-decoration:none}.key{font-weight:700;color:#086d70}code{background:#edf4f6;border-radius:4px;padding:2px 5px}ul{margin:7px 0 14px;padding-left:1.3em}li{margin:5px 0}
@media(max-width:850px){.layout{display:block}nav{position:static;display:flex;flex-wrap:wrap;margin-bottom:18px}nav a{padding:4px 9px}.controls{grid-template-columns:1fr 1fr}.stats{grid-template-columns:1fr 1fr}}@media(max-width:560px){.shell{padding:12px}.hero{padding:26px 23px}.controls{grid-template-columns:1fr}section{padding:21px 16px}}@media print{body{background:white}.shell{max-width:none;padding:0}.hero{background:white;color:var(--ink);padding:0}.hero p{color:var(--muted)}.layout{display:block}nav,.controls,.pager,.switch{display:none}section{border:0;border-top:1px solid var(--line);break-inside:avoid}.table-wrap{max-height:none;overflow:visible}th{position:static}}
</style></head><body><div class="shell">
<header class="hero"><div class="eyebrow">主观视频质量实验 · gMAD 选片结果</div><h1>新选出的 gMAD 视频对</h1><p>本页面使用“删除所有负分帧、其余分数不变、正值偏移量为 0”的重算结果。可以切换两种时间参数版本，分别查看完整 gMAD 清单和预实验 84 对。</p><p>这里展示的是算法初筛；正式播放前还需拼接完整 4.5 秒视频并复核切换处的质量分数。</p></header>
<div class="layout"><nav aria-label="页面目录"><a href="#overview">结果概览</a><a href="#catalog">查看视频对</a><a href="#method">怎么选出来的</a><a href="#downloads">下载文件</a></nav><main>
<section id="overview"><h2>结果概览</h2><div class="switch" role="group" aria-label="时间参数版本"><button type="button" data-version="original" aria-pressed="true">原代码 100/125 帧</button><button type="button" data-version="converted" aria-pressed="false">按原研究时间换算</button></div><p id="version-description"></p><div class="stats"><div class="stat"><strong id="candidate-count"></strong><span>候选视频</span></div><div class="stat"><strong id="task-count"></strong><span>成功选对的任务</span></div><div class="stat"><strong id="gmad-count"></strong><span>全部 gMAD 唯一对</span></div><div class="stat"><strong id="pilot-count"></strong><span>预实验对</span></div></div><p id="input-detail"></p><p class="note">18 个原始 chunk 帧的 JOD 小于 0，已从计算输入中删除。它们在候选组合中重复出现，因此共有 216 个候选受到影响；最低保留分数是 0.144821167。没有做正值平移，也没有把负分改成 0。删帧后受影响的候选分数序列只有 536 或 539 帧，时间窗口会按缩短后的序列计算。</p></section>
<section id="catalog"><h2>查看视频对</h2><p><b>全部 gMAD 唯一对：</b>每个成功的攻击任务先挑一对视频，同样的两段视频只保留一条。<b>预实验对：</b>每个场景选 10 对 gMAD、2 对随机、2 对诊断，6 个场景共 84 对。</p><div class="switch" role="group" aria-label="清单类型"><button type="button" data-list="gmad" aria-pressed="true">全部 gMAD 唯一对</button><button type="button" data-list="pilot" aria-pressed="false">预实验 84 对</button></div><div class="controls"><label>搜索场景、Pair ID 或设置<input id="search" type="search" placeholder="例如 gallery、pair_、720p30"></label><label>场景<select id="scene"><option value="">全部场景</option><option>bistro</option><option>gallery</option><option>makeway</option><option>rogue</option><option>school</option><option>sibenik</option></select></label><label>每页<select id="page-size"><option value="25">25 对</option><option value="50" selected>50 对</option><option value="100">100 对</option></select></label></div><p id="list-status" aria-live="polite"></p><div class="table-wrap"><table><thead><tr><th>场景</th><th>Pair ID</th><th>视频 A（三段设置）</th><th>视频 B（三段设置）</th><th>关联 gMAD 任务数</th><th id="role-heading">预实验用途</th></tr></thead><tbody id="pair-rows"></tbody></table></div><div class="pager"><button id="previous" type="button">上一页</button><span id="page-label"></span><button id="next" type="button">下一页</button></div><p class="small">表里的 A/B 只用于标识两段视频；给被试播放时应随机安排先后顺序。点击下载链接可查看完整 CSV 和选中视频的拼接配方。</p></section>
<section id="method"><h2>怎么选出来的？</h2><p>一个 gMAD 攻击任务由“场景、防守规则、不同的攻击规则、质量档”四件事确定。程序在同场景、同质量档内找两段视频：防守规则觉得很接近，攻击规则觉得差别尽量大。多个任务可以挑中同一对视频，因此任务数大于去重后的视频对数。</p><p>预实验清单里的 <strong>60 对 gMAD</strong>不是随机抽的。每个场景依次挑 10 对，优先覆盖更多不同的“防守—攻击—质量档”任务，覆盖相同时优先选攻击分差较大的对。另有 <strong>12 对随机</strong>（每场景一对全程固定、一对至少含变化视频）和 <strong>12 对诊断</strong>（每场景一对前后顺序颠倒、一对平均分接近的稳定与变化视频）。</p><p>完整 gMAD 对清单用于查看所有有效攻击的选对结果；84 对预实验清单用于先测被试判断、试次耗时和视频切换。它们都不是主观实验的最终模型排名。</p></section>
<section id="downloads"><h2>下载与复核</h2><div class="links"><a id="gmad-csv" href="#">全部 gMAD 对 CSV</a><a id="pilot-csv" href="#">预实验 84 对 CSV</a><a id="task-csv" href="#">攻击任务映射 CSV</a><a id="pilot-recipes" href="#">预实验视频拼接配方</a><a id="full-recipes" href="#">全部选中视频配方</a><a href="gmad_skip_negative_no_offset_comparison.md">与之前结果的对比</a></div></section>
</main></div></div>
<script id="gmad-data" type="application/json">__EMBEDDED_DATA__</script>
<script>
(()=>{'use strict';
const all=JSON.parse(document.querySelector('#gmad-data').textContent);
const state={version:'original',list:'gmad',page:1};
const $=id=>document.getElementById(id);
const fmt=n=>Number(n).toLocaleString('zh-CN');
const roleText={gmad_pilot:'gMAD 预实验',random_fixed:'随机：两段全程固定',random_varying:'随机：至少一段中途变化',diagnostic_reversal:'诊断：变化顺序颠倒',diagnostic_stable_vs_varying:'诊断：稳定与变化，平均分接近'};
function cell(text,cls){const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;return td;}
function render(){
  const d=all[state.version],s=d.summary,t=d.time;
  document.querySelectorAll('[data-version]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.version===state.version)));
  document.querySelectorAll('[data-list]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.list===state.list)));
  $('version-description').textContent=state.version==='original'?`沿用代码里的 100 帧最差窗口、100 帧指数衰减和最后 125 帧；在 120 Hz 下分别约为 0.83 秒和 1.04 秒。`:`保留原研究的物理时间：100 帧从 25 fps 换算成 ${t.worst_window_frames} 帧（4 秒）；最后 125 帧换算成 ${t.last_frames} 帧（5 秒）。`;
  $('candidate-count').textContent=fmt(s.candidates);$('task-count').textContent=fmt(s.task_status.selected);$('gmad-count').textContent=fmt(s.gmad_unique_pairs);$('pilot-count').textContent=fmt(s.pilot_unique_pairs);
  $('input-detail').textContent=`6 个场景 × 每场景 216 个候选，共 ${fmt(s.attack_tasks)} 个攻击任务；其中 ${fmt(s.task_status.selected)} 个成功选出视频对。本版预实验共需 ${fmt(s.pilot_unique_videos)} 个不同视频。`;
  $('gmad-csv').href=d.dirname+'/gmad_pairs.csv';$('pilot-csv').href=d.dirname+'/pilot_pairs.csv';$('task-csv').href=d.dirname+'/attack_tasks.csv';$('pilot-recipes').href=d.dirname+'/pilot_video_recipes.json';$('full-recipes').href=d.dirname+'/selected_video_recipes.json';
  $('role-heading').textContent=state.list==='pilot'?'预实验用途':'是否进入预实验';
  const q=$('search').value.trim().toLowerCase(),scene=$('scene').value;
  const filtered=d[state.list].filter(p=>(!scene||p.scene===scene)&&(!q||[p.scene,p.pair_id,p.settings_a,p.settings_b,p.video_a,p.video_b].some(v=>v.toLowerCase().includes(q))));
  const pageSize=Number($('page-size').value),pages=Math.max(1,Math.ceil(filtered.length/pageSize));state.page=Math.min(state.page,pages);
  const from=(state.page-1)*pageSize,shown=filtered.slice(from,from+pageSize);const body=$('pair-rows');body.replaceChildren();const pilotIds=new Set(d.pilot.map(p=>p.pair_id));
  for(const p of shown){const tr=document.createElement('tr');tr.append(cell(p.scene),cell(p.pair_id,'mono'),cell(p.settings_a,'settings'),cell(p.settings_b,'settings'),cell(p.gmad_task_count),cell(state.list==='pilot'?(p.roles||'').split(';').map(v=>roleText[v]||v).join('；'):(pilotIds.has(p.pair_id)?'是':'否')));body.append(tr);}
  $('list-status').textContent=`筛选后 ${fmt(filtered.length)} 对；当前显示 ${filtered.length?from+1:0}–${Math.min(from+pageSize,filtered.length)} 对。`;
  $('page-label').textContent=`第 ${state.page} / ${pages} 页`;$('previous').disabled=state.page<=1;$('next').disabled=state.page>=pages;
}
document.querySelectorAll('[data-version]').forEach(b=>b.addEventListener('click',()=>{state.version=b.dataset.version;state.page=1;render()}));
document.querySelectorAll('[data-list]').forEach(b=>b.addEventListener('click',()=>{state.list=b.dataset.list;state.page=1;render()}));
for(const id of ['search','scene','page-size'])$(id).addEventListener(id==='search'?'input':'change',()=>{state.page=1;render()});
$('previous').addEventListener('click',()=>{state.page--;render()});$('next').addEventListener('click',()=>{state.page++;render()});render();
})();
</script></body></html>"""
    OUTPUT.write_text(page.replace("__EMBEDDED_DATA__", embedded), encoding="utf-8")
    print(f"Built {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
