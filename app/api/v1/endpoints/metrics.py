"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.core.telemetry import metrics_payload

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(
        content=metrics_payload(), headers={"Content-Type": CONTENT_TYPE_LATEST}
    )
