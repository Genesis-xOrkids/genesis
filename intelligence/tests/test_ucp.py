"""UCP discovery, against a captured storefront document.

Discovery decides which path a storefront is read through, so the cases that
matter are the routing ones: a storefront that offers a catalog service, one
that does not, and a malformed document that must not be mistaken for either.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from intelligence.catalog.ucp import (
    CATALOG_TOOLS,
    SHOPPING_SERVICE,
    UcpUnavailable,
    discover,
    route_for,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class FakeFetcher:
    def __init__(self, document: Any = None, *, error: Exception | None = None) -> None:
        self._document = document
        self._error = error
        self.requested: list[str] = []

    def get_json(self, url: str) -> Any:
        self.requested.append(url)
        if self._error is not None:
            raise self._error
        return self._document


def _live_document() -> Any:
    return json.loads((FIXTURES / "ucp_discovery.json").read_text())


def test_a_real_storefront_document_parses() -> None:
    discovery = discover(FakeFetcher(_live_document()), "www.everlane.com")
    assert discovery.version
    assert discovery.supported_versions
    assert discovery.capabilities


def test_the_catalog_endpoint_is_read_from_the_document_not_constructed() -> None:
    """The MCP endpoint usually lives on the canonical myshopify domain rather
    than the storefront domain, so building it from the domain would 404."""
    discovery = discover(FakeFetcher(_live_document()), "www.everlane.com")
    endpoint = discovery.mcp_endpoint
    assert endpoint is not None
    assert endpoint.startswith("https://")
    assert discovery.offers_catalog is True


def test_discovery_is_requested_at_the_well_known_path() -> None:
    fetcher = FakeFetcher(_live_document())
    discover(fetcher, "www.everlane.com")
    assert fetcher.requested == ["https://www.everlane.com/.well-known/ucp"]


def test_a_storefront_without_ucp_is_routed_to_the_public_feed() -> None:
    """Not an error: most storefronts do not implement UCP, and this is a
    routing decision."""
    fetcher = FakeFetcher(error=RuntimeError("404 not found"))
    with pytest.raises(UcpUnavailable):
        discover(fetcher, "shop.test")
    assert route_for(fetcher, "shop.test") == "public_feed"


def test_a_document_without_a_version_is_not_ucp() -> None:
    with pytest.raises(UcpUnavailable, match="states no UCP version"):
        discover(FakeFetcher({"ucp": {}}), "shop.test")


def test_a_non_json_object_is_not_ucp() -> None:
    with pytest.raises(UcpUnavailable):
        discover(FakeFetcher(["not", "a", "document"]), "shop.test")


def test_a_storefront_advertising_ucp_without_a_catalog_service_falls_back() -> None:
    """Advertising the protocol is not the same as offering catalog access."""
    document = {
        "ucp": {
            "version": "2026-08-25",
            "services": {SHOPPING_SERVICE: [{"version": "2026-04-08", "transport": "embedded"}]},
            "capabilities": {},
        }
    }
    discovery = discover(FakeFetcher(document), "shop.test")
    assert discovery.offers_catalog is False
    assert route_for(FakeFetcher(document), "shop.test") == "public_feed"


def test_a_catalog_offering_storefront_is_routed_to_ucp() -> None:
    assert route_for(FakeFetcher(_live_document()), "www.everlane.com") == "ucp"


def test_checkout_tools_are_not_in_the_catalog_surface() -> None:
    """Cart and checkout live on the same endpoint, and the merchants' own
    instructions require human approval before payment. Keeping them out of the
    catalog surface is what stops a retrieval path from acquiring the ability to
    spend money."""
    assert {"search_catalog", "lookup_catalog", "get_product"} == CATALOG_TOOLS
    assert not any("checkout" in tool or "cart" in tool for tool in CATALOG_TOOLS)
