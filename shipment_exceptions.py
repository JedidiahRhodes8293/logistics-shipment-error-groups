from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import uuid4

import infrai
from infrai import InfraiError
from pydantic import BaseModel, Field


class ShipmentEventType(str, Enum):
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_FAILED = "DELIVERY_FAILED"


class ShipmentEvent(BaseModel):
    event_type: ShipmentEventType
    occurred_at: str
    location_code: str


class ProofOfDeliveryFile(BaseModel):
    document_id: str
    content_type: str
    uploaded_at: str


class ShipmentUpdateRequest(BaseModel):
    shipment_id: str
    tenant_id: str
    events: list[ShipmentEvent] = Field(default_factory=list)
    pod_files: list[ProofOfDeliveryFile] = Field(default_factory=list)


class ShipmentProcessingResult(BaseModel):
    shipment_id: str
    status: Literal["delivered", "exception", "pending"]
    reason: str | None = None
    worker_mode: str


def read_worker_mode() -> str:
    try:
        response = infrai.flags.get_value("logistics-worker-cutover", default_value="legacy")
    except InfraiError as exc:
        if exc.code == "FLAG_NOT_FOUND":
            return "legacy"
        raise
    data = response.get("data")
    if isinstance(data, dict) and "value" in data:
        return str(data["value"])
    return "legacy"


def process_shipment_update(request: ShipmentUpdateRequest) -> ShipmentProcessingResult:
    worker_mode = read_worker_mode()
    event_types = {event.event_type for event in request.events}

    if ShipmentEventType.DELIVERED in event_types and request.pod_files:
        return ShipmentProcessingResult(
            shipment_id=request.shipment_id,
            status="delivered",
            reason=None,
            worker_mode=worker_mode,
        )

    if ShipmentEventType.DELIVERED in event_types and not request.pod_files:
        capture_delivery_exception(request, "missing_pod", worker_mode)
        return ShipmentProcessingResult(
            shipment_id=request.shipment_id,
            status="exception",
            reason="missing_pod",
            worker_mode=worker_mode,
        )

    if ShipmentEventType.DELIVERY_FAILED in event_types:
        capture_delivery_exception(request, "delivery_failed", worker_mode)
        return ShipmentProcessingResult(
            shipment_id=request.shipment_id,
            status="exception",
            reason="delivery_failed",
            worker_mode=worker_mode,
        )

    return ShipmentProcessingResult(
        shipment_id=request.shipment_id,
        status="pending",
        reason=None,
        worker_mode=worker_mode,
    )


def capture_delivery_exception(request: ShipmentUpdateRequest, reason: str, worker_mode: str) -> None:
    last_event = request.events[-1] if request.events else None
    event_name = last_event.event_type.value if last_event else "UNKNOWN"
    idempotency_key = f"shipment-exception:{request.shipment_id}:{reason}"
    infrai.errors.capture(
        {
            "title": f"Shipment {request.shipment_id} entered exception",
            "message": f"Shipment {request.shipment_id} requires review: {reason}",
            "level": "error",
            "fingerprint": [request.tenant_id, reason, event_name],
            "exception": f"ShipmentException: {reason}",
            "context": {
                "shipment_id": request.shipment_id,
                "tenant_id": request.tenant_id,
                "pod_count": len(request.pod_files),
                "worker_mode": worker_mode,
                "idempotency_key": idempotency_key,
            },
        }
    )


def example_request() -> ShipmentUpdateRequest:
    return ShipmentUpdateRequest(
        shipment_id="SHIP-1001",
        tenant_id="tenant-eu-1",
        events=[
            ShipmentEvent(
                event_type=ShipmentEventType.OUT_FOR_DELIVERY,
                occurred_at="2026-09-15T08:00:00Z",
                location_code="AMS-HUB",
            ),
            ShipmentEvent(
                event_type=ShipmentEventType.DELIVERED,
                occurred_at="2026-09-15T12:10:00Z",
                location_code="AMS-STOP-44",
            ),
        ],
        pod_files=[],
    )
