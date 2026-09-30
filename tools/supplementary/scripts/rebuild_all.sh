#!/usr/bin/env bash
# Rebuild every table, confidence interval, paired test, Holm correction and
# figure from the per-case results and per-request data — no simulation.
#
#   scripts/rebuild_all.sh [output dir, default: rebuilt]
#
# Uses $PYTHON (default: python) with the analysis code in code/ on the path;
# run it from an environment created with `uv sync --frozen --project code`
# (see README.md), e.g.  PYTHON="uv run --project code python" scripts/rebuild_all.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-rebuilt}"
case "$OUT" in /*) ;; *) OUT="$ROOT/$OUT" ;; esac
PYTHON="${PYTHON:-python}"

ABLATION="$ROOT/data/ablation_run/20260926T223707Z_seeds1-2-3-4+6_ablation"
PILOT="$ROOT/data/pilot_run/20260928T191459Z_seeds1-2-3_congestion_pilot"

rm -rf "$OUT"
mkdir -p "$OUT"
cd "$ROOT/code"
export PYTHONPATH="$ROOT/code${PYTHONPATH:+:$PYTHONPATH}"
export MPLBACKEND=Agg

echo "[1/3] Main campaign: indicators, means and 95% CIs, paired tests, Holm, figures"
$PYTHON -m src.pipeline.reanalysis "$ABLATION" "$OUT/ablation_modified" > /dev/null

echo "[2/3] Congestion pilot: same indicators, capacity effect, components, figures"
$PYTHON -m src.pipeline.congestion "$PILOT" "$ABLATION" "$OUT/congestion_pilot" > /dev/null

echo "[3/3] Comparison with the shipped outputs"
if [ -d "$ROOT/outputs" ]; then
    $PYTHON "$ROOT/scripts/compare_outputs.py" "$ROOT/outputs" "$OUT"
else
    echo "no outputs/ directory to compare with: skipped"
fi
