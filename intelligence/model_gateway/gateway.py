"""The one model gateway.

Every model call in the platform goes through here. Nothing else imports the
Anthropic SDK, so provider selection, prompt-cache placement, effort routing,
usage accounting, and cost attribution have exactly one implementation.

Two platforms sit behind one interface:

- **Claude Platform on AWS** (default) - the full Claude API surface, reached
  with bare model ids.
- **Claude in Amazon Bedrock** (``bedrock-mantle``) - AWS as sole data processor,
  reached with ``anthropic.``-prefixed ids, for tenants whose security review
  requires it.

The request body is the same on both; only the client and the model id differ,
which is what makes the platform a per-tenant setting rather than a rewrite.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, cast

import structlog

from intelligence.model_gateway.pricing import bare_model_id, cost_usd

log = structlog.get_logger(__name__)


class Platform(enum.Enum):
    """Where a call is served. Selected per tenant, not per call site.

    ``anthropic_api`` is the first-party API: no AWS account in the path, billed
    on prepaid credits with a spend limit set in Anthropic's console. It is the
    right default while the product is in testing, because it removes a cloud
    dependency from something that has no other reason to need one.

    The other two exist for customers rather than for us. ``claude_platform_aws``
    bills through AWS Marketplace while keeping full API parity;
    ``bedrock_mantle`` puts AWS in the position of sole data processor, which
    some enterprise security reviews require.
    """

    anthropic_api = "anthropic_api"
    claude_platform_aws = "claude_platform_aws"
    bedrock_mantle = "bedrock_mantle"


class Effort(enum.Enum):
    """Thinking depth, tuned per route rather than globally.

    Chat turns run at medium, reports at high, and only correctness-critical
    adjudication earns max. Raising a default without measuring is how an
    inference bill doubles for no quality gain.
    """

    low = "low"
    medium = "medium"
    high = "high"
    xhigh = "xhigh"
    max = "max"


class Route(enum.Enum):
    """What a call is for.

    Routes exist so model and effort are chosen by the work, in one table, rather
    than by whoever wrote the call site.
    """

    conversation = "conversation"
    synthesis = "synthesis"
    extraction = "extraction"
    adjudication = "adjudication"


@dataclass(frozen=True)
class RouteConfig:
    model: str
    effort: Effort


# The routing table from PLAN.md section 4.2. Opus 5 for judgment, Haiku 4.5 for
# volume. Sonnet 5 is deliberately absent: it is a cost-optimization to adopt
# after evals show parity on a route, not a default to drift into.
ROUTES: dict[Route, RouteConfig] = {
    Route.conversation: RouteConfig(model="claude-opus-5", effort=Effort.medium),
    Route.synthesis: RouteConfig(model="claude-opus-5", effort=Effort.high),
    Route.extraction: RouteConfig(model="claude-haiku-4-5", effort=Effort.low),
    Route.adjudication: RouteConfig(model="claude-opus-5", effort=Effort.xhigh),
}


class MessagesClient(Protocol):
    """The slice of the Anthropic client the gateway uses.

    Narrow on purpose: it keeps the gateway testable without credentials and
    makes the coupling to the SDK one method wide.
    """

    def create(self, **kwargs: Any) -> Any: ...


class AnthropicClient(Protocol):
    messages: MessagesClient


@dataclass
class Usage:
    """Token accounting for one call, straight from the response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def cache_hit(self) -> bool:
        return self.cache_read_tokens > 0


@dataclass
class Completion:
    """One model call's result, with what it cost."""

    text: str
    model: str
    platform: Platform
    usage: Usage
    cost_usd: Decimal
    stop_reason: str | None
    latency_ms: int
    raw: Any = field(repr=False, default=None)


class ModelGatewayError(RuntimeError):
    pass


class RefusalError(ModelGatewayError):
    """Raised when the model declined the request.

    A refusal returns HTTP 200 with ``stop_reason == "refusal"``, so code that
    reads ``content`` without checking gets an empty string and treats a decline
    as an answer.
    """


def model_id_for(platform: Platform, model: str) -> str:
    """The id this platform expects for a model.

    Bedrock carries an ``anthropic.`` prefix; Claude Platform on AWS uses the
    bare id. Callers name models bare and the gateway translates, so a tenant
    switching platforms changes one setting.
    """
    bare = bare_model_id(model)
    if platform is Platform.bedrock_mantle:
        return f"anthropic.{bare}"
    return bare


def build_client(platform: Platform, *, aws_region: str | None = None) -> AnthropicClient:
    """Construct the SDK client for one platform.

    The only place in the codebase that imports the Anthropic SDK's client
    classes. Callers name a platform and get a client; nothing else needs to know
    that the three differ in construction, authentication, or billing.

    Credentials are resolved by the SDK from the environment rather than passed
    in, so no key is ever held in application code or a settings object.
    """
    import anthropic

    if platform is Platform.anthropic_api:
        # Resolves ANTHROPIC_API_KEY, or an `ant auth login` profile.
        return cast(AnthropicClient, anthropic.Anthropic())

    if platform is Platform.claude_platform_aws:
        # Region and workspace come from AWS_REGION and
        # ANTHROPIC_AWS_WORKSPACE_ID; both are required and the client raises at
        # construction if either is missing, which is the right time to find out.
        return cast(AnthropicClient, anthropic.AnthropicAWS())

    if platform is Platform.bedrock_mantle:
        if not aws_region:
            raise ModelGatewayError(
                "bedrock_mantle needs an AWS region; pass aws_region or set AWS_REGION"
            )
        return cast(AnthropicClient, anthropic.AnthropicBedrockMantle(aws_region=aws_region))

    raise ModelGatewayError(f"no client for platform {platform!r}")


def build_request(
    *,
    route: Route,
    platform: Platform,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tokens: int = 8192,
    tools: list[dict[str, Any]] | None = None,
    cache_system: bool = True,
) -> dict[str, Any]:
    """Shape one request.

    Three things this always does, because getting them wrong is silent:

    - **Adaptive thinking, never a token budget.** ``budget_tokens`` is rejected
      by current models; adaptive is the only on-mode.
    - **Effort from the route**, inside ``output_config`` where the API expects
      it, not as a top-level field.
    - **A cache breakpoint on the system prefix** when it is cacheable, so the
      frozen instructions and tool schemas are paid for once per window rather
      than on every turn.
    """
    config = ROUTES[route]
    system_blocks: list[dict[str, Any]]
    if isinstance(system, str):
        system_blocks = [{"type": "text", "text": system}]
    else:
        system_blocks = [dict(block) for block in system]

    if cache_system and system_blocks:
        # The breakpoint goes on the last system block: everything before it is
        # the stable prefix. Volatile per-request context belongs in messages,
        # after this point, or it invalidates the cache on every call.
        system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}

    request: dict[str, Any] = {
        "model": model_id_for(platform, config.model),
        "max_tokens": max_tokens,
        "system": system_blocks,
        "messages": messages,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": config.effort.value},
    }
    if tools:
        request["tools"] = tools
    return request


def _extract_usage(response: Any) -> Usage:
    raw = getattr(response, "usage", None)
    if raw is None:
        return Usage()
    return Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "".join(parts)


class ModelGateway:
    """Calls Claude, prices the call, and records what it cost.

    Construct one per process and pass it down. It does not own credentials
    beyond the client it is given, so tests inject a fake client and exercise
    the same code path production uses.
    """

    def __init__(
        self,
        client: AnthropicClient,
        *,
        platform: Platform = Platform.claude_platform_aws,
        tenant_id: int | None = None,
    ) -> None:
        self._client = client
        self._platform = platform
        self._tenant_id = tenant_id

    @property
    def platform(self) -> Platform:
        return self._platform

    def complete(
        self,
        *,
        route: Route,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,
        tools: list[dict[str, Any]] | None = None,
        cache_system: bool = True,
    ) -> Completion:
        request = build_request(
            route=route,
            platform=self._platform,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            tools=tools,
            cache_system=cache_system,
        )

        started = time.perf_counter()
        response = self._client.messages.create(**request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise RefusalError(
                f"model declined the request (category="
                f"{getattr(details, 'category', None)!r}); handle this rather than "
                "reading empty content as an answer"
            )

        usage = _extract_usage(response)
        model = request["model"]
        spend = cost_usd(
            model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )

        log.info(
            "model_call",
            route=route.value,
            model=model,
            platform=self._platform.value,
            tenant_id=self._tenant_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cache_hit=usage.cache_hit,
            cost_usd=str(spend),
            latency_ms=latency_ms,
        )

        return Completion(
            text=_extract_text(response),
            model=model,
            platform=self._platform,
            usage=usage,
            cost_usd=spend,
            stop_reason=stop_reason,
            latency_ms=latency_ms,
            raw=response,
        )
