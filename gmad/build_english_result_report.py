"""Translate the existing skip-negative, no-offset gMAD report without rerunning selection."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_result_report import ROOT, escape, read_csv, table


def quantile(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    low = int(position)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)


def render(directory: Path) -> None:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    assert config["negative_frame_policy"] == "skip"
    assert config["common_input_offset"] == 0 and config["time_policy"] == "converted"

    pilot = read_csv(directory / "pilot_pairs.csv")
    negative = read_csv(directory / "negative_frames.csv")
    predictions = read_csv(directory / "predictions.csv")
    status = summary["task_status"]
    bistro_mean = sorted(float(row["mean"]) for row in predictions if row["candidate_id"].startswith("bistro__"))
    p5, p95 = quantile(bistro_mean, .05), quantile(bistro_mean, .95)
    span = p95 - p5
    epsilon = min(config["epsilon_cap"], config["epsilon_fraction"] * span)

    roles = {
        "gmad_pilot": "gMAD: covers additional attack tasks",
        "random_fixed": "Random: both videos have fixed settings",
        "random_varying": "Random: at least one video changes settings",
        "diagnostic_reversal": "Diagnostic: reversed order of changes",
        "diagnostic_stable_vs_varying": "Diagnostic: fixed vs. changing settings, with similar mean scores",
    }
    pilot_rows = [
        [row["scene"], row["pair_id"], row["settings_a"], row["settings_b"],
         "; ".join(roles[role] for role in row["roles"].split(";") if role),
         row["gmad_task_count"]]
        for row in pilot
    ]
    role_counts = Counter(role for row in pilot for role in row["roles"].split(";") if role)
    assert len(pilot) == summary["pilot_unique_pairs"] == 84
    assert role_counts == {
        "gmad_pilot": 60, "random_fixed": 6, "random_varying": 6,
        "diagnostic_reversal": 6, "diagnostic_stable_vs_varying": 6,
    }

    negative_rows = []
    for row in negative:
        path = Path(row["source_csv"])
        scene = next(item for item in summary["scenes"] if item in path.parts)
        chunk = int(path.name.split("_")[0].removeprefix("chunk"))
        setting = path.name.split("_")[1]
        frame = int(row["frame_index"])
        full_time = (chunk - 1) * 1.5 + frame / config["fps"]
        negative_rows.append([scene, chunk, setting, frame, f"{full_time:.3f}", f"{float(row['score']):.3f}"])
    negative_rows.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    negative_files = len({row["source_csv"] for row in negative})
    affected = sum(int(count) for length, count in summary["candidate_frame_count_distribution"].items() if int(length) < 540)
    assert len(negative_rows) == summary["negative_input_samples"] == 18
    assert affected == summary["candidates_with_skipped_frames"]

    equivalence = defaultdict(list)
    for rule, representative in config["representative"].items():
        equivalence[representative].append(rule)
    equiv_rows = []
    for members in equivalence.values():
        if len(members) > 1:
            reason = (
                "The 50th percentile is the median."
                if "median" in members else
                "With these 4.5-second videos and current parameters, each rule gives every candidate the same overall mean score."
            )
            equiv_rows.append([" = ".join(members), reason])
    assert len(equiv_rows) == 2

    weight_rows = [
        ["early_dominance", "1", "0", "0", "Only the first chunk counts"],
        ["late_dominance", "0", "0", "1", "Only the last chunk counts"],
        ["increasing_weights", "1/6", "2/6", "3/6", "Later chunks matter more"],
        ["decreasing_weights", "3/6", "2/6", "1/6", "Earlier chunks matter more"],
    ]

    chinese_report = (directory / "report.html").read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", chinese_report, re.DOTALL)
    if match is None:
        raise ValueError("The Chinese report has no embedded stylesheet")
    css = match.group(1)
    time = config["time_parameters"]
    player_locations = [
        "../../../VQA2-dataset/pilot_videos_bicubic_120fps/bistro/play_pairs.html",
        "pilot_videos_bicubic_120fps/bistro/play_pairs.html",
    ]
    player = next((path for path in player_locations if (directory / path).is_file()), None)
    playback_link = (
        f"<p><a href='{player}'>Play the 14 bistro pilot pairs locally</a></p>"
        if player else ""
    )

    markup = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>gMAD Pair Selection · Skip Negative JOD Frames</title><style>{css}</style></head><body><main>
    <header class='hero'><div class='eyebrow'>Subjective video quality study · video selection guide</div><h1>gMAD Screening Results</h1><p>Original 25 fps durations converted to 120 Hz · negative frame scores skipped · no positive offset. There are 6 scenes and 216 three-chunk settings per scene; each chunk lasts 1.5 seconds. All numbers and linked CSV files come from this same result set.</p><p><a href='report.html'>中文版 / Chinese version</a> · <a href='../legacy/gmad_selection/report.html'>Comparison run retaining negative scores with a positive offset (Chinese report)</a>. The two runs handle negative frame scores differently, so their selected-pair counts differ.</p></header>
    <nav aria-label='Page navigation'><a href='#tasks'>Attack tasks</a><a href='#rules'>Rules and time</a><a href='#negative'>Negative frames</a><a href='#threshold'>Defender tolerance</a><a href='#pilot'>Pilot pairs</a><a href='#files'>Result files</a></nav>
    <div class='stats'><div class='stat'><strong>{summary['candidates']:,}</strong><span>Candidate videos</span></div><div class='stat'><strong>{summary['attack_tasks']:,}</strong><span>Attack tasks</span></div><div class='stat'><strong>{status['selected']:,}</strong><span>Tasks with a selected pair</span></div><div class='stat'><strong>{summary['gmad_unique_pairs']:,}</strong><span>Distinct gMAD pairs</span></div><div class='stat'><strong>{summary['pilot_unique_pairs']}</strong><span>Pilot pairs</span></div></div>
    <section id='tasks'><h2>What counts as one attack task?</h2><p><b>How does gMAD work?</b> First, each pooling rule scores the candidate videos. The rules then take turns as “defender” and “attacker.” The attacker seeks two videos that the defender rates almost equally but the attacker rates very differently. People must compare the selected videos to determine which rule better matches perceived quality; that human evaluation has not yet been done.</p><p class="small">Method reference: K. Ma <i>et al.</i>, “Group maximum differentiation competition: Model comparison with few samples,” <i>IEEE Transactions on Pattern Analysis and Machine Intelligence</i>, vol. 42, no. 4, pp. 851–864, 2020, doi: <a href="https://doi.org/10.1109/TPAMI.2018.2889948">10.1109/TPAMI.2018.2889948</a>.</p><p>A task is specified by <strong>one scene, one defender rule, a different attacker rule, and one quality bin.</strong></p><p>For example: “In the middle-quality bin of <b>bistro</b>, let <code>median</code> defend and <code>mean</code> attack.” The program looks for two videos that <code>median</code> rates almost equally but <code>mean</code> rates as differently as possible. A task succeeds only if the pair meets the predefined defender and attacker gap criteria. A task with no valid pair still counts as an attempted task.</p><p class='formula'>6 scenes × 15 defender rules × 14 other attacker rules × 3 quality bins = {summary['attack_tasks']:,} tasks</p><p><b>Why is K=3 different from searching all videos once?</b> The three bins together do contain every candidate video. Without bins, however, each defender–attacker combination would select just the single pair with the largest disagreement, possibly concentrating selections in one score range. With K=3, the attacker searches separately within the defender's low-, middle-, and high-score bins and can obtain up to three pairs. Both videos in a pair must belong to the same bin, and the defender and attacker gap thresholds still apply. For example, if the largest attacker gaps in the three bins are 1.0, 0.8, and 0.3, a search without bins would select only the 1.0 pair; binning attempts to select one pair from each bin. K=3 makes every bin eligible for an attempt, but does not guarantee equal numbers of pilot pairs from each bin.</p><p><b>{status['selected']:,} tasks</b> yielded a pair. Different tasks can select the same two videos; after deduplication, there are <b>{summary['gmad_unique_pairs']:,} distinct pairs</b>.</p><p><code>insufficient_attack_gap: {status['insufficient_attack_gap']}</code> means a pair was close enough under the defender, but the largest available score difference under the attacker fell below the required threshold. Those {status['insufficient_attack_gap']} tasks had no valid attack; this does not establish that the defender wins. Rules with identical predictions cannot attack each other effectively either.</p></section>
    <section id='rules'><h2>Why do some rules give identical scores?</h2><p>The comparison uses 15 pooling rules in the code. Under the current parameters and video duration, some differently named rules produce the same result for every candidate:</p>{table(['Equivalent rules', 'Why'], equiv_rows)}<h3>How long are the time windows?</h3><p>The original study's 25 fps durations are converted to 120 Hz: 100 frames, or 4 seconds, becomes <strong>{time['worst_window_frames']} frames</strong>; 125 frames, or 5 seconds, becomes <strong>{time['last_frames']} frames</strong>.</p><p><code>worst_window</code> slides a 4-second window across the entire 4.5-second video. <code>exp_weighted_minkowski</code> uses a 4-second weighting decay scale. The 5-second <code>last_frames_mean</code> window covers the whole video, so it equals <code>mean</code>. <code>hysteresis</code> explicitly uses 120 Hz and a 2-second memory.</p><h3>Four position-weighting rules</h3><p>Split each 4.5-second video into three 1.5-second chunks, average the scores within each chunk, and combine the three means using these weights.</p>{table(['Rule', 'First', 'Middle', 'Last', 'In plain language'], weight_rows)}</section>
    <section id='negative'><h2>How many frame scores were negative?</h2><p>The 108 chunk files contain 19,440 frame scores. Of these, <strong>{len(negative_rows)} scores are below zero</strong>, spread across <strong>{negative_files} files</strong>. The table lists <a href='negative_frames.csv'>every negative record in the CSV</a>. Frame indices start at zero; “position in full video” is where that frame would fall after assembling the 4.5-second video.</p>{table(['Scene', 'Chunk', 'Setting', 'Frame index in chunk', 'Position in full video (s)', 'Score'], negative_rows)}<p class='small'>These are per-frame proxy scores exported from CVVDP video-mode features. This run excludes the {len(negative_rows)} negative records from the pooling inputs. It neither replaces them with zero nor adds a positive offset. The lowest retained raw score is {summary['min_raw_score']:.3f}. As a result, {affected} candidate score sequences have fewer than 540 frames, although the videos themselves remain 4.5 seconds long. These are screening scores based on shortened sequences; the assembled videos still need full-video verification before use.</p></section>
    <section id='threshold'><h2>How close must the defender's scores be?</h2><p>For each scene and defender rule, take its scores for the 216 candidate videos. The 95th percentile minus the 5th percentile is the width of the usual score range, excluding the extremes. The maximum permitted difference between the two videos is the smaller of 5% of that width and 0.10.</p><p class='formula'>Defender score difference ≤ min(0.10, 5% × [defender p95 − p5])</p><p>Actual example: for <code>mean</code> on <b>bistro</b>, p5 is about <b>{p5:.2f}</b> and p95 about <b>{p95:.2f}</b>. The usual range is about {p95:.2f} − {p5:.2f} = <b>{span:.2f}</b> points; 5% of it is about <b>{epsilon:.3f}</b> points. Thus, when <code>mean</code> defends, a pair's scores may differ by at most about {epsilon:.3f} points. This is a selection threshold, not evidence from human judgments that viewers cannot tell the videos apart.</p></section>
    <section id='pilot'><h2>How were the 84 pilot pairs chosen?</h2><p>Each scene contributes <b>10 gMAD pairs + 2 random pairs + 2 diagnostic pairs</b>, giving <b>84 pairs</b> across 6 scenes. A pair linked to several attack tasks is shown only once.</p><ol><li><b>60 gMAD pairs:</b> Choose 10 per scene from the full list of distinct gMAD pairs. Prefer pairs that cover more different defender–attacker–quality-bin combinations; break ties by the larger attacker score gap. This is not a random sample of 60 pairs.</li><li><b>12 random pairs:</b> Two per scene. Sample one from pairs where both videos keep fixed settings throughout, and one from pairs where at least one video changes settings. These pairs need not satisfy the gMAD gap criteria.</li><li><b>12 diagnostic pairs:</b> Two per scene. One compares reversed orders of quality changes. The other compares fixed settings against changing settings, with similar <code>mean</code> scores. The reversal pair does not have to have similar <code>mean</code> scores.</li></ol><p><b>What does “cover a task” mean?</b> If an attack task selected a video pair and that pair enters the pilot, the task is covered. For example, suppose a chosen pair already covers tasks 1 and 2. A candidate linked only to tasks 1 and 2 adds little, while a candidate that also covers task 3 is preferred. The selection counts newly covered defender–attacker–quality-bin combinations, rather than simply how often a pair appears. Each pair is shown only once.</p><p>Each video lasts 4.5 seconds, so one A/B viewing takes 9 seconds. Allowing roughly 20 seconds per pair for viewing and response gives about <b>28 minutes of trials</b> for 84 pairs. Add practice, replays, and breaks when planning the full session. Randomize A/B presentation order. No human ratings are available yet, so these results do not rank the pooling rules by perceptual accuracy.</p><h3>Pilot pair list</h3>{playback_link}<p class='small'>A and B are only list labels here; their playback order must be randomized for participants.</p><label for='pair-search'>Search by scene, setting, or Pair ID:</label> <input id='pair-search' type='search' placeholder='e.g. bistro, 720p30, pair_'><div id='pilot-table'>{table(['Scene', 'Pair ID', 'Video A: three settings', 'Video B: three settings', 'Purpose', 'Linked gMAD tasks'], pilot_rows, 'pilot-table')}</div></section>
    <section id='files'><h2>What is the difference between the two pair lists?</h2><p><b>All distinct gMAD pairs:</b> Every pair selected by a successful attack task, with duplicate video combinations removed; this run has {summary['gmad_unique_pairs']:,} pairs. <b>Pilot pair list:</b> The 84 pairs for a small-scale study: 60 from the full gMAD list, plus 12 random and 12 diagnostic pairs.</p><div class='links'><a href='pilot_pairs.csv'>Pilot pairs CSV</a><a href='gmad_pairs.csv'>All distinct gMAD pairs CSV</a><a href='attack_tasks.csv'>All tasks and selected pairs</a><a href='negative_frames.csv'>Negative frames CSV</a><a href='predictions.csv'>Candidate predictions</a><a href='sensitivity.csv'>Sensitivity check</a><a href='config.json'>Parameters and source hashes</a><a href='pilot_video_recipes.json'>Pilot assembly recipes</a></div><p class='caution' style='margin-top:17px'>This is a first screening based on concatenated chunk-level score sequences. Before using the selected items, assemble the chunks into actual 4.5-second videos and verify CVVDP scores at the transitions using the full videos. Also check that chunk content is continuous in the rogue scene.</p></section>
    </main><script>document.getElementById('pair-search').addEventListener('input',e=>{{const value=e.target.value.trim().toLowerCase();document.querySelectorAll('.pilot-table tbody tr').forEach(row=>{{row.hidden=!row.textContent.toLowerCase().includes(value)}})}});</script></body></html>"""
    output = directory / "report_en.html"
    output.write_text(markup, encoding="utf-8", newline="\n")
    print(f"Updated {output}")


if __name__ == "__main__":
    render(ROOT / "gmad_selection_skip_negative_no_offset_time_converted")
