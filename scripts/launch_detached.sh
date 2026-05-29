#!/bin/bash
# Launches the scraper fully detached from any controlling terminal.
# Survives parent shell exit, harness restarts, terminal close.
cd "$(dirname "$0")/.."
set -a
source .env
set +a
export JOBSCRAPER_HEADLESS=1
LOG="logs/run_$(date +%Y%m%d_%H%M%S).log"
echo "Detached pipeline starting; log -> $LOG"
nohup .venv/bin/python -m src.main < /dev/null > "$LOG" 2>&1 &
echo "Detached PID: $!"
disown
