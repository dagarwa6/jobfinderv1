from __future__ import annotations

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://apply.workable.com/api/v3/accounts/{subdomain}/jobs"


class WorkableScraper(BaseScraper):
    platform = "workable"
    base_delay = 2.0

    async def fetch_jobs(self, company: dict) -> list[RawJob]:
        subdomain = company["subdomain"]
        name = company.get("name", subdomain)

        all_postings = []
        token = None

        while True:
            body = {"query": "", "location": []}
            if token:
                body["token"] = token

            data = await self.fetch_with_retry(
                BASE_URL.format(subdomain=subdomain),
                method="POST",
                json_body=body,
            )
            if not data:
                break

            results = data.get("results", [])
            if not results:
                break

            all_postings.extend(results)
            token = data.get("nextPage")
            if not token:
                break
            await self.throttle()

        logger.info(f"[workable] {name}: {len(all_postings)} postings")
        results = []

        for j in all_postings:
            try:
                title = j.get("title", "")
                location_raw = j.get("location", {}).get("location_str", "") if isinstance(j.get("location"), dict) else str(j.get("location", ""))
                workplace = j.get("location", {}).get("telecommuting", False) if isinstance(j.get("location"), dict) else False

                shortcode = j.get("shortcode", "")
                apply_url = f"https://apply.workable.com/{subdomain}/j/{shortcode}/"

                posted_at = None
                published = j.get("published_on") or j.get("created_at", "")
                if published:
                    try:
                        posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                desc_html = j.get("description", "") or ""
                req_html = j.get("requirements", "") or ""
                full_html = desc_html + " " + req_html
                desc_text = BeautifulSoup(full_html, "lxml").get_text(separator=" ", strip=True) if full_html.strip() else ""

                raw = RawJob(
                    source_platform=self.platform,
                    company_token=subdomain,
                    company_name=name,
                    external_id=shortcode or j.get("id", ""),
                    title=title,
                    location_raw=location_raw,
                    description_html=full_html,
                    description_text=desc_text,
                    posted_at=posted_at,
                    apply_url=apply_url,
                    workplace_type="remote" if workplace else "",
                    metadata={
                        "department": j.get("department", ""),
                    },
                )
                results.append(raw)
            except Exception as e:
                logger.error(f"[workable] Error parsing job from {name}: {e}")

        return results
