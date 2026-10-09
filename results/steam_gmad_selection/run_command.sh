#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")/../.."
/opt/anaconda3/bin/python -u gmad/run_selection.py \
  --input ../VQA2-dataset/steam-cvvdp-results \
  --output results/steam_gmad_selection \
  --time-policy converted \
  --skip-negative \
  --input-offset 0 \
  > results/steam_gmad_selection/run.log 2>&1
