"""Compare completed skip-negative runs with their untouched baselines."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "legacy"
VERSIONS = [
    ("原代码 100/125 帧", "gmad_selection_120hz_defaults", "gmad_selection_skip_negative_120hz_defaults"),
    ("按 25 fps 时间换算", "gmad_selection", "gmad_selection_skip_negative_time_converted"),
]


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def compare(name, old_name, new_name):
    old, new = ROOT / old_name, ROOT / new_name
    old_summary = json.loads((old / "summary.json").read_text())
    new_summary = json.loads((new / "summary.json").read_text())
    old_pred = {r["candidate_id"]: r for r in rows(old / "predictions.csv")}
    new_pred = {r["candidate_id"]: r for r in rows(new / "predictions.csv")}
    assert old_pred.keys() == new_pred.keys()
    rules = [key for key in next(iter(old_pred.values())) if key != "candidate_id"]
    changed_candidates = []
    rule_deltas = {}
    for rule in rules:
        deltas = {cid: abs(float(row[rule]) - float(new_pred[cid][rule])) for cid, row in old_pred.items()}
        rule_deltas[rule] = {
            "changed_candidates": sum(delta > 1e-8 for delta in deltas.values()),
            "maximum_absolute_score_change": max(deltas.values()),
        }
    for cid, row in old_pred.items():
        if any(abs(float(row[rule]) - float(new_pred[cid][rule])) > 1e-8 for rule in rules):
            changed_candidates.append(cid)

    old_tasks = {r["task_id"]: r for r in rows(old / "attack_tasks.csv")}
    new_tasks = {r["task_id"]: r for r in rows(new / "attack_tasks.csv")}
    assert old_tasks.keys() == new_tasks.keys()
    changed_tasks = []
    for task_id, row in old_tasks.items():
        other = new_tasks[task_id]
        if row["status"] != other["status"] or row["pair_id"] != other["pair_id"]:
            changed_tasks.append({
                "task_id": task_id, "scene": row["scene"], "defender": row["defender"],
                "attacker": row["attacker"], "quality_bin": row["quality_bin"],
                "old_status": row["status"], "new_status": other["status"],
                "old_pair_id": row["pair_id"], "new_pair_id": other["pair_id"],
            })

    def pair_ids(directory, filename):
        return {r["pair_id"]: r for r in rows(directory / filename)}

    old_pairs, new_pairs = pair_ids(old, "gmad_pairs.csv"), pair_ids(new, "gmad_pairs.csv")
    old_pilot, new_pilot = pair_ids(old, "pilot_pairs.csv"), pair_ids(new, "pilot_pairs.csv")
    old_pair_ids, new_pair_ids = set(old_pairs), set(new_pairs)
    old_pilot_ids, new_pilot_ids = set(old_pilot), set(new_pilot)
    pilot_changes = []
    for label, ids, source in [
        ("removed", old_pilot_ids - new_pilot_ids, old_pilot),
        ("added", new_pilot_ids - old_pilot_ids, new_pilot),
    ]:
        for pair_id in sorted(ids):
            r = source[pair_id]
            pilot_changes.append({
                "change": label, "scene": r["scene"], "pair_id": pair_id,
                "video_a": r["video_a"], "video_b": r["video_b"], "roles": r["roles"],
            })

    def save_csv(path, data):
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)

    suffix = "original" if "100/125" in name else "converted"
    save_csv(ROOT / f"gmad_skip_negative_changed_tasks_{suffix}.csv", changed_tasks)
    save_csv(ROOT / f"gmad_skip_negative_pilot_changes_{suffix}.csv", pilot_changes)

    return {
        "version": name,
        "baseline_directory": str(old),
        "skip_negative_directory": str(new),
        "source_negative_frame_values": new_summary["negative_input_samples"],
        "skipped_candidate_frame_values": new_summary["skipped_candidate_frame_values"],
        "candidate_count_with_any_score_change": len(changed_candidates),
        "changed_candidate_scenes": dict(Counter(cid.split("__", 1)[0] for cid in changed_candidates)),
        "rule_score_changes": rule_deltas,
        "old_task_status": old_summary["task_status"],
        "new_task_status": new_summary["task_status"],
        "task_count_with_changed_status": sum(old_tasks[k]["status"] != new_tasks[k]["status"] for k in old_tasks),
        "task_count_with_changed_pair": sum(old_tasks[k]["pair_id"] != new_tasks[k]["pair_id"] for k in old_tasks),
        "old_unique_gmad_pairs": len(old_pairs),
        "new_unique_gmad_pairs": len(new_pairs),
        "unchanged_gmad_pairs": len(old_pair_ids & new_pair_ids),
        "removed_gmad_pairs": len(old_pair_ids - new_pair_ids),
        "added_gmad_pairs": len(new_pair_ids - old_pair_ids),
        "gmad_pair_jaccard": len(old_pair_ids & new_pair_ids) / len(old_pair_ids | new_pair_ids),
        "old_pilot_pairs": len(old_pilot),
        "new_pilot_pairs": len(new_pilot),
        "unchanged_pilot_pairs": len(old_pilot_ids & new_pilot_ids),
        "removed_pilot_pairs": len(old_pilot_ids - new_pilot_ids),
        "added_pilot_pairs": len(new_pilot_ids - old_pilot_ids),
        "pilot_changes_by_scene": dict(Counter(r["scene"] for r in pilot_changes if r["change"] == "removed")),
        "candidate_frame_count_distribution": new_summary["candidate_frame_count_distribution"],
    }


def main():
    results = [compare(*version) for version in VERSIONS]
    (ROOT / "gmad_skip_negative_comparison.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    text = ["# 跳过负分帧后，gMAD 选对变化", "",
            "本次只改逐帧输入：删除小于 0 的分数，其他分数原样保留；两版均沿用其原有的规则时间参数、分档和选对阈值。为了隔离删帧的影响，池化前的正值偏移量仍固定为 6.025888443。原结果目录未覆盖。", "",
            "108 个 chunk 文件中只有 18 个负分帧值，涉及 6 个文件。因为 chunk 被不同候选重复使用，组合后共有 216 个候选受到影响；其余 1,080 个候选的逐帧输入未变。", "",
            "| 时间参数 | 成功攻击任务：原→新 | 去重 gMAD 对：原→新 | 退出 / 新进入的 gMAD 对 | 84 对预实验清单替换 |", "|---|---:|---:|---:|---:|"]
    for r in results:
        text.append(f"| {r['version']} | {r['old_task_status']['selected']:,} → {r['new_task_status']['selected']:,} | {r['old_unique_gmad_pairs']:,} → {r['new_unique_gmad_pairs']:,} | {r['removed_gmad_pairs']} / {r['added_gmad_pairs']} | {r['removed_pilot_pairs']} 对 |")
    text.extend(["", "**结论：有区别。**旧 100/125 帧版的预实验 84 对中保留了 76 对，更换 8 对；按时间换算版保留 74 对，更换 10 对。所以下游实验应明确使用哪一种负分处理方式。", "",
                 "负帧主要集中于 gallery 第 3 段和 rogue 第 2 段。18 是原始 chunk 文件里的负值数；同一个 chunk 在候选视频中重复使用，所以实际从全部候选分数序列中删去了 648 个值。", "",
                 "**时间轴限制：**按字面跳过负帧后，受影响候选从 540 个分数变成 536 或 539 个。帧数窗口和位置权重会基于压短后的序列计算；这只是敏感性分析，不等同于对完整 4.5 秒播放画面的重新测量。", "",
                 "可复核的逐项文件：`gmad_skip_negative_changed_tasks_original.csv`、`gmad_skip_negative_changed_tasks_converted.csv`、`gmad_skip_negative_pilot_changes_original.csv`、`gmad_skip_negative_pilot_changes_converted.csv`。完整新结果分别在 `gmad_selection_skip_negative_120hz_defaults/` 与 `gmad_selection_skip_negative_time_converted/`。", ""])
    (ROOT / "gmad_skip_negative_comparison.md").write_text("\n".join(text))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
