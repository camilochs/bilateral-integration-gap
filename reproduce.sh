#!/usr/bin/env bash
# Reproduce every number in the paper from the frozen run — NO models, NO network, NO API keys.
# One command. Requires only Python 3 (standard library). The bootstrap is seeded (seed=7),
# so confidence intervals reproduce exactly, byte for byte.
set -euo pipefail
cd "$(dirname "$0")"

cp results/_merged_results.json _merged_results.json     # analyze/qualitative write beside themselves

echo "==> 1/3  Qualitative failure-shape classification (transparent heuristics, no LLM judge)"
python3 qualitative.py _merged_results.json >/dev/null

echo "==> 2/3  Machine-readable number file the manuscript is filled from"
python3 analyze.py _merged_results.json --emit-numbers >/dev/null

echo "==> 3/3  Full per-RQ tables and cluster-bootstrap intervals"
python3 analyze.py _merged_results.json

echo
if diff -q _paper_numbers.json results/_paper_numbers.json >/dev/null; then
  echo "OK  Regenerated numbers are byte-identical to the shipped results/_paper_numbers.json."
  echo "    Every value in the paper is reproduced from the frozen run alone."
else
  echo "WARN  Regenerated numbers differ from shipped — investigate before trusting."
  diff _paper_numbers.json results/_paper_numbers.json | head
fi
