#!/usr/bin/env bash
set -euo pipefail

REMOTE="iridium:/local/scratch-2/yl962/VQA2/results/gmad_frame_scores/lossless_spatiotemporal_chunks/"
LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/results/legacy/gmad_frame_scores/lossless_spatiotemporal_chunks/"

mkdir -p "$LOCAL"
rsync -av --timeout=60 -e 'ssh -o BatchMode=yes -o ConnectTimeout=8' \
  --include='*/' \
  --include='*_frames.csv' \
  --include='*_native.csv' \
  --include='*.metadata.json' \
  --include='manifest.json' \
  --exclude='*' \
  "$REMOTE" "$LOCAL"

printf 'Downloaded frame scores to %s\n' "$LOCAL"
