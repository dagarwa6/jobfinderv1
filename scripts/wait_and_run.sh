#!/bin/bash
# Load-safe, self-cleaning pipeline launcher.
#
# Two things historically broke on-demand runs on this Mac:
#   1. Heavy startup imports (anthropic/pydantic) stalled the process under
#      load — now fixed by lazy-importing anthropic, so `import src.main` is
#      ~2s regardless of load.
#   2. Leftover processes from killed/failed runs accumulated threads & FDs,
#      eventually causing macOS errno-11 ("resource deadlock avoided"). This
#      script kills any stale scraper processes before starting.
#
# It still waits for basic headroom (src.main imports in <15s) as a safety net,
# then launches the full pipeline under caffeinate so it can't sleep mid-run.
#
# Usage:
#   nohup scripts/wait_and_run.sh > logs/wait_and_run.log 2>&1 & disown
#
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date +%H:%M:%S)] === launcher start ==="

# --- 1. Clean up any stale scraper processes (prevents thread/FD buildup) ---
STALE=$(pgrep -f "python -m src.main" || true)
if [ -n "$STALE" ]; then
  echo "[$(date +%H:%M:%S)] killing stale scraper pids: $STALE"
  pkill -9 -f "python -m src.main" 2>/dev/null || true
  pkill -9 -f "caffeinate.*src.main" 2>/dev/null || true
  sleep 2
fi
rm -f .scraper.lock

# --- 2. Wait for headroom: src.main must import in under 15s ---
MAX_CHECKS=40          # ~20 min ceiling
BUDGET=15
for i in $(seq 1 "$MAX_CHECKS"); do
  start=$(date +%s)
  ( .venv/bin/python -c "import src.main" 2>/dev/null & p=$!; \
    ( sleep "$BUDGET"; kill -9 $p 2>/dev/null ) & w=$!; \
    wait $p 2>/dev/null; rc=$?; kill $w 2>/dev/null; exit $rc ) && rc=0 || rc=$?
  el=$(( $(date +%s) - start ))
  load=$(uptime | sed 's/.*averages: //')

  if [ "$rc" -eq 0 ] && [ "$el" -lt "$BUDGET" ]; then
    echo "[$(date +%H:%M:%S)] ready (src.main import ${el}s, load ${load}) — launching"
    sqlite3 data/jobs.db "DELETE FROM job_evaluations;"
    set -a; source .env; set +a
    JOBSCRAPER_HEADLESS=1 caffeinate -i -m -s .venv/bin/python -m src.main
    code=$?
    echo "[$(date +%H:%M:%S)] === pipeline exited rc=${code} ==="
    exit $code
  fi
  echo "[$(date +%H:%M:%S)] waiting (src.main ${el}s rc=${rc}, load ${load})"
  sleep 30
done

echo "[$(date +%H:%M:%S)] gave up: machine stayed busy ~20 min"
exit 1
