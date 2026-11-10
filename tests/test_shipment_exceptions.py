import pytest

from infrai import InfraiError
from shipment_exceptions import (
    ProofOfDeliveryFile,
    ShipmentEvent,
    ShipmentEventType,
    ShipmentUpdateRequest,
    process_shipment_update,
    read_worker_mode,
)


def test_missing_cutover_flag_uses_legacy(monkeypatch):
    def missing_flag(*args, **kwargs):
        raise InfraiError("FLAG_NOT_FOUND", {"code": "FLAG_NOT_FOUND"}, 404)

    monkeypatch.setattr("shipment_exceptions.infrai.flags.get_value", missing_flag)

    assert read_worker_mode() == "legacy"


def test_other_flag_errors_propagate(monkeypatch):
    error = InfraiError("UNAUTHORIZED", {"code": "UNAUTHORIZED"}, 401)

    def failed_flag(*args, **kwargs):
        raise error

    monkeypatch.setattr("shipment_exceptions.infrai.flags.get_value", failed_flag)

    with pytest.raises(InfraiError) as caught:
        read_worker_mode()
    assert caught.value is error


class _FakeFlags:
    @staticmethod
    def get_value(key, default_value):
        assert key == "logistics-worker-cutover"
        assert default_value == "legacy"
        return {"data": {"value": "infrai"}, "metadata": {}}


class _FakeErrors:
    def __init__(self):
        self.payloads = []

    def capture(self, payload):
        self.payloads.append(payload)
        return {"data": {"event_id": "evt-1"}, "metadata": {}}


class _FakeInfrai:
    def __init__(self):
        self.errors = _FakeErrors()
        self.flags = _FakeFlags()


def test_missing_pod_becomes_exception_and_captures_grouped_error(monkeypatch):
    fake_infrai = _FakeInfrai()
    monkeypatch.setattr("shipment_exceptions.infrai", fake_infrai)

    request = ShipmentUpdateRequest(
        shipment_id="SHIP-42",
        tenant_id="tenant-1",
        events=[
            ShipmentEvent(
                event_type=ShipmentEventType.DELIVERED,
                occurred_at="2026-09-15T10:00:00Z",
                location_code="LHR-22",
            )
        ],
        pod_files=[],
    )

    result = process_shipment_update(request)

    assert result.status == "exception"
    assert result.reason == "missing_pod"
    assert result.worker_mode == "infrai"
    assert len(fake_infrai.errors.payloads) == 1
    payload = fake_infrai.errors.payloads[0]
    assert payload["fingerprint"] == ["tenant-1", "missing_pod", "DELIVERED"]
    assert payload["context"]["shipment_id"] == "SHIP-42"


def test_delivered_with_pod_stays_delivered(monkeypatch):
    fake_infrai = _FakeInfrai()
    monkeypatch.setattr("shipment_exceptions.infrai", fake_infrai)

    request = ShipmentUpdateRequest(
        shipment_id="SHIP-43",
        tenant_id="tenant-1",
        events=[
            ShipmentEvent(
                event_type=ShipmentEventType.DELIVERED,
                occurred_at="2026-09-15T10:05:00Z",
                location_code="LHR-22",
            )
        ],
        pod_files=[
            ProofOfDeliveryFile(
                document_id="pod-1",
                content_type="image/jpeg",
                uploaded_at="2026-09-15T10:06:00Z",
            )
        ],
    )

    result = process_shipment_update(request)

    assert result.status == "delivered"
    assert result.reason is None
    assert fake_infrai.errors.payloads == []
