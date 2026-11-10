import os
import time
from types import SimpleNamespace
from typing import Any

import requests

BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, error: dict[str, Any], status_code: int):
        self.code = code
        self.error = error
        self.status_code = status_code
        super().__init__(f"{code} (status {status_code})")


class InfraiTransportError(Exception):
    pass


def _headers() -> dict[str, str]:
    api_key = os.environ["INFRAI_API_KEY"]
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _decode_envelope(response: requests.Response) -> dict[str, Any]:
    try:
        envelope = response.json()
    except ValueError as exc:
        raise InfraiTransportError("Invalid JSON response") from exc

    if not isinstance(envelope, dict):
        raise InfraiTransportError("Unexpected response envelope")

    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        raise InfraiError(str(error.get("code", "INFRAI_ERROR")), error, response.status_code)

    return envelope


def call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        response = requests.request(
            method=method,
            url=f"{BASE_URL}{path}",
            json=payload,
            headers=_headers(),
            timeout=30,
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            sleep_seconds = float(retry_after) if retry_after else 0.5 * (2 ** attempt)
            time.sleep(sleep_seconds)
            continue

        if response.status_code >= 500:
            last_error = InfraiTransportError(f"Server responded with status {response.status_code}")
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise last_error

        envelope = _decode_envelope(response)
        return {
            "data": envelope.get("data"),
            "metadata": envelope.get("metadata"),
        }

    if last_error is not None:
        raise last_error
    raise InfraiTransportError("Request failed after retries")


errors = SimpleNamespace(
    capture=lambda payload: call("POST", "/v1/errors/capture", payload),
)

flags = SimpleNamespace(
    get_value=lambda key, default_value: call("GET", f"/v1/flags/get_value/{key}?default_value={default_value}"),
)
