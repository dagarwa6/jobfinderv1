#!/usr/bin/env python3
"""Discover 2000+ company boards by testing massive slug lists at high concurrency."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

PROJECT = Path(__file__).resolve().parent.parent

# Load existing
with open(PROJECT / "config/companies.json") as f:
    existing = json.load(f)
all_known = set()
for p in ["greenhouse", "lever", "ashby"]:
    for c in existing.get(p, []):
        all_known.add((c.get("token") or c.get("site") or c.get("board") or "").lower())


def generate_slugs():
    """Generate thousands of potential company slugs."""
    # Base company names — comprehensive across all sectors
    companies = [
        # S&P 500 / Fortune 500 (common slug patterns)
        "3m", "abbott", "abbvie", "accenture", "activision", "adobe", "adp", "aetna",
        "aflac", "agilent", "airbnb", "akamai", "albertsons", "alcoa", "align", "allegion",
        "allergan", "allstate", "alphabet", "altria", "amazon", "amd", "ameren", "amgen",
        "ametek", "amphenol", "analog-devices", "ansys", "anthem", "aon", "apa", "apple",
        "applied-materials", "aptiv", "arconic", "arista", "assurant", "at-t", "atmos",
        "autodesk", "autozone", "avalonbay", "avery", "avnet", "axon", "baker-hughes",
        "ball", "baxter", "becton-dickinson", "berkshire", "best-buy", "biogen", "bio-rad",
        "bio-techne", "blackberry", "blackrock", "block", "boeing", "booking",
        "borgwarner", "boston-properties", "boston-scientific", "bristol-myers", "broadcom",
        "broadridge", "brown-forman", "brunswick", "bunge", "burlington", "cadence",
        "caesars", "campbell", "cardinal-health", "carlisle", "carnival", "carrier",
        "catalent", "caterpillar", "cboe", "cdk", "celanese", "centene", "centerpoint",
        "ceridian", "cerner", "cf-industries", "charles-schwab", "charter", "chegg",
        "cheniere", "chevron", "chipotle", "church-dwight", "cigna", "cintas", "cisco",
        "citizens", "citrix", "clorox", "cloudflare", "cme", "cms", "cognizant",
        "colgate", "comcast", "comerica", "conagra", "conocophillips", "consolidated-edison",
        "constellation", "copart", "corning", "corteva", "costar", "costco", "coty",
        "crown-castle", "cummins", "cvs", "danaher", "darden", "davita", "deere",
        "dell", "delta", "dentsply", "devon-energy", "dexcom", "diamondback",
        "digital-realty", "discover", "dish", "disney", "docusign", "dollar-general",
        "dollar-tree", "dominion", "dominos", "dover", "dow", "draftkings", "dropbox",
        "duke-energy", "dupont", "eastman", "eaton", "ebay", "ecolab", "edison",
        "edwards", "electronic-arts", "eli-lilly", "emerson", "enphase", "entergy",
        "eog", "epam", "equifax", "equinix", "erie-indemnity", "essex", "estee-lauder",
        "etsy", "everest", "eversource", "exelon", "expedia", "expeditors", "extra-space",
        "exxonmobil", "f5", "factset", "fastenal", "fedex", "fidelity", "fifth-third",
        "first-republic", "first-solar", "firstenergy", "fiserv", "fleetcor", "flir",
        "fmc", "ford", "fortinet", "fortive", "fox", "franklin-templeton", "freeport",
        "frontier", "gartner", "ge", "generac", "general-dynamics", "general-mills",
        "general-motors", "genuine-parts", "gilead", "global-payments", "globe-life",
        "godaddy", "goldman-sachs", "grainger", "graybar", "halliburton", "hanesbrands",
        "hartford", "hasbro", "hca", "healthpeak", "henry-schein", "hershey", "hess",
        "hewlett-packard", "hilton", "hologic", "home-depot", "honeywell", "hormel",
        "host-hotels", "howmet", "hp", "hubspot", "humana", "huntington", "huntsman",
        "hyatt", "ibm", "idex", "idexx", "illumina", "incyte", "ingersoll-rand",
        "insulet", "intel", "intercontinental", "intuit", "intuitive-surgical",
        "invesco", "ipg", "iqvia", "iron-mountain", "jack-henry", "jacobs",
        "jabil", "johnson-controls", "johnson-johnson", "jpmorgan", "juniper",
        "kb-home", "kellogg", "keysight", "kforce", "kimberly-clark", "kimco",
        "kinder-morgan", "klarna", "knight-swift", "kohls", "kroger", "l3harris",
        "labcorp", "lamb-weston", "lancaster", "las-vegas-sands", "leidos", "lennar",
        "lennox", "levi", "liberty", "lincoln", "linde", "live-nation", "lkq",
        "lockheed-martin", "loews", "lowe", "lowes", "lpl-financial", "lululemon",
        "lyft", "lyondellbasell", "m-t-bank", "macy", "macys", "marathon", "markel",
        "marriott", "marsh", "martin-marietta", "masco", "masimo", "mastercard",
        "match", "maxim", "mccormick", "mcdonalds", "mcgraw-hill", "mckesson",
        "medtronic", "mercadolibre", "merck", "meta", "metlife", "mettler-toledo",
        "mgm", "microchip", "micron", "microsoft", "mid-america", "mohawk",
        "molina", "molson-coors", "mondelez", "mongodb", "monster", "moody",
        "morgan-stanley", "morningstar", "mosaic", "motorola", "msci", "murphy",
        "nasdaq", "national-instruments", "navient", "nch", "netapp", "netflix",
        "neurocrine", "new-york-life", "newmont", "news-corp", "nextera", "nike",
        "nisource", "nordstrom", "norfolk-southern", "northern-trust", "northrop",
        "northwest", "norton", "novartis", "now", "nucor", "nvidia", "nxp", "occidental",
        "okta", "old-dominion", "omnicom", "on-semiconductor", "oneok", "oracle",
        "organon", "oshkosh", "otis", "owens", "paccar", "packaging", "palo-alto",
        "paramount", "parker", "paychex", "paycom", "paypal", "pearson", "penske",
        "pentair", "peoples", "pepsico", "perkinelmer", "pfizer", "pg-e", "phillips",
        "pinnacle-west", "pinterest", "pioneer", "planet-fitness", "plaid", "pluralsight",
        "pnc", "polaris", "pool", "ppg", "principal", "procter-gamble", "progressive",
        "prologis", "prudential", "psa", "ptc", "public-storage", "pulte", "pvh",
        "qorvo", "qualcomm", "quanta", "quest", "ralph-lauren", "raymond-james",
        "raytheon", "realty-income", "regeneron", "regency", "regions", "renaissancere",
        "repligen", "republic", "resmed", "revvity", "reynolds", "ringcentral",
        "rivian", "robert-half", "roblox", "rockwell", "roku", "rollins", "roper",
        "ross", "royal-caribbean", "rpm", "ryder", "salesforce", "samsara",
        "sb-financial", "scanning", "schlumberger", "schwab", "seagate", "sealed-air",
        "sempra", "servicenow", "sherwin-williams", "simon-property", "skyworks",
        "snap", "snowflake", "solaredge", "southern", "southwest", "spectrum",
        "spirit", "splunk", "spotify", "square", "stanley", "starbucks", "state-street",
        "steelcase", "stryker", "svb", "synchrony", "synopsys", "sysco",
        "t-mobile", "t-rowe-price", "take-two", "tapestry", "target", "teladoc",
        "teleflex", "tenable", "tesla", "texas-instruments", "textron",
        "thermo-fisher", "tiffany", "toast", "toll-brothers", "tractor-supply",
        "trade-desk", "travelers", "trimble", "tripadvisor", "truist", "twilio",
        "twitter", "tyler", "tyson", "uber", "udr", "under-armour", "union-pacific",
        "united", "united-airlines", "united-rentals", "unitedhealth", "universal",
        "ups", "us-bank", "usaa", "valero", "veeva", "ventas", "veralto", "verizon",
        "verisk", "vertex", "vf", "viatris", "vici", "visa", "vistra", "vmware",
        "vulcan", "wabtec", "walgreens", "walmart", "warner", "waste-management",
        "waters", "wec", "wells-fargo", "welltower", "wendy", "west-pharmaceutical",
        "western-digital", "western-union", "westinghouse", "westrock", "weyerhaeuser",
        "whirlpool", "williams", "willis-towers", "wingstop", "wipro", "wolfspeed",
        "workday", "wyndham", "xcel", "xerox", "xilinx", "xpo", "xylem",
        "yahoo", "yeti", "yum", "zebra", "zenimax", "zillow", "zimmer", "zions",
        "zoetis", "zscaler", "zynga",

        # YC top companies (all batches)
        "airbnb", "stripe", "cruise", "instacart", "dropbox", "coinbase", "doordash",
        "gusto", "brex", "faire", "ginkgo", "deel", "fivetran", "amplitude",
        "webflow", "retool", "posthog", "cal-com", "supabase", "railway",
        "replit", "render", "inngest", "resend", "novu", "trigger-dev",
        "loops", "dub", "tinybird", "neon", "upstash", "turso",
        "unkey", "infisical", "depot", "airplane", "baseten",
        "modal", "replicate", "together", "anyscale", "weights-and-biases",
        "labelbox", "scale", "snorkel", "cleanlab", "humanloop",
        "arize", "whylabs", "fiddler", "gantry",
        "airbyte", "rudderstack", "hightouch", "census", "polytomic",
        "merge", "nango", "vessel", "finch", "kombo",
        "stytch", "clerk", "descope", "frontegg", "workos",
        "propel", "plaid", "unit", "treasury-prime", "column",
        "mercury", "ramp", "brex", "airbase",
        "vanta", "drata", "secureframe", "thoropass",
        "chainguard", "endor", "semgrep", "snyk",
        "wiz", "orca", "lacework", "aqua",
        "linear", "height", "plane", "attio",
        "clay", "bardeen", "browse-ai",
        "jasper", "copy-ai", "writer", "grammarly",
        "cursor", "codeium", "tabnine", "sourcegraph",
        "vercel", "netlify", "fly", "railway",
        "planetscale", "neon", "supabase", "turso",
        "temporal", "inngest", "trigger-dev",
        "resend", "loops", "postmark",
        "knock", "novu", "courier",
        "liveblocks", "partykit", "ably",
        "tinybird", "clickhouse", "timescale",
        "materialize", "risingwave",
        "buf", "kong", "solo",
        "tailscale", "teleport", "strongdm",
        "doppler", "infisical",
        "grafana", "honeycomb", "chronosphere",
        "sentry", "logrocket", "fullstory",
        "launchdarkly", "split", "statsig", "eppo",
        "circleci", "buildkite", "harness",
        "docker", "coder", "gitpod",
        "mintlify", "readme", "speakeasy",
        "stainless", "fern", "zuplo",
        "orb", "metronome", "amberflo", "lago",
        "stigg", "schematic",

        # Unicorns / Late stage startups
        "notion", "figma", "canva", "miro", "lucid",
        "airtable", "clickup", "monday", "asana", "smartsheet",
        "hubspot", "zendesk", "freshworks", "intercom",
        "braze", "iterable", "customer-io",
        "segment", "amplitude", "mixpanel", "heap", "pendo",
        "outreach", "salesloft", "gong", "clari",
        "zoominfo", "apollo", "clearbit", "cognism",
        "datadog", "newrelic", "dynatrace", "elastic",
        "snowflake", "databricks", "dbt-labs", "fivetran",
        "confluent", "redpanda", "aiven",
        "hashicorp", "terraform", "vault",
        "crowdstrike", "sentinelone", "paloaltonetworks",
        "okta", "sailpoint", "cyberark", "beyondtrust",
        "proofpoint", "mimecast", "abnormalsecurity",
        "tenable", "rapid7", "qualys", "varonis",
        "veeva", "flatiron", "tempus",
        "gusto", "rippling", "deel", "remote", "oyster",
        "lattice", "cultureamp", "leapsome",
        "greenhouse", "lever", "ashby", "gem", "eightfold",
        "toast", "square", "clover", "lightspeed",
        "shopify", "bigcommerce",
        "affirm", "klarna", "afterpay",
        "chargebee", "recurly", "zuora", "paddle",
        "contentful", "sanity", "strapi",
        "algolia", "typesense",
        "twilio", "sendgrid", "vonage", "bandwidth",
        "auth0", "onelogin", "jumpcloud",
        "1password", "bitwarden",
        "calendly", "chili-piper",
        "loom", "vidyard",
        "openai", "anthropic", "cohere", "mistral",
        "huggingface", "stability",
        "perplexity", "glean", "moveworks",
        "harvey", "casetext", "everlaw",
        "ironclad", "icertis", "pandadoc",
        "carta", "pulley",
        "benchling", "ginkgo",
        "relativity", "palantir", "anduril",
        "lemonade", "hippo", "root",
        "chime", "sofi", "robinhood", "acorns", "betterment",
        "coinbase", "ripple", "circle", "gemini",
        "wise", "remitly", "flywire",
        "zillow", "redfin", "compass", "opendoor",
        "waymo", "cruise", "aurora", "nuro", "zoox",
        "rivian", "lucid",
        "watershed", "persefoni", "patch",
        "hims", "ro", "noom", "oura", "whoop",
        "lyra", "springhealth", "modernhealth", "headspace", "calm",
        "alma", "headway", "rula", "grow-therapy", "sondermind",
        "doximity", "zocdoc",
        "oscar", "devoted", "clover-health",
        "procore", "buildertrend",
        "samsara", "motive", "verkada",
        "flexport", "project44",
        "carvana", "vroom", "turo",
        "bird", "lime",
        "duolingo", "coursera", "masterclass",
        "roblox", "niantic", "epic-games", "riot-games", "unity",
        "discord", "snap", "reddit", "pinterest",
        "spotify", "netflix",
        "substack", "medium",
        "automattic", "webflow", "squarespace",
        "upwork", "fiverr", "toptal",
        "navan", "expensify",
        "podium", "birdeye", "trustpilot",
        "eventbrite", "seatgeek",
        "sweetgreen", "cava", "shake-shack",
        "beyond-meat", "impossible-foods",
        "handshake", "ripplematch",
        "guild", "springboard",

        # Defense / Gov contractors
        "booz-allen", "boozallen", "leidos", "saic", "caci",
        "peraton", "mitre", "mantech", "parsons", "jacobs",
        "aecom", "kbr", "maximus", "icf", "serco", "amentum",
        "bah", "general-dynamics", "northrop-grumman",
        "l3harris", "textron", "huntington-ingalls",
        "science-applications", "raytheon-technologies",

        # Regional / niche tech
        "gitlab", "github", "bitbucket", "atlassian",
        "jira", "trello", "confluence",
        "zapier", "make", "tray", "workato",
        "postman", "insomnia",
        "grafana-labs", "elastic-co",
        "couchbase", "redis", "neo4j", "fauna",
        "cockroach-labs", "yugabyte", "singlestore",
        "starburst", "dremio", "rockset", "motherduck",
        "pinecone", "weaviate", "qdrant", "chroma",
        "langchain", "llamaindex",
        "dataiku", "alteryx", "hex", "deepnote", "mode",
        "domo", "sisense", "looker", "tableau",
        "thoughtspot", "sigma", "preset", "lightdash",
        "census", "hightouch", "rudderstack",
        "fivetran", "matillion", "stitch",
        "airbyte", "hevo", "rivery",
        "monte-carlo", "bigeye", "anomalo",
        "great-expectations", "soda", "elementary",
        "prefect", "dagster", "astronomer",
        "determined", "lightning", "grid",
        "seldon", "bentoml", "banana",
        "coreweave", "lambda", "together-ai",
        "groq", "cerebras", "sambanova",
        "adept", "inflection", "character",
        "cohere-ai", "ai21", "aleph-alpha",
        "runway", "stability-ai", "midjourney",
        "synthesia", "heygen", "descript",
        "notion-so", "coda", "almanac",
        "clickup-com", "height-app",
        "linear-app", "shortcut", "plane-so",
        "attio", "folk", "twenty",
        "clay-com", "apollo-io",
        "lemlist", "woodpecker", "instantly",
        "lavender", "regie", "smartlead",
        "orum", "nooks", "dialpad", "aircall",
        "gong-io", "chorus-ai", "wingman-ai",
        "seismic", "highspot", "showpad",
        "dooly", "scratchpad", "rattle",
        "gainsight", "totango", "churnzero", "vitally",
        "planhat", "catalyst-io",
        "productboard", "aha", "pendo-io",
        "walkme", "whatfix", "userpilot", "appcues",
        "chameleon", "userflow",
        "clearbit-inc", "6sense", "demandbase", "bombora",
        "mutiny", "intellimize",
        "optimizely", "kameleoon", "vwo",
        "hotjar", "crazy-egg", "mouseflow",
        "yotpo", "stamped", "okendo",
        "gorgias", "gladly", "kustomer", "dixa",
        "assembled", "ada-cx",
        "forethought", "observe-ai", "cresta",
        "balto", "cogito", "uniphore",
        "verint", "nice", "genesys", "five9", "talkdesk",
        "sprinklr", "khoros",
        "sprout-social", "hootsuite", "buffer",
        "later", "planoly", "tailwind",
        "canva-inc", "shutterstock", "getty",
        "figma-inc", "sketch", "invision",
        "mural", "miro-com", "whimsical",
        "lucidchart", "draw-io", "creately",
        "prezi", "pitch", "beautiful-ai",
        "slido", "mentimeter", "ahaslides",
        "loom-inc", "vidyard-com", "wistia", "vimeo",
        "descript-com", "riverside", "squadcast",
        "krisp", "otter", "fireflies-ai",
        "grain", "chorus", "gong",
        "zoom-video", "ringcentral", "8x8",
        "vonage", "bandwidth-inc", "sinch",
        "messagebird", "twilio-inc",
        "sendbird", "stream", "ably-com",
        "pusher", "pubnub",
        "agora", "daily", "100ms", "mux",
        "cloudinary", "imgix", "uploadcare",
        "transloadit", "filestack",
        "sanity-io", "contentful-inc", "strapi-io",
        "ghost", "butter-cms", "prismic",
        "storyblok", "hygraph", "kontent",
        "commercetools", "saleor", "medusa-commerce",
        "shopify-inc", "bigcommerce-inc",
        "bolt-com", "fast-co",
        "recharge", "ordergroove", "smartrr",
        "yotpo-inc", "smile-io", "loyalty-lion",
        "attentive", "postscript", "recart",
        "klaviyo-inc", "mailchimp",
        "sendgrid-inc", "mailgun", "postmark-inc",
        "convertkit", "beehiiv", "substack-inc",
        "typeform", "jotform", "paperform",
        "formstack", "cognito-forms", "fillout",
        "tally", "formbricks",
        "zapier-inc", "make-com", "n8n",
        "activepieces", "pipedream", "alloy-automation",
        "retool-inc", "appsmith", "tooljet", "budibase",
        "plasmic", "builder-io", "webflow-inc",
        "bubble", "glide", "adalo", "softr",
        "framer", "editor-x", "duda",
        "godaddy-inc", "namecheap-inc",
        "squarespace-inc", "wix-inc",
        "carrd", "typedream", "unicorn-platform",

        # More banks / finance
        "goldman", "morgan-stanley", "jpmorgan-chase",
        "bank-of-america", "wells-fargo", "citigroup", "citibank",
        "barclays", "hsbc", "deutsche-bank", "ubs", "credit-suisse",
        "bnp-paribas", "societe-generale", "ing",
        "td-bank", "bmo", "rbc", "scotiabank",
        "american-express", "discover-financial",
        "capital-one", "ally-financial", "synchrony",
        "svb-financial", "first-republic-bank",
        "blackrock", "vanguard", "fidelity-investments",
        "state-street", "northern-trust",
        "charles-schwab", "td-ameritrade", "interactive-brokers",
        "edward-jones", "raymond-james", "stifel",
        "lpl-financial-inc", "ameriprise",
        "moody-analytics", "sp-global", "msci", "factset",
        "bloomberg-lp", "refinitiv", "pitchbook",
        "morningstar-inc", "cbinsights",
        "two-sigma", "citadel", "de-shaw", "bridgewater",
        "jane-street", "point72", "millennium",
        "aqr", "man-group", "winton",
        "renaissance", "worldquant", "pdg",

        # Insurance
        "progressive", "allstate", "geico", "usaa", "nationwide",
        "travelers", "liberty-mutual", "hartford", "chubb", "aig",
        "aflac", "metlife", "prudential", "principal",
        "lincoln-financial", "unum", "guardian", "massmutual",
        "state-farm", "farmers", "erie",
        "lemonade", "hippo", "root", "clearcover",
        "branch", "kin", "sure", "socotra",
        "duck-creek", "guidewire", "majesco",
        "applied-systems", "verisk", "lexisnexis",

        # Additional random
        "twitch-interactive", "epic", "valve", "bungie", "bethesda",
        "blizzard", "rockstar", "naughty-dog", "insomniac",
        "weta", "ilm", "pixar", "dreamworks",
        "stripe-inc", "adyen-inc", "checkout-com",
        "marqeta-inc", "galileo-inc",
        "plaid-inc", "mx", "yodlee",
        "socure", "persona", "onfido", "jumio",
        "alloy-inc", "sardine", "unit21", "hummingbird",
        "coupa-inc", "tipalti-inc", "bill-com",
        "navan-inc", "center", "teampay",
        "stampli", "mineraltree",
        "docebo-inc", "cornerstone-ondemand",
        "workboard", "betterworks", "lattice-inc",
        "qualtrics", "medallia", "momentive",
        "surveymonkey", "typeform-inc",
        "domo", "sisense-inc", "metabase",
        "snowplow-analytics", "matomo",
        "heap-analytics", "mixpanel-inc",
        "amplitude-inc", "pendo-inc", "gainsight-inc",
    ]

    # Deduplicate
    return list(dict.fromkeys(companies))


APIS = {
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{}/jobs", "jobs"),
    "lever": ("https://api.lever.co/v0/postings/{}", None),
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/{}", "jobs"),
}

SEM = asyncio.Semaphore(20)  # 20 concurrent requests

async def test(client, url, key, token):
    async with SEM:
        try:
            r = await client.get(url.format(token), timeout=12)
            if r.status_code == 200:
                data = r.json()
                count = len(data.get(key, [])) if key else (len(data) if isinstance(data, list) else 0)
                if count > 0:
                    return (token, count)
        except:
            pass
    return None


async def main():
    slugs = generate_slugs()
    new_slugs = [s for s in slugs if s.lower() not in all_known]
    print(f"Total slugs: {len(slugs)} | New to test: {len(new_slugs)} | Already known: {len(all_known)}\n")

    results = {"greenhouse": [], "lever": [], "ashby": []}

    async with httpx.AsyncClient(http2=True) as client:
        for platform, (url, key) in APIS.items():
            print(f"=== {platform.upper()} ({len(new_slugs)} slugs) ===")
            tasks = [test(client, url, key, s) for s in new_slugs]
            found = []
            # Process in chunks to show progress
            chunk = 100
            for i in range(0, len(tasks), chunk):
                batch_results = await asyncio.gather(*tasks[i:i+chunk])
                for r in batch_results:
                    if r:
                        found.append(r)
                        print(f"  ✓ {r[0]}: {r[1]} jobs")
                pct = min(100, (i + chunk) * 100 // len(tasks))
                print(f"  ... {pct}% complete", end="\r")
                await asyncio.sleep(0.1)
            results[platform] = found
            print(f"\n  Found {len(found)} boards\n")

    # Merge
    added = 0
    for t, c in results["greenhouse"]:
        if t.lower() not in all_known:
            existing["greenhouse"].append({"token": t})
            all_known.add(t.lower()); added += 1
    for t, c in results["lever"]:
        if t.lower() not in all_known:
            existing["lever"].append({"site": t})
            all_known.add(t.lower()); added += 1
    for t, c in results["ashby"]:
        if t.lower() not in all_known:
            existing["ashby"].append({"board": t})
            all_known.add(t.lower()); added += 1

    with open(PROJECT / "config/companies.json", "w") as f:
        json.dump(existing, f, indent=2)

    total = sum(len(v) for k, v in existing.items() if not k.startswith("_"))
    print(f"\nAdded {added} new companies")
    print(f"GRAND TOTAL: {total} companies across all platforms")


if __name__ == "__main__":
    asyncio.run(main())
