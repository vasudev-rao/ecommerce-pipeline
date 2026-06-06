#!/usr/bin/env bash
set -euo pipefail
DATE=${1:-$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d)}
echo "Running pipeline for: $DATE"
python -m pipeline.batch_pipeline --date "$DATE"
