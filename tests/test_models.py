"""Tests for data models and deduplication."""
import pytest

from src.models import FilteredJob, RawJob


class TestDedupKey:
    """Verify dedup key generation is deterministic and normalized."""

    def test_same_input_same_key(self):
        key1 = FilteredJob.compute_dedup_key("Google", "Business Analyst", "New York, NY")
        key2 = FilteredJob.compute_dedup_key("Google", "Business Analyst", "New York, NY")
        assert key1 == key2

    def test_case_insensitive(self):
        key1 = FilteredJob.compute_dedup_key("Google", "Business Analyst", "New York, NY")
        key2 = FilteredJob.compute_dedup_key("GOOGLE", "BUSINESS ANALYST", "NEW YORK, NY")
        assert key1 == key2

    def test_whitespace_normalized(self):
        key1 = FilteredJob.compute_dedup_key("Google", "Business  Analyst", "New York,  NY")
        key2 = FilteredJob.compute_dedup_key("Google", "Business Analyst", "New York, NY")
        assert key1 == key2

    def test_different_jobs_different_keys(self):
        key1 = FilteredJob.compute_dedup_key("Google", "Business Analyst", "New York, NY")
        key2 = FilteredJob.compute_dedup_key("Google", "Data Analyst", "New York, NY")
        assert key1 != key2

    def test_key_length(self):
        key = FilteredJob.compute_dedup_key("Test", "Test", "Test")
        assert len(key) == 16


class TestFilteredJobFromRaw:
    """Verify FilteredJob.from_raw constructor."""

    def test_from_raw_basic(self, make_raw_job):
        raw = make_raw_job(title="Data Analyst", company="Acme", location="NYC")
        filtered = FilteredJob.from_raw(
            raw,
            matched_lane="Data Analytics",
            match_score=85.0,
            sponsorship_flag="GREEN",
            h1b_count=150,
        )
        assert filtered.title == "Data Analyst"
        assert filtered.company_name == "Acme"
        assert filtered.matched_lane == "Data Analytics"
        assert filtered.match_score == 85.0
        assert filtered.sponsorship_flag == "GREEN"
        assert filtered.dedup_key  # non-empty

    def test_from_raw_dedup_key_computed(self, make_raw_job):
        raw = make_raw_job()
        filtered = FilteredJob.from_raw(raw, matched_lane="BA", match_score=80.0)
        expected_key = FilteredJob.compute_dedup_key(raw.company_name, raw.title, raw.location_raw)
        assert filtered.dedup_key == expected_key
