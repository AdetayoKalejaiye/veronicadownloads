#!/usr/bin/env bash
# Runs one workflow step with its output kept off this public repository's logs.
#
#   shell: bash --noprofile --norc ../downloads/scripts/release/quiet.sh {0}   (from a step whose working-directory is app)
#   (add "powershell" after {0} for a PowerShell step; no quotes: macOS runners split the shell line on spaces)
#
# The step's output goes to a file on the runner, which is discarded with it. Deliberate ::warning:: and
# ::notice:: lines are passed through. If the step fails, only that fact is logged. With SHOW_LOGS=true
# (the workflow's show_logs input) the step runs normally and everything is shown.
script="$1"
kind="${2:-bash}"
if [ "$kind" = "powershell" ]; then
  # GitHub's own PowerShell shell stops on the first error; do the same.
  { echo "\$ErrorActionPreference = 'Stop'"; cat "$script"; } > "$script.ps1"
  run=(powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$script.ps1")
else
  run=(bash --noprofile --norc -eo pipefail "$script")
fi
if [ "${SHOW_LOGS:-false}" = "true" ]; then
  exec "${run[@]}"
fi
log="${RUNNER_TEMP:-/tmp}/step-$$-$RANDOM.log"
"${run[@]}" > "$log" 2>&1
code=$?
grep -E '^::(warning|notice)::' "$log" || true
if [ "$code" -ne 0 ]; then
  echo "::error::This step failed (exit $code). Its output is hidden because this repository's logs are public. Run the workflow again with show_logs ticked to see it."
fi
exit "$code"
