"""Tests for the location filter module."""
import pytest

from src.filters.location_filter import is_us_location


class TestUSLocations:
    """Verify correct US location detection."""

    @pytest.mark.parametrize("loc,expected_us", [
        ("New York, NY", True),
        ("San Francisco, CA", True),
        ("Remote - US", True),
        ("Remote - USA", True),
        ("United States", True),
        ("Austin, TX", True),
        ("Remote", True),
        ("Bloomington, IN", True),  # Indiana, not India — Finding #14
        ("Washington, DC", True),
        ("Chicago, IL", True),
        ("Remote - United States", True),
    ])
    def test_us_locations(self, loc, expected_us):
        is_us, _ = is_us_location(loc)
        assert is_us == expected_us, f"Expected {loc!r} to be US={expected_us}"

    @pytest.mark.parametrize("loc", [
        "London, UK",
        "Toronto, Canada",
        "Bangalore, India",
        "Berlin, Germany",
        "IN - Bengaluru",  # India country code prefix — Finding #14
        "DE - Berlin",
        "Tokyo, Japan",
        "Singapore",
        "Mumbai, India",
    ])
    def test_non_us_locations(self, loc):
        is_us, _ = is_us_location(loc)
        assert not is_us, f"Expected {loc!r} to be non-US"

    def test_empty_location(self):
        is_us, normalized = is_us_location("")
        assert not is_us
        assert normalized == ""

    def test_remote_anywhere(self):
        is_us, normalized = is_us_location("Remote - Anywhere")
        assert is_us
        assert normalized == "Remote"

    def test_remote_us_normalized(self):
        is_us, normalized = is_us_location("Remote - US")
        assert is_us
        assert normalized == "Remote (US)"
