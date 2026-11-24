"""History: a log of setpoint changes and of water temperature readings.

Stored in a second DynamoDB table, keyed by kind and time:

  kind = "change"       at, setpoint ("off" | "104" ...), source, changed_by
  kind = "temperature"  at, temperature, heating

Items carry an `expires` attribute and DynamoDB deletes them after it:
temperature readings after 35 days, changes after 400 days.

History is a convenience.  Failing to record it must never stop the tub from
being controlled, so the record_* functions log errors instead of raising.
"""

import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

from common import ApiError, respond

TABLE = boto3.resource("dynamodb").Table(os.environ["HISTORY_TABLE_NAME"])

TEMPERATURE_DAYS = 35
CHANGE_DAYS = 400

# The periods the UI may ask for, in hours: a day, a week, 30 days.
PERIODS = (24, 168, 720)
# A graph does not need more points than it has pixels.
MAX_POINTS = 240
MAX_CHANGES = 100

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def record_change(at: str, setpoint: str, source: str, changed_by) -> None:
    item = {"setpoint": setpoint, "source": source}
    if changed_by is not None:
        item["changed_by"] = changed_by
    _record("change", at, CHANGE_DAYS, item)


def record_temperature(at: str, temperature, heating: bool) -> None:
    _record("temperature", at, TEMPERATURE_DAYS, {"temperature": temperature, "heating": heating})


def _record(kind: str, at: str, keep_days: int, attributes: dict) -> None:
    try:
        expires = _parse(at) + timedelta(days=keep_days)
        TABLE.put_item(Item={"kind": kind, "at": at, "expires": int(expires.timestamp()), **attributes})
    except Exception as e:
        print(f"Could not record {kind} history: {type(e).__name__}: {e}")


def get_history(event, user):
    """GET /history?hours=24 — temperature readings and setpoint changes."""
    raw = (event.get("queryStringParameters") or {}).get("hours", "24")
    if raw not in {str(p) for p in PERIODS}:
        raise ApiError(400, f"'hours' must be one of {', '.join(str(p) for p in PERIODS)}")
    hours = int(raw)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    readings = _query("temperature", start)
    changes = _query("change", start)
    changes.reverse()  # newest first

    return respond(200, {
        "hours": hours,
        "from": start.strftime(_TIME_FORMAT),
        "to": end.strftime(_TIME_FORMAT),
        "stats": {
            "heating_hours": round(heating_hours(readings), 1),
            # Times someone (or a timer) asked for a temperature, not "off".
            "times_used": sum(1 for c in changes if c["setpoint"] != "off" and c["source"] != "schedule"),
        },
        "temperatures": _downsample(readings, start, end),
        "changes": [
            {
                "at": c["at"],
                "setpoint": c["setpoint"],
                "source": c["source"],
                "changed_by": c.get("changed_by"),
            }
            for c in changes[:MAX_CHANGES]
        ],
    })


# A gap longer than this between readings (the tub was unreachable) is not
# counted as heating time, whatever the reading before it said.
MAX_GAP_SECONDS = 10 * 60


def heating_hours(readings: list) -> float:
    """Hours the heater was on, from readings in time order."""
    seconds = 0.0
    for before, after in zip(readings, readings[1:]):
        gap = (_parse(after["at"]) - _parse(before["at"])).total_seconds()
        if before.get("heating") and gap <= MAX_GAP_SECONDS:
            seconds += gap
    return seconds / 3600


def readings_since(start: datetime) -> list:
    """Temperature readings since `start`, oldest first, as stored."""
    return _query("temperature", start)


def _query(kind: str, start: datetime) -> list:
    """All items of one kind since `start`, oldest first."""
    condition = Key("kind").eq(kind) & Key("at").gte(start.strftime(_TIME_FORMAT))
    items, kwargs = [], {}
    while True:
        page = TABLE.query(KeyConditionExpression=condition, **kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _downsample(readings: list, start: datetime, end: datetime) -> list:
    """Reduce readings to at most MAX_POINTS by averaging within equal time slots."""
    width = (end - start).total_seconds() / MAX_POINTS
    slots = {}
    for reading in readings:
        index = int((_parse(reading["at"]) - start).total_seconds() // width)
        slots.setdefault(min(max(index, 0), MAX_POINTS - 1), []).append(reading)

    points = []
    for index in sorted(slots):
        group = slots[index]
        points.append({
            "at": group[-1]["at"],
            "temperature": round(sum(float(r["temperature"]) for r in group) / len(group), 1),
            "heating": any(r.get("heating") for r in group),
        })
    return points


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, _TIME_FORMAT).replace(tzinfo=timezone.utc)
