#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${1:-$REPO_ROOT/tmp/metrics}"

mkdir -p "$OUTPUT_DIR"

for root_rel in assets/result src/traj_logs traj_logs; do
  root="$REPO_ROOT/$root_rel"
  [ -d "$root" ] || continue

  find "$root" -mindepth 1 -maxdepth 1 -type d | sort | while read -r d; do
    name="$(basename "$d")"

    python "$REPO_ROOT/scripts/calc_paper_metrics.py" "$d" \
      > "$OUTPUT_DIR/${name}_paper.txt"

    python "$REPO_ROOT/scripts/calc_split_difficulty_metrics.py" "$d" --source task_dirs \
      > "$OUTPUT_DIR/${name}_split.txt"

    if find "$d" -mindepth 1 -maxdepth 1 -type d -name '*@*' -print -quit | grep -q .; then
      python "$REPO_ROOT/scripts/calc_persona_pref_routine_merged_avg.py" "$d" \
        > "$OUTPUT_DIR/${name}_merged_avg.txt"
    fi
  done
done
