"""Politeness guarantees of the fetcher.

These are the rules that make reading public endpoints defensible rather than
merely possible, so they are tested rather than asserted in a docstring. No test
here touches the network.
"""

from __future__ import annotations

from typing import Any

import httpx2
import pytest

from intelligence.catalog.fetching import (
    USER_AGENT,
    Blocked,
    DisallowedByRobots,
    FetchError,
    PoliteFetcher,
)

# A real Shopify storefront's robots.txt opens with a broad Allow and then
# disallows specific paths. This shape is why the parser choice matters.
SHOPIFY_ROBOTS = """
User-agent: *
Allow: /
Disallow: /recommendations/products
Disallow: /*/recommendations/products
Disallow: /checkout
Crawl-delay: 2
"""


class FakeResponse:
    def __init__(
        self, status: int, *, text: str = "", payload: Any = None, headers: dict | None = None
    ) -> None:
        self.status_code = status
        self.text = text
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeClient:
    """Stands in for the HTTP client, recording every request."""

    def __init__(self, responses: dict[str, list[FakeResponse]]) -> None:
        self._responses = responses
        self.requests: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.requests.append(url)
        for fragment, queue in self._responses.items():
            if fragment in url:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected request {url}")

    def close(self) -> None:
        return None


def _fetcher(responses: dict[str, list[FakeResponse]], **kwargs: Any) -> PoliteFetcher:
    fetcher = PoliteFetcher(**kwargs)
    fetcher._client = FakeClient(responses)  # noqa: SLF001 - substituting the transport
    return fetcher


def test_a_disallowed_path_is_refused_before_any_request() -> None:
    """The check happens before the fetch, so a disallowed URL costs the host
    nothing."""
    fetcher = _fetcher({"robots.txt": [FakeResponse(200, text=SHOPIFY_ROBOTS)]})
    with pytest.raises(DisallowedByRobots):
        fetcher.get_json("https://shop.test/recommendations/products")
    assert all("robots.txt" in url for url in fetcher._client.requests)  # noqa: SLF001


def test_a_broad_allow_does_not_override_a_specific_disallow() -> None:
    """RFC 9309 says the most specific rule wins. A first-match parser reads this
    exact file as permitting everything, which is how a crawler ends up fetching
    paths a site explicitly refused."""
    fetcher = _fetcher({"robots.txt": [FakeResponse(200, text=SHOPIFY_ROBOTS)]})
    assert fetcher.allowed("https://shop.test/products.json") is True
    assert fetcher.allowed("https://shop.test/recommendations/products") is False
    assert fetcher.allowed("https://shop.test/checkout") is False


def test_a_stated_crawl_delay_is_adopted() -> None:
    fetcher = _fetcher({"robots.txt": [FakeResponse(200, text=SHOPIFY_ROBOTS)]})
    fetcher.allowed("https://shop.test/products.json")
    assert fetcher._hosts["shop.test"].delay_seconds == 2.0  # noqa: SLF001


def test_an_absurd_crawl_delay_is_capped() -> None:
    """A misconfigured or hostile delay must not stall a run indefinitely."""
    fetcher = _fetcher({"robots.txt": [FakeResponse(200, text="User-agent: *\nCrawl-delay: 8000")]})
    fetcher.allowed("https://shop.test/products.json")
    assert fetcher._hosts["shop.test"].delay_seconds <= 30.0  # noqa: SLF001


def test_a_missing_robots_file_is_permission_not_refusal() -> None:
    fetcher = _fetcher({"robots.txt": [FakeResponse(404)]})
    assert fetcher.allowed("https://shop.test/products.json") is True


def test_robots_is_read_once_per_host() -> None:
    fetcher = _fetcher(
        {
            "robots.txt": [FakeResponse(200, text=SHOPIFY_ROBOTS)],
            "products.json": [FakeResponse(200, payload={"products": []})],
        },
        max_retries=0,
    )
    fetcher._hosts.clear()  # noqa: SLF001
    fetcher.get_json("https://shop.test/products.json?page=1")
    fetcher.get_json("https://shop.test/products.json?page=2")
    robots_requests = [u for u in fetcher._client.requests if "robots.txt" in u]  # noqa: SLF001
    assert len(robots_requests) == 1


def test_a_403_is_a_refusal_and_is_not_retried() -> None:
    """Some storefronts sit behind bot management. The honest outcome is that the
    source is unavailable, not that we try to look like someone else."""
    fetcher = _fetcher(
        {"robots.txt": [FakeResponse(404)], "products.json": [FakeResponse(403)]},
        max_retries=3,
    )
    with pytest.raises(Blocked):
        fetcher.get_json("https://shop.test/products.json")
    attempts = [u for u in fetcher._client.requests if "products.json" in u]  # noqa: SLF001
    assert len(attempts) == 1
    assert fetcher.stats.blocked == 1
    assert fetcher.stats.retries == 0


def test_a_404_is_an_answer_and_is_not_retried() -> None:
    fetcher = _fetcher(
        {"robots.txt": [FakeResponse(404)], "products.json": [FakeResponse(404)]}, max_retries=3
    )
    with pytest.raises(FetchError, match="not found"):
        fetcher.get_json("https://shop.test/products.json")
    assert len([u for u in fetcher._client.requests if "products" in u]) == 1  # noqa: SLF001


def test_a_429_is_retried_and_then_succeeds() -> None:
    """Rate limiting is the host asking for patience, which is worth honoring."""
    fetcher = _fetcher(
        {
            "robots.txt": [FakeResponse(404)],
            "products.json": [
                FakeResponse(429, headers={"Retry-After": "0"}),
                FakeResponse(200, payload={"products": [{"id": 1}]}),
            ],
        },
        max_retries=3,
    )
    payload = fetcher.get_json("https://shop.test/products.json")
    assert payload["products"][0]["id"] == 1
    assert fetcher.stats.retries == 1


def test_an_html_response_to_a_json_request_fails_loudly() -> None:
    """A storefront answering HTML is usually a regional redirect or an
    interstitial. Handing that to a connector as if it were a feed is worse than
    failing."""
    fetcher = _fetcher(
        {"robots.txt": [FakeResponse(404)], "products.json": [FakeResponse(200, text="<html>")]},
        max_retries=0,
    )
    with pytest.raises(FetchError, match="not JSON"):
        fetcher.get_json("https://shop.test/products.json")


def test_the_fetcher_identifies_itself() -> None:
    """An anonymous crawler gives an operator no way to contact us or to allow
    us deliberately."""
    assert "genesis" in USER_AGENT
    assert "http" in USER_AGENT


def test_using_the_fetcher_outside_its_context_manager_raises() -> None:
    with pytest.raises(FetchError, match="context manager"):
        PoliteFetcher().get_json("https://shop.test/products.json")


def test_the_real_client_is_constructed_with_the_user_agent() -> None:
    with PoliteFetcher() as fetcher:
        assert isinstance(fetcher._client, httpx2.Client)  # noqa: SLF001
        assert fetcher._client.headers["User-Agent"] == USER_AGENT  # noqa: SLF001
