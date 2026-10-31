"""Prometheus RED metrics for HTTP, plus gauges/counters used by domain code."""
from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter(
    "crimeai_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "crimeai_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
WS_CONNECTIONS = Gauge("crimeai_ws_connections", "Open alert-stream WebSocket connections")
ML_INFERENCE_SECONDS = Histogram(
    "crimeai_ml_inference_seconds", "Time spent in synchronous model inference", ["model"]
)
ALERTS_RAISED = Counter("crimeai_alerts_raised_total", "Alerts raised by automated detectors", ["alert_type"])


class PrometheusMiddleware:
    """Pure ASGI so it adds no per-request task overhead and never touches streaming bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            # Route templates keep label cardinality bounded (no raw IDs in labels).
            template = getattr(route, "path", "unmatched")
            method = scope.get("method", "GET")
            HTTP_REQUESTS.labels(method, template, str(status_holder["code"])).inc()
            HTTP_LATENCY.labels(method, template).observe(time.perf_counter() - start)


async def metrics_endpoint(_: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
