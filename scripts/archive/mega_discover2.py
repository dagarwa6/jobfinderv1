#!/usr/bin/env python3
"""Wave 2 mega discovery — try thousands of slug variations to reach 2000+ companies."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
COMPANIES_FILE = BASE_DIR / "config" / "companies.json"

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
LEVER_URL = "https://api.lever.co/v0/postings/{}?mode=json&limit=1"
ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{}"
SMARTRECRUITERS_URL = "https://api.smartrecruiters.com/v1/companies/{}/postings?limit=1"

SEM = asyncio.Semaphore(30)

# --- Massive company name list ---
# Fortune 500, S&P 500, tech companies, consulting, finance, healthcare, defense, etc.
# Each entry is a base name — we'll generate multiple slug variations from it.
COMPANIES_RAW = [
    # === TECH GIANTS & MAJOR TECH ===
    "apple", "microsoft", "amazon", "meta", "alphabet", "google", "netflix", "nvidia",
    "tesla", "intel", "amd", "qualcomm", "broadcom", "cisco", "oracle", "ibm",
    "salesforce", "adobe", "vmware", "dell", "hp", "hpe", "lenovo",
    "samsung", "sony", "panasonic", "lg", "philips", "siemens",

    # === CLOUD & SAAS ===
    "snowflake", "datadog", "splunk", "elastic", "confluent", "mongodb", "redis",
    "cockroachdb", "timescale", "influxdata", "grafana", "newrelic", "dynatrace",
    "sumo-logic", "logz", "observe", "lightstep", "honeycomb", "chronosphere",
    "cribl", "mezmo", "coralogix", "axiom", "betterstack",
    "twilio", "sendgrid", "segment", "mparticle", "amplitude", "mixpanel",
    "heap", "fullstory", "hotjar", "pendo", "walkme", "whatfix",
    "zendesk", "freshworks", "freshdesk", "intercom", "drift", "qualified",
    "gong", "chorus", "clari", "salesloft", "outreach", "apollo",
    "hubspot", "marketo", "pardot", "mailchimp", "klaviyo", "braze",
    "iterable", "customer-io", "oneSignal", "airship", "leanplum", "clevertap",
    "contentful", "sanity", "strapi", "prismic", "storyblok", "butter-cms",
    "vercel", "netlify", "render", "railway", "fly-io", "cloudflare",
    "fastly", "akamai", "cloudfront", "stackpath", "imperva",
    "auth0", "okta", "onelogin", "ping-identity", "beyondtrust", "sailpoint",
    "crowdstrike", "sentinelone", "palo-alto-networks", "fortinet", "zscaler",
    "cloudflare", "snyk", "sonarqube", "veracode", "checkmarx", "synopsys",
    "rapid7", "tenable", "qualys", "nessus", "bugcrowd", "hackerone",
    "wiz", "orca-security", "lacework", "prisma-cloud", "aqua-security",

    # === FINTECH & PAYMENTS ===
    "stripe", "square", "block", "paypal", "adyen", "checkout-com",
    "braintree", "worldpay", "fis", "fiserv", "fico", "experian",
    "transunion", "equifax", "plaid", "mx", "finicity", "yodlee",
    "affirm", "klarna", "afterpay", "sezzle", "zip", "bread-financial",
    "marqeta", "lithic", "highnote", "unit", "treasury-prime", "column",
    "robinhood", "webull", "etrade", "schwab", "fidelity", "vanguard",
    "betterment", "wealthfront", "personal-capital", "acorns", "stash",
    "coinbase", "kraken", "gemini", "binance-us", "ftx",
    "ripple", "circle", "chainalysis", "elliptic", "fireblocks",
    "brex", "ramp", "divvy", "navan", "center", "mesh-payments",
    "bill-com", "tipalti", "stampli", "mineraltree", "coupa",
    "nerdwallet", "creditkarma", "lendingtree", "sofi", "upstart",
    "lendingclub", "prosper", "avant", "oportun", "upgrade",
    "chime", "current", "varo", "dave", "moneyLion", "albert",
    "greenlight", "step", "copper-banking", "till",

    # === BANKING & FINANCIAL SERVICES ===
    "jpmorgan", "jp-morgan", "goldman-sachs", "goldmansachs", "morgan-stanley",
    "morganstanley", "bank-of-america", "bankofamerica", "citigroup", "citi",
    "wells-fargo", "wellsfargo", "us-bank", "usbank", "pnc", "truist",
    "capital-one", "capitalone", "td-bank", "tdbank", "bny-mellon", "bnymellon",
    "state-street", "statestreet", "northern-trust", "northerntrust",
    "blackrock", "vanguard", "fidelity", "schwab", "ameriprise",
    "raymond-james", "raymondjames", "edward-jones", "edwardjones",
    "lazard", "evercore", "moelis", "centerview", "perella-weinberg",
    "jefferies", "cowen", "piper-sandler", "pipersandler", "baird",
    "hsbc", "barclays", "deutsche-bank", "deutschebank", "ubs", "credit-suisse",
    "bnp-paribas", "societe-generale", "nomura", "mizuho", "daiwa",
    "macquarie", "natixis", "calyon", "standard-chartered",

    # === CONSULTING & PROFESSIONAL SERVICES ===
    "mckinsey", "bcg", "boston-consulting", "bain", "bainandcompany",
    "deloitte", "pwc", "ey", "ernst-young", "kpmg", "accenture",
    "booz-allen", "boozallen", "oliver-wyman", "oliverwyman",
    "roland-berger", "rolandberger", "strategy-and", "lek-consulting",
    "parthenon", "kearney", "atkearney", "simon-kucher",
    "alvarez-marsal", "fti-consulting", "huron", "navigant",
    "west-monroe", "westmonroe", "slalom", "infosys", "wipro", "tcs",
    "cognizant", "hcl", "tech-mahindra", "capgemini", "atos",
    "thoughtworks", "epam", "globant", "endava", "luxoft",
    "gartner", "forrester", "idc", "frost-sullivan",

    # === HEALTHCARE & BIOTECH ===
    "unitedhealth", "anthem", "cigna", "aetna", "humana", "centene",
    "molina", "wellcare", "kaiser", "oscar-health", "oscarhealth",
    "clover-health", "devoted-health", "alignment-healthcare", "bright-health",
    "pfizer", "johnson-johnson", "jnj", "merck", "abbvie", "amgen",
    "gilead", "regeneron", "vertex", "biogen", "moderna", "biontech",
    "eli-lilly", "lilly", "bristol-myers", "bms", "astrazeneca", "novartis",
    "roche", "sanofi", "gsk", "takeda", "daiichi-sankyo",
    "medtronic", "abbott", "stryker", "boston-scientific", "edwards-lifesciences",
    "intuitive-surgical", "zimmer-biomet", "baxter", "becton-dickinson",
    "epic-systems", "cerner", "athenahealth", "allscripts", "veeva",
    "health-catalyst", "phreesia", "doximity", "zocdoc", "teladoc",
    "amwell", "hims", "ro", "nurx", "cerebral", "talkiatry",
    "tempus", "flatiron-health", "flatironhealth", "grail", "guardant",
    "illumina", "10x-genomics", "pacbio", "nanopore", "twist-bioscience",

    # === RETAIL & ECOMMERCE ===
    "walmart", "target", "costco", "kroger", "albertsons",
    "amazon", "ebay", "etsy", "wayfair", "chewy", "zappos",
    "shopify", "bigcommerce", "woocommerce", "magento",
    "instacart", "doordash", "uber-eats", "grubhub", "postmates",
    "starbucks", "mcdonalds", "chipotle", "sweetgreen", "cava",
    "nike", "adidas", "under-armour", "lululemon", "peloton",
    "nordstrom", "macys", "kohls", "tjx", "ross",
    "home-depot", "lowes", "williams-sonoma", "restoration-hardware", "ikea",
    "best-buy", "bestbuy", "gamestop", "b-and-h",

    # === MEDIA & ENTERTAINMENT ===
    "disney", "warner-bros", "warnerbros", "paramount", "nbcuniversal",
    "fox", "viacom", "lionsgate", "mgm", "a24",
    "spotify", "apple-music", "pandora", "tidal", "deezer",
    "youtube", "tiktok", "snapchat", "pinterest", "reddit",
    "twitter", "x-corp", "mastodon", "threads",
    "nytimes", "new-york-times", "washingtonpost", "wsj", "bloomberg",
    "reuters", "ap", "cnn", "bbc", "vice", "vox", "buzzfeed",
    "electronic-arts", "ea", "activision", "blizzard", "riot-games", "riotgames",
    "epic-games", "epicgames", "valve", "steam", "ubisoft",
    "nintendo", "playstation", "xbox",
    "unity", "unreal", "roblox", "niantic",

    # === AUTOMOTIVE & MOBILITY ===
    "ford", "gm", "general-motors", "chrysler", "stellantis",
    "toyota", "honda", "nissan", "hyundai", "kia", "bmw", "mercedes",
    "volkswagen", "vw", "audi", "porsche", "volvo", "jaguar", "land-rover",
    "tesla", "rivian", "lucid", "fisker", "polestar", "canoo",
    "waymo", "cruise", "argo-ai", "aurora", "nuro", "zoox", "motional",
    "uber", "lyft", "grab", "gojek", "didi",
    "lime", "bird", "spin", "tier",

    # === AEROSPACE & DEFENSE ===
    "lockheed", "lockheed-martin", "boeing", "raytheon", "northrop-grumman",
    "northropgrumman", "general-dynamics", "bae-systems", "l3harris",
    "leidos", "saic", "booz-allen-hamilton", "caci", "mantech",
    "parsons", "maxar", "harris", "textron", "honeywell",
    "spacex", "blue-origin", "virgin-galactic", "rocket-lab", "aerojet",
    "axiom-space", "relativity-space", "firefly-aerospace",
    "palantir", "anduril", "shield-ai", "skydio", "kratos",

    # === ENERGY & UTILITIES ===
    "exxon", "chevron", "shell", "bp", "conocophillips",
    "duke-energy", "southern-company", "dominion", "nextera", "aes",
    "enphase", "sunrun", "sunpower", "firstsolar", "nextracker",
    "tesla-energy", "fluence", "stem-inc", "eos-energy",
    "chargepoint", "evgo", "electrify-america", "blink-charging",

    # === REAL ESTATE & PROPTECH ===
    "zillow", "redfin", "realtor", "compass", "opendoor",
    "offerpad", "knock", "homelight", "flyhomes",
    "cbre", "jll", "cushman-wakefield", "colliers", "marcus-millichap",
    "wework", "regus", "industrious", "knotel", "convene",
    "procore", "buildertrend", "plangrid", "fieldwire",
    "yardi", "realpage", "appfolio", "buildium", "rent-manager",

    # === INSURANCE ===
    "progressive", "geico", "allstate", "state-farm", "liberty-mutual",
    "libertymutual", "travelers", "hartford", "chubb", "aig",
    "metlife", "prudential", "new-york-life", "northwestern-mutual",
    "aflac", "unum", "lincoln-financial", "principal",
    "lemonade", "root-insurance", "hippo", "kin-insurance",
    "next-insurance", "pie-insurance", "coterie", "cowbell",

    # === LOGISTICS & SUPPLY CHAIN ===
    "fedex", "ups", "dhl", "usps", "amazon-logistics",
    "flexport", "project44", "fourkites", "descartes",
    "samsara", "motive", "keeptruckin", "platform-science",
    "convoy", "uber-freight", "transfix", "loadsmart",
    "shipbob", "shippo", "easypost", "stamps-com",

    # === EDUCATION & EDTECH ===
    "coursera", "udemy", "edx", "khan-academy", "duolingo",
    "chegg", "pearson", "mcgraw-hill", "cengage",
    "instructure", "canvas", "blackboard", "brightspace",
    "guild-education", "springboard", "flatiron-school", "general-assembly",
    "2u", "trilogy", "thinkful", "codecademy", "pluralsight",
    "masterclass", "skillshare", "brilliant", "outschool",

    # === HR & RECRUITING ===
    "workday", "adp", "paychex", "paylocity", "paycom",
    "bamboohr", "namely", "rippling", "gusto", "justworks",
    "lever", "greenhouse", "icims", "jobvite", "smartrecruiters",
    "gem", "beamery", "eightfold", "phenom", "seekout",
    "lattice", "culture-amp", "cultureamp", "15five", "betterworks",
    "deel", "remote-com", "oyster-hr", "papaya-global", "velocity-global",

    # === DEV TOOLS & INFRASTRUCTURE ===
    "github", "gitlab", "bitbucket", "atlassian", "jira",
    "jetbrains", "hashicorp", "terraform", "docker", "kubernetes",
    "circleci", "travisci", "jenkins", "buildkite", "drone",
    "launchdarkly", "split-io", "optimizely", "statsig",
    "sentry", "rollbar", "bugsnag", "airbrake", "raygun",
    "postman", "stoplight", "swagger", "readme",
    "retool", "internal", "tooljet", "appsmith", "budibase",
    "supabase", "firebase", "appwrite", "nhost",
    "planetscale", "neon", "cockroachlabs", "singlestore", "vitess",
    "pinecone", "weaviate", "qdrant", "milvus", "chroma",
    "langchain", "llamaindex", "cohere", "anthropic", "openai",
    "huggingface", "weights-biases", "wandb", "mlflow", "dvc",
    "databricks", "dbt-labs", "dbtlabs", "fivetran", "airbyte", "stitch",
    "prefect", "dagster", "airflow", "temporal", "inngest",

    # === AI & ML COMPANIES ===
    "deepmind", "openai", "anthropic", "google-ai", "meta-ai",
    "nvidia-ai", "cerebras", "graphcore", "sambanova", "groq",
    "scale-ai", "scaleai", "labelbox", "snorkel", "surge-ai",
    "jasper-ai", "jasperai", "copy-ai", "writesonic", "grammarly",
    "midjourney", "stability-ai", "runway", "pika", "luma",
    "perplexity", "you-com", "neeva", "brave-search",
    "character-ai", "inflection", "adept", "cohere", "ai21",
    "datarobot", "h2o-ai", "c3-ai", "palantir", "databricks",

    # === TELECOM ===
    "att", "verizon", "t-mobile", "tmobile", "sprint",
    "comcast", "charter", "cox", "dish", "directv",
    "twilio", "vonage", "ringcentral", "zoom", "eight-by-eight",
    "bandwidth", "sinch", "messagebird", "telnyx", "plivo",

    # === FOOD & AGRICULTURE ===
    "cargill", "adm", "bunge", "tyson", "jbs",
    "nestle", "unilever", "kraft-heinz", "general-mills", "kellogg",
    "pepsico", "coca-cola", "dr-pepper", "monster-beverage",
    "impossible-foods", "beyondmeat", "oatly", "just-egg",

    # === MANUFACTURING & INDUSTRIAL ===
    "ge", "general-electric", "3m", "honeywell", "emerson",
    "caterpillar", "deere", "john-deere", "parker-hannifin",
    "rockwell", "rockwell-automation", "abb", "schneider-electric",
    "siemens", "bosch", "danaher", "illinois-tool-works", "itw",

    # === TRAVEL & HOSPITALITY ===
    "airbnb", "booking", "expedia", "tripadvisor", "kayak",
    "marriott", "hilton", "hyatt", "ihg", "wyndham", "accor",
    "delta", "united", "american-airlines", "southwest", "jetblue",
    "hopper", "kiwi", "skyscanner", "momondo",

    # === GOVERNMENT & CIVIC TECH ===
    "palantir", "anduril", "maxar", "bah", "leidos",
    "caci-international", "perspecta", "unisys", "cgifederal",

    # === CRYPTO & WEB3 ===
    "coinbase", "kraken", "gemini", "binance", "crypto-com",
    "opensea", "dapper-labs", "dapperlabs", "yuga-labs", "yugalabs",
    "consensys", "polygon", "solana-labs", "avalanche", "near",
    "aave", "uniswap", "compound", "makerdao", "curve",
    "alchemy", "infura", "moralis", "thirdweb", "magic",

    # === ADDITIONAL TECH STARTUPS (YC, Series B+) ===
    "notion", "figma", "canva", "miro", "airtable",
    "clickup", "monday", "asana", "todoist", "linear",
    "loom", "calendly", "cal-com", "savvy-cal",
    "webflow", "framer", "bubble", "retool", "zapier",
    "make", "tray-io", "workato", "boomi", "mulesoft",
    "algolia", "typesense", "meilisearch",
    "clerk", "stytch", "magic-link", "privy",
    "neon-tech", "convex", "fauna", "cockroach", "upstash",
    "inngest", "trigger-dev", "defer", "qstash",
    "resend", "postmark", "sendgrid", "mailgun", "sparkpost",
    "axiom-co", "baselime", "highlight-run", "openobserve",
    "pieces", "tabnine", "sourcegraph", "codeium", "cursor",
    "replit", "gitpod", "codespaces", "stackblitz", "codesandbox",
    "depot", "namespace", "dagger-io",
    "pulumi", "crossplane", "spacelift", "env0",
    "teleport", "tailscale", "netbird", "boundary",
    "snyk", "semgrep", "endor-labs", "socket-dev",
    "vanta", "drata", "secureframe", "laika", "anecdotes",
    "zip-co", "procurify", "precoro", "fairmarkit",

    # === More enterprise/B2B ===
    "servicenow", "pagerduty", "opsgenie", "blameless", "rootly",
    "firehydrant", "incident-io", "statuspage",
    "okta", "duo", "yubico", "1password", "bitwarden",
    "sophos", "trellix", "mandiant", "recorded-future", "anomali",
    "proofpoint", "mimecast", "abnormal-security", "tessian",
    "knowbe4", "cofense", "ironscales",
    "cyberark", "delinea", "privileged-access",
    "varonis", "rubrik", "cohesity", "veeam", "commvault",
    "pure-storage", "purestorage", "netapp", "nutanix", "vmware",
    "tanium", "jamf", "kandji", "mosyle", "addigy",
    "crowdstrike", "carbonblack", "cylance",

    # === Prop trading / quant ===
    "citadel", "two-sigma", "twosigma", "de-shaw", "deshaw",
    "renaissance", "jane-street", "janestreet", "jump-trading", "jumptrading",
    "virtu", "hrt", "hudson-river", "tower-research", "towerresearch",
    "sig", "susquehanna", "imc", "optiver", "akuna",
    "drw", "belvedere", "peak6", "wolverine", "group-one",

    # === Additional enterprise software ===
    "sap", "oracle", "infor", "epicor", "sage",
    "netsuite", "intuit", "quickbooks", "xero", "freshbooks",
    "concur", "expensify", "certify", "abacus",
    "anaplan", "adaptive-insights", "vena", "planful",
    "verint", "nice", "five9", "talkdesk", "genesys",
    "sprinklr", "khoros", "sprout-social", "hootsuite", "buffer",
    "seismic", "highspot", "showpad", "guru", "bloomfire",
    "docusign", "pandadoc", "conga", "icertis", "ironclad",
    "box", "dropbox", "egnyte", "sharefile",

    # === Semiconductors ===
    "tsmc", "samsung-semi", "globalfoundries", "skyworks", "marvell",
    "microchip", "maxim", "analog-devices", "texas-instruments", "ti",
    "nxp", "infineon", "renesas", "stmicro", "onsemi",
    "arm", "synopsys", "cadence", "mentor", "ansys",
    "lam-research", "lamresearch", "applied-materials", "asml", "kla",
]


def generate_slug_variations(name: str) -> list[str]:
    """Generate multiple slug variations from a company name."""
    slugs = set()
    clean = name.strip().lower()
    slugs.add(clean)

    # Remove hyphens
    slugs.add(clean.replace("-", ""))
    # Replace spaces with hyphens
    slugs.add(clean.replace(" ", "-"))
    # Remove spaces
    slugs.add(clean.replace(" ", ""))
    # Common suffixes
    for suffix in ["-inc", "-co", "-io", "-hq", "-app", "-labs", "-tech", "-ai"]:
        slugs.add(clean + suffix)
        slugs.add(clean.replace("-", "") + suffix)

    # Remove common suffixes that might be in the name
    for suffix in ["-inc", "-co", "-io", "-hq", "-app", "-labs", "-tech", "-ai",
                   "-com", "-us", "-global", "-group"]:
        if clean.endswith(suffix):
            base = clean[:-len(suffix)]
            slugs.add(base)

    return [s for s in slugs if s and len(s) >= 2]


async def check_greenhouse(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    async with SEM:
        try:
            r = await client.get(GREENHOUSE_URL.format(slug), timeout=8)
            if r.status_code == 200:
                data = r.json()
                jobs = data.get("jobs", [])
                if jobs:
                    return (slug, len(jobs))
        except:
            pass
    return None


async def check_lever(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    async with SEM:
        try:
            r = await client.get(LEVER_URL.format(slug), timeout=8)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    return (slug, len(data))
        except:
            pass
    return None


async def check_ashby(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    async with SEM:
        try:
            r = await client.get(ASHBY_URL.format(slug), timeout=8)
            if r.status_code == 200:
                data = r.json()
                jobs = data.get("jobs", [])
                if jobs:
                    return (slug, len(jobs))
        except:
            pass
    return None


async def check_smartrecruiters(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    async with SEM:
        try:
            r = await client.get(SMARTRECRUITERS_URL.format(slug), timeout=8)
            if r.status_code == 200:
                data = r.json()
                content = data.get("content", [])
                if content:
                    return (slug, len(content))
        except:
            pass
    return None


async def main():
    with open(COMPANIES_FILE) as f:
        existing_data = json.load(f)

    existing_slugs = set()
    for platform, companies in existing_data.items():
        if platform.startswith("_"):
            continue
        for c in companies:
            if isinstance(c, dict):
                existing_slugs.add(c.get("token", "").lower())
                existing_slugs.add(c.get("company_id", "").lower())
            else:
                existing_slugs.add(str(c).lower())

    # Generate all slug variations
    all_slugs = set()
    for name in COMPANIES_RAW:
        for slug in generate_slug_variations(name):
            if slug not in existing_slugs:
                all_slugs.add(slug)

    slugs_to_test = sorted(all_slugs)
    print(f"Base companies: {len(COMPANIES_RAW)} | Slug variations: {len(slugs_to_test)} | Already known: {len(existing_slugs)}")

    found = {"greenhouse": [], "lever": [], "ashby": [], "smartrecruiters": []}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Test each platform
        for platform, check_fn in [
            ("greenhouse", check_greenhouse),
            ("lever", check_lever),
            ("ashby", check_ashby),
            ("smartrecruiters", check_smartrecruiters),
        ]:
            print(f"\n=== {platform.upper()} ({len(slugs_to_test)} slugs) ===")
            tasks = [check_fn(client, s) for s in slugs_to_test]

            batch_size = 200
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                results = await asyncio.gather(*batch)
                hits = [r for r in results if r]
                for slug, count in hits:
                    print(f"  ✓ {slug}: {count} jobs")
                    found[platform].append(slug)
                pct = min(100, int((i + batch_size) / len(tasks) * 100))
                if pct % 20 == 0 or i + batch_size >= len(tasks):
                    print(f"  ... {pct}% complete")

            print(f"  Found {len(found[platform])} boards")

    # Merge into companies.json
    added = 0
    for platform, slugs in found.items():
        if platform not in existing_data:
            existing_data[platform] = []

        current = set()
        for c in existing_data[platform]:
            if isinstance(c, dict):
                current.add(c.get("token", "").lower())
            else:
                current.add(str(c).lower())

        for slug in slugs:
            if slug.lower() not in current:
                existing_data[platform].append(slug)
                added += 1

    with open(COMPANIES_FILE, "w") as f:
        json.dump(existing_data, f, indent=2)

    total = sum(len(v) for k, v in existing_data.items() if not k.startswith("_"))
    print(f"\nAdded {added} new companies")
    print(f"GRAND TOTAL: {total} companies across all platforms")


if __name__ == "__main__":
    asyncio.run(main())
