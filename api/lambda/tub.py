"""Hot tub control API — Lambda handler.

Routes
------
GET  /tub                  Return full tub state                (Cognito auth)
PUT  /tub/setpoint         Set desired temperature or "off"     (Cognito auth)
GET  /operator/desired     Return desired setpoint              (API key auth)
PUT  /operator/report      Operator reports current temperature (API key auth)
OPTIONS *                  CORS preflight                       (no auth)

DynamoDB item
-------------
pk = "tub", sk = "state"
  desired_setpoint       : "off" | "102" … "106"
  setpoint_changed_at    : ISO-8601 UTC string
  setpoint_changed_by    : Cognito username
  current_temperature    : Decimal (°F)
  temperature_measured_at: ISO-8601 UTC string
  operator_last_seen_at  : ISO-8601 UTC string
"""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
TABLE = dynamodb.Table(os.environ["TABLE_NAME"])

TUB_KEY = {"pk": "tub", "sk": "state"}
VALID_SETPOINTS = {"off"} | {str(t) for t in range(102, 107)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    method = event.get("httpMethod", "")
    path = event.get("path", "")

    if method == "OPTIONS":
        return _respond(200, {})

    routes = {
        ("GET", "/tub"):                _get_tub,
        ("PUT", "/tub/setpoint"):       _put_setpoint,
        ("GET", "/operator/desired"):   _get_desired,
        ("PUT", "/operator/report"):    _put_report,
    }

    fn = routes.get((method, path))
    if fn is None:
        return _respond(404, {"error": "Not found"})

    try:
        return fn(event)
    except Exception as e:
        print(f"Unhandled error on {method} {path}: {e}")
        return _respond(500, {"error": "Internal server error"})


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _get_tub(event):
    return _respond(200, _read_state())


def _put_setpoint(event):
    body = _parse_body(event)
    if body is None:
        return _respond(400, {"error": "Invalid JSON body"})

    raw = body.get("setpoint")
    if raw is None:
        return _respond(400, {"error": "Missing 'setpoint' field"})

    setpoint = str(int(raw)) if isinstance(raw, (int, float)) else str(raw)
    if setpoint not in VALID_SETPOINTS:
        return _respond(400, {"error": "setpoint must be 'off' or an integer 102–106"})

    username = _cognito_username(event)
    now = _now()

    TABLE.update_item(
        Key=TUB_KEY,
        UpdateExpression=(
            "SET desired_setpoint = :s, "
            "setpoint_changed_at = :t, "
            "setpoint_changed_by = :u"
        ),
        ExpressionAttributeValues={":s": setpoint, ":t": now, ":u": username},
    )
    return _respond(200, {"setpoint": setpoint, "changed_by": username, "changed_at": now})


def _get_desired(event):
    state = _read_state()
    return _respond(200, {
        "desired_setpoint":    state.get("desired_setpoint", "off"),
        "setpoint_changed_at": state.get("setpoint_changed_at"),
        "setpoint_changed_by": state.get("setpoint_changed_by"),
    })


def _put_report(event):
    body = _parse_body(event)
    if body is None:
        return _respond(400, {"error": "Invalid JSON body"})

    now = _now()
    updates = {"operator_last_seen_at": now}

    temp = body.get("current_temperature")
    if temp is not None:
        if not isinstance(temp, (int, float)):
            return _respond(400, {"error": "'current_temperature' must be a number"})
        updates["current_temperature"] = Decimal(str(temp))
        updates["temperature_measured_at"] = now

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    expr_values = {f":{k}": v for k, v in updates.items()}

    TABLE.update_item(
        Key=TUB_KEY,
        UpdateExpression=f"SET {set_clause}",
        ExpressionAttributeValues=expr_values,
    )
    return _respond(200, {"reported_at": now})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_state() -> dict:
    result = TABLE.get_item(Key=TUB_KEY)
    item = result.get("Item", {})
    item.pop("pk", None)
    item.pop("sk", None)
    return item


def _parse_body(event) -> dict | None:
    body = event.get("body") or ""
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _cognito_username(event) -> str:
    claims = (
        event.get("requestContext", {})
             .get("authorizer", {})
             .get("claims", {})
    )
    return claims.get("cognito:username") or claims.get("email") or "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,x-api-key",
            "Access-Control-Allow-Methods": "GET,PUT,OPTIONS",
        },
        "body": json.dumps(body, cls=_DecimalEncoder),
    }


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)
