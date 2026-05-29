"""Probe candidate iCIMS tenants and report which serve job listings.

Each candidate is a (subdomain, display_name) tuple; we hit
https://{subdomain}.icims.com/jobs/search and count parseable job hrefs.

Prints a JSON snippet at the end ready to paste into config/companies.json
under "icims".
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


# (subdomain, name). Subdomains follow `careers-{tenant}` for most companies
# but some use `{tenant}careers`, `jobs-{tenant}`, or other variants.
CANDIDATES = [
    # --- Federal contractors / defense ---
    ("careers-peraton", "Peraton"),
    ("careers-caci", "CACI"),
    ("careers-mantech", "ManTech"),
    ("careers-icf", "ICF International"),
    ("careers-saic", "SAIC"),
    ("careers-leidos", "Leidos"),
    ("careers-boozallen", "Booz Allen (iCIMS)"),
    ("careers-engility", "Engility"),
    ("careers-batellememorial", "Battelle"),
    ("careers-l3harris", "L3Harris"),
    ("careers-northropgrumman", "Northrop Grumman"),
    ("careers-lockheedmartin", "Lockheed Martin"),
    ("careers-bae-systems-inc", "BAE Systems"),
    ("careers-cgifederal", "CGI Federal"),
    ("careers-vencore", "Vencore"),
    ("careers-mantech-international", "ManTech alt"),
    ("careers-noblis", "Noblis"),
    ("careers-aretumtechnologies", "Aretum"),
    ("careers-attainpartners", "Attain Partners"),
    ("careers-guidehouse", "Guidehouse"),

    # --- Big consulting / strategy ---
    ("careers-baincapital", "Bain Capital"),
    ("careers-aon", "Aon"),
    ("careers-wtwco", "Willis Towers Watson"),
    ("careers-marsh", "Marsh McLennan"),
    ("careers-ftiglobalsolutions", "FTI Consulting"),
    ("careers-protiviti", "Protiviti (iCIMS)"),

    # --- Healthcare ---
    ("careers-clevelandclinic", "Cleveland Clinic"),
    ("careers-mayoclinic", "Mayo Clinic"),
    ("careers-mountsinai", "Mount Sinai"),
    ("careers-pfizer", "Pfizer"),
    ("careers-merck", "Merck"),
    ("careers-abbott", "Abbott"),
    ("careers-novartis", "Novartis"),
    ("careers-jnj", "Johnson & Johnson"),
    ("careers-sanofi", "Sanofi"),

    # --- Financial services ---
    ("careers-fidelity", "Fidelity"),
    ("careers-tdameritrade", "TD Ameritrade"),
    ("careers-firstrepublic", "First Republic"),
    ("careers-blackrock", "BlackRock"),
    ("careers-stifel", "Stifel"),
    ("careers-bnymellon", "BNY Mellon"),
    ("careers-northerntrust", "Northern Trust"),

    # --- Tech / media ---
    ("careers-att", "AT&T"),
    ("careers-comcast", "Comcast"),
    ("careers-disney", "Disney (iCIMS)"),
    ("careers-nbcuniversal", "NBCUniversal"),
    ("careers-foxnews", "Fox News"),
    ("careers-verizon", "Verizon"),
    ("careers-spotify", "Spotify (iCIMS)"),
    ("careers-spectrum", "Spectrum"),

    # --- Hospitality / retail ---
    ("careers-marriott", "Marriott"),
    ("careers-hilton", "Hilton"),
    ("careers-hyatt", "Hyatt"),
    ("careers-wynn", "Wynn Resorts"),
    ("careers-mgmresorts", "MGM Resorts"),
    ("careers-bestbuy", "Best Buy"),
    ("careers-roosters", "Hooters"),
    ("careers-darden", "Darden Restaurants"),

    # --- Manufacturing / industrial ---
    ("careers-caterpillar", "Caterpillar"),
    ("careers-cummins", "Cummins"),
    ("careers-deere", "John Deere"),
    ("careers-ge-aerospace", "GE Aerospace"),
    ("careers-flowserve", "Flowserve"),
    ("careers-emerson", "Emerson"),
    ("careers-rockwellautomation", "Rockwell Automation"),
]


async def probe(subdomain: str, client: httpx.AsyncClient) -> tuple[int, int]:
    """Return (http_status, total_jobs)."""
    url = f"https://{subdomain}.icims.com/jobs/search?ss=1&pr=0&in_iframe=1"
    try:
        r = await client.get(url, timeout=15.0)
        if r.status_code != 200:
            return r.status_code, -1
        # count unique job IDs (loose pattern — slugs vary)
        ids = set(re.findall(r"/jobs/(\d+)/", r.text))
        return 200, len(ids)
    except httpx.HTTPError:
        return -1, -1


SUBDOMAIN_PATTERNS = [
    "careers-{t}",   # careers-peraton
    "{t}",           # peraton
    "{t}-careers",   # peraton-careers
    "{t}careers",    # peratoncareers
    "jobs-{t}",      # jobs-peraton
    "careers.{t}",   # careers.peraton (note: this would need full domain, see fallback)
]


async def main():
    accepted: list[dict] = []
    failed: list[str] = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 JobScraper/1.0"},
        timeout=15.0,
    ) as client:
        for subdomain, name in CANDIDATES:
            # `subdomain` here is the "tenant" stem (e.g., "peraton").
            # Try each subdomain pattern until one returns jobs.
            tenant_stem = subdomain.replace("careers-", "", 1)
            found = False
            tried = []
            for pat in SUBDOMAIN_PATTERNS:
                if "{t}" not in pat:
                    continue
                candidate = pat.format(t=tenant_stem)
                if candidate.startswith("careers."):
                    continue  # full-domain redirects, skip for now
                tried.append(candidate)
                status, total = await probe(candidate, client)
                if status == 200 and total > 0:
                    print(f"  OK   {name:<32} {candidate:<40} {total} jobs")
                    accepted.append({"tenant": candidate, "name": name})
                    found = True
                    break
            if not found:
                print(f"  --   {name:<32} (tried {len(tried)} patterns)")
                failed.append(name)

    print()
    print(f"Validated: {len(accepted)} / {len(CANDIDATES)}")
    print()
    print('--- Paste under "icims" in config/companies.json ---')
    print(json.dumps(accepted, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
