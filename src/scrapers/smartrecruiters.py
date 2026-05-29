from __future__ import annotations

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from src.models import RawJob
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings"


class SmartRecruitersScraper(BaseScraper):
    platform = "smartrecruiters"
    base_delay = 2.0  # more conservative, 10 req/sec limit

    async def fetch_jobs(self, company: dict) -> list[RawJob]:
        company_id = company["id"]
        name = company.get("name", company_id)

        all_postings = []
        offset = 0
        limit = 100

        while True:
            data = await self.fetch_with_retry(
                BASE_URL.format(company_id=company_id),
                params={"limit": limit, "offset": offset},
            )
            if not data:
                break

            content = data.get("content", [])
            if not content:
                break

            all_postings.extend(content)
            total = data.get("totalFound", 0)

            offset += limit
            if offset >= total:
                break
            await self.throttle()

        logger.info(f"[smartrecruiters] {name}: {len(all_postings)} postings")
        results = []

        for j in all_postings:
            try:
                name_field = j.get("name", "")
                location_data = j.get("location", {})
                city = location_data.get("city", "")
                region = location_data.get("region", "")
                country = location_data.get("country", "")
                location_raw = ", ".join(filter(None, [city, region, country]))

                desc_html = j.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "") or ""
                desc_text = BeautifulSoup(desc_html, "lxml").get_text(separator=" ", strip=True) if desc_html else ""

                qualifications = j.get("jobAd", {}).get("sections", {}).get("qualifications", {}).get("text", "") or ""
                if qualifications:
                    desc_text += " " + BeautifulSoup(qualifications, "lxml").get_text(separator=" ", strip=True)

                posted_at = None
                released = j.get("releasedDate", "")
                if released:
                    try:
                        posted_at = datetime.fromisoformat(released.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                apply_url = j.get("ref", "") or j.get("company", {}).get("identifier", "")
                job_id = j.get("id", "") or j.get("uuid", "")
                if not apply_url:
                    apply_url = f"https://jobs.smartrecruiters.com/{company_id}/{job_id}"

                raw = RawJob(
                    source_platform=self.platform,
                    company_token=company_id,
                    company_name=name,
                    external_id=str(job_id),
                    title=name_field,
                    location_raw=location_raw,
                    description_html=desc_html,
                    description_text=desc_text,
                    posted_at=posted_at,
                    apply_url=apply_url,
                    metadata={
                        "department": j.get("department", {}).get("label", ""),
                        "typeOfEmployment": j.get("typeOfEmployment", {}).get("label", ""),
                    },
                )
                results.append(raw)
            except Exception as e:
                logger.error(f"[smartrecruiters] Error parsing job from {name}: {e}")

        return results
