"""Tests for the sponsorship blacklist filter."""
import pytest

from src.filters.sponsorship import SponsorshipFilter


@pytest.fixture
def sponsor_filter(config_dir):
    return SponsorshipFilter(config_dir / "sponsorship_blacklist.txt")


class TestSponsorshipFilter:
    def test_clean_description_passes(self, sponsor_filter):
        result = sponsor_filter.check("We are looking for a talented analyst to join our team.")
        assert result is None

    def test_no_sponsorship_detected(self, sponsor_filter):
        result = sponsor_filter.check("Candidates must be authorized to work. No sponsorship available.")
        assert result is not None

    def test_must_be_authorized(self, sponsor_filter):
        result = sponsor_filter.check(
            "Must be authorized to work in the US without sponsorship for employment visa status."
        )
        assert result is not None

    def test_empty_description(self, sponsor_filter):
        assert sponsor_filter.check("") is None

    def test_none_description(self, sponsor_filter):
        assert sponsor_filter.check(None) is None

    def test_case_insensitive(self, sponsor_filter):
        result = sponsor_filter.check("NO SPONSORSHIP available for this role")
        assert result is not None
