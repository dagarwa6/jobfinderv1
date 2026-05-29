"""Import user feedback from dashboard-exported JSON into the learning engine.

The dashboard stores feedback in localStorage and exports it as a JSON file.
This module reads that file and feeds it into the LearnedRulesEngine so
rules get strengthened or weakened based on real user signals.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from src.learning.learned_rules import LearnedRulesEngine

logger = logging.getLogger(__name__)


def import_feedback_file(
    db_conn: sqlite3.Connection,
    feedback_path: Path,
    log: logging.Logger | None = None,
) -> int:
    """Import feedback from a JSON file exported by the dashboard.

    Expected JSON format (array of objects):
        [
            {"job_id": 123, "feedback_type": "regret_applied", "timestamp": "..."},
            {"job_id": 456, "feedback_type": "confirmed_good", "timestamp": "..."},
        ]

    Valid feedback_type values: regret_applied, regret_skipped, confirmed_good.

    After importing, the feedback file is renamed to .imported.json so it
    won't be re-imported on the next run.

    Args:
        db_conn: SQLite connection with learned_rules tables.
        feedback_path: Path to the feedback.json file.
        log: Optional logger (defaults to module logger).

    Returns:
        Number of feedback entries successfully imported.
    """
    log = log or logger

    if not feedback_path.exists():
        return 0

    with open(feedback_path) as f:
        entries = json.load(f)

    if not entries:
        return 0

    engine = LearnedRulesEngine(db_conn)
    imported = 0
    for entry in entries:
        try:
            engine.record_feedback(
                job_id=entry["job_id"],
                feedback_type=entry["feedback_type"],
            )
            imported += 1
        except (ValueError, KeyError) as e:
            log.warning(f"Skipping invalid feedback entry: {entry} — {e}")

    if imported > 0:
        engine.mine_negative_rules()
        log.info(f"Imported {imported} feedback entries, negative rules updated")

    # Archive the file so it isn't re-imported
    archive_path = feedback_path.with_suffix(".imported.json")
    feedback_path.rename(archive_path)
    log.info(f"Archived feedback file to {archive_path}")

    return imported
