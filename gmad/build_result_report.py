"""Build readable HTML from existing gMAD result files; does not run selection."""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results"
VERSIONS = ("legacy/gmad_selection_120hz_defaults", "legacy/gmad_selection")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def table(headers: list[str], rows: list[list[object]], css: str = "") -> str:
    head = "".join(f"<th scope='col'>{escape(name)}</th>" for name in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<div class='table-wrap'><table class='{css}'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def render(directory: Path) -> None:
    summary = json.loads((directory / "summary.json").read_text())
    config = json.loads((directory / "config.json").read_text())
    pilot = read_csv(directory / "pilot_pairs.csv")
    negative = read_csv(directory / "negative_frames.csv")
    predictions = read_csv(directory / "predictions.csv")
    is_original = config["time_policy"] != "converted"
    skip_negative = config.get("negative_frame_policy") == "skip"
    if skip_negative:
        assert not is_original and config["common_input_offset"] == 0
        other = "legacy/gmad_selection"
        other_title = "保留负分、使用正值偏移的同参数版本"
        version_title = "按 25 fps 原时间换算 · 跳过负分帧 · 不加偏移 · 120 Hz 初筛"
        version_difference = "两版对负分帧的处理不同，选对数字也不同。"
    else:
        other = "gmad_selection" if is_original else "gmad_selection_120hz_defaults"
        other_title = "按 25 fps 原时间换算的版本" if is_original else "原代码 100/125 帧的版本"
        version_title = "原代码 100/125 帧 · 120 Hz 初筛" if is_original else "按 25 fps 原时间换算 · 120 Hz 初筛"
        version_difference = "两版的窗口时长和选对数字不同。"
    status = summary["task_status"]

    bistro_mean = sorted(float(row["mean"]) for row in predictions if row["candidate_id"].startswith("bistro__"))
    def quantile(values: list[float], fraction: float) -> float:
        position = (len(values) - 1) * fraction
        low = int(position)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)
    p5, p95 = quantile(bistro_mean, .05), quantile(bistro_mean, .95)
    span = p95 - p5
    epsilon = min(config["epsilon_cap"], config["epsilon_fraction"] * span)

    roles = {
        "gmad_pilot": "gMAD：覆盖更多不同攻击任务",
        "random_fixed": "随机：两个视频都全程固定",
        "random_varying": "随机：至少一个视频中途变化",
        "diagnostic_reversal": "诊断：前后变化顺序颠倒",
        "diagnostic_stable_vs_varying": "诊断：稳定与变化，mean 分数接近",
    }
    pilot_rows = [
        [row["scene"], row["pair_id"], row["settings_a"], row["settings_b"],
         "；".join(roles.get(role, role) for role in row["roles"].split(";") if role),
         row["gmad_task_count"]]
        for row in pilot
    ]
    role_counts = Counter(role for row in pilot for role in row["roles"].split(";") if role)
    assert len(pilot) == 84 and role_counts["gmad_pilot"] == 60
    assert role_counts["random_fixed"] == role_counts["random_varying"] == 6
    assert role_counts["diagnostic_reversal"] == role_counts["diagnostic_stable_vs_varying"] == 6

    negative_rows = []
    for row in negative:
        path = Path(row["source_csv"])
        parts = path.parts
        scene = next(item for item in summary["scenes"] if item in parts)
        chunk = int(path.name.split("_")[0].removeprefix("chunk"))
        setting = path.name.split("_")[1]
        frame = int(row["frame_index"])
        full_time = (chunk - 1) * 1.5 + frame / 120
        negative_rows.append([scene, chunk, setting, frame, f"{full_time:.3f}", f"{float(row['score']):.3f}"])
    assert len(negative_rows) == 18
    negative_rows.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    negative_files = len(set(row["source_csv"] for row in negative))
    if skip_negative:
        lengths = summary["candidate_frame_count_distribution"]
        affected = sum(int(count) for length, count in lengths.items() if int(length) < 540)
        negative_note = (
            f"这些是 CVVDP 视频模式特征导出的逐帧代理分数。本版计算时删除这 {len(negative_rows)} 个负分记录，"
            f"未把它们改为 0，也未加正值偏移；剩余原始分数的最低值为 {summary['min_raw_score']:.3f}。"
            f"有 {affected} 个候选视频的分数序列因此少于 540 帧，实际视频仍长 4.5 秒。"
            "这是按删除帧分数计算的初筛，正式播放前仍需用拼好的完整视频复核。"
        )
    else:
        negative_note = (
            "这些是 CVVDP 视频模式特征导出的逐帧代理分数；负值没有被改为 0。"
            f"本轮为了让需要正输入的规则可计算，统一加 {config['common_input_offset']:.9f}，"
            "汇总后减回同一偏移。非线性规则可能受该偏移影响，详见敏感性检查。"
        )

    equivalence = defaultdict(list)
    for rule, representative in config["representative"].items():
        equivalence[representative].append(rule)
    equivalent_groups = [members for members in equivalence.values() if len(members) > 1]
    assert len(equivalent_groups) == 2
    equiv_rows = []
    for members in equivalent_groups:
        names = " = ".join(members)
        reason = (
            "第 50 百分位就是中位数。"
            if "median" in members else
            "在这批 4.5 秒视频和当前参数下，它们对每个候选给出相同的整段平均分。"
        )
        equiv_rows.append([names, reason])

    time = config["time_parameters"]
    if is_original:
        time_text = f"""
        <p>本版保留原代码的帧数参数，全部分数统一在每秒 120 帧的时间轴上。因此 <code>100 帧 ÷ 120 ≈ 0.83 秒</code>，<code>125 帧 ÷ 120 ≈ 1.04 秒</code>。</p>
        <ul>
          <li><code>worst_window</code>：在完整 4.5 秒里移动一个 <strong>100 帧（约 0.83 秒）</strong>的窗口，找平均分最低的连续一段。它会扫描整段视频，不是只看开头 0.83 秒。</li>
          <li><code>exp_weighted_minkowski</code>：100 帧是越往前权重衰减的时间尺度，约 0.83 秒；它也会使用整段视频的分数。</li>
          <li><code>last_frames_mean</code>：只平均最后 125 帧，约 1.04 秒。</li>
          <li><code>hysteresis</code>：明确指定 120 Hz 和 2 秒，所以它的 2 秒记忆约对应 240 帧。</li>
        </ul>
        <p class='caution'>这是“沿用原代码帧数”的版本。如果要保持原研究在 25 fps 下的物理时长，100 帧应改成 480 帧；那是另一个版本，选对数字不同。</p>"""
    else:
        time_text = f"""
        <p>本版把原研究 25 fps 的时间长度换算到 120 Hz：100 帧所代表的 4 秒变为 <strong>{time['worst_window_frames']} 帧</strong>；125 帧所代表的 5 秒变为 <strong>{time['last_frames']} 帧</strong>。</p>
        <p><code>worst_window</code> 在完整 4.5 秒中移动 4 秒窗口；<code>exp_weighted_minkowski</code> 的衰减尺度是 4 秒；<code>last_frames_mean</code> 的 5 秒覆盖了整段，因此与 <code>mean</code> 相同。<code>hysteresis</code> 仍明确使用 120 Hz 和 2 秒。</p>"""

    weight_rows = [
        ["early_dominance", "1", "0", "0", "只看前段"],
        ["late_dominance", "0", "0", "1", "只看后段"],
        ["increasing_weights", "1/6", "2/6", "3/6", "越往后越重要"],
        ["decreasing_weights", "3/6", "2/6", "1/6", "越往前越重要"],
    ]
    version_link = f"../{other}/report.html"
    css = """
    :root{--ink:#1a3545;--muted:#526a76;--teal:#0a777a;--wash:#e8f5f3;--line:#d4e2e8;--amber:#fff3dc}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f7f8;color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif}
    a{color:#07686c;text-underline-offset:2px}main{max-width:1180px;margin:auto;padding:24px 18px 64px}.hero{background:linear-gradient(120deg,#17394a,#0a7071);border-radius:18px;padding:30px 36px;color:white}.hero p{max-width:820px}.hero a{color:white}h1{font-size:2.05rem;line-height:1.2;margin:8px 0 14px}h2{font-size:1.35rem;margin:0 0 14px}h3{font-size:1.04rem;margin:18px 0 8px}p{margin:0 0 14px}.eyebrow{font-size:.8rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#c9e8e5}
    nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}nav a{background:white;border:1px solid var(--line);border-radius:999px;padding:6px 12px;text-decoration:none}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:18px 0}.stat{background:white;border:1px solid var(--line);border-radius:12px;padding:13px}.stat strong{display:block;color:var(--teal);font-size:1.55rem;line-height:1.2}.stat span{font-size:.83rem;color:var(--muted)}section{background:white;border:1px solid var(--line);border-radius:15px;padding:25px 29px;margin:18px 0}code{background:#edf3f6;padding:1px 5px;border-radius:4px;font-size:.92em}.formula{font-weight:700;background:var(--wash);border-radius:9px;padding:12px 15px;margin:15px 0}.caution{background:var(--amber);border-left:4px solid #d08a1c;padding:12px 15px;border-radius:0 8px 8px 0}.table-wrap{overflow:auto;margin:15px 0}table{border-collapse:collapse;min-width:660px;width:100%;font-size:.9rem}th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}th{background:#eef7f5;position:sticky;top:0}tr:nth-child(even) td{background:#fafcfc}ul,ol{margin:8px 0 15px;padding-left:1.4em}li{margin:5px 0}.small{font-size:.86rem;color:var(--muted)}.links{display:flex;flex-wrap:wrap;gap:9px}.links a{border:1px solid var(--line);border-radius:8px;padding:5px 9px;text-decoration:none}input{border:1px solid #a9c5cd;border-radius:8px;padding:10px;width:360px;max-width:100%;font:inherit}
    @media(max-width:760px){.hero{padding:24px}.stats{grid-template-columns:repeat(2,1fr)}section{padding:20px 16px}}@media print{body{background:white}main{max-width:none;padding:0}.hero{background:white;color:var(--ink);padding:0}.hero a{color:var(--teal)}nav,input{display:none}section{border:0;border-top:1px solid var(--line);break-inside:avoid}.stat{break-inside:avoid}}
    """

    markup = f"""<!doctype html><html lang='zh'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>gMAD 选对结果 · {escape(version_title)}</title><style>{css}</style></head><body><main>
    <header class='hero'><div class='eyebrow'>主观视频质量实验 · 选片说明</div><h1>gMAD 初筛结果</h1><p>{escape(version_title)}。6 个场景，每个场景 216 种三段设置；每段 1.5 秒。所有数字和下方 CSV 均来自同一版结果。</p><p>另有<a href='{escape(version_link)}'>{escape(other_title)}</a>；{escape(version_difference)}</p></header>
    <nav aria-label='页面导航'><a href='#tasks'>攻击任务</a><a href='#rules'>规则与时间</a><a href='#negative'>负分帧</a><a href='#threshold'>分差门槛</a><a href='#pilot'>预实验清单</a><a href='#files'>结果文件</a></nav>
    <div class='stats'><div class='stat'><strong>{summary['candidates']:,}</strong><span>候选视频</span></div><div class='stat'><strong>{summary['attack_tasks']:,}</strong><span>攻击任务</span></div><div class='stat'><strong>{status['selected']:,}</strong><span>成功选对的任务</span></div><div class='stat'><strong>{summary['gmad_unique_pairs']:,}</strong><span>去重 gMAD 视频对</span></div><div class='stat'><strong>{summary['pilot_unique_pairs']}</strong><span>预实验视频对</span></div></div>
    <section id='tasks'><h2>什么是一个攻击任务？</h2><p><b>gMAD 怎么工作？</b>先让每条池化规则给候选视频打分，再轮流指定一条规则当“防守者”、另一条当“攻击者”。攻击者寻找这样的两段视频：防守者认为画质几乎一样，攻击者却认为差很多。把选出的两段视频交给人比较，才能判断哪条规则更符合人的感受；目前这一步还没做。</p><p class="small">方法来源：K. Ma <i>et al.</i>, “Group maximum differentiation competition: Model comparison with few samples,” <i>IEEE Transactions on Pattern Analysis and Machine Intelligence</i>, vol. 42, no. 4, pp. 851–864, 2020, doi: <a href="https://doi.org/10.1109/TPAMI.2018.2889948">10.1109/TPAMI.2018.2889948</a>.</p><p>一个任务由四件事定下来：<strong>一个场景、一个防守规则、一个不同的攻击规则、一个质量档。</strong></p><p>例如：“在 <b>bistro</b> 场景的<b>中等质量档</b>，让 <code>median</code> 防守、<code>mean</code> 攻击。”程序要找一对视频：<code>median</code> 觉得它们质量很接近，<code>mean</code> 觉得差别尽可能大。两边的分差都满足预设条件，任务才算成功选对；找不到也仍是一个已尝试的任务。</p><p class='formula'>6 个场景 × 15 个防守规则 × 14 个不同的攻击规则 × 3 个质量档 = {summary['attack_tasks']:,} 个任务</p><p><b>为什么 K=3 不等于在全部视频里找一次？</b>三个档合起来确实包含全部候选视频；但不分档时，每个“防守者—攻击者”组合只会从全部视频中挑分歧最大的一对，结果可能集中在某个分数范围。设 K=3 后，要在防守者预测的低、中、高分档各找一对，最多得到三对；一对中的两个视频必须在同一档，而且仍要满足防守分差和攻击分差门槛。例如三档可找到的最大攻击分差分别是 1.0、0.8、0.3，不分档只会挑 1.0 那对；分档后会分别尝试挑三对。K=3 保证每档都尝试，但不保证最后的预实验清单每档数量相等。</p><p>其中 <b>{status['selected']:,} 个</b>成功选出了视频对。不同任务可能选中同一对，所以合并重复后是 <b>{summary['gmad_unique_pairs']:,} 对</b>，不是 {status['selected']:,} 对不同视频。</p><p><code>insufficient_attack_gap: {status['insufficient_attack_gap']}</code> 的意思是：虽然找到了防守者觉得接近的候选对，但攻击者对它们的最大分差仍达不到门槛，因此这 {status['insufficient_attack_gap']} 个任务没有有效攻击；这不能算防守者胜利。预测完全相同的规则之间也无法构造有效攻击。</p></section>
    <section id='rules'><h2>规则为什么会重复？</h2><p>这里比较的是代码中的 15 条规则。有些名称不同，但在当前参数和视频时长下对每个候选给出的结果一样：</p>{table(['等价的规则','原因'],equiv_rows)}<h3>窗口到底看多久？</h3>{time_text}<h3>四种位置权重</h3><p>先把 4.5 秒视频分为前、中、后三个 1.5 秒的 chunk，各算平均分，然后按下表合成总分。</p>{table(['规则','前段','中段','后段','大白话'],weight_rows)}</section>
    <section id='negative'><h2>有多少帧得了负分？</h2><p>108 个 chunk 文件共有 19,440 个逐帧分数；其中 <strong>{len(negative_rows)} 帧小于 0</strong>，分布在 <strong>{negative_files} 个文件</strong>。下表列出 <a href='negative_frames.csv'>CSV 中的全部负分记录</a>；帧号从 0 开始，“整段时间”是拼成 4.5 秒视频后的位置。</p>{table(['场景','第几段','设置','段内帧号','整段时间（秒）','分数'],negative_rows)}<p class='small'>{escape(negative_note)}</p></section>
    <section id='threshold'><h2>“防守分差很小”具体有多小？</h2><p>对每个场景、每条防守规则，先看它给该场景 216 个候选视频的分数。第 95 百分位减去第 5 百分位，代表去掉两端极值后的常见分数宽度。允许的两段视频分差，取这段宽度的 5% 和 0.10 中较小的一个。</p><p class='formula'>防守分差 ≤ min(0.10, 5% ×〔防守者 p95 − p5〕)</p><p>真实例子：<code>mean</code> 给 <b>bistro</b> 场景打分时，p5 约为 <b>{p5:.2f}</b>，p95 约为 <b>{p95:.2f}</b>。常见分数宽度约为 {p95:.2f} − {p5:.2f} = <b>{span:.2f}</b> 分；它的 5% 约为 <b>{epsilon:.3f}</b> 分。因此 <code>mean</code> 当防守者时，一对视频的分差最多允许约 {epsilon:.3f} 分。这个门槛只是选片用的，尚未通过人评证明“看不出差别”。</p></section>
    <section id='pilot'><h2>84 对预实验视频从哪里来？</h2><p>每个场景选 <b>10 对 gMAD + 2 对随机 + 2 对诊断</b>；6 个场景共 <b>84 对</b>。即使一对视频服务于多个攻击任务，也只播放一次。</p><ol><li><b>60 对 gMAD：</b>从“全部 gMAD 唯一对”中，每个场景选 10 对。优先覆盖更多不同的“防守规则—攻击规则—质量档”组合，覆盖一样时再选攻击分差较大的；不是随机抽 60 对。</li><li><b>12 对随机：</b>每场景 2 对。第一对从“两段视频都全程固定”的组合中随机抽；第二对从“至少一段中途变化”的组合中随机抽。这些对不要求满足 gMAD 分差门槛。</li><li><b>12 对诊断：</b>每场景 2 对。一对比较前后变化顺序颠倒；另一对比较全程稳定与中途变化，并要求两段的 <code>mean</code> 分数接近。顺序颠倒的一对不要求 <code>mean</code> 接近。</li></ol><p><b>“覆盖任务”是什么意思？</b>如果某个攻击任务挑中了这对视频，而它进入了预实验，就算这个任务被覆盖。比如已选的甲对覆盖任务 1、2；候选乙对也只覆盖任务 1、2，几乎没有新增内容；候选丙对还能覆盖任务 3，就更优先选丙。这里看的是新覆盖了多少种“防守规则—攻击规则—质量档”组合，不是只看这对视频出现了多少次。同一对视频只播放一次。</p><p>两段视频各 4.5 秒，A/B 共 9 秒；暂按每对 20 秒（含选择和评分）估算，84 对约 <b>28 分钟纯试次</b>。正式时长还要加练习、重播和休息。播放时随机决定 A/B 顺序。目前没有人评数据，也就没有模型胜负排名。</p><h3>预实验对清单</h3><p class='small'>A/B 在下表只作清单编号；真正呈现给被试时仍须随机顺序。</p><label for='pair-search'>按场景、设置或 Pair ID 搜索：</label> <input id='pair-search' type='search' placeholder='例如 bistro、720p30、pair_'><div id='pilot-table'>{table(['场景','Pair ID','视频 A 三段设置','视频 B 三段设置','用途','关联 gMAD 任务数'],pilot_rows,'pilot-table')}</div></section>
    <section id='files'><h2>两个清单有什么区别？</h2><p><b>全部 gMAD 唯一对：</b>所有成功攻击任务挑中的视频对，重复组合只留一次；这版共有 {summary['gmad_unique_pairs']:,} 对。<b>预实验对清单：</b>供小规模测试的 84 对，其中 60 对来自完整 gMAD 清单，另加 12 对随机、12 对诊断。</p><div class='links'><a href='pilot_pairs.csv'>预实验对清单 CSV</a><a href='gmad_pairs.csv'>全部 gMAD 唯一对 CSV</a><a href='attack_tasks.csv'>全部任务与选对映射</a><a href='negative_frames.csv'>负分帧 CSV</a><a href='predictions.csv'>候选视频预测</a><a href='sensitivity.csv'>敏感性检查</a><a href='config.json'>参数和来源哈希</a><a href='pilot_video_recipes.json'>预实验拼接配方</a></div><p class='caution' style='margin-top:17px'>这些是逐段分数拼接后的初筛结果。正式使用前，需要把入选 chunk 真正拼成 4.5 秒视频，再用完整视频复核切换处的 CVVDP 分数；rogue 场景还要核对片段内容是否连续。</p></section>
    </main><script>document.getElementById('pair-search').addEventListener('input',e=>{{const value=e.target.value.trim().toLowerCase();document.querySelectorAll('.pilot-table tbody tr').forEach(row=>{{row.hidden=!row.textContent.toLowerCase().includes(value)}})}});</script></body></html>"""
    (directory / "report.html").write_text(markup, encoding="utf-8")
    print(f"Updated {directory / 'report.html'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", help="Result directory under results/; if omitted, render the two archived baseline reports")
    args = parser.parse_args()
    if args.directory:
        directory = ROOT / args.directory
        if not directory.resolve().is_relative_to(ROOT.resolve()) or not directory.is_dir():
            parser.error("directory must name an existing directory under results/")
        render(directory)
    else:
        for version in VERSIONS:
            render(ROOT / version)
