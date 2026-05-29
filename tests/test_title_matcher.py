"""Tests for the fuzzy title matcher module."""
import pytest

from src.filters.title_matcher import TitleMatcher


@pytest.fixture
def matcher(config_dir):
    """TitleMatcher loaded from real config."""
    return TitleMatcher(config_dir / "role_lanes.json")


class TestTitleMatching:
    """Verify fuzzy title matching against configured role lanes."""

    @pytest.mark.parametrize("title", [
        "Business Analyst",
        "Associate Business Analyst",
        "Business Analyst, Strategy",
        "Jr. Business Analyst",
    ])
    def test_business_analyst_matches(self, title, matcher, make_raw_job):
        job = make_raw_job(title=title)
        result = matcher.match(job)
        assert result is not None, f"{title!r} should match a lane"
        lane, score, _ = result
        assert score >= 70

    @pytest.mark.parametrize("title", [
        "Data Analyst",
        "Data Analyst I",
        "Associate Data Analyst",
    ])
    def test_data_analyst_matches(self, title, matcher, make_raw_job):
        job = make_raw_job(title=title)
        result = matcher.match(job)
        assert result is not None, f"{title!r} should match a lane"

    def test_senior_titles_rejected(self, matcher, make_raw_job):
        """Senior titles should be filtered by seniority check."""
        job = make_raw_job(title="Senior Business Analyst")
        result = matcher.match(job)
        assert result is None, "Senior BA should be rejected by seniority filter"

    def test_completely_unrelated_title(self, matcher, make_raw_job):
        job = make_raw_job(title="Executive Chef")
        result = matcher.match(job)
        assert result is None

    def test_abbreviation_expansion(self, matcher):
        expanded = matcher.expand_abbreviations("BA II")
        assert "business analyst" in expanded.lower() or "ba" in expanded.lower()

    def test_rotational_detection(self, matcher, make_raw_job):
        job = make_raw_job(title="Leadership Development Program - Business Analyst")
        result = matcher.match(job)
        if result:
            _, _, is_rotational = result
            assert is_rotational, "LDP should flag as rotational"
