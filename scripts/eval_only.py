"""Evaluate existing jobs in the DB + regenerate dashboard/digest/CSV/resumes.

Skips the scrape step entirely. Useful when you want to re-score after
weights/prompt changes without paying for another full scrape.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from src.db import JobDB
from src.evaluator.scorer import (
    AIScorer,
    get_all_evaluated_jobs,
    get_unevaluated_jobs,
    init_eval_schema,
    save_evaluations,
)
from src.learning.learned_rules import LearnedRulesEngine
from src.learning.feedback_import import import_feedback_file
from src.apply.bookmarklet import generate_fill_js
from src.apply.profile import load_profile
from src.output.csv_export import export_csv
from src.output.dashboard import render_dashboard
from src.output.digest import render_digest
from src.resume.generate import generate_resumes


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="[%H:%M:%S]",
)
logger = logging.getLogger("eval_only")


async def main():
    cfg_dir = BASE_DIR / "config"
    with open(cfg_dir / "settings.toml", "rb") as f:
        settings = tomllib.load(f)

    db = JobDB(BASE_DIR / settings["output"]["db_path"])
    init_eval_schema(db)

    output_dir = BASE_DIR / settings["output"]["dashboard_dir"]
    feedback_path = output_dir / "feedback.json"
    import_feedback_file(db.conn, feedback_path, logger)

    learning_engine = LearnedRulesEngine(db.conn)
    rule_stats = learning_engine.mine_rules()
    if any(v > 0 for v in rule_stats.values()):
        logger.info(f"Learned rules updated: {rule_stats}")

    unevaluated = get_unevaluated_jobs(db)
    logger.info(f"Unevaluated jobs in DB: {len(unevaluated)}")

    if unevaluated:
        auto_skipped, boosted, to_evaluate = learning_engine.filter_for_eval(unevaluated)
        if auto_skipped:
            logger.info(f"Learned rules auto-skipped {len(auto_skipped)}")
            from src.evaluator.scorer import EvalResult
            save_evaluations(
                db,
                [
                    EvalResult(
                        job_id=j["id"],
                        global_score=0.0,
                        reasoning=f"Auto-skipped by learned rule: {j.get('_auto_skip_reason', 'unknown')}",
                        recommended_action="skip",
                    )
                    for j in auto_skipped
                ],
                model="learned_rules",
            )
        queue = boosted + to_evaluate
        if queue:
            logger.info(f"AI evaluating {len(queue)} jobs...")
            scorer = AIScorer(model="claude-haiku-4-5-20251001")
            results = await scorer.evaluate_batch(
                queue,
                concurrency=5,
                requests_per_minute=40,
                progress_callback=lambda d, t: logger.info(f"  {d}/{t}"),
            )
            save_evaluations(db, results, model=scorer.model)
            apply_n = sum(1 for r in results if r.recommended_action == "apply")
            cons_n = sum(1 for r in results if r.recommended_action == "consider")
            logger.info(f"Done: {apply_n} apply / {cons_n} consider / {len(results) - apply_n - cons_n} skip")

    # Regenerate outputs
    profile_path = cfg_dir / "applicant_profile.yml"
    if profile_path.exists():
        try:
            profile = load_profile(profile_path)
            (output_dir / "autofill.js").write_text(generate_fill_js(profile))
        except Exception as e:
            logger.warning(f"autofill js failed: {e}")

    jobs_for_output = get_all_evaluated_jobs(db)
    templates_dir = BASE_DIR / "templates"
    stats = {
        "total_fetched": len(jobs_for_output),
        "total_passed": len(jobs_for_output),
        "total_new": 0,
        "total_companies": len(set(j["company_name"] for j in jobs_for_output)),
    }
    dashboard_path = render_dashboard(jobs_for_output, stats, output_dir, templates_dir)
    logger.info(f"Dashboard: {dashboard_path}")
    digest_path = render_digest(jobs_for_output, stats, output_dir)
    logger.info(f"Digest: {digest_path}")
    csv_path = export_csv(jobs_for_output, output_dir)
    logger.info(f"CSV: {csv_path}")

    master_path = cfg_dir / "master_resume.yml"
    if master_path.exists():
        resume_paths = generate_resumes(
            jobs_for_output,
            master_path=master_path,
            output_dir=output_dir,
            actions=("apply",),
            max_resumes=25,
        )
        logger.info(f"Resumes generated: {len(resume_paths)}")

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
