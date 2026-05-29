"""Shared fixtures for the job scraper test suite."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Ensure src is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models import RawJob


@pytest.fixture
def config_dir():
    """Path to the real config directory."""
    return ROOT / "config"


@pytest.fixture
def make_raw_job():
    """Factory fixture for creating RawJob instances with sensible defaults."""

    def _make(
        title: str = "Business Analyst",
        company: str = "Acme Corp",
        location: str = "New York, NY",
        description: str = "Looking for a business analyst...",
        platform: str = "greenhouse",
    ) -> RawJob:
        return RawJob(
            source_platform=platform,
            company_token="acme",
            company_name=company,
            external_id="12345",
            title=title,
            location_raw=location,
            description_html=f"<p>{description}</p>",
            description_text=description,
            posted_at=datetime(2026, 5, 1),
            apply_url="https://example.com/apply/12345",
        )

    return _make
