"""Probe a list of candidate Workday tenants and report which ones serve jobs.

Hits the listing endpoint with offset=0/limit=1 and reports:
  - HTTP status
  - total job count (if any)

Run:
  .venv/bin/python scripts/probe_workday.py

Prints a JSON snippet at the end ready to paste into config/companies.json
for tenants that returned >0 jobs.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


# Curated candidate list. Format: (tenant, wd, site, display_name)
# Multiple wd/site combos per tenant are tried in order until one works.
CANDIDATES = [
    # --- Big banks / financial services ---
    ("wellsfargo",   ["wd1"], ["wellsfargojobs"],                  "Wells Fargo"),
    ("bankofamerica",["wd1"], ["Lateral-Experienced"],             "Bank of America"),
    ("citi",         ["wd5"], ["2"],                               "Citi"),
    ("morganstanley",["wd5"], ["External"],                        "Morgan Stanley"),
    ("aexp",         ["wd1"], ["AmericanExpressCareers", "jobs"], "American Express"),
    ("schwab",       ["wd5"], ["SchwabCareers"],                   "Charles Schwab"),
    ("usaa",         ["wd1"], ["usaajobs"],                        "USAA"),
    ("ally",         ["wd1"], ["Ally_Careers"],                    "Ally Financial"),
    ("synchrony",    ["wd1"], ["Careers"],                         "Synchrony Financial"),
    ("nationwide",   ["wd1"], ["careers"],                         "Nationwide Insurance"),
    ("statefarm",    ["wd1"], ["careers"],                         "State Farm"),
    ("allstate",     ["wd5"], ["Allstate_Careers"],                "Allstate"),
    ("metlife",      ["wd5"], ["External"],                        "MetLife"),
    ("prudential",   ["wd1"], ["PRUCareers"],                      "Prudential"),
    ("aig",          ["wd1"], ["AIG"],                             "AIG"),
    ("travelers",    ["wd5"], ["External"],                        "Travelers"),

    # --- Healthcare ---
    ("uhg",          ["wd5"], ["External"],                        "UnitedHealth Group"),
    ("elevancehealth",["wd1"], ["ANT"],                            "Elevance Health"),
    ("cigna",        ["wd5"], ["cigna_careers"],                   "Cigna"),
    ("humana",       ["wd1"], ["Humana_External_Career_Site"],     "Humana"),
    ("hcahealthcare",["wd1"], ["HCA_External"],                    "HCA Healthcare"),
    ("kp",           ["wd1"], ["External"],                        "Kaiser Permanente"),
    ("mckesson",     ["wd5"], ["External_Careers"],                "McKesson"),

    # --- Big tech / enterprise software ---
    ("adobe",        ["wd5"], ["external_experienced"],            "Adobe"),
    ("salesforce",   ["wd12"], ["External_Career_Site"],           "Salesforce"),
    ("cisco",        ["wd5"], ["external_career_site"],            "Cisco"),
    ("hpe",          ["wd1"], ["jobs"],                            "Hewlett Packard Enterprise"),
    ("hp",           ["wd1"], ["ExternalCareerSite"],              "HP Inc"),
    ("dell",         ["wd1"], ["External"],                        "Dell Technologies"),
    ("nvidia",       ["wd5"], ["NVIDIAExternalCareerSite"],        "NVIDIA"),
    ("workday",      ["wd5"], ["Workday"],                         "Workday Inc"),
    ("vmware",       ["wd1"], ["VMware"],                          "VMware"),
    ("intuit",       ["wd12"], ["IntuitExternalCareerSite"],       "Intuit"),
    ("paypal",       ["wd1"], ["jobs"],                            "PayPal"),
    ("ebay",         ["wd5"], ["ebay_careers"],                    "eBay"),

    # --- Retail / CPG ---
    ("target",       ["wd5"], ["targetcareers"],                   "Target"),
    ("bestbuy",      ["wd1"], ["External"],                        "Best Buy"),
    ("lowes",        ["wd1"], ["External"],                        "Lowe's"),
    ("costco",       ["wd5"], ["costco_careers"],                  "Costco"),
    ("kroger",       ["wd5"], ["Kroger_Careers"],                  "Kroger"),
    ("coke",         ["wd1"], ["coke_careers"],                    "Coca-Cola"),
    ("pepsico",      ["wd3"], ["PepsiCo_Career_Site"],             "PepsiCo"),
    ("pg",           ["wd5"], ["pgcareers"],                       "Procter & Gamble"),
    ("unilever",     ["wd3"], ["Unilever_External_Careers"],       "Unilever"),
    ("nike",         ["wd1"], ["nikecareers"],                     "Nike"),
    ("estee",        ["wd1"], ["ELCareers"],                       "Estée Lauder"),

    # --- Federal contractors / defense ---
    ("lockheedmartin",["wd1"], ["External"],                       "Lockheed Martin"),
    ("ngc",          ["wd1"], ["NGCExternal"],                     "Northrop Grumman"),
    ("rtx",          ["wd1"], ["REC_RTX_Ext_Gateway"],             "RTX (Raytheon)"),
    ("l3harris",     ["wd1"], ["l3harris"],                        "L3Harris"),
    ("saic",         ["wd1"], ["SAIC_External"],                   "SAIC"),
    ("gdit",         ["wd5"], ["External_Career_Site_GDIT"],       "General Dynamics IT"),
    ("mantech",      ["wd1"], ["ManTech"],                         "ManTech"),
    ("peraton",      ["wd1"], ["Peraton_Careers"],                 "Peraton"),
    ("icf",          ["wd5"], ["ICF_External"],                    "ICF International"),

    # --- Big 4 / consulting ---
    ("deloitte",     ["wd103"], ["Experienced"],                   "Deloitte US"),
    ("kpmg",         ["wd1"], ["KPMGCareers"],                     "KPMG US"),
    ("ey",           ["wd103"], ["EYCareers"],                     "EY"),
    ("accenture",    ["wd103"], ["AccentureCareers"],              "Accenture"),
    ("crowe",        ["wd1"], ["External"],                        "Crowe"),
    ("protiviti",    ["wd5"], ["External_Careers"],                "Protiviti"),
    ("bdo",          ["wd1"], ["BDOUSACareers"],                   "BDO USA"),

    # --- Telecom / utilities ---
    ("att",          ["wd1"], ["ATT"],                             "AT&T"),
    ("verizon",      ["wd5"], ["VerizonCareers"],                  "Verizon"),
    ("tmobile",      ["wd1"], ["External"],                        "T-Mobile"),

    # --- Other interesting large H1B sponsors ---
    ("ge",           ["wd1"], ["GE_ExternalSite"],                 "General Electric"),
    ("honeywell",    ["wd1"], ["Honeywell"],                       "Honeywell"),
    ("3m",           ["wd1"], ["3M_External_Career_Site"],         "3M"),
    ("emerson",      ["wd1"], ["Emerson_Careers"],                 "Emerson"),
    ("amd",          ["wd1"], ["External"],                        "AMD"),
    ("micron",       ["wd1"], ["External"],                        "Micron"),
    ("appliedmaterials",["wd1"], ["External"],                     "Applied Materials"),
    ("lamresearch", ["wd1"], ["External"],                         "Lam Research"),
]


async def probe(tenant: str, wd: str, site: str, client: httpx.AsyncClient) -> tuple[int, int]:
    """Return (http_status, total_jobs). total_jobs=-1 on parse failure."""
    url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    body = {"appliedFacets": {}, "searchText": "", "limit": 1, "offset": 0}
    try:
        resp = await client.post(url, json=body, timeout=15.0)
        if resp.status_code != 200:
            return resp.status_code, -1
        data = resp.json()
        return 200, int(data.get("total", 0))
    except (httpx.HTTPError, ValueError):
        return -1, -1


async def main():
    accepted: list[dict] = []
    failed: list[str] = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "JobScraper/1.0"},
        timeout=15.0,
    ) as client:
        for tenant, wds, sites, name in CANDIDATES:
            found = False
            for wd in wds:
                for site in sites:
                    status, total = await probe(tenant, wd, site, client)
                    label = f"{name:<32} {tenant}.{wd}/{site}"
                    if status == 200 and total > 0:
                        print(f"  OK   {label:<70} {total} jobs")
                        accepted.append({"tenant": tenant, "wd": wd, "site": site, "name": name})
                        found = True
                        break
                    elif status == 200 and total == 0:
                        print(f"  ZERO {label:<70} 0 jobs (live but empty)")
                    else:
                        print(f"  --   {label:<70} HTTP {status}")
                if found:
                    break
            if not found:
                failed.append(name)

    print()
    print(f"Validated: {len(accepted)} / {len(CANDIDATES)}")
    if failed:
        print(f"Failed:    {', '.join(failed)}")
    print()
    print("--- Paste this into config/companies.json under \"workday\": ---")
    print(json.dumps(accepted, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
