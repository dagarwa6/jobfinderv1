#!/usr/bin/env python3
"""
Import H1B employer data into the SQLite database.

Usage:
  1. Download the USCIS H-1B Employer Data Hub file from:
     https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
     (Click "H-1B Employer Data Hub Files" → download the CSV)

  2. OR download DOL OFLC LCA disclosure data from:
     https://www.dol.gov/agencies/eta/foreign-labor/performance
     (Select the most recent fiscal year H-1B data Excel file)

  3. Run this script:
     python scripts/import_h1b.py --file path/to/downloaded_file.csv
     python scripts/import_h1b.py --file path/to/downloaded_file.xlsx

The script auto-detects the file format and column names.
If no file is provided, it loads the built-in curated employer list.
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def normalize_employer(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|group|plc|lp|na|n\.a\.)\.?\b", "", name)
    name = re.sub(r"[.,;:'\"-]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_curated_employers() -> list[tuple[str, str, int]]:
    """Built-in list of known H1B sponsors with approximate annual counts."""
    employers = [
        # Big Tech
        ("Google LLC", 10000), ("Meta Platforms Inc", 5000), ("Amazon.com Services LLC", 8000),
        ("Microsoft Corporation", 7000), ("Apple Inc", 3000), ("Netflix Inc", 200),
        # Enterprise Tech
        ("Salesforce Inc", 2000), ("Oracle America Inc", 3000), ("IBM Corporation", 3000),
        ("SAP America Inc", 1500), ("ServiceNow Inc", 800), ("Workday Inc", 600),
        ("Snowflake Inc", 400), ("Databricks Inc", 500), ("MongoDB Inc", 300),
        # Fintech / Finance
        ("Stripe Inc", 400), ("Block Inc", 300), ("Robinhood Markets Inc", 200),
        ("Affirm Inc", 150), ("Brex Inc", 100), ("Marqeta Inc", 80),
        ("Chime Financial Inc", 100), ("Plaid Inc", 150), ("Ramp Business Corporation", 100),
        ("Visa Inc", 1500), ("Mastercard International", 1000),
        ("JPMorgan Chase", 4000), ("Goldman Sachs", 2000), ("Morgan Stanley", 1500),
        ("Bank of America", 2000), ("Capital One", 2000), ("Citigroup", 1500),
        # Consulting / Big 4
        ("Deloitte LLP", 5000), ("Ernst & Young LLP", 3000), ("PricewaterhouseCoopers LLP", 3000),
        ("KPMG LLP", 2000), ("Accenture LLP", 5000), ("McKinsey & Company Inc", 500),
        ("Boston Consulting Group", 400), ("Bain & Company", 300),
        ("Booz Allen Hamilton", 500), ("Slalom Consulting", 200),
        ("West Monroe Partners", 100), ("Huron Consulting Group", 200),
        ("FTI Consulting", 150), ("Protiviti Inc", 200), ("RSM US LLP", 300),
        # Growth Tech
        ("Airbnb Inc", 500), ("DoorDash Inc", 300), ("Lyft Inc", 200),
        ("Instacart", 150), ("Pinterest Inc", 200), ("Reddit Inc", 100),
        ("Discord Inc", 100), ("Spotify USA Inc", 300), ("Palantir Technologies", 400),
        ("Figma Inc", 100), ("Notion Labs Inc", 80), ("Asana Inc", 100),
        ("Gusto Inc", 80), ("Toast Inc", 150), ("Klaviyo Inc", 100),
        ("Samsara Inc", 200), ("Verkada Inc", 150), ("Flexport Inc", 100),
        ("GitLab Inc", 100), ("Elastic NV", 150), ("Postman Inc", 80),
        ("Amplitude Inc", 60), ("LaunchDarkly Inc", 40), ("Contentful Inc", 60),
        ("Squarespace Inc", 80), ("Twilio Inc", 300), ("Cloudflare Inc", 200),
        # Cyber
        ("CrowdStrike Inc", 300), ("Palo Alto Networks", 500), ("Zscaler Inc", 200),
        ("Fortinet Inc", 200), ("Okta Inc", 200), ("Tanium Inc", 100),
        ("Abnormal Security", 50), ("Axonius Inc", 30), ("Vanta Inc", 40),
        ("SentinelOne Inc", 100),
        # Federal / Defense
        ("Leidos Inc", 500), ("SAIC Inc", 400), ("CACI International", 300),
        ("Peraton Inc", 200), ("MITRE Corporation", 300),
        # Healthcare / Other
        ("CVS Health Corporation", 1000), ("Walt Disney Company", 500),
        ("Walmart Inc", 800), ("PwC", 3000),
        # OpenAI / AI
        ("OpenAI Inc", 200), ("Anthropic", 100),
        ("Deel Inc", 50), ("Linear Inc", 20), ("Supabase Inc", 20),
        ("Benchling Inc", 60), ("Carvana LLC", 100), ("Opendoor Technologies", 80),
        ("Relativity", 100), ("Cockroach Labs", 40), ("Faire Inc", 50),
        ("Airtable Inc", 60),
    ]

    return [(name, normalize_employer(name), count) for name, count in employers]


def import_curated(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM h1b_employers")

    employers = load_curated_employers()
    conn.executemany(
        "INSERT INTO h1b_employers (employer_name, employer_name_normalized, case_status, fiscal_year, worker_count) VALUES (?, ?, 'Certified', 2025, ?)",
        employers,
    )
    conn.commit()
    print(f"Imported {len(employers)} curated employers into {db_path}")
    conn.close()


def import_csv(filepath: Path, db_path: Path):
    import pandas as pd

    print(f"Reading {filepath}...")
    if filepath.suffix in ('.xlsx', '.xls'):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath, low_memory=False)

    print(f"Loaded {len(df)} rows, columns: {list(df.columns)[:10]}...")

    # Auto-detect column names (USCIS vs DOL format)
    employer_col = None
    for candidate in ['Employer', 'EMPLOYER_NAME', 'employer_name', 'Petitioner Name']:
        if candidate in df.columns:
            employer_col = candidate
            break

    count_col = None
    for candidate in ['Initial Approvals', 'Continuing Approvals', 'TOTAL_WORKER_POSITIONS', 'worker_count']:
        if candidate in df.columns:
            count_col = candidate
            break

    if not employer_col:
        print(f"ERROR: Could not find employer name column. Available columns: {list(df.columns)}")
        sys.exit(1)

    print(f"Using employer column: {employer_col}")
    if count_col:
        print(f"Using count column: {count_col}")

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM h1b_employers")

    if count_col and 'Initial Approvals' in df.columns and 'Continuing Approvals' in df.columns:
        # USCIS format: aggregate by employer
        df['total'] = df['Initial Approvals'].fillna(0).astype(int) + df['Continuing Approvals'].fillna(0).astype(int)
        grouped = df.groupby(employer_col)['total'].sum().reset_index()
        records = [
            (row[employer_col], normalize_employer(str(row[employer_col])), int(row['total']))
            for _, row in grouped.iterrows()
            if row['total'] > 0
        ]
    elif count_col:
        grouped = df.groupby(employer_col)[count_col].sum().reset_index()
        records = [
            (row[employer_col], normalize_employer(str(row[employer_col])), int(row[count_col]))
            for _, row in grouped.iterrows()
            if row[count_col] > 0
        ]
    else:
        # Just count rows per employer
        grouped = df.groupby(employer_col).size().reset_index(name='count')
        records = [
            (row[employer_col], normalize_employer(str(row[employer_col])), int(row['count']))
            for _, row in grouped.iterrows()
        ]

    conn.executemany(
        "INSERT INTO h1b_employers (employer_name, employer_name_normalized, case_status, fiscal_year, worker_count) VALUES (?, ?, 'Certified', 2025, ?)",
        records,
    )
    conn.commit()
    print(f"Imported {len(records)} unique employers into {db_path}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Import H1B employer data")
    parser.add_argument("--file", type=Path, help="Path to USCIS CSV or DOL Excel file")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "jobs.db")
    args = parser.parse_args()

    # Ensure DB exists with schema
    from src.db import JobDB
    db = JobDB(args.db)
    db.close()

    if args.file:
        import_csv(args.file, args.db)
    else:
        print("No file provided — loading curated employer list...")
        import_curated(args.db)


if __name__ == "__main__":
    main()
