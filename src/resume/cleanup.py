"""Resume cleanup — delete tailored PDFs for jobs already applied to.

Keeps the output/resumes/ directory from growing without bound. Resumes are
matched to jobs via the resume_cache.json (job_id -> file) written by
src.resume.generate. Deleting a resume also prunes its cache entry so a
future pipeline run won't think it still exists.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_FILE = "resume_cache.json"


def _load_cache(resume_dir: Path) -> dict:
    cache_path = resume_dir / CACHE_FILE
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(resume_dir: Path, cache: dict) -> None:
    (resume_dir / CACHE_FILE).write_text(json.dumps(cache, indent=2))


def cleanup_by_job_ids(
    job_ids: list[int],
    output_dir: Path | str,
) -> dict:
    """Delete resume PDFs whose cache entry matches any of the given job_ids.

    Args:
        job_ids: Job IDs (from the dashboard) whose resumes should be removed.
        output_dir: Output dir containing the resumes/ subfolder.

    Returns:
        {"deleted": int, "files": [...], "missing": [...]} summary.
    """
    resume_dir = Path(output_dir) / "resumes"
    if not resume_dir.exists():
        return {"deleted": 0, "files": [], "missing": []}

    wanted = {int(j) for j in job_ids}
    cache = _load_cache(resume_dir)
    generated: dict = cache.get("generated", {})

    deleted_files: list[str] = []
    missing: list[int] = []
    remaining = dict(generated)

    # Map job_id -> cache key(s)
    for key, meta in generated.items():
        if not isinstance(meta, dict):
            continue
        jid = meta.get("job_id")
        if jid is None or int(jid) not in wanted:
            continue
        fname = meta.get("file")
        if fname:
            fpath = resume_dir / fname
            if fpath.exists():
                fpath.unlink()
                deleted_files.append(fname)
            else:
                missing.append(int(jid))
        remaining.pop(key, None)

    if deleted_files or len(remaining) != len(generated):
        cache["generated"] = remaining
        _save_cache(resume_dir, cache)

    logger.info(
        f"Resume cleanup: deleted {len(deleted_files)} PDF(s) for "
        f"{len(wanted)} applied job(s)"
    )
    return {"deleted": len(deleted_files), "files": deleted_files, "missing": missing}


def cleanup_orphans(output_dir: Path | str, db) -> dict:
    """Delete resume PDFs for jobs no longer active in the DB.

    A safety-net sweep: any cached resume whose job_id is inactive or absent
    in the jobs table gets removed. Useful after postings expire.
    """
    resume_dir = Path(output_dir) / "resumes"
    if not resume_dir.exists():
        return {"deleted": 0, "files": []}

    cache = _load_cache(resume_dir)
    generated: dict = cache.get("generated", {})

    active_ids = {
        row[0]
        for row in db.conn.execute("SELECT id FROM jobs WHERE is_active = 1").fetchall()
    }

    orphan_ids = [
        int(meta["job_id"])
        for meta in generated.values()
        if isinstance(meta, dict) and meta.get("job_id") is not None
        and int(meta["job_id"]) not in active_ids
    ]
    if not orphan_ids:
        return {"deleted": 0, "files": []}
    return cleanup_by_job_ids(orphan_ids, output_dir)


def main() -> int:
    """CLI: python -m src.resume.cleanup <job_id> [job_id ...]"""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base_dir = Path(__file__).resolve().parent.parent.parent
    output_dir = base_dir / "output"

    args = [a for a in sys.argv[1:] if a.isdigit()]
    if not args:
        print("Usage: python -m src.resume.cleanup <job_id> [job_id ...]")
        return 1
    result = cleanup_by_job_ids([int(a) for a in args], output_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
