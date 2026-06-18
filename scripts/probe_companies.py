"""Probe candidate companies across Greenhouse / Lever / Ashby (no-auth APIs).

For each candidate token, tries all three platforms and reports which return
jobs. Prints ready-to-paste JSON for companies.json grouped by platform.

Focus: H1B-sponsoring consulting firms + companies hiring heavily (June 2026).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Candidate tokens to try. We try each across all 3 platforms; the platform
# that returns jobs wins. Tokens are lowercased ATS slugs (best guesses).
CANDIDATES = [
    # --- Consulting (H1B sponsors, analyst/strategy/transformation roles) ---
    "slalom", "slalomconsulting", "slalombuild",
    "zsassociates", "zs",
    "guidehouse",
    "westmonroe", "westmonroepartners",
    "huronconsultinggroup", "huron",
    "fticonsulting", "fti",
    "kearney", "atkearney",
    "oliverwyman",
    "lek", "lekconsulting",
    "alvarezandmarsal", "alvarezmarsal",
    "thoughtworks",
    "publicissapient",
    "pointb",
    "credera",
    "siliconvalleybank",
    "cognizant",
    "capgemini",
    "infosys", "infosysconsulting",
    "grantthornton",
    "rsm", "rsmus",
    "bdo",
    "crowe",
    "claritypartners",
    "trinity", "trinitylifesciences",
    "analysisgroup",
    "cornerstoneresearch",
    "charlesriverassociates", "crai",
    "bcg", "bostonconsdefault",
    "kornferry",
    "gartner",
    "forrester",
    # --- Tech / finance hiring heavily (June 2026), H1B-friendly ---
    "databricks",
    "scaleai", "scale",
    "figma",
    "gitlab",
    "hashicorp",
    "confluent",
    "datadog",
    "mongodb",
    "samsara",
    "chime",
    "sofi",
    "robinhood",
    "coinbase",
    "anduril",
    "cadence",
    "synopsys",
    "rippling",
    "deel",
    "mercury",
    "vanta",
    "wiz",
    "crowdstrike",
    "cloudflare",
    "databricksinc",
    "doordash",
    "airbnb",
    "reddit",
    "dropbox",
    "twilio",
    "asana",
    "amplitude",
    "segment",
    "benchling",
    "airtable",
    "grammarly",
    "scribd",
    "faire",
    "gemini",
    "kraken",
    "circle",
    "addepar",
    "carta",
    "betterment",
]

PLATFORMS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
}


async def try_platform(client, platform, url):
    try:
        r = await client.get(url, timeout=12.0)
        if r.status_code != 200:
            return None
        data = r.json()
        if platform == "greenhouse":
            n = len(data.get("jobs", []))
        elif platform == "lever":
            n = len(data) if isinstance(data, list) else 0
        else:  # ashby
            n = len(data.get("jobs", []))
        return n if n > 0 else None
    except (httpx.HTTPError, ValueError):
        return None


async def probe(client, token):
    for platform, tmpl in PLATFORMS.items():
        n = await try_platform(client, platform, tmpl.format(t=token))
        if n:
            return platform, n
    return None, 0


async def main():
    hits = {"greenhouse": [], "lever": [], "ashby": []}
    async with httpx.AsyncClient(
        follow_redirects=True, headers={"User-Agent": "JobScraper/1.0"}
    ) as client:
        sem = asyncio.Semaphore(8)

        async def one(token):
            async with sem:
                platform, n = await probe(client, token)
                if platform:
                    print(f"  OK   {token:<28} -> {platform} ({n} jobs)")
                    hits[platform].append((token, n))
                else:
                    print(f"  --   {token:<28} (no match)")

        await asyncio.gather(*(one(t) for t in CANDIDATES))

    print("\n=== Validated, grouped by platform (paste into companies.json) ===")
    for platform in ("greenhouse", "lever", "ashby"):
        toks = sorted(hits[platform])
        if toks:
            print(f"\n# {platform}: {len(toks)} new")
            print(json.dumps([t for t, _ in toks]))


if __name__ == "__main__":
    asyncio.run(main())
