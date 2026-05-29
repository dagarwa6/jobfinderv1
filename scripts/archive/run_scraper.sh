#!/usr/bin/env bash
# Job scraper launchd wrapper
# - Activates venv and loads .env
# - Prevents overlapping runs via lock file
# - Auto-imports feedback from Downloads folder
# - Sends macOS notification on completion
# - Logs everything to logs/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
LOCK_FILE="$PROJECT_DIR/.scraper.lock"
OUTPUT_DIR="$PROJECT_DIR/output"

mkdir -p "$LOG_DIR"

# --- Lock file: prevent overlapping runs ---
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "$(date): Scraper already running (PID $OLD_PID), skipping" >> "$LOG_DIR/launchd_stderr.log"
        exit 0
    fi
    # Stale lock file — remove it
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

echo "=== Job Scraper Run: $(date) ==="

# --- Activate virtualenv ---
source "$VENV/bin/activate"
cd "$PROJECT_DIR"

# --- Load .env if present ---
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# --- Auto-import feedback from ~/Downloads if present ---
DOWNLOADS_FB="$HOME/Downloads/feedback.json"
OUTPUT_FB="$OUTPUT_DIR/feedback.json"
if [ -f "$DOWNLOADS_FB" ]; then
    echo "Found feedback.json in Downloads, moving to output/"
    mv "$DOWNLOADS_FB" "$OUTPUT_FB"
fi

# --- Run the scraper ---
START_TIME=$(date +%s)
python -m src.main 2>&1
EXIT_CODE=$?
END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
MINUTES=$(( ELAPSED / 60 ))

echo "=== Finished: $(date) (${MINUTES}m ${ELAPSED}s, exit code $EXIT_CODE) ==="

# --- macOS notification ---
if [ $EXIT_CODE -eq 0 ]; then
    # Count new jobs from the latest run log
    NEW_COUNT=$(python -c "
import sqlite3
conn = sqlite3.connect('data/jobs.db')
row = conn.execute('SELECT total_new FROM run_log ORDER BY id DESC LIMIT 1').fetchone()
print(row[0] if row else 0)
conn.close()
" 2>/dev/null || echo "?")
    osascript -e "display notification \"Found ${NEW_COUNT} new jobs (${MINUTES}min)\" with title \"Job Scraper\" sound name \"Glass\"" 2>/dev/null || true
else
    osascript -e "display notification \"Run failed (exit code $EXIT_CODE)\" with title \"Job Scraper\" sound name \"Basso\"" 2>/dev/null || true
fi
