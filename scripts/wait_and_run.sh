#!/bin/bash
# Load-safe pipeline launcher.
#
# This Mac runs hot — when system load is high (e.g. right after a reboot, or
# when other heavy apps are running), the scraper's startup imports (notably
# `anthropic`, which pulls in pydantic) can take 30s+ and the process stalls
# at 0% CPU, looking like a hang. The real cause is thread/CPU starvation, not
# a code bug.
#
# This script waits until the machine has headroom (proxied by: `import
# anthropic` completing in under 12s) and only THEN launches the full pipeline
# under caffeinate so it can't sleep mid-run. Use this instead of calling
# `python -m src.main` directly when load might be high.
#
# Usage:
#   nohup scripts/wait_and_run.sh > logs/wait_and_run.log 2>&1 & disown
#
set -euo pipefail
cd "$(dirname "$0")/.."

MAX_CHECKS=60          # give up after ~30 min of sustained high load
IMPORT_BUDGET=12       # seconds; anthropic must import faster than this

for i in $(seq 1 "$MAX_CHECKS"); do
  start=$(date +%s)
  ( .venv/bin/python -c "import anthropic" 2>/dev/null & p=$!; \
    ( sleep "$IMPORT_BUDGET"; kill -9 $p 2>/dev/null ) & w=$!; \
    wait $p 2>/dev/null; rc=$?; kill $w 2>/dev/null; exit $rc ) && rc=0 || rc=$?
  el=$(( $(date +%s) - start ))
  load=$(uptime | sed 's/.*averages: //')

  if [ "$rc" -eq 0 ] && [ "$el" -lt "$IMPORT_BUDGET" ]; then
    echo "[$(date +%H:%M:%S)] SETTLED (anthropic import ${el}s, load ${load}) — launching pipeline"
    rm -f .scraper.lock
    sqlite3 data/jobs.db "DELETE FROM job_evaluations;"
    set -a; source .env; set +a
    JOBSCRAPER_HEADLESS=1 caffeinate -i -m -s .venv/bin/python -m src.main
    echo "[$(date +%H:%M:%S)] pipeline exited rc=$?"
    exit 0
  fi
  echo "[$(date +%H:%M:%S)] not settled (anthropic ${el}s rc=${rc}, load ${load}) — wait 30s"
  sleep 30
done

echo "[$(date +%H:%M:%S)] gave up: load stayed high for ~30 min"
exit 1
