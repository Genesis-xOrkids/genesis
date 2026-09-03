"""Polite HTTP for public storefront endpoints.

Every rule about how we are allowed to read a public endpoint lives here rather
than in the connectors: robots.txt, crawl delay, per-host pacing, and backoff.
A connector translates payloads and never decides how hard to hit a server.

The posture is deliberate and narrow. We read endpoints the platform publishes
for machine consumption, logged out, at a pace the host asks for, identifying
ourselves. We do not work around bot management: a 403 is the site declining,
and the response is to stop asking, not to look like a different client.

Robots parsing uses Protego rather than the standard library. ``urllib`` matches
the first applicable rule, while RFC 9309 specifies the most specific one wins.
On a real Shopify storefront that difference is not academic: the file opens with
``Allow: /`` and then disallows specific paths, so first-match reports every
disallowed path as permitted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx2
import structlog
from protego import Protego

log = structlog.get_logger(__name__)

USER_AGENT = "genesis-catalog/0.1 (+https://genesis.example/crawler)"

# Floor between requests to one host when robots.txt names no crawl delay.
DEFAULT_CRAWL_DELAY_SECONDS = 1.0
# Ceiling, so a hostile or misconfigured crawl-delay cannot stall a run forever.
MAX_CRAWL_DELAY_SECONDS = 30.0


class FetchError(RuntimeError):
    """A request that cannot be completed as asked."""


class DisallowedByRobots(FetchError):
    """The host's robots.txt refuses this path.

    A distinct type because it is not a failure to retry or report as an outage:
    it is a decision by the site that the caller must respect.
    """


class Blocked(FetchError):
    """The host refused us (403).

    Also not retried. Some storefronts sit behind bot management; the honest
    outcome is that this source is unavailable to us, recorded as such.
    """


@dataclass
class HostState:
    delay_seconds: float = DEFAULT_CRAWL_DELAY_SECONDS
    last_request_at: float = 0.0
    robots: Protego | None = None
    # No robots.txt served, or it could not be read. Absence states no
    # restriction, which is not the same as refusal.
    unrestricted: bool = False


@dataclass
class FetchStats:
    requests: int = 0
    retries: int = 0
    disallowed: int = 0
    blocked: int = 0


@dataclass
class PoliteFetcher:
    """Fetches public URLs while honoring each host's stated rules.

    One instance per run, shared across connectors, because pacing state has to
    be per host and not per connector: two connectors reading the same storefront
    would otherwise each think they were being polite.
    """

    timeout_seconds: float = 15.0
    max_retries: int = 3
    respect_robots: bool = True
    stats: FetchStats = field(default_factory=FetchStats)
    _hosts: dict[str, HostState] = field(default_factory=dict)
    _client: httpx2.Client | None = None

    def __enter__(self) -> PoliteFetcher:
        self._client = httpx2.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _state(self, url: str) -> HostState:
        host = urlparse(url).netloc
        if host not in self._hosts:
            self._hosts[host] = HostState()
            if self.respect_robots:
                self._load_robots(url, self._hosts[host])
        return self._hosts[host]

    def _load_robots(self, url: str, state: HostState) -> None:
        """Read robots.txt once per host.

        A host that serves no robots.txt has stated no restriction, which is not
        the same as refusing: absence is treated as permission, the same way a
        browser treats it.
        """
        robots_url = urljoin(url, "/robots.txt")
        try:
            assert self._client is not None
            response = self._client.get(robots_url)
        except httpx2.HTTPError:
            state.unrestricted = True
            return
        if response.status_code != 200:
            state.unrestricted = True
            return

        state.robots = Protego.parse(response.text)
        delay = state.robots.crawl_delay(USER_AGENT)
        if delay is not None:
            state.delay_seconds = min(float(delay), MAX_CRAWL_DELAY_SECONDS)

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        state = self._state(url)
        if state.unrestricted or state.robots is None:
            return True
        return bool(state.robots.can_fetch(url, USER_AGENT))

    def _wait(self, state: HostState) -> None:
        elapsed = time.monotonic() - state.last_request_at
        remaining = state.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        state.last_request_at = time.monotonic()

    def get_json(self, url: str) -> Any:
        """Fetch one JSON document, honoring robots and pacing.

        Retries only what is worth retrying: a 429 or a 5xx is the host asking
        for patience, and ``Retry-After`` is obeyed when given. A 403 or a 404 is
        an answer, and asking again would just be rudeness with extra steps.
        """
        if self._client is None:
            raise FetchError("use PoliteFetcher as a context manager")
        if not self.allowed(url):
            self.stats.disallowed += 1
            raise DisallowedByRobots(f"robots.txt disallows {url}")

        state = self._state(url)
        backoff = state.delay_seconds

        for attempt in range(self.max_retries + 1):
            self._wait(state)
            self.stats.requests += 1
            try:
                response = self._client.get(url)
            except httpx2.HTTPError as exc:
                if attempt == self.max_retries:
                    raise FetchError(f"{url}: {exc}") from exc
                self.stats.retries += 1
                time.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code == 403:
                self.stats.blocked += 1
                raise Blocked(f"{url}: host refused (403)")
            if response.status_code == 404:
                raise FetchError(f"{url}: not found (404)")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.max_retries:
                    raise FetchError(f"{url}: gave up after {attempt + 1} attempts")
                self.stats.retries += 1
                time.sleep(_retry_after(response, backoff))
                backoff *= 2
                continue
            if response.status_code != 200:
                raise FetchError(f"{url}: unexpected status {response.status_code}")

            try:
                return response.json()
            except ValueError as exc:
                # A storefront that answers HTML to a .json request is usually a
                # redirect to a regional site or an interstitial, not a product
                # feed. Fail rather than hand a connector a login page.
                raise FetchError(f"{url}: response was not JSON") from exc

        raise FetchError(f"{url}: exhausted retries")


def _retry_after(response: httpx2.Response, fallback: float) -> float:
    header = response.headers.get("Retry-After")
    if not header:
        return fallback
    try:
        return min(float(header), MAX_CRAWL_DELAY_SECONDS)
    except ValueError:
        return fallback
