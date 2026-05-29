#!/usr/bin/env python3
"""Bulk-test company tokens against Greenhouse, Lever, and Ashby APIs."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

COMPANIES = [
    # Tech/SaaS
    "dropbox", "hubspot", "notion", "airtable", "linear", "vercel", "supabase",
    "retool", "zapier", "calendly", "loom", "miro", "canva", "grammarly",
    "duolingo", "coursera", "zoom", "docusign", "box", "splunk", "dynatrace",
    "datadog", "newrelic", "hashicorp", "confluent", "cockroachlabs",
    "planetscale", "neon", "dbt", "fivetran", "airbyte", "census", "hightouch",
    "segment", "amplitude", "mixpanel", "heap", "fullstory", "hotjar",
    "optimizely", "launchdarkly", "split", "harness", "circleci", "gitlab",
    "github", "atlassian", "monday", "clickup", "smartsheet", "wrike",
    # Fintech
    "coinbase", "ripple", "circle", "sofi", "betterment", "wealthfront",
    "acorns", "public", "nerdwallet", "creditkarma", "paypal", "wise",
    "remitly", "flywire", "bill", "tipalti", "coupa", "navan", "expensify",
    # Cybersecurity
    "crowdstrike", "paloaltonetworks", "fortinet", "sailpoint", "cyberark",
    "beyondtrust", "tenable", "rapid7", "qualys", "varonis", "proofpoint",
    "mimecast", "abnormalsecurity", "sentinelone", "trellix",
    "recorded-future", "wiz", "orca", "lacework", "snyk", "aquasec", "sysdig",
    "veracode", "checkmarx",
    # Consulting
    "thoughtworks", "capgemini", "slalom",
    # Healthcare Tech
    "veeva", "hims", "cerebral", "lyra", "springhealth", "modernhealth",
    "headspace", "calm", "noom", "oura", "whoop", "tempus", "flatiron",
    # Defense/Gov
    "anduril", "primer", "maxar", "planet",
    # E-commerce/Retail
    "shopify", "bigcommerce", "bolt", "klarna", "afterpay", "chargebee",
    "recurly", "zuora", "paddle", "adyen", "checkout",
    # Real Estate
    "zillow", "redfin", "compass", "opendoor", "offerpad", "fundrise",
    # HR/People
    "rippling", "deel", "remote", "oyster", "lattice", "cultureamp",
    "betterworks", "qualtrics", "medallia", "typeform",
    # Additional well-known companies
    "snap", "uber", "doordash", "grubhub", "instacart", "lyft",
    "pinterest", "reddit", "twitter", "meta", "netflix", "spotify",
    "robinhood", "chime", "plaid", "marqeta", "toast", "square",
    "cloudflare", "twilio", "sendgrid", "postman", "elastic",
    "mongodb", "couchbase", "redis", "cockroach-labs", "timescale",
    "databricks", "snowflake", "dbt-labs", "fivetran",
    "pagerduty", "victorops", "opsgenie", "statuspage",
    "figma", "invision", "sketch", "abstract", "zeplin",
    "intercom", "drift", "zendesk", "freshworks", "helpscout",
    "sentry", "bugsnag", "rollbar", "logrocket",
    "auth0", "onelogin", "jumpcloud",
    "contentful", "contentstack", "sanity", "strapi",
    "algolia", "elasticsearch", "meilisearch",
    "vercel", "netlify", "render", "railway",
    "lemonade", "hippo", "root", "metromile",
    "benchling", "ginkgo", "zymergen",
    "relativity", "everlaw", "casetext",
    "gusto", "justworks", "trinet",
    "braze", "iterable", "customer-io", "sendbird",
    "clearbit", "zoominfo", "apollo-io", "outreach", "salesloft",
    "gong", "chorus", "clari", "revenue",
    "weave", "podium", "birdeye", "reputation",
    "vanta", "drata", "secureframe", "laika",
    "notion", "coda", "almanac",
    "loom", "vidyard", "wistia",
    "calendly", "chili-piper", "kronologic",
    "ironclad", "docusign", "pandadoc", "conga",
    "costar", "yardi", "realpage", "appfolio",
    "procore", "plangrid", "buildertrend",
    "carta", "shareworks", "capshare",
    "navan", "brex", "ramp", "airbase",
    "watershed", "persefoni", "sweepboard",
    "masterclass", "skillshare", "pluralsight",
    "webflow", "squarespace", "wix",
    "airtable", "smartsheet", "coda",
    "upwork", "fiverr", "toptal",
    "glassdoor", "lever", "greenhouse",
    "applovin", "unity", "ironsource",
    "niantic", "roblox", "epicgames",
    "scale", "labelbox", "v7labs",
    "weights-and-biases", "neptune", "mlflow",
    "huggingface", "openai", "anthropic", "cohere",
    "jasper", "copy-ai", "writer",
    "runway", "stability", "midjourney",
    "cursor", "replit", "codespaces",
    "segment", "rudderstack", "snowplow",
    "stytch", "clerk", "descope",
    "neon", "supabase", "planetscale", "fauna",
    "temporal", "inngest", "trigger-dev",
]

# Deduplicate
COMPANIES = list(dict.fromkeys(COMPANIES))

APIS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}


async def test_token(client, platform, url_template, token):
    url = url_template.format(token=token)
    try:
        r = await client.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if platform == "greenhouse":
                count = len(data.get("jobs", []))
            elif platform == "lever":
                count = len(data) if isinstance(data, list) else 0
            elif platform == "ashby":
                count = len(data.get("jobs", []))
            else:
                count = 0
            if count > 0:
                return (token, count)
    except Exception:
        pass
    return None


async def discover_platform(platform, url_template, tokens):
    found = []
    async with httpx.AsyncClient(http2=True) as client:
        # Process in batches of 5 with 0.5s between batches
        batch_size = 5
        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i + batch_size]
            tasks = [test_token(client, platform, url_template, t) for t in batch]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r:
                    found.append(r)
                    print(f"  ✓ {platform}/{r[0]}: {r[1]} jobs")
            await asyncio.sleep(0.5)
    return found


async def main():
    print(f"Testing {len(COMPANIES)} company tokens across 3 platforms...\n")
    results = {}

    for platform, url_template in APIS.items():
        print(f"\n=== {platform.upper()} ===")
        found = await discover_platform(platform, url_template, COMPANIES)
        results[platform] = [{"token": t, "jobs": c} for t, c in sorted(found, key=lambda x: -x[1])]
        print(f"  Found {len(found)} valid boards")

    # Save
    out_path = Path(__file__).parent / "discovered_companies.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out_path}")

    total = sum(len(v) for v in results.values())
    print(f"\nTotal valid boards: {total}")
    for p, v in results.items():
        print(f"  {p}: {len(v)}")


if __name__ == "__main__":
    asyncio.run(main())
