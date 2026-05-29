"""Tests for the learned rules engine (with temporal decay, fusion, negative mining)."""
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.learning.learned_rules import LearnedRulesEngine, LEARNED_RULES_SCHEMA


@pytest.fixture
def memory_db():
    """In-memory SQLite database with eval data for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create required tables
    conn.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY, company_name TEXT, title TEXT,
            matched_lane TEXT, sponsorship_flag TEXT, description_text TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE job_evaluations (
            id INTEGER PRIMARY KEY, job_id INTEGER,
            global_score REAL, recommended_action TEXT,
            red_flags TEXT, reasoning TEXT
        );
    """)

    # Insert test data: RED H1B jobs that always skip
    for i in range(10):
        conn.execute(
            "INSERT INTO jobs (id, company_name, title, matched_lane, sponsorship_flag, description_text) "
            "VALUES (?,?,?,?,?,?)",
            (i + 1, "BadCo", f"Analyst {i}", "Data Analyst", "RED", "some desc"),
        )
        conn.execute(
            "INSERT INTO job_evaluations (job_id, global_score, recommended_action, red_flags, reasoning) "
            "VALUES (?,?,?,?,?)",
            (i + 1, 1.8, "skip", "[]", "RED H1B"),
        )

    # Insert GREEN H1B jobs that mostly apply
    for i in range(5):
        jid = 20 + i
        conn.execute(
            "INSERT INTO jobs (id, company_name, title, matched_lane, sponsorship_flag, description_text) "
            "VALUES (?,?,?,?,?,?)",
            (jid, "GoodCo", f"BA {i}", "Business Analyst", "GREEN", "good desc"),
        )
        action = "apply" if i < 3 else "consider"
        conn.execute(
            "INSERT INTO job_evaluations (job_id, global_score, recommended_action, red_flags, reasoning) "
            "VALUES (?,?,?,?,?)",
            (jid, 4.0 if i < 3 else 3.2, action, "[]", "Good match"),
        )

    conn.commit()
    yield conn
    conn.close()


class TestRuleMining:
    def test_mines_h1b_skip_rule(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        stats = engine.mine_rules()
        assert stats["skip_created"] > 0

        rules = engine.get_rules_summary()
        h1b_skip = [r for r in rules if r["type"] == "skip" and r["pattern"] == "h1b_flag"]
        assert len(h1b_skip) >= 1
        assert h1b_skip[0]["key"] == "RED"

    def test_mines_boost_rule(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        rules = engine.get_rules_summary()
        boost = [r for r in rules if r["type"] == "boost"]
        assert len(boost) > 0

    def test_min_sample_size_respected(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=100)
        stats = engine.mine_rules()
        assert stats["skip_created"] == 0
        assert stats["boost_created"] == 0


class TestTemporalDecay:
    """Verify that old rules lose effective confidence over time."""

    def test_fresh_rule_no_decay(self, memory_db):
        engine = LearnedRulesEngine(memory_db)
        now = datetime.now().isoformat()
        eff = engine._compute_effective_confidence(0.90, now)
        assert abs(eff - 0.90) < 0.01  # essentially no decay

    def test_old_rule_decays(self, memory_db):
        engine = LearnedRulesEngine(memory_db)
        eight_weeks_ago = (datetime.now() - timedelta(weeks=8)).isoformat()
        eff = engine._compute_effective_confidence(1.0, eight_weeks_ago)
        # 0.95^8 ≈ 0.663
        assert eff < 0.70
        assert eff > 0.60

    def test_decay_has_floor(self, memory_db):
        engine = LearnedRulesEngine(memory_db)
        ancient = (datetime.now() - timedelta(weeks=100)).isoformat()
        eff = engine._compute_effective_confidence(1.0, ancient)
        assert eff >= 0.40  # DECAY_FLOOR

    def test_rules_sorted_by_effective_confidence(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()
        rules = engine.load_active_rules()
        confs = [r.effective_confidence for r in rules]
        assert confs == sorted(confs, reverse=True)

    def test_effective_confidence_in_summary(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()
        summary = engine.get_rules_summary()
        assert all("effective_confidence" in r for r in summary)


class TestMultiPatternFusion:
    """Verify soft voting when multiple rules fire on the same job."""

    def test_multiple_skip_rules_reinforce(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        # RED H1B + Data Analyst lane → both skip rules fire
        job = {"id": 100, "sponsorship_flag": "RED", "matched_lane": "Data Analyst",
               "company_name": "NewCo", "description_text": "some job"}
        skip_matches, boost_matches = engine._collect_matching_rules(job)
        assert len(skip_matches) >= 2  # h1b_flag + lane or lane_h1b

        fused = engine._fused_confidence(skip_matches)
        # Multiple matching rules should produce high fused confidence
        assert fused >= 0.75  # well above the skip threshold
        # Fused confidence is capped at 0.99
        assert fused <= 0.99

    def test_conflicting_rules_resolved(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        # GREEN H1B (boost) + Business Analyst lane (boost) → boost wins
        job = {"id": 101, "sponsorship_flag": "GREEN", "matched_lane": "Business Analyst",
               "company_name": "NewCo", "description_text": ""}
        action, reason, rule_id = engine.evaluate_job(job)
        assert action in ("boost", "evaluate")

    def test_single_rule_no_reinforcement_bonus(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()
        rules = engine.load_active_rules()

        # Single rule: fused confidence should equal effective confidence
        single = [rules[0]]
        fused = engine._fused_confidence(single)
        assert abs(fused - single[0].effective_confidence) < 0.001

    def test_empty_rules_zero_confidence(self, memory_db):
        engine = LearnedRulesEngine(memory_db)
        engine._init_schema()
        assert engine._fused_confidence([]) == 0.0


class TestNegativePatternMining:
    """Verify user feedback creates/weakens rules."""

    def test_record_feedback(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        engine.record_feedback(job_id=20, feedback_type="regret_applied")
        row = memory_db.execute(
            "SELECT * FROM user_feedback WHERE job_id = 20"
        ).fetchone()
        assert row is not None
        assert row["feedback_type"] == "regret_applied"

    def test_invalid_feedback_rejected(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        with pytest.raises(ValueError):
            engine.record_feedback(job_id=1, feedback_type="invalid_type")

    def test_regret_applied_weakens_boost(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        # Get initial boost confidence for GoodCo's lane
        boost_before = memory_db.execute(
            "SELECT confidence FROM learned_rules WHERE rule_type='boost' AND pattern_type='company' AND pattern_key='GoodCo'"
        ).fetchone()

        if boost_before:
            conf_before = boost_before[0]
            # Record regret on a GoodCo job
            engine.record_feedback(job_id=20, feedback_type="regret_applied")
            engine.mine_negative_rules()

            boost_after = memory_db.execute(
                "SELECT confidence FROM learned_rules WHERE rule_type='boost' AND pattern_type='company' AND pattern_key='GoodCo'"
            ).fetchone()
            assert boost_after[0] < conf_before

    def test_confirmed_good_strengthens_boost(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        boost_before = memory_db.execute(
            "SELECT confidence FROM learned_rules WHERE rule_type='boost' AND pattern_type='lane' AND pattern_key='Business Analyst'"
        ).fetchone()

        if boost_before:
            conf_before = boost_before[0]
            engine.record_feedback(job_id=20, feedback_type="confirmed_good")
            engine.mine_negative_rules()

            boost_after = memory_db.execute(
                "SELECT confidence FROM learned_rules WHERE rule_type='boost' AND pattern_type='lane' AND pattern_key='Business Analyst'"
            ).fetchone()
            assert boost_after[0] >= conf_before

    def test_negative_override_suppresses_boost(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        # Record regret on a GoodCo job
        engine.record_feedback(job_id=20, feedback_type="regret_applied")

        # Now a new GoodCo job should have suppressed boost
        job = {"id": 200, "sponsorship_flag": "GREEN", "matched_lane": "Business Analyst",
               "company_name": "GoodCo", "description_text": ""}
        has_override = engine._check_negative_override(
            job,
            [r for r in engine.load_active_rules() if r.rule_type == "boost"],
        )
        assert has_override


class TestRuleApplication:
    def test_red_h1b_auto_skipped(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        job = {"id": 100, "sponsorship_flag": "RED", "matched_lane": "Data Analyst",
               "company_name": "NewCo", "description_text": "some job"}
        action, reason, rule_id = engine.evaluate_job(job)
        assert action == "auto_skip"
        assert rule_id is not None

    def test_green_h1b_not_skipped(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        job = {"id": 101, "sponsorship_flag": "GREEN", "matched_lane": "Business Analyst",
               "company_name": "NewCo", "description_text": "some job"}
        action, reason, rule_id = engine.evaluate_job(job)
        assert action in ("boost", "evaluate"), f"GREEN BA should not be skipped, got {action}"

    def test_filter_for_eval_partitions(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        jobs = [
            {"id": 1, "sponsorship_flag": "RED", "matched_lane": "DA", "company_name": "X", "description_text": ""},
            {"id": 2, "sponsorship_flag": "GREEN", "matched_lane": "BA", "company_name": "Y", "description_text": ""},
            {"id": 3, "sponsorship_flag": "YELLOW", "matched_lane": "BA", "company_name": "Z", "description_text": ""},
        ]
        skipped, boosted, to_eval = engine.filter_for_eval(jobs)
        assert len(skipped) + len(boosted) + len(to_eval) == 3
        assert any(j["id"] == 1 for j in skipped)

    def test_upsert_updates_existing_rule(self, memory_db):
        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        stats1 = engine.mine_rules()
        created = stats1["skip_created"]

        stats2 = engine.mine_rules()
        assert stats2["skip_created"] == 0
        assert stats2["skip_updated"] == created


class TestFeedbackImport:
    """Verify the JSON feedback import flow used by the dashboard."""

    def test_import_feedback_from_json(self, memory_db):
        from src.learning.feedback_import import import_feedback_file
        import logging

        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        # Write a feedback JSON file
        feedback_data = [
            {"job_id": 20, "feedback_type": "regret_applied", "timestamp": "2026-05-18T10:00:00"},
            {"job_id": 21, "feedback_type": "confirmed_good", "timestamp": "2026-05-18T10:01:00"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(feedback_data, f)
            tmp_path = Path(f.name)

        logger = logging.getLogger("test")
        count = import_feedback_file(memory_db, tmp_path, logger)
        assert count == 2

        # Verify feedback was recorded in DB
        rows = memory_db.execute("SELECT * FROM user_feedback").fetchall()
        assert len(rows) == 2

        # Verify file was archived
        archived = tmp_path.with_suffix(".imported.json")
        assert archived.exists()
        assert not tmp_path.exists()
        archived.unlink()  # cleanup

    def test_import_nonexistent_file(self, memory_db):
        from src.learning.feedback_import import import_feedback_file
        import logging

        logger = logging.getLogger("test")
        count = import_feedback_file(memory_db, Path("/tmp/nonexistent_feedback.json"), logger)
        assert count == 0

    def test_import_invalid_feedback_skipped(self, memory_db):
        from src.learning.feedback_import import import_feedback_file
        import logging

        engine = LearnedRulesEngine(memory_db, min_sample_size=3)
        engine.mine_rules()

        feedback_data = [
            {"job_id": 20, "feedback_type": "invalid_type", "timestamp": "2026-05-18T10:00:00"},
            {"job_id": 21, "feedback_type": "confirmed_good", "timestamp": "2026-05-18T10:01:00"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(feedback_data, f)
            tmp_path = Path(f.name)

        logger = logging.getLogger("test")
        count = import_feedback_file(memory_db, tmp_path, logger)
        assert count == 1  # only the valid one

        archived = tmp_path.with_suffix(".imported.json")
        if archived.exists():
            archived.unlink()
