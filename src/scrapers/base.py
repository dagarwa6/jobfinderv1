from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from src.models import RawJob

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base scraper with retry logic, rate limiting, and resource management.

    Subclasses implement `fetch_jobs()` for their specific ATS API.
    The base class handles HTTP client lifecycle, retry with exponential backoff,
    and request throttling.
    """

    platform: str = ""
    base_delay: float = 1.5

    def __init__(self, delay: float | None = None):
        self.delay = delay if delay is not None else self.base_delay
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client with configured timeouts."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                # Finding #10: Per-operation timeouts (connect, read, write, pool)
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=30.0,
                    write=10.0,
                    pool=10.0,
                ),
                follow_redirects=True,
                headers={"User-Agent": "JobScraper/1.0 (personal job search tool)"},
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    async def close(self):
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def fetch_jobs(self, company: dict) -> list[RawJob]:
        """Fetch all job postings for a single company.

        Args:
            company: Company config dict with platform-specific keys
                     (e.g., {'token': 'abc', 'name': 'Acme Corp'}).

        Returns:
            List of RawJob objects parsed from the API response.
        """
        ...

    async def fetch_with_retry(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict | None = None,
        json_body: dict | None = None,
        max_retries: int = 3,
        timeout_override: float | None = None,
    ) -> dict | list | None:
        """Make an HTTP request with retry logic and exponential backoff.

        Handles 429 (rate limit), 5xx (server errors), timeouts, and
        connection errors with appropriate retry strategies.

        Args:
            url: Request URL.
            method: HTTP method ("GET" or "POST").
            params: URL query parameters.
            json_body: JSON request body (for POST).
            max_retries: Maximum number of retry attempts.
            timeout_override: Override the default read timeout for slow endpoints.

        Returns:
            Parsed JSON response, or None if all retries failed.
        """
        client = await self.get_client()
        # Finding #10: Allow per-request timeout override for slow APIs (e.g., Workday)
        request_timeout = None
        if timeout_override:
            request_timeout = httpx.Timeout(
                connect=10.0,
                read=timeout_override,
                write=10.0,
                pool=10.0,
            )

        # Hard overall ceiling per request — httpx's per-phase timeouts can be
        # bypassed when servers trickle data (no single read exceeds `read=30s`
        # but the total transfer hangs for hours). asyncio.wait_for enforces
        # an absolute wall-clock cap so a single stuck request can't freeze
        # the whole pipeline (Finding from May-22 hang).
        OVERALL_CAP = (timeout_override or 30.0) + 60.0  # transfer + buffer

        for attempt in range(max_retries + 1):
            try:
                if method == "POST":
                    resp = await asyncio.wait_for(
                        client.post(url, params=params, json=json_body, timeout=request_timeout),
                        timeout=OVERALL_CAP,
                    )
                else:
                    resp = await asyncio.wait_for(
                        client.get(url, params=params, timeout=request_timeout),
                        timeout=OVERALL_CAP,
                    )

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5 * (2 ** attempt)))
                    logger.warning(f"Rate limited on {url}, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    wait = 3 * (3 ** attempt)
                    logger.warning(f"Server error {resp.status_code} on {url}, retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue

                # 4xx (not 429) — don't retry, just skip
                if resp.status_code != 404:
                    logger.error(f"HTTP {resp.status_code} for {url} — skipping")
                return None

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError,
                    asyncio.TimeoutError) as e:
                if attempt < max_retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"{type(e).__name__} on {url}, retry in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Failed after {max_retries} retries: {url} — {e}")

        return None

    async def throttle(self):
        """Wait for the configured delay between requests."""
        await asyncio.sleep(self.delay)
