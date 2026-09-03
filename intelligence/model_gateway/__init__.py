"""The single entry point for model access.

Import from here, never from ``anthropic`` directly: provider selection, cache
placement, effort routing, and cost accounting live behind this boundary.
"""

from intelligence.model_gateway.gateway import (
    ROUTES,
    Completion,
    Effort,
    ModelGateway,
    ModelGatewayError,
    Platform,
    RefusalError,
    Route,
    RouteConfig,
    Usage,
    build_client,
    build_request,
    model_id_for,
)
from intelligence.model_gateway.pricing import (
    MODEL_PRICES,
    ModelPrice,
    UnknownModelError,
    bare_model_id,
    cost_usd,
    price_for,
)

__all__ = [
    "MODEL_PRICES",
    "ROUTES",
    "Completion",
    "Effort",
    "ModelGateway",
    "ModelGatewayError",
    "ModelPrice",
    "Platform",
    "RefusalError",
    "Route",
    "RouteConfig",
    "UnknownModelError",
    "Usage",
    "bare_model_id",
    "build_client",
    "build_request",
    "cost_usd",
    "model_id_for",
    "price_for",
]
