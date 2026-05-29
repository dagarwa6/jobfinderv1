"""Tests for the exclusion filter module."""
import pytest

from src.filters.exclusion_filter import check_exclusions, _extract_max_yoe


class TestTitleExclusions:
    """Verify title-based exclusion rules."""

    @pytest.mark.parametrize("title,should_exclude", [
        ("Senior Business Analyst", True),
        ("Sr. Data Analyst", True),
        ("Staff Software Engineer", True),
        ("Principal Consultant", True),
        ("Director of Analytics", True),
        ("VP of Strategy", True),
        ("Business Analyst", False),
        ("Associate Analyst", False),
        ("Data Analyst I", False),
        ("Junior Business Analyst", False),
        ("Cybersecurity Analyst", False),
    ])
    def test_seniority_exclusion(self, title, should_exclude, make_raw_job):
        job = make_raw_job(title=title)
        result = check_exclusions(job)
        if should_exclude:
            assert result is not None, f"{title!r} should be excluded"
        else:
            assert result is None, f"{title!r} should pass, got: {result}"

    @pytest.mark.parametrize("title", [
        "Account Executive",
        "Sales Development Representative",
        "SDR",
        "BDR",
        "Inside Sales",
    ])
    def test_sales_exclusion(self, title, make_raw_job):
        job = make_raw_job(title=title)
        result = check_exclusions(job)
        assert result is not None and "sales" in result.lower()

    @pytest.mark.parametrize("title", [
        "Software Engineer",
        "DevOps Engineer",
        "ML Engineer",
        "Backend Engineer",
    ])
    def test_engineering_exclusion(self, title, make_raw_job):
        job = make_raw_job(title=title)
        result = check_exclusions(job)
        assert result is not None and "engineering" in result.lower()

    def test_internship_excluded(self, make_raw_job):
        job = make_raw_job(title="Business Analyst Intern")
        assert check_exclusions(job) is not None

    @pytest.mark.parametrize("title,should_pass", [
        ("Project Manager", True),
        ("Program Manager", True),
        ("Product Manager", True),
        ("Operations Manager", False),
        ("Marketing Manager", False),
    ])
    def test_manager_context(self, title, should_pass, make_raw_job):
        job = make_raw_job(title=title)
        result = check_exclusions(job)
        if should_pass:
            assert result is None, f"{title!r} should pass"
        else:
            assert result is not None, f"{title!r} should be excluded"


class TestYOEExtraction:
    """Verify years-of-experience parsing from description text."""

    @pytest.mark.parametrize("text,expected", [
        ("5+ years of experience in data analysis", 5),
        ("3-5 years of relevant experience", 5),
        ("Minimum 4 years of professional experience", 4),
        ("At least 7 years of industry experience", 7),
        ("Requires 3 years of hands-on experience", 3),
        ("No experience specified", None),
        ("", None),
    ])
    def test_yoe_extraction(self, text, expected):
        result = _extract_max_yoe(text)
        assert result == expected, f"Expected {expected} from {text!r}, got {result}"

    def test_high_yoe_excludes_job(self, make_raw_job):
        job = make_raw_job(
            title="Business Analyst",
            description="Requires minimum 7 years of experience in business analysis",
        )
        result = check_exclusions(job)
        assert result is not None and "yoe" in result.lower()

    def test_low_yoe_passes(self, make_raw_job):
        job = make_raw_job(
            title="Business Analyst",
            description="2-3 years of experience preferred",
        )
        result = check_exclusions(job)
        assert result is None
