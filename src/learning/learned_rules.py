"""Learned rules engine for pre-AI filtering.

Mines past AI evaluation results to build deterministic rules that skip
or fast-track jobs before the expensive AI eval step. Rules are stored
in SQLite and applied as a filter stage between the existing pipeline
filters and the AI scorer.

Three rule types:
  - SKIP rules: Auto-reject jobs matching patterns that historically always fail.
  - BOOST rules: Prioritize jobs matching patterns that historically score well.
  - NEGATIVE rules: Contrapositive patterns from user feedback (regret signals).

Advanced features (cherry-picked from Ruflo/SONA architecture):
  - Temporal confidence decay: older rules lose confidence weekly (EWC++ inspired).
  - Multi-pattern fusion: soft voting when multiple rules fire on the same job.
  - Negative pattern mining: learns from "regret_applied" / "regret_skipped" feedback.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LEARNED_RULES_SCHEMA = """
CREATE TABLE IF NOT EXISTS learned_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type       TEXT NOT NULL,           -- 'skip' or 'boost'
    pattern_type    TEXT NOT NULL,           -- 'h1b_flag', 'lane', 'lane_h1b', 'company', 'keyword'
    pattern_key     TEXT NOT NULL,           -- the pattern value (e.g., 'RED', 'Technology Consultant', etc.)
    sample_size     INTEGER NOT NULL,        -- how many past evals informed this rule
    avg_score       REAL,                    -- average global_score of matching past evals
    skip_rate       REAL,                    -- fraction that were 'skip' (0.0-1.0)
    apply_rate      REAL,                    -- fraction that were 'apply' (0.0-1.0)
    confidence      REAL NOT NULL,           -- rule confidence (0.0-1.0)
    reasoning       TEXT,                    -- human-readable explanation
    is_active       INTEGER DEFAULT 1,       -- can be manually disabled
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    times_applied   INTEGER DEFAULT 0,       -- how many jobs this rule has auto-skipped/boosted
    UNIQUE(rule_type, pattern_type, pattern_key)
);

CREATE INDEX IF NOT EXISTS idx_rules_active ON learned_rules(is_active, rule_type);

CREATE TABLE IF NOT EXISTS rule_applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         INTEGER NOT NULL,
    job_id          INTEGER NOT NULL,
    action_taken    TEXT NOT NULL,           -- 'auto_skip' or 'boost'
    applied_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (rule_id) REFERENCES learned_rules(id)
);

CREATE INDEX IF NOT EXISTS idx_rule_app_job ON rule_applications(job_id);

-- Pattern interaction weights for multi-pattern fusion (Ruflo SONA-inspired)
CREATE TABLE IF NOT EXISTS pattern_weights (
    pattern_type_a  TEXT NOT NULL,
    pattern_type_b  TEXT NOT NULL,
    interaction_strength REAL DEFAULT 0.0,  -- positive = reinforce, negative = conflict
    samples         INTEGER DEFAULT 0,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (pattern_type_a, pattern_type_b)
);

-- User feedback for negative pattern mining (Ruflo trajectory-inspired)
CREATE TABLE IF NOT EXISTS user_feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL,
    feedback_type   TEXT NOT NULL,           -- 'regret_applied', 'regret_skipped', 'confirmed_good'
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, feedback_type)
);

CREATE INDEX IF NOT EXISTS idx_feedback_type ON user_feedback(feedback_type);
"""


@dataclass
class LearnedRule:
    """A single learned rule extracted from evaluation history."""
    id: int | None
    rule_type: str          # 'skip', 'boost', or 'negative'
    pattern_type: str       # 'h1b_flag', 'lane', 'lane_h1b', 'company', 'keyword'
    pattern_key: str        # the matching value
    sample_size: int
    avg_score: float
    skip_rate: float
    apply_rate: float
    confidence: float       # raw confidence from mining
    effective_confidence: float = 0.0  # after temporal decay
    reasoning: str = ""
    is_active: bool = True
    updated_at: str = ""    # ISO timestamp of last update


# Decay constant: rules lose ~5% confidence per week of staleness
WEEKLY_DECAY_FACTOR = 0.95
# Floor: decayed confidence never drops below this (prevents total rule death)
DECAY_FLOOR = 0.40


class LearnedRulesEngine:
    """Manages learned rules: mining, storage, and application.

    Cherry-picked from Ruflo/SONA architecture:
      - Temporal decay (EWC++ inspired): older rules lose effective confidence.
      - Multi-pattern fusion: soft voting resolves conflicts when multiple rules fire.
      - Negative mining: user feedback ("regret") generates contrapositive rules.

    Args:
        db_conn: SQLite connection (typically from JobDB.conn).
        skip_confidence_threshold: Minimum effective confidence to apply a skip rule.
        boost_confidence_threshold: Minimum effective confidence to apply a boost rule.
        min_sample_size: Minimum evaluations needed to create a rule.
        decay_factor: Weekly confidence decay multiplier (default 0.95).
    """

    def __init__(
        self,
        db_conn: sqlite3.Connection,
        skip_confidence_threshold: float = 0.75,
        boost_confidence_threshold: float = 0.70,
        min_sample_size: int = 3,
        decay_factor: float = WEEKLY_DECAY_FACTOR,
    ):
        self.conn = db_conn
        self.skip_threshold = skip_confidence_threshold
        self.boost_threshold = boost_confidence_threshold
        self.min_samples = min_sample_size
        self.decay_factor = decay_factor
        self._init_schema()
        self._rules_cache: list[LearnedRule] | None = None
        self._interaction_cache: dict[tuple[str, str], float] | None = None

    def _init_schema(self):
        self.conn.executescript(LEARNED_RULES_SCHEMA)
        self.conn.commit()

    # ── Mining: extract rules from past evaluations ──────────────

    def mine_rules(self) -> dict[str, int]:
        """Analyze past evaluations and create/update learned rules.

        Returns dict with counts of rules created/updated per type.
        """
        stats = {"skip_created": 0, "skip_updated": 0, "boost_created": 0, "boost_updated": 0}

        # Rule 1: H1B flag patterns
        self._mine_h1b_flag_rules(stats)

        # Rule 2: Lane-level patterns
        self._mine_lane_rules(stats)

        # Rule 3: Lane × H1B flag combo patterns
        self._mine_lane_h1b_rules(stats)

        # Rule 4: Company-level patterns (repeat companies)
        self._mine_company_rules(stats)

        # Rule 5: Red-flag keyword patterns from AI reasoning
        self._mine_keyword_rules(stats)

        # Rule 6: Negative patterns from user feedback
        neg_stats = self.mine_negative_rules()
        stats.update(neg_stats)

        self.conn.commit()
        self._rules_cache = None  # invalidate cache
        self._interaction_cache = None
        logger.info(f"Rule mining complete: {stats}")
        return stats

    def _mine_h1b_flag_rules(self, stats: dict):
        """Mine rules based on H1B sponsorship flag."""
        rows = self.conn.execute("""
            SELECT j.sponsorship_flag, COUNT(*) cnt,
                   AVG(e.global_score) avg_score,
                   SUM(CASE WHEN e.recommended_action='skip' THEN 1.0 ELSE 0 END) / COUNT(*) skip_rate,
                   SUM(CASE WHEN e.recommended_action='apply' THEN 1.0 ELSE 0 END) / COUNT(*) apply_rate
            FROM jobs j JOIN job_evaluations e ON j.id = e.job_id
            GROUP BY j.sponsorship_flag
            HAVING cnt >= ?
        """, (self.min_samples,)).fetchall()

        for r in rows:
            flag, cnt, avg, skip_rate, apply_rate = r
            # Do NOT auto-skip on H1B flag alone. RED just means "company name
            # didn't fuzzy-match DOL data" — a coarse signal with huge false-
            # negative rates (name variants, newer/smaller sponsors). Auto-
            # skipping RED was also self-reinforcing: skipped jobs get recorded
            # as 'skip', which re-mined the same RED skip rule each run. Let the
            # AI's sponsorship_likelihood dimension + the keyword filter judge
            # sponsorship per-job instead. We still allow BOOST rules below.
            if skip_rate >= 0.90 and flag not in ("RED", "YELLOW"):
                confidence = min(skip_rate, 1.0) * min(cnt / 10, 1.0)
                self._upsert_rule(
                    "skip", "h1b_flag", flag, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"H1B flag '{flag}': {skip_rate*100:.0f}% skip rate across {cnt} jobs (avg score {avg:.2f})",
                    stats,
                )
            if apply_rate >= 0.10 and avg >= 3.0:
                confidence = min(apply_rate * 3, 1.0) * min(cnt / 5, 1.0)
                self._upsert_rule(
                    "boost", "h1b_flag", flag, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"H1B flag '{flag}': {apply_rate*100:.0f}% apply rate, avg score {avg:.2f}",
                    stats,
                )

    def _mine_lane_rules(self, stats: dict):
        """Mine rules based on matched lane performance."""
        rows = self.conn.execute("""
            SELECT j.matched_lane, COUNT(*) cnt,
                   AVG(e.global_score) avg_score,
                   SUM(CASE WHEN e.recommended_action='skip' THEN 1.0 ELSE 0 END) / COUNT(*) skip_rate,
                   SUM(CASE WHEN e.recommended_action='apply' THEN 1.0 ELSE 0 END) / COUNT(*) apply_rate
            FROM jobs j JOIN job_evaluations e ON j.id = e.job_id
            GROUP BY j.matched_lane
            HAVING cnt >= ?
        """, (self.min_samples,)).fetchall()

        for r in rows:
            lane, cnt, avg, skip_rate, apply_rate = r
            # Skip rule: lane with 100% skip and avg < 2.5
            if skip_rate >= 0.95 and avg < 2.5 and cnt >= 5:
                confidence = min(skip_rate, 1.0) * min(cnt / 10, 1.0)
                self._upsert_rule(
                    "skip", "lane", lane, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"Lane '{lane}': {skip_rate*100:.0f}% skip, avg {avg:.2f} across {cnt} jobs",
                    stats,
                )
            # Boost rule: lane with high apply rate
            if apply_rate >= 0.05 and avg >= 3.0:
                confidence = min(apply_rate * 5, 1.0) * min(cnt / 5, 1.0)
                self._upsert_rule(
                    "boost", "lane", lane, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"Lane '{lane}': {apply_rate*100:.0f}% apply rate, avg {avg:.2f}",
                    stats,
                )

    def _mine_lane_h1b_rules(self, stats: dict):
        """Mine rules based on lane × H1B flag combinations."""
        rows = self.conn.execute("""
            SELECT j.matched_lane || '|' || j.sponsorship_flag combo,
                   j.matched_lane, j.sponsorship_flag,
                   COUNT(*) cnt,
                   AVG(e.global_score) avg_score,
                   SUM(CASE WHEN e.recommended_action='skip' THEN 1.0 ELSE 0 END) / COUNT(*) skip_rate,
                   SUM(CASE WHEN e.recommended_action='apply' THEN 1.0 ELSE 0 END) / COUNT(*) apply_rate
            FROM jobs j JOIN job_evaluations e ON j.id = e.job_id
            GROUP BY j.matched_lane, j.sponsorship_flag
            HAVING cnt >= ?
        """, (self.min_samples,)).fetchall()

        for r in rows:
            combo, lane, flag, cnt, avg, skip_rate, apply_rate = r
            if skip_rate >= 0.90 and avg < 2.5:
                confidence = min(skip_rate, 1.0) * min(cnt / 8, 1.0)
                self._upsert_rule(
                    "skip", "lane_h1b", combo, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"'{lane}' + {flag} H1B: {skip_rate*100:.0f}% skip, avg {avg:.2f}",
                    stats,
                )
            if apply_rate >= 0.10 and avg >= 3.5:
                confidence = min(apply_rate * 3, 1.0) * min(cnt / 5, 1.0)
                self._upsert_rule(
                    "boost", "lane_h1b", combo, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"'{lane}' + {flag} H1B: {apply_rate*100:.0f}% apply, avg {avg:.2f}",
                    stats,
                )

    def _mine_company_rules(self, stats: dict):
        """Mine rules for companies with multiple evaluated postings."""
        rows = self.conn.execute("""
            SELECT j.company_name, COUNT(*) cnt,
                   AVG(e.global_score) avg_score,
                   SUM(CASE WHEN e.recommended_action='skip' THEN 1.0 ELSE 0 END) / COUNT(*) skip_rate,
                   SUM(CASE WHEN e.recommended_action='apply' THEN 1.0 ELSE 0 END) / COUNT(*) apply_rate
            FROM jobs j JOIN job_evaluations e ON j.id = e.job_id
            GROUP BY j.company_name
            HAVING cnt >= ?
        """, (self.min_samples,)).fetchall()

        for r in rows:
            company, cnt, avg, skip_rate, apply_rate = r
            if skip_rate >= 1.0 and avg < 2.0 and cnt >= 3:
                confidence = min(cnt / 5, 1.0) * 0.8  # slightly lower — company could add new role types
                self._upsert_rule(
                    "skip", "company", company, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"'{company}': all {cnt} jobs were skip (avg {avg:.2f})",
                    stats,
                )
            if apply_rate >= 0.20 and avg >= 3.5:
                confidence = min(apply_rate * 3, 1.0) * min(cnt / 3, 1.0)
                self._upsert_rule(
                    "boost", "company", company, cnt, avg, skip_rate, apply_rate,
                    confidence,
                    f"'{company}': {apply_rate*100:.0f}% apply rate, avg {avg:.2f}",
                    stats,
                )

    def _mine_keyword_rules(self, stats: dict):
        """Mine skip rules from common red-flag keywords in AI reasoning."""
        rows = self.conn.execute("""
            SELECT e.red_flags FROM job_evaluations e
            WHERE e.red_flags IS NOT NULL AND e.red_flags != '[]'
              AND e.recommended_action = 'skip'
        """).fetchall()

        from collections import Counter
        keyword_counts = Counter()
        for r in rows:
            for flag in json.loads(r[0]):
                # Normalize and extract actionable keywords
                flag_lower = flag.strip().lower()
                # Only extract novel patterns (not just "RED H1B" which we already capture)
                if "security clearance" in flag_lower:
                    keyword_counts["requires security clearance"] += 1
                elif "citizen" in flag_lower and "us" in flag_lower:
                    keyword_counts["us citizen required"] += 1
                elif "contract" in flag_lower and "only" in flag_lower:
                    keyword_counts["contract only"] += 1
                # NOTE: "no remote" intentionally excluded — remote status is not
                # a skip signal. The AI often mentions location logistics as a
                # secondary red flag when the real skip reason is sponsorship.

        for keyword, cnt in keyword_counts.items():
            if cnt >= self.min_samples:
                confidence = min(cnt / 10, 1.0) * 0.7
                self._upsert_rule(
                    "skip", "keyword", keyword, cnt, 0, 1.0, 0,
                    confidence,
                    f"Red flag keyword '{keyword}' appeared in {cnt} skipped jobs",
                    stats,
                )

    def _upsert_rule(
        self, rule_type, pattern_type, pattern_key,
        sample_size, avg_score, skip_rate, apply_rate,
        confidence, reasoning, stats,
    ):
        """Insert or update a learned rule."""
        existing = self.conn.execute(
            "SELECT id FROM learned_rules WHERE rule_type=? AND pattern_type=? AND pattern_key=?",
            (rule_type, pattern_type, pattern_key),
        ).fetchone()

        if existing:
            self.conn.execute("""
                UPDATE learned_rules SET sample_size=?, avg_score=?, skip_rate=?,
                       apply_rate=?, confidence=?, reasoning=?, updated_at=datetime('now')
                WHERE id=?
            """, (sample_size, avg_score, skip_rate, apply_rate, confidence, reasoning, existing[0]))
            stats[f"{rule_type}_updated"] = stats.get(f"{rule_type}_updated", 0) + 1
        else:
            self.conn.execute("""
                INSERT INTO learned_rules
                    (rule_type, pattern_type, pattern_key, sample_size, avg_score,
                     skip_rate, apply_rate, confidence, reasoning)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (rule_type, pattern_type, pattern_key, sample_size, avg_score,
                  skip_rate, apply_rate, confidence, reasoning))
            stats[f"{rule_type}_created"] = stats.get(f"{rule_type}_created", 0) + 1

    # ── Temporal Decay (EWC++ inspired) ─────────────────────────

    def _compute_effective_confidence(self, raw_confidence: float, updated_at: str) -> float:
        """Apply temporal decay to a rule's confidence.

        Newer rules retain full confidence; older rules decay exponentially
        by ~5% per week. A rule untouched for 8 weeks drops from 1.0 to ~0.66.
        Decay floors at DECAY_FLOOR to prevent total rule death — a rule that
        was once strong still has residual value.
        """
        if not updated_at:
            return raw_confidence
        try:
            updated = datetime.fromisoformat(updated_at)
            weeks_old = (datetime.now() - updated).total_seconds() / (7 * 86400)
            decayed = raw_confidence * (self.decay_factor ** weeks_old)
            return max(decayed, DECAY_FLOOR)
        except (ValueError, TypeError):
            return raw_confidence

    # ── Application: filter jobs using learned rules ─────────────

    def load_active_rules(self) -> list[LearnedRule]:
        """Load all active rules with temporal decay applied to confidence."""
        if self._rules_cache is not None:
            return self._rules_cache

        rows = self.conn.execute("""
            SELECT id, rule_type, pattern_type, pattern_key, sample_size,
                   avg_score, skip_rate, apply_rate, confidence, reasoning,
                   is_active, updated_at
            FROM learned_rules WHERE is_active = 1
            ORDER BY confidence DESC
        """).fetchall()

        rules = []
        for r in rows:
            raw_conf = r[8]
            updated_at = r[11] or ""
            effective = self._compute_effective_confidence(raw_conf, updated_at)
            rules.append(LearnedRule(
                id=r[0], rule_type=r[1], pattern_type=r[2], pattern_key=r[3],
                sample_size=r[4], avg_score=r[5], skip_rate=r[6], apply_rate=r[7],
                confidence=raw_conf, effective_confidence=effective,
                reasoning=r[9], is_active=bool(r[10]), updated_at=updated_at,
            ))

        # Sort by effective confidence (post-decay) so strongest rules fire first
        rules.sort(key=lambda r: r.effective_confidence, reverse=True)
        self._rules_cache = rules

        decayed_count = sum(1 for r in rules if r.effective_confidence < r.confidence - 0.01)
        logger.info(
            f"Loaded {len(rules)} active learned rules "
            f"({sum(1 for r in rules if r.rule_type == 'skip')} skip, "
            f"{sum(1 for r in rules if r.rule_type == 'boost')} boost, "
            f"{decayed_count} with temporal decay applied)"
        )
        return rules

    def _load_interaction_weights(self) -> dict[tuple[str, str], float]:
        """Load pattern interaction weights for multi-pattern fusion."""
        if self._interaction_cache is not None:
            return self._interaction_cache

        rows = self.conn.execute(
            "SELECT pattern_type_a, pattern_type_b, interaction_strength "
            "FROM pattern_weights WHERE samples > 0"
        ).fetchall()

        weights = {}
        for r in rows:
            weights[(r[0], r[1])] = r[2]
        self._interaction_cache = weights
        return weights

    # ── Multi-Pattern Fusion (SONA soft voting inspired) ─────────

    def _collect_matching_rules(self, job: dict) -> tuple[list[LearnedRule], list[LearnedRule]]:
        """Find ALL rules that match a job (not just the first one).

        Returns (skip_matches, boost_matches) for fusion.
        """
        rules = self.load_active_rules()
        flag = job.get("sponsorship_flag", "")
        lane = job.get("matched_lane", "")
        company = job.get("company_name", "")
        desc = (job.get("description_text") or "").lower()[:1000]
        combo = f"{lane}|{flag}"

        skip_matches = []
        boost_matches = []

        for rule in rules:
            match = False
            if rule.pattern_type == "h1b_flag" and rule.pattern_key == flag:
                match = True
            elif rule.pattern_type == "lane" and rule.pattern_key == lane:
                match = True
            elif rule.pattern_type == "lane_h1b" and rule.pattern_key == combo:
                match = True
            elif rule.pattern_type == "company" and rule.pattern_key == company:
                match = True
            elif rule.pattern_type == "keyword" and rule.pattern_key in desc:
                match = True

            if match:
                if rule.rule_type == "skip":
                    skip_matches.append(rule)
                elif rule.rule_type == "boost":
                    boost_matches.append(rule)

        return skip_matches, boost_matches

    def _fused_confidence(self, rules: list[LearnedRule]) -> float:
        """Compute fused confidence from multiple matching rules using soft voting.

        Multiple rules reinforcing each other strengthens confidence.
        Uses weighted average + interaction bonus for pattern combinations.
        """
        if not rules:
            return 0.0
        if len(rules) == 1:
            return rules[0].effective_confidence

        # Weighted average of effective confidences
        total_weight = sum(r.sample_size for r in rules)
        if total_weight == 0:
            return rules[0].effective_confidence

        avg_conf = sum(r.effective_confidence * r.sample_size for r in rules) / total_weight

        # Interaction bonus: certain pattern combos reinforce each other
        interaction_bonus = 0.0
        weights = self._load_interaction_weights()
        pattern_types = [r.pattern_type for r in rules]
        for i, pt_a in enumerate(pattern_types):
            for pt_b in pattern_types[i + 1:]:
                pair = (pt_a, pt_b)
                reverse = (pt_b, pt_a)
                strength = weights.get(pair, weights.get(reverse, 0.0))
                interaction_bonus += strength * 0.05  # cap per interaction at 5%

        # Multi-rule reinforcement: each additional rule adds a small bonus
        reinforcement = min(len(rules) - 1, 3) * 0.03  # up to +9% for 4+ rules

        return min(avg_conf + interaction_bonus + reinforcement, 0.99)

    def evaluate_job(self, job: dict) -> tuple[str, str | None, int | None]:
        """Apply learned rules to a single job using multi-pattern fusion.

        Instead of stopping at the first matching rule, collects ALL matches
        and uses soft voting to resolve the final decision. This handles
        conflicts (e.g., skip rule on H1B + boost rule on company) principally.

        Args:
            job: Job dict with keys: sponsorship_flag, matched_lane, company_name,
                 description_text.

        Returns:
            Tuple of (action, reason, rule_id):
              - ("auto_skip", reason, rule_id) if skip rules win the vote
              - ("boost", reason, rule_id) if boost rules win the vote
              - ("evaluate", None, None) if no rule matches or vote is inconclusive
        """
        skip_matches, boost_matches = self._collect_matching_rules(job)

        skip_conf = self._fused_confidence(skip_matches)
        boost_conf = self._fused_confidence(boost_matches)

        # Check for negative overrides (user feedback contrapositive rules)
        negative_override = self._check_negative_override(job, boost_matches)

        if negative_override:
            boost_conf *= 0.5  # Suppress boost if negative pattern exists

        # Skip wins if above threshold and stronger than boost
        if skip_conf >= self.skip_threshold and skip_conf > boost_conf:
            best_rule = skip_matches[0]  # highest confidence skip rule
            reasons = [r.reasoning for r in skip_matches[:3]]
            combined_reason = " | ".join(reasons)
            self._record_application(best_rule.id, job.get("id", 0), "auto_skip")
            return ("auto_skip", combined_reason, best_rule.id)

        # Boost wins if above threshold and stronger than skip
        if boost_conf >= self.boost_threshold and boost_conf > skip_conf:
            best_rule = boost_matches[0]
            reasons = [r.reasoning for r in boost_matches[:3]]
            combined_reason = " | ".join(reasons)
            self._record_application(best_rule.id, job.get("id", 0), "boost")
            return ("boost", combined_reason, best_rule.id)

        return ("evaluate", None, None)

    def _check_negative_override(self, job: dict, boost_matches: list[LearnedRule]) -> bool:
        """Check if user feedback contradicts a boost decision.

        If the user previously marked a similar job as 'regret_applied',
        suppress the boost to avoid repeating the mistake.
        """
        if not boost_matches:
            return False

        company = job.get("company_name", "")
        lane = job.get("matched_lane", "")

        # Check if there's regret feedback for this company+lane combo
        row = self.conn.execute("""
            SELECT COUNT(*) FROM user_feedback uf
            JOIN jobs j ON uf.job_id = j.id
            WHERE uf.feedback_type = 'regret_applied'
              AND (j.company_name = ? OR j.matched_lane = ?)
        """, (company, lane)).fetchone()

        return row[0] > 0 if row else False

    def _record_application(self, rule_id: int, job_id: int, action: str):
        """Record that a rule was applied to a job."""
        self.conn.execute(
            "INSERT INTO rule_applications (rule_id, job_id, action_taken) VALUES (?,?,?)",
            (rule_id, job_id, action),
        )
        self.conn.execute(
            "UPDATE learned_rules SET times_applied = times_applied + 1 WHERE id = ?",
            (rule_id,),
        )

    def filter_for_eval(self, jobs: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        """Partition jobs into skip, boost, and evaluate buckets.

        Args:
            jobs: List of unevaluated job dicts.

        Returns:
            Tuple of (auto_skipped, boosted, to_evaluate):
              - auto_skipped: Jobs that matched skip rules (won't be AI-evaluated)
              - boosted: Jobs that matched boost rules (evaluated first, higher priority)
              - to_evaluate: Remaining jobs for standard AI evaluation
        """
        skipped = []
        boosted = []
        to_eval = []

        for job in jobs:
            action, reason, rule_id = self.evaluate_job(job)
            if action == "auto_skip":
                job["_auto_skip_reason"] = reason
                job["_auto_skip_rule_id"] = rule_id
                skipped.append(job)
            elif action == "boost":
                job["_boost_reason"] = reason
                job["_boost_rule_id"] = rule_id
                boosted.append(job)
            else:
                to_eval.append(job)

        self.conn.commit()
        logger.info(
            f"Learned rules: {len(skipped)} auto-skipped, {len(boosted)} boosted, "
            f"{len(to_eval)} sent to AI eval"
        )
        return skipped, boosted, to_eval

    # ── Reporting ────────────────────────────────────────────────

    def get_rules_summary(self) -> list[dict]:
        """Get a summary of all active rules for dashboard display."""
        rows = self.conn.execute("""
            SELECT rule_type, pattern_type, pattern_key, sample_size,
                   avg_score, confidence, reasoning, times_applied, updated_at
            FROM learned_rules WHERE is_active = 1
            ORDER BY rule_type, confidence DESC
        """).fetchall()
        results = []
        for r in rows:
            eff_conf = self._compute_effective_confidence(r[5], r[8] or "")
            results.append({
                "type": r[0], "pattern": r[1], "key": r[2],
                "samples": r[3], "avg_score": r[4],
                "confidence": r[5], "effective_confidence": eff_conf,
                "reasoning": r[6], "applied": r[7],
            })
        return results

    # ── Negative Pattern Mining (Ruflo trajectory-inspired) ──────

    def record_feedback(self, job_id: int, feedback_type: str):
        """Record user feedback on a job decision.

        Called from the dashboard when a user marks a job as:
          - 'regret_applied': Applied but shouldn't have (waste of time)
          - 'regret_skipped': Skipped but should have applied (missed opportunity)
          - 'confirmed_good': Applied and it was a good match (positive signal)

        Args:
            job_id: The job's database ID.
            feedback_type: One of 'regret_applied', 'regret_skipped', 'confirmed_good'.
        """
        valid_types = {"regret_applied", "regret_skipped", "confirmed_good"}
        if feedback_type not in valid_types:
            raise ValueError(f"feedback_type must be one of {valid_types}")

        self.conn.execute(
            "INSERT OR REPLACE INTO user_feedback (job_id, feedback_type) VALUES (?,?)",
            (job_id, feedback_type),
        )
        self.conn.commit()
        self._rules_cache = None  # invalidate
        logger.info(f"Recorded feedback: job_id={job_id}, type={feedback_type}")

    def mine_negative_rules(self) -> dict[str, int]:
        """Mine contrapositive rules from user feedback.

        'regret_applied' → creates negative rules to suppress boosts for similar patterns.
        'regret_skipped' → weakens skip rules for similar patterns.
        'confirmed_good' → strengthens boost rules and learns interaction weights.

        Returns dict with counts of actions taken.
        """
        stats = {"negative_created": 0, "rules_weakened": 0, "rules_strengthened": 0,
                 "interactions_learned": 0}

        # Process regret_applied: create anti-boost patterns
        regret_applied = self.conn.execute("""
            SELECT j.company_name, j.matched_lane, j.sponsorship_flag
            FROM user_feedback uf JOIN jobs j ON uf.job_id = j.id
            WHERE uf.feedback_type = 'regret_applied'
        """).fetchall()

        for r in regret_applied:
            company, lane, flag = r
            # Weaken any boost rules that match these patterns
            updated = self.conn.execute("""
                UPDATE learned_rules
                SET confidence = MAX(confidence * 0.7, 0.3),
                    reasoning = reasoning || ' [weakened by regret feedback]',
                    updated_at = datetime('now')
                WHERE rule_type = 'boost' AND is_active = 1
                  AND ((pattern_type = 'company' AND pattern_key = ?)
                    OR (pattern_type = 'lane' AND pattern_key = ?)
                    OR (pattern_type = 'lane_h1b' AND pattern_key = ?))
            """, (company, lane, f"{lane}|{flag}"))
            if updated.rowcount > 0:
                stats["rules_weakened"] += updated.rowcount

        # Process regret_skipped: weaken skip rules for these patterns
        regret_skipped = self.conn.execute("""
            SELECT j.company_name, j.matched_lane, j.sponsorship_flag
            FROM user_feedback uf JOIN jobs j ON uf.job_id = j.id
            WHERE uf.feedback_type = 'regret_skipped'
        """).fetchall()

        for r in regret_skipped:
            company, lane, flag = r
            updated = self.conn.execute("""
                UPDATE learned_rules
                SET confidence = MAX(confidence * 0.7, 0.3),
                    reasoning = reasoning || ' [weakened by regret-skip feedback]',
                    updated_at = datetime('now')
                WHERE rule_type = 'skip' AND is_active = 1
                  AND ((pattern_type = 'company' AND pattern_key = ?)
                    OR (pattern_type = 'lane' AND pattern_key = ?)
                    OR (pattern_type = 'lane_h1b' AND pattern_key = ?))
            """, (company, lane, f"{lane}|{flag}"))
            if updated.rowcount > 0:
                stats["rules_weakened"] += updated.rowcount

        # Process confirmed_good: strengthen boost rules + learn interaction weights
        confirmed = self.conn.execute("""
            SELECT j.company_name, j.matched_lane, j.sponsorship_flag
            FROM user_feedback uf JOIN jobs j ON uf.job_id = j.id
            WHERE uf.feedback_type = 'confirmed_good'
        """).fetchall()

        for r in confirmed:
            company, lane, flag = r
            updated = self.conn.execute("""
                UPDATE learned_rules
                SET confidence = MIN(confidence * 1.1, 1.0),
                    reasoning = reasoning || ' [strengthened by positive feedback]',
                    updated_at = datetime('now')
                WHERE rule_type = 'boost' AND is_active = 1
                  AND ((pattern_type = 'company' AND pattern_key = ?)
                    OR (pattern_type = 'lane' AND pattern_key = ?)
                    OR (pattern_type = 'lane_h1b' AND pattern_key = ?))
            """, (company, lane, f"{lane}|{flag}"))
            if updated.rowcount > 0:
                stats["rules_strengthened"] += updated.rowcount

            # Learn interaction weights: if lane + h1b_flag both fired, strengthen their bond
            self._learn_interaction("lane", "h1b_flag", positive=True)
            self._learn_interaction("company", "h1b_flag", positive=True)
            stats["interactions_learned"] += 2

        self.conn.commit()
        self._rules_cache = None
        self._interaction_cache = None
        if any(v > 0 for v in stats.values()):
            logger.info(f"Negative pattern mining: {stats}")
        return stats

    def _learn_interaction(self, pattern_a: str, pattern_b: str, positive: bool):
        """Update interaction weight between two pattern types.

        Bayesian-style update: positive feedback increases strength,
        negative decreases it.
        """
        existing = self.conn.execute(
            "SELECT interaction_strength, samples FROM pattern_weights "
            "WHERE pattern_type_a = ? AND pattern_type_b = ?",
            (pattern_a, pattern_b),
        ).fetchone()

        delta = 0.05 if positive else -0.03

        if existing:
            strength, samples = existing
            new_strength = (strength * samples + delta) / (samples + 1)
            self.conn.execute(
                "UPDATE pattern_weights SET interaction_strength = ?, samples = samples + 1, "
                "updated_at = datetime('now') WHERE pattern_type_a = ? AND pattern_type_b = ?",
                (new_strength, pattern_a, pattern_b),
            )
        else:
            self.conn.execute(
                "INSERT INTO pattern_weights (pattern_type_a, pattern_type_b, "
                "interaction_strength, samples) VALUES (?,?,?,1)",
                (pattern_a, pattern_b, delta),
            )
