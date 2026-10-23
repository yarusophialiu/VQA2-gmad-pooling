"""Write an HTML table of the DSIS training videos, in presentation order.

Reads results/dsis_training/training_recipes.json (used by run_dsis_training.m)
and writes results/dsis_training/training_videos.html, styled like
combined_jod_report.html.
"""
import json
import re
from pathlib import Path

from build_combined_jod_report import BINS, LEVELS, LONG, PAGE, ROOT, esc

TRAINING = ROOT / 'results' / 'dsis_training'
STYLE = re.search(r'<style>.*?</style>', PAGE, re.S).group(0)


def shown_range(level):
    """What participants see: one level below the CVVDP level up to it (expectedRange in MATLAB)."""
    if level <= 1:
        return f'{level} {LEVELS[level]}'
    return f'{level - 1}–{level} {LEVELS[level - 1]} to {LEVELS[level]}'


def main():
    # Entries can be switched off with // line comments, which MATLAB's jsondecode accepts.
    text = (TRAINING / 'training_recipes.json').read_text()
    recipes = json.loads('\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('//')))
    rows = []
    for number, r in enumerate(recipes, 1):
        level = r['expected_level']
        scene, shot = r['scene'].split('__', 1)
        source = 'Experiment video' if r.get('also_in_experiment') else 'Training only'
        rows.append(
            f'<tr><td class="num">{number}</td><td>{esc(scene)}</td><td>{esc(shot)}</td>'
            f'<td>{esc(r["chunk1"])}</td><td>{esc(r["chunk2"])}</td><td>{esc(r["chunk3"])}</td>'
            f'<td class="num">{r["expected_jod"]:.3f}</td>'
            f'<td>{level} {LEVELS[level]}</td>'
            f'<td><span class="chip" style="background:var(--level-{level})"></span>{shown_range(level)}</td>'
            f'<td>{source}</td></tr>')
    bins = ''.join(f'<tr><td><span class="chip" style="background:var(--level-{lv})"></span>{lv}</td>'
                   f'<td>{LEVELS[lv]} – {LONG[lv]}</td><td>{BINS[lv]}</td></tr>' for lv in (5, 4, 3, 2, 1))
    reused = sum(bool(r.get('also_in_experiment')) for r in recipes)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DSIS Training Videos</title>
{STYLE}
</head>
<body>
<main>
<h1>DSIS training videos</h1>
<p class="lede">The {len(recipes)} practice videos played by <code>run_dsis_training.m</code>, in presentation
order. Each is compared with its shot's 1080p120 reference, as in the experiment. The CVVDP level is the
video's 4.5&nbsp;s CVVDP JOD mapped to the DSIS scale. Participants are shown a range from one level below
it up to it (level&nbsp;1 stays 1), after rating and top-left during the test video when
<code>SHOW_EXPECTED_LEVEL</code> is on.</p>

<div class="card" style="padding:0; overflow-x:auto">
<table>
<thead><tr><th class="num">#</th><th>Scene</th><th>Shot</th><th>Chunk 1</th><th>Chunk 2</th><th>Chunk 3</th>
<th class="num">CVVDP JOD</th><th>CVVDP level</th><th>Shown to participants</th><th>Source</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>

<h2>Notes</h2>
<ul>
<li>School reaches only levels 3–5: even its most impaired versions score about JOD&nbsp;8.3, so levels 1–2
are shown with sibenik.</li>
<li>{reused} of the {len(recipes)} videos are also experiment videos; participants will rate them again
in the experiment. The others are not part of the experiment.</li>
<li>Within each scene the videos go from most to least impaired.</li>
</ul>

<h2>JOD to DSIS level</h2>
<div class="card">
<table class="bins">
<thead><tr><th>Level</th><th>DSIS label</th><th>JOD</th></tr></thead>
<tbody>{bins}</tbody>
</table>
</div>
</main>
</body>
</html>
"""
    destination = TRAINING / 'training_videos.html'
    destination.write_text(page, encoding='utf-8')
    print(f'Wrote {destination}')


if __name__ == '__main__':
    main()
