"""The gateway's guarantees, tested without credentials.

A fake client stands in for the SDK so these exercise the real request shaping,
usage accounting, and cost arithmetic. What they cover is what silently breaks:
a stale thinking parameter, a lost cache breakpoint, a refusal read as an answer,
and a cost recorded as zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from intelligence.model_gateway import (
    ModelGateway,
    Platform,
    RefusalError,
    Route,
    UnknownModelError,
    build_request,
    cost_usd,
    model_id_for,
)


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeBlock:
    type: str
    text: str


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    usage: FakeUsage
    stop_reason: str | None = "end_turn"
    stop_details: Any = None


class FakeMessages:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


@dataclass
class FakeClient:
    messages: FakeMessages


def _client(responses: list[FakeResponse] | None = None) -> FakeClient:
    return FakeClient(
        messages=FakeMessages(
            responses
            or [
                FakeResponse(
                    content=[FakeBlock(type="text", text="ok")],
                    usage=FakeUsage(input_tokens=1000, output_tokens=200),
                )
            ]
        )
    )


def test_thinking_is_adaptive_and_never_carries_a_token_budget() -> None:
    """``budget_tokens`` is rejected by current models; adaptive is the only
    on-mode. A request carrying the old shape fails at the API, not here."""
    request = build_request(
        route=Route.conversation,
        platform=Platform.claude_platform_aws,
        system="s",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert request["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in str(request)


def test_effort_lives_inside_output_config_and_follows_the_route() -> None:
    conversation = build_request(
        route=Route.conversation,
        platform=Platform.claude_platform_aws,
        system="s",
        messages=[],
    )
    adjudication = build_request(
        route=Route.adjudication,
        platform=Platform.claude_platform_aws,
        system="s",
        messages=[],
    )
    assert conversation["output_config"] == {"effort": "medium"}
    assert adjudication["output_config"] == {"effort": "xhigh"}
    assert "effort" not in conversation, "effort is not a top-level parameter"


def test_high_volume_extraction_routes_to_the_cheap_model() -> None:
    request = build_request(
        route=Route.extraction, platform=Platform.claude_platform_aws, system="s", messages=[]
    )
    assert request["model"] == "claude-haiku-4-5"


def test_cache_breakpoint_lands_on_the_last_system_block() -> None:
    """The stable prefix is paid for once per window; without the breakpoint the
    system prompt and tool schemas are re-billed on every turn."""
    request = build_request(
        route=Route.conversation,
        platform=Platform.claude_platform_aws,
        system=[{"type": "text", "text": "rules"}, {"type": "text", "text": "schemas"}],
        messages=[],
    )
    assert "cache_control" not in request["system"][0]
    assert request["system"][1]["cache_control"] == {"type": "ephemeral"}


def test_cache_breakpoint_can_be_disabled_for_volatile_prompts() -> None:
    request = build_request(
        route=Route.conversation,
        platform=Platform.claude_platform_aws,
        system="s",
        messages=[],
        cache_system=False,
    )
    assert "cache_control" not in request["system"][0]


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        (Platform.claude_platform_aws, "claude-opus-5"),
        (Platform.bedrock_mantle, "anthropic.claude-opus-5"),
    ],
)
def test_model_ids_are_translated_per_platform(platform: Platform, expected: str) -> None:
    assert model_id_for(platform, "claude-opus-5") == expected


def test_the_two_platforms_differ_only_in_the_model_id() -> None:
    """Switching a tenant to Bedrock is a setting, not a rewrite: the request
    body has to be otherwise identical or that claim is false."""
    kwargs: dict[str, Any] = {
        "route": Route.synthesis,
        "system": "shared prompt",
        "messages": [{"role": "user", "content": "hi"}],
    }
    on_aws = build_request(platform=Platform.claude_platform_aws, **kwargs)
    on_bedrock = build_request(platform=Platform.bedrock_mantle, **kwargs)

    assert on_aws.pop("model") == "claude-opus-5"
    assert on_bedrock.pop("model") == "anthropic.claude-opus-5"
    assert on_aws == on_bedrock


def test_cost_is_computed_from_reported_usage() -> None:
    """1M input and 1M output on Opus 5 is $5 + $25."""
    assert cost_usd("claude-opus-5", input_tokens=1_000_000, output_tokens=1_000_000) == Decimal(30)


def test_cached_reads_are_priced_at_a_tenth_of_input() -> None:
    uncached = cost_usd("claude-opus-5", input_tokens=1_000_000, output_tokens=0)
    cached = cost_usd("claude-opus-5", input_tokens=0, output_tokens=0, cache_read_tokens=1_000_000)
    assert cached == uncached / 10


def test_bedrock_prefixed_ids_price_identically() -> None:
    """One price table serves both platforms; a prefix must not change the cost."""
    assert cost_usd("anthropic.claude-opus-5", input_tokens=1000, output_tokens=1000) == cost_usd(
        "claude-opus-5", input_tokens=1000, output_tokens=1000
    )


def test_an_unpriced_model_raises_rather_than_costing_zero() -> None:
    """No silent fallbacks: a zero cost corrupts every budget that reads it."""
    with pytest.raises(UnknownModelError):
        cost_usd("claude-nonexistent-9", input_tokens=1, output_tokens=1)


def test_complete_reports_usage_and_cost() -> None:
    gateway = ModelGateway(
        _client(
            [
                FakeResponse(
                    content=[FakeBlock(type="text", text="a styled answer")],
                    usage=FakeUsage(
                        input_tokens=1_000,
                        output_tokens=500,
                        cache_read_input_tokens=10_000,
                    ),
                )
            ]
        )
    )
    result = gateway.complete(
        route=Route.conversation, system="s", messages=[{"role": "user", "content": "hi"}]
    )
    assert result.text == "a styled answer"
    assert result.usage.cache_hit is True
    # 1000 * 5/1e6 + 500 * 25/1e6 + 10000 * 0.5/1e6
    assert result.cost_usd == Decimal("0.0225")


def test_a_refusal_raises_instead_of_returning_empty_text() -> None:
    """A refusal is HTTP 200 with empty content; reading it as an answer is how a
    decline reaches a user as a blank recommendation."""

    @dataclass
    class Details:
        category: str = "cyber"

    gateway = ModelGateway(
        _client(
            [
                FakeResponse(
                    content=[],
                    usage=FakeUsage(input_tokens=10, output_tokens=0),
                    stop_reason="refusal",
                    stop_details=Details(),
                )
            ]
        )
    )
    with pytest.raises(RefusalError, match="declined"):
        gateway.complete(route=Route.conversation, system="s", messages=[])


def test_repeated_calls_reuse_the_same_cached_prefix() -> None:
    """The prefix has to be byte-identical across turns or the cache never hits.

    This is the check that catches a timestamp or a per-request id sneaking into
    the system prompt, which is the usual cause of a cache-hit rate of zero.
    """
    client = _client()
    gateway = ModelGateway(client)
    system = "frozen stylist instructions"
    for turn in range(3):
        gateway.complete(
            route=Route.conversation,
            system=system,
            messages=[{"role": "user", "content": f"turn {turn}"}],
        )
    prefixes = {repr(call["system"]) for call in client.messages.calls}
    assert len(prefixes) == 1, "the cached prefix changed between turns"


def test_gateway_defaults_to_claude_platform_on_aws() -> None:
    assert ModelGateway(_client()).platform is Platform.claude_platform_aws
