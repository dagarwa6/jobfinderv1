#!/bin/bash
# Double-clickable job-scraper runner.
#
# Double-click this file in Finder (or run it from Terminal) to start a full
# pipeline run. It launches the load-safe launcher in the background, tails the
# progress live, and opens the dashboard in Chrome when the run finishes.
#
# First-time setup (once): in Finder, right-click this file -> Open, and
# confirm the "unidentified developer" prompt. After that, double-click works.

cd "$(dirname "$0")/.." || exit 1
PROJECT="$(pwd)"
LOG="logs/wait_and_run.log"

echo "============================================="
echo "  Job Scraper — starting a run"
echo "  $(date)"
echo "============================================="
echo

# Kick off the load-safe launcher in the background (survives this window).
: > "$LOG"
nohup scripts/wait_and_run.sh > "$LOG" 2>&1 &
disown

echo "Launcher started. Watching progress below."
echo "(You can close this window any time — the run keeps going.)"
echo "When it finishes, the dashboard opens in Chrome automatically."
echo
echo "---------------------------------------------"

# Tail until we see the pipeline exit line, then open the dashboard.
# Also surface scraper milestones as they happen.
( tail -f "$LOG" logs/scraper.log 2>/dev/null & TAIL_PID=$!
  while true; do
    if grep -q "=== pipeline exited" "$LOG" 2>/dev/null; then
      kill $TAIL_PID 2>/dev/null
      break
    fi
    sleep 5
  done
) | grep --line-buffered -E "launcher|ready|waiting|Scraping|Progress:|Done:|Passed filters|AI evaluating|AI evaluation complete|Dashboard:|pipeline exited|Generated [0-9]+ tailored"

echo
echo "---------------------------------------------"
echo "Run complete. Opening dashboard..."
open -a "Google Chrome" "$PROJECT/output/latest.html" 2>/dev/null || open "$PROJECT/output/latest.html"
echo "Done. You can close this window."
