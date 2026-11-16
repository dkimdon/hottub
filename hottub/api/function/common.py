"""Small helpers shared by the route handlers."""

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal


class ApiError(Exception):
    """Raised by handlers to return an HTTP error to the caller."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_body(event) -> dict:
    """Return the request body as a dict; raise a 400 for anything else."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except ValueError:
            raise ApiError(400, "Invalid request body")
    if not raw:
        return {}
    try:
        body = json.loads(raw, parse_constant=_reject_constant)
    except ValueError:
        raise ApiError(400, "Request body must be valid JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return body


def _reject_constant(name):
    # NaN and Infinity are accepted by Python's JSON parser but are not JSON.
    raise ValueError(f"Invalid JSON constant {name}")


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=_json_default),
    }


def _json_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Cannot serialise {type(obj).__name__}")
