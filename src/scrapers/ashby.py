from __future__ import annotations

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"


class AshbyScraper(BaseScraper):
    platform = "ashby"
    base_delay = 1.5

    async def fetch_jobs(self, company: dict) -> list[RawJob]:
        board = company["board"]
        name = company.get("name", board)

        data = await self.fetch_with_retry(
            BASE_URL.format(board=board),
            params={"includeCompensation": "true"},
        )
        if not data:
            logger.warning(f"[ashby] No data for {name} ({board})")
            return []

        jobs_data = data.get("jobs", [])
        logger.info(f"[ashby] {name}: {len(jobs_data)} postings")
        results = []

        for j in jobs_data:
            try:
                if not j.get("isListed", True):
                    continue

                desc_html = j.get("descriptionHtml", "") or ""
                desc_plain = j.get("descriptionPlain", "") or ""
                desc_text = desc_plain or BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True)

                location = j.get("location", "") or ""
                if isinstance(location, dict):
                    location = location.get("name", "")

                posted_at = None
                published = j.get("publishedAt") or j.get("updatedAt", "")
                if published:
                    try:
                        posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                apply_url = j.get("jobUrl", "") or j.get("applyUrl", "")

                comp = j.get("compensation", {})
                salary_raw = None
                if comp:
                    salary_raw = f"{comp.get('compensationTierSummary', '')}"

                raw = RawJob(
                    source_platform=self.platform,
                    company_token=board,
                    company_name=name,
                    external_id=j.get("id", ""),
                    title=j.get("title", ""),
                    location_raw=location,
                    description_html=desc_html,
                    description_text=desc_text,
                    posted_at=posted_at,
                    apply_url=apply_url,
                    salary_raw=salary_raw,
                    workplace_type=j.get("employmentType", ""),
                    metadata={
                        "department": j.get("department", ""),
                        "team": j.get("team", ""),
                        "isRemote": j.get("isRemote", False),
                    },
                )
                results.append(raw)
            except Exception as e:
                logger.error(f"[ashby] Error parsing job from {name}: {e}")

        return results
