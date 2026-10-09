"""Build an English report from the saved Steam gMAD selection results."""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "results"
ROLES = {
    "gmad_pilot": "gMAD pilot",
    "random_fixed": "Random: both videos have fixed settings",
    "random_varying": "Random: at least one video changes settings",
    "diagnostic_reversal": "Diagnostic: reversed setting order",
    "diagnostic_stable_vs_varying": "Diagnostic: fixed vs. varying settings",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers, rows, *, element_id=""):
    head = "".join(f"<th scope='col'>{html.escape(str(x))}</th>" for x in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in row) + "</tr>"
        for row in rows
    )
    return (f"<div class='table-wrap'><table id='{element_id}'><thead><tr>{head}</tr>"
            f"</thead><tbody>{body}</tbody></table></div>")


def render(directory):
    summary = json.loads((directory / "summary.json").read_text())
    config = json.loads((directory / "config.json").read_text())
    validation = json.loads((directory / "validation.json").read_text())
    pilot = read_csv(directory / "pilot_pairs.csv")
    audit = read_csv(directory / "input_audit.csv")
    sensitivity = read_csv(directory / "sensitivity.csv")
    recipes = json.loads((directory / "pilot_video_recipes.json").read_text())
    role_counts = Counter(role for row in pilot for role in row["roles"].split(";"))
    pilot_ids = {row[key] for row in pilot for key in ("video_a", "video_b")}
    assert len(pilot) == summary["pilot_unique_pairs"]
    assert len(pilot_ids) == summary["pilot_unique_videos"] == len(recipes)
    assert {row["candidate_id"] for row in recipes} == pilot_ids
    assert len(audit) == len(config["source_files"])

    group_counts = Counter(row["scene"] for row in pilot)
    group_roles = defaultdict(Counter)
    for row in pilot:
        group_roles[row["scene"]].update(row["roles"].split(";"))
    group_rows = [[group.replace("__", "/"), group_counts[group],
                   group_roles[group]["gmad_pilot"],
                   group_roles[group]["random_fixed"] + group_roles[group]["random_varying"],
                   group_roles[group]["diagnostic_reversal"] + group_roles[group]["diagnostic_stable_vs_varying"]]
                  for group in summary["scenes"]]
    pilot_rows = [[row["scene"].replace("__", "/"), row["pair_id"],
                   row["settings_a"], row["settings_b"],
                   "; ".join(ROLES[role] for role in row["roles"].split(";")),
                   row["gmad_task_count"]] for row in pilot]
    equivalents = defaultdict(list)
    for rule, representative in config["representative"].items():
        equivalents[representative].append(rule)
    equivalent_rows = [[" = ".join(members)] for members in equivalents.values() if len(members) > 1]
    status_rows = [[status.replace("_", " ").capitalize(), f"{count:,}"]
                   for status, count in summary["task_status"].items()]
    sensitivity_rows = [[row["kind"].replace("_", " "), row["value"],
                         f"{int(row['selected_tasks']):,}", f"{int(row['unique_pairs']):,}",
                         f"{float(row['pair_jaccard']):.3f}"] for row in sensitivity]
    stats = [
        (len(summary["scenes"]), "Original video clips"),
        (summary["candidates"], "Candidate combinations"),
        (summary["gmad_unique_pairs"], "Distinct gMAD pairs"),
        (summary["pilot_unique_pairs"], "Pilot pairs"),
        (summary["pilot_unique_videos"], "Distinct pilot videos"),
    ]
    cards = "".join(f"<div class='stat'><strong>{value:,}</strong><span>{label}</span></div>"
                    for value, label in stats)
    random_count = role_counts["random_fixed"] + role_counts["random_varying"]
    diagnostic_count = role_counts["diagnostic_reversal"] + role_counts["diagnostic_stable_vs_varying"]
    time = config["time_parameters"]
    time_rows = [
        ["Exponential weighted Minkowski: decay scale", time["exp_tau_frames"], time["exp_tau_s"]],
        ["Worst window: moving average", time["worst_window_frames"], time["worst_window_s"]],
        ["Last frames: tail window", time["last_frames"], time["last_seconds"]],
        ["Hysteresis: memory and forward window", round(time["hysteresis_tau_s"] * config["fps"]), time["hysteresis_tau_s"]],
    ]
    policy = ("Negative scores are excluded before pooling."
              if config["negative_frame_policy"] == "skip" else "Negative scores are retained.")
    markup = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Steam gMAD Video Selection</title><style>
*{{box-sizing:border-box}}body{{font:16px/1.65 system-ui,sans-serif;background:#f3f6f8;color:#173447;margin:0}}
main{{max-width:1250px;margin:30px auto;padding:28px;background:white;border-radius:16px}}
h1,h2{{color:#096c70}}h1{{margin-bottom:8px}}h2{{margin-top:32px}}a{{color:#096c70}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:24px 0}}
.stat{{background:#e9f5f3;padding:18px;border-radius:10px}}.stat strong{{display:block;font-size:28px}}
.stat span{{display:block}}.note{{background:#fff0d6;padding:16px;border-radius:8px}}
.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border-bottom:1px solid #ccdce2;padding:9px;text-align:left;vertical-align:top}}th{{background:#e9f5f3}}
#pilot-table{{min-width:1000px}}input{{padding:10px;width:360px;max-width:100%;margin-bottom:12px}}
code{{font-size:.9em;overflow-wrap:anywhere}}nav{{display:flex;gap:16px;flex-wrap:wrap}}
.small{{font-size:14px;color:#486373}}@media(max-width:650px){{main{{margin:0;padding:20px;border-radius:0}}}}
</style></head><body><main>
<h1>Steam gMAD Video Selection</h1>
<p>Screening results from <code>VQA2-dataset/steam-cvvdp-results</code>, using {len(config['rules'])} temporal pooling rules. Each original clip forms an independent content group; videos from different original clips are never paired.</p>
<p><a href="report.html">Chinese report</a> · <a href="pilot_pairs.csv">Pilot pairs CSV</a> · <a href="pilot_video_recipes.json">Pilot video assembly recipes</a></p>
<nav aria-label="Report navigation"><a href="#method">Selection method</a><a href="#pooling">Pooling rules</a><a href="#pilot">Pilot design</a><a href="#pairs">Pair list</a><a href="#files">Result files</a></nav>
<div class="stats">{cards}</div>
<h2 id="method">Inputs and selection method</h2>
<p>The input contains {len(audit):,} chunk-score files: {len(summary['scenes'])} original clips × 3 chunks × 6 settings. Each setting combines one of two resolutions (720p or 1080p) with one of three frame rates (30, 60 or 120 fps). Each chunk lasts 1.5 seconds and has {config['frames_per_chunk']} proxy scores on a common {config['fps']} Hz timeline. Combining all three chunks gives 6³ = 216 candidate settings per original clip and {summary['candidates']:,} candidates in total.</p>
<p>gMAD alternates pooling rules as defender and attacker. Within each original clip, it searches for two candidates that the defender rates nearly equally but the attacker rates as differently as possible. The defender's predictions define {config['bins']} quantile bins. Both videos must fall in the same bin; equal predictions are kept together.</p>
<ul><li>Defender gap ≤ min({config['epsilon_cap']:g}, {config['epsilon_fraction']*100:g}% × defender p95−p5 span).</li>
<li>Attacker gap ≥ {config['min_attack_fraction']*100:g}% × attacker p95−p5 span.</li>
<li>Among feasible pairs in each bin, select the pair with the largest attacker gap.</li></ul>
<p>There are {len(summary['scenes'])} content groups × {len(config['rules'])} defenders × {len(config['rules'])-1} other attackers × {config['bins']} bins = {summary['attack_tasks']:,} attack tasks. {summary['task_status'].get('selected',0):,} tasks selected a valid pair, yielding {summary['gmad_unique_pairs']:,} distinct gMAD pairs after deduplication. A task without a valid pair does not establish that the defender wins.</p>
{table(['Task outcome', 'Count'], status_rows)}
<h2 id="pooling">Pooling rules and score treatment</h2>
<p>The {len(config['rules'])} rules produce {summary['effective_rules']} distinct prediction groups on these candidates. The following rules have equivalent predictions for this run:</p>
{table(['Equivalent predictions'], equivalent_rows)}
<p>The 50th percentile is the median. The 5-second tail window covers each entire 4.5-second sequence; the duration-corrected cumulative-quality calculation also reduces to the overall mean at this duration.</p>
<p>Time policy: <code>{html.escape(config['time_policy'])}</code>. The original {time['source_study_fps']} fps study durations are converted to {time['display_fps']} Hz while preserving their duration in seconds.</p>
{table(['Parameter', 'Frames at 120 Hz', 'Seconds'], time_rows)}
<p>The four position-weighting rules use the three chunks: early dominance [1, 0, 0], late dominance [0, 0, 1], increasing weights [1/6, 2/6, 3/6], and decreasing weights [3/6, 2/6, 1/6].</p>
<p>{policy} This dataset contains {summary['negative_input_samples']} negative input scores, so {summary['candidates_with_skipped_frames']} candidate sequences are affected. The input offset is {config['common_input_offset']:g}; retained scores range from {summary['min_raw_score']:.3f} to {summary['max_raw_score']:.3f}. Every candidate has 540 scores, corresponding to 4.5 seconds.</p>
<h2 id="pilot">Pilot selection</h2>
<p>The pilot contains <strong>{summary['pilot_unique_pairs']} pairs involving {summary['pilot_unique_videos']} distinct videos</strong>: {role_counts['gmad_pilot']} gMAD pairs, {random_count} random pairs and {diagnostic_count} diagnostic pairs. Each original clip contributes 10 gMAD pairs, 2 random pairs and 2 diagnostic pairs.</p>
<ul><li>gMAD pairs are chosen greedily to cover additional effective defender–attacker–bin combinations, with normalized attacker gap used to break coverage ties.</li>
<li>Random pairs include one pair of fixed-setting videos and one pair where at least one video changes settings. They need not meet the gMAD gap criteria.</li>
<li>Diagnostic pairs compare reversed setting orders, or fixed against varying settings with similar mean scores.</li></ul>
<p>The pilot is a subset for an initial study. The full gMAD list contains all distinct pairs selected by successful attack tasks. Video A and Video B are list labels; participant presentation order should be randomized.</p>
{table(['Original clip', 'Pilot pairs', 'gMAD', 'Random', 'Diagnostic'], group_rows)}
<h2 id="pairs">Pilot pair list</h2>
<label for="pair-search">Search by original clip, settings, purpose or pair ID</label><br>
<input id="pair-search" type="search" placeholder="e.g. input01_1, 720p30, gMAD">
<p class="small"><span id="visible-count">{len(pilot)}</span> of {len(pilot)} pairs shown. The settings in each video column follow chunk order 1 → 2 → 3.</p>
{table(['Original clip', 'Pair ID', 'Video A settings', 'Video B settings', 'Purpose', 'Linked gMAD tasks'], pilot_rows, element_id='pilot-table')}
<h2>Verification and sensitivity</h2>
<p>Saved validation status: <strong>{html.escape(validation['status'])}</strong>. Input CSV and metadata hashes were verified. All {validation['selected_tasks_checked']:,} selected tasks were independently checked for the same content group, the same defender quality bin, the required score gaps and the maximum feasible attacker gap. Pilot recipes cover all {summary['pilot_unique_videos']} pilot video IDs.</p>
{table(['Sensitivity parameter', 'Value', 'Selected tasks', 'Distinct pairs', 'Pair-set Jaccard vs. primary run'], sensitivity_rows)}
<p class="note">These results are a first screening from concatenated chunk-score sequences. Assemble the selected chunks into actual 4.5-second videos and recompute full-video CVVDP before finalizing experimental stimuli, particularly around chunk transitions. Human evaluation has not yet been performed; this report does not establish a perceptual ranking of pooling rules.</p>
<h2 id="files">Result files</h2>
<ul><li><a href="pilot_pairs.csv">Pilot pairs</a> · <a href="gmad_pairs.csv">All distinct gMAD pairs</a></li>
<li><a href="pilot_video_recipes.json">Pilot assembly recipes</a> · <a href="selected_video_recipes.json">All selected assembly recipes</a></li>
<li><a href="predictions.csv">Candidate predictions</a> · <a href="attack_tasks.csv">Attack tasks</a> · <a href="compact_attack_tasks.csv">Compact task design</a></li>
<li><a href="config.json">Parameters and input hashes</a> · <a href="summary.json">Summary</a> · <a href="validation.json">Validation</a> · <a href="sensitivity.csv">Sensitivity results</a></li>
<li><a href="run_command.sh">Selection command</a> · <a href="run.log">Selection log</a></li></ul>
</main><script>
document.getElementById('pair-search').addEventListener('input', event => {{
  const query = event.target.value.trim().toLowerCase();
  let visible = 0;
  document.querySelectorAll('#pilot-table tbody tr').forEach(row => {{
    row.hidden = !row.textContent.toLowerCase().includes(query);
    if (!row.hidden) visible++;
  }});
  document.getElementById('visible-count').textContent = visible;
}});
</script></body></html>
"""
    output = directory / "report_en.html"
    output.write_text(markup, encoding="utf-8")
    print(f"Created {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=ROOT / "steam_gmad_selection")
    render(parser.parse_args().directory)
