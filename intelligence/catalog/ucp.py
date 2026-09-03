"""Universal Commerce Protocol discovery.

Shopify storefronts advertise a sanctioned agent interface in their own
robots.txt and serve a discovery document at ``/.well-known/ucp``. Their agent
instructions are explicit that agents should prefer it over reading the
storefront directly, and a specified, versioned protocol does not change shape
underneath us the way a page can. So this exists to answer one question per
storefront: is there a sanctioned path, and where is it?

Two things this deliberately does not do.

It does not wrap the cart or checkout tools. Those exist on the same endpoint,
and the merchants' own instructions require a contemporaneous human approval
before payment. Exposing them from the catalog layer is exactly the excessive
agency failure the tool boundary is built to prevent; when checkout is built it
gets its own gated surface.

It does not call the catalog tools either, yet. A merchant server fetches back
the agent profile URI we send and refuses the call if it is unreachable, so
catalog access requires Genesis to publish a profile at a real URL. That is a
deployment prerequisite, and the honest state until then is that discovery
works and calls do not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

DISCOVERY_PATH = "/.well-known/ucp"
SHOPPING_SERVICE = "dev.ucp.shopping"

# Catalog tools on the shopping service. Checkout and cart tools are excluded on
# purpose; see the module docstring.
CATALOG_TOOLS = frozenset({"search_catalog", "lookup_catalog", "get_product"})


class JsonFetcher(Protocol):
    def get_json(self, url: str) -> Any: ...


class UcpError(RuntimeError):
    pass


class UcpUnavailable(UcpError):
    """The storefront advertises no UCP support.

    Not a failure. Most storefronts do not implement it, and the caller falls
    back to the public product feed.
    """


@dataclass(frozen=True)
class UcpService:
    """One transport a storefront offers for a UCP service."""

    name: str
    version: str
    transport: str
    spec: str | None = None
    schema: str | None = None
    endpoint: str | None = None


@dataclass(frozen=True)
class UcpDiscovery:
    """What one storefront says it supports."""

    domain: str
    version: str
    supported_versions: tuple[str, ...]
    services: tuple[UcpService, ...]
    capabilities: tuple[str, ...]

    @property
    def mcp_endpoint(self) -> str | None:
        """The shopping service's MCP endpoint, when it offers one.

        The endpoint is frequently on the store's canonical myshopify domain
        rather than the storefront domain, so it is read from the document
        rather than constructed.
        """
        for service in self.services:
            if service.name == SHOPPING_SERVICE and service.transport == "mcp" and service.endpoint:
                return service.endpoint
        return None

    @property
    def offers_catalog(self) -> bool:
        return self.mcp_endpoint is not None


def _parse_services(raw: dict[str, Any]) -> tuple[UcpService, ...]:
    services: list[UcpService] = []
    for name, entries in (raw.get("services") or {}).items():
        for entry in entries or []:
            services.append(
                UcpService(
                    name=str(name),
                    version=str(entry.get("version", "")),
                    transport=str(entry.get("transport", "")),
                    spec=entry.get("spec"),
                    schema=entry.get("schema"),
                    endpoint=entry.get("endpoint"),
                )
            )
    return tuple(services)


def discover(fetcher: JsonFetcher, domain: str) -> UcpDiscovery:
    """Read a storefront's UCP discovery document.

    Raises :class:`UcpUnavailable` when the storefront does not advertise UCP,
    which is the common case and a routing decision rather than an error.
    """
    url = f"https://{domain}{DISCOVERY_PATH}"
    try:
        payload = fetcher.get_json(url)
    except Exception as exc:  # noqa: BLE001 - any failure here means "no UCP"
        raise UcpUnavailable(f"{domain}: no UCP discovery document ({exc})") from exc

    block = payload.get("ucp") if isinstance(payload, dict) else None
    if not isinstance(block, dict) or not block.get("version"):
        raise UcpUnavailable(f"{domain}: discovery document states no UCP version")

    discovery = UcpDiscovery(
        domain=domain,
        version=str(block["version"]),
        supported_versions=tuple(str(v) for v in (block.get("supported_versions") or {})),
        services=_parse_services(block),
        capabilities=tuple(str(c) for c in (block.get("capabilities") or {})),
    )
    log.info(
        "ucp_discovered",
        domain=domain,
        version=discovery.version,
        offers_catalog=discovery.offers_catalog,
        capabilities=len(discovery.capabilities),
    )
    return discovery


def route_for(fetcher: JsonFetcher, domain: str) -> str:
    """Which path to read this storefront through.

    Returns ``"ucp"`` when the storefront advertises a usable catalog service and
    ``"public_feed"`` otherwise. Keeping the decision in one function means the
    ingestion job never has to guess, and adoption can be measured by counting
    what this returns.
    """
    try:
        discovery = discover(fetcher, domain)
    except UcpUnavailable:
        return "public_feed"
    return "ucp" if discovery.offers_catalog else "public_feed"
