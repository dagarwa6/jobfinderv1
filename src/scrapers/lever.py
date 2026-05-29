from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{site}"


class LeverScraper(BaseScraper):
    platform = "lever"
    base_delay = 1.5

    async def fetch_jobs(self, company: dict) -> list[RawJob]:
        site = company["site"]
        name = company.get("name", site)

        data = await self.fetch_with_retry(BASE_URL.format(site=site))
        if not data:
            logger.warning(f"[lever] No data for {name} ({site})")
            return []

        if not isinstance(data, list):
            logger.warning(f"[lever] Unexpected response type for {name}: {type(data)}")
            return []

        logger.info(f"[lever] {name}: {len(data)} postings")
        results = []

        for j in data:
            try:
                desc_html = j.get("descriptionPlain", "") or j.get("description", "") or ""
                desc_text = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True) if "<" in desc_html else desc_html

                lists = j.get("lists", [])
                for lst in lists:
                    desc_text += " " + lst.get("text", "") + " " + " ".join(
                        BeautifulSoup(item.get("content", ""), "lxml").get_text(separator=" ", strip=True)
                        for item in lst.get("items", []) if isinstance(item, dict)
                    )

                location = j.get("categories", {}).get("location", "") if isinstance(j.get("categories"), dict) else ""
                workplace = j.get("workplaceType", "")

                posted_at = None
                created_at = j.get("createdAt")
                if created_at:
                    try:
                        posted_at = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
                    except (ValueError, TypeError, OSError):
                        pass

                urls = j.get("urls", {})
                apply_url = urls.get("apply", "") or urls.get("show", "") or j.get("hostedUrl", "")

                raw = RawJob(
                    source_platform=self.platform,
                    company_token=site,
                    company_name=name,
                    external_id=j.get("id", ""),
                    title=j.get("text", ""),
                    location_raw=location,
                    description_html=desc_html,
                    description_text=desc_text,
                    posted_at=posted_at,
                    apply_url=apply_url,
                    workplace_type=workplace,
                    metadata={
                        "team": j.get("categories", {}).get("team", ""),
                        "department": j.get("categories", {}).get("department", ""),
                        "commitment": j.get("categories", {}).get("commitment", ""),
                    },
                )
                results.append(raw)
            except Exception as e:
                logger.error(f"[lever] Error parsing job from {name}: {e}")

        return results
