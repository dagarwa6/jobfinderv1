from __future__ import annotations

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


class GreenhouseScraper(BaseScraper):
    platform = "greenhouse"
    base_delay = 1.5

    async def fetch_jobs(self, company: dict) -> list[RawJob]:
        token = company["token"]
        name = company.get("name", token)

        url = BASE_URL.format(token=token)
        data = await self.fetch_with_retry(url, params={"content": "true"})
        if not data:
            logger.warning(f"[greenhouse] No data for {name} ({token})")
            return []

        jobs_data = data.get("jobs", [])
        logger.info(f"[greenhouse] {name}: {len(jobs_data)} postings")

        results = []
        for j in jobs_data:
            try:
                desc_html = j.get("content", "") or ""
                desc_text = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True)

                location_raw = j.get("location", {}).get("name", "") if isinstance(j.get("location"), dict) else ""

                posted_str = j.get("updated_at") or j.get("first_published_at", "")
                posted_at = None
                if posted_str:
                    try:
                        posted_at = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                apply_url = j.get("absolute_url", "")

                raw = RawJob(
                    source_platform=self.platform,
                    company_token=token,
                    company_name=name,
                    external_id=str(j.get("id", "")),
                    title=j.get("title", ""),
                    location_raw=location_raw,
                    description_html=desc_html,
                    description_text=desc_text,
                    posted_at=posted_at,
                    apply_url=apply_url,
                    metadata={"departments": [d.get("name", "") for d in j.get("departments", [])]},
                )
                results.append(raw)
            except Exception as e:
                logger.error(f"[greenhouse] Error parsing job from {name}: {e}")

        return results
