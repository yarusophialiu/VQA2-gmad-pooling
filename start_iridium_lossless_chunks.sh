#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_SCRIPTS="/local/scratch-2/yl962/VQA2/results/gmad_frame_scores/scripts"
REMOTE_RESULTS="/local/scratch-2/yl962/VQA2/results/gmad_frame_scores"

rsync -av "$SCRIPT_DIR/run_iridium_lossless_chunks.py" \
  "$SCRIPT_DIR/extract_gmad_frame_scores.py" \
  "iridium:$REMOTE_SCRIPTS/"

ssh -o BatchMode=yes -o ConnectTimeout=8 iridium \
  "cd '$REMOTE_SCRIPTS' && /home/yl962/miniconda3/envs/cvvdp/bin/python run_iridium_lossless_chunks.py --limit 1"

ssh -o BatchMode=yes -o ConnectTimeout=8 iridium \
  "cd '$REMOTE_SCRIPTS' && nohup /home/yl962/miniconda3/envs/cvvdp/bin/python run_iridium_lossless_chunks.py > '$REMOTE_RESULTS/lossless_spatiotemporal_chunks.log' 2>&1 < /dev/null &"

printf 'Started on iridium. Log: %s\n' "$REMOTE_RESULTS/lossless_spatiotemporal_chunks.log"
