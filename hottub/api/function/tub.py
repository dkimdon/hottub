"""Tub state: what users want the tub to do, and what the operator reports.

Everything lives in one DynamoDB item (id = "tub").

Desired state — what the tub should be doing.  Stored as the three tub
controls, exactly as the tub itself represents them:

  desired_heating_mode       "ready" | "rest"
  desired_temperature_range  "high" | "low"
  desired_set_temperature    integer °F
  desired_version            integer, incremented on every change
  setpoint_changed_at        ISO-8601 UTC
  setpoint_source            "ui" | "panel" | "schedule" | "timer"
  setpoint_changed_by        email of the user (sources "ui" and "timer")

The most recent change wins, wherever it was made:
  * a user picks a setpoint in the web UI                    (source "ui")
  * someone presses buttons on the tub's front panel; the
    operator notices and reports the tub's new state         (source "panel")
  * the nightly automatic turn-off                           (source "schedule")
  * a timer someone set to have the tub hot by a given time   (source "timer";
    see "Timer" below)

Reported state — written by the operator:

  current_temperature      °F, last value the tub reported
  temperature_measured_at  when that value was read
  tub_set_temperature, tub_heating_mode, tub_temperature_range, tub_heating
  tub_last_seen_at         last time the operator reached the tub
  operator_last_seen_at    last time the operator reached this API

Cached for the heating estimate (see estimate.py):

  heating_rate             °F per hour over the past week's heating, or null
  heating_rate_at          when that was computed
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

import estimate
import history
from common import ApiError, json_body, now, respond

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
KEY = {"id": "tub"}

SETPOINT_TEMPERATURES = range(102, 107)
ALLOWED_SETPOINTS = ["off"] + [str(t) for t in SETPOINT_TEMPERATURES]

# "Off" is rest mode in the low range at its minimum, so that the tub does
# not heat during filter cycles either.
OFF = {"heating_mode": "rest", "temperature_range": "low", "set_temperature": 50}

HEATING_MODES = {"ready", "rest", "ready_in_rest"}
TEMPERATURE_RANGES = {"high", "low"}


# ---------------------------------------------------------------------------
# Routes for users
# ---------------------------------------------------------------------------

def get_tub(event, user):
    item = _read()
    setpoint = _setpoint(_desired(item))
    return respond(200, {
        "setpoint": setpoint,
        "setpoint_changed_at": item.get("setpoint_changed_at"),
        "setpoint_changed_by": item.get("setpoint_changed_by"),
        "setpoint_source": item.get("setpoint_source"),
        "current_temperature": item.get("current_temperature"),
        "temperature_measured_at": item.get("temperature_measured_at"),
        "heating": item.get("tub_heating"),
        "tub_last_seen_at": item.get("tub_last_seen_at"),
        "operator_last_seen_at": item.get("operator_last_seen_at"),
        "allowed_setpoints": ALLOWED_SETPOINTS,
        "heating_estimate": _heating_estimate(item, setpoint),
        "timer": _timer_view(item, datetime.now(timezone.utc)),
    })


def _heating_estimate(item: dict, setpoint):
    """When the tub should reach its setpoint (see estimate.py), or None.

    A convenience: any failure gives no estimate rather than a failed page.
    The past week's rate takes a larger query, so it is kept in the tub item
    and recomputed at most every RATE_CACHE_HOURS.
    """
    if setpoint in (None, "off") or item.get("current_temperature") is None:
        return None
    target = int(setpoint)
    if float(item["current_temperature"]) >= target:
        return None
    try:
        now_dt = datetime.now(timezone.utc)
        rate, based_on = _heating_rate(item, now_dt)
        return estimate.estimate(target, item["current_temperature"],
                                 item.get("temperature_measured_at"), rate, based_on, now_dt)
    except Exception as e:
        print(f"Could not estimate heating time: {type(e).__name__}: {e}")
        return None


def _heating_rate(item: dict, now_dt):
    """(°F per hour, based_on): the best rate available; see estimate.py."""
    recent = history.readings_since(now_dt - timedelta(hours=estimate.RECENT_HOURS))
    rate = estimate.current_rate(recent)
    if rate is not None:
        return rate, "this_heating"
    rate = _past_week_rate(item, now_dt)
    if rate is not None:
        return rate, "past_week"
    return estimate.DEFAULT_RATE, "typical"


RATE_CACHE_HOURS = 6


def _past_week_rate(item: dict, now_dt):
    cached_at = item.get("heating_rate_at")
    if cached_at and now_dt - estimate.parse(cached_at) < timedelta(hours=RATE_CACHE_HOURS):
        rate = item.get("heating_rate")
        return None if rate is None else float(rate)
    rate = estimate.learned_rate(history.readings_since(now_dt - timedelta(days=estimate.LEARN_DAYS)))
    TABLE.update_item(
        Key=KEY,
        UpdateExpression="SET heating_rate = :rate, heating_rate_at = :at",
        ExpressionAttributeValues={
            ":rate": None if rate is None else Decimal(str(round(rate, 2))),
            ":at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    return rate


def put_setpoint(event, user):
    raw = json_body(event).get("setpoint")
    # Accept 104 or "104"; reject true, 104.5 and anything else.
    if isinstance(raw, int) and not isinstance(raw, bool):
        raw = str(raw)
    if raw not in ALLOWED_SETPOINTS:
        raise ApiError(400, "setpoint must be 'off' or a whole number from 102 to 106")

    if raw == "off":
        desired = OFF
    else:
        desired = {"heating_mode": "ready", "temperature_range": "high", "set_temperature": int(raw)}

    changed_at = _set_desired(desired, source="ui", changed_by=user["email"])
    _remove_timer()  # one request at a time: this replaces any timer
    return respond(200, {
        "setpoint": raw,
        "setpoint_changed_at": changed_at,
        "setpoint_changed_by": user["email"],
        "setpoint_source": "ui",
    })


# ---------------------------------------------------------------------------
# Timer: "have it at 104 °F by 7 PM"
# ---------------------------------------------------------------------------
#
# One timer at a time, shared by everyone, kept in the tub item:
#   timer_setpoint  integer °F       timer_ready_at  ISO-8601 UTC
#   timer_set_by    email            timer_set_at    ISO-8601 UTC
#
# It starts the heating at ready_at minus the time to heat (at the best
# heating rate available, see estimate.py) minus TIMER_MARGIN_MINUTES.  The
# start is checked whenever the operator asks for the desired state, every
# couple of minutes, so no extra scheduler is needed.  Starting the heating is
# an ordinary change of desired state (source "timer", by the person who set
# the timer), and the timer is then removed.
#
# There is one request at a time, "heat now" or "heat by then": setting a
# timer turns the tub off until the timer starts it, and a setpoint chosen in
# the UI or at the tub's panel removes the timer.
# A timer never starts the heating during the nightly turn-off hour.

TIMER_MAX_HOURS = 48
TIMER_MARGIN_MINUTES = 20
# Assumed water temperature when there is no reading at all.
TIMER_COLD_START = 80
_TIMER_FIELDS = ("timer_setpoint", "timer_ready_at", "timer_set_by", "timer_set_at")


def put_timer(event, user):
    body = json_body(event)
    raw = body.get("setpoint")
    if isinstance(raw, str) and raw.isdigit():
        raw = int(raw)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw not in SETPOINT_TEMPERATURES:
        raise ApiError(400, "setpoint must be a whole number from 102 to 106")
    ready_at = _parse_time(body.get("ready_at"))
    now_dt = datetime.now(timezone.utc)
    if ready_at is None:
        raise ApiError(400, "ready_at must be a date and time, e.g. 2026-11-24T03:00:00Z")
    if ready_at <= now_dt + timedelta(minutes=10):
        raise ApiError(400, "Choose a time at least 10 minutes from now")
    if ready_at > now_dt + timedelta(hours=TIMER_MAX_HOURS):
        raise ApiError(400, f"Choose a time within the next {TIMER_MAX_HOURS} hours")
    if _quiet_hour(ready_at):
        raise ApiError(400, "The tub is turned off between midnight and 1 AM; choose another time")

    TABLE.update_item(
        Key=KEY,
        UpdateExpression="SET timer_setpoint = :t, timer_ready_at = :r, timer_set_by = :b, timer_set_at = :a",
        ExpressionAttributeValues={
            ":t": raw,
            ":r": ready_at.strftime(_ISO),
            ":b": user["email"],
            ":a": now_dt.strftime(_ISO),
        },
    )
    print(f"{user['email']} set a timer: {raw} °F by {ready_at.strftime(_ISO)}")
    # One request at a time: the tub rests until the timer starts it.
    desired = _desired(_read())
    if desired is not None and desired["heating_mode"] == "ready":
        _set_desired(OFF, source="ui", changed_by=user["email"])
    return respond(200, {"timer": _timer_view(_read(), now_dt)})


def delete_timer(event, user):
    _remove_timer()
    print(f"{user['email']} cancelled the timer")
    return respond(200, {"timer": None})


def _remove_timer():
    TABLE.update_item(Key=KEY, UpdateExpression="REMOVE " + ", ".join(_TIMER_FIELDS))


def _timer_view(item: dict, now_dt):
    """The timer as the UI shows it, or None."""
    if "timer_ready_at" not in item:
        return None
    try:
        starts_at = _timer_start(item, now_dt).strftime(_ISO)
    except Exception as e:
        print(f"Could not work out the timer's start: {type(e).__name__}: {e}")
        starts_at = None
    return {
        "setpoint": str(int(item["timer_setpoint"])),
        "ready_at": item["timer_ready_at"],
        "set_by": item.get("timer_set_by"),
        "set_at": item.get("timer_set_at"),
        "starts_at": starts_at,
    }


def _timer_start(item: dict, now_dt) -> datetime:
    """When heating should start to be ready in time."""
    ready = estimate.parse(item["timer_ready_at"])
    target = int(item["timer_setpoint"])
    current = item.get("current_temperature")
    current = TIMER_COLD_START if current is None else float(current)
    rate, _ = _heating_rate(item, now_dt)
    needed = timedelta(hours=max(0.0, target - current) / rate)
    start = ready - needed - timedelta(minutes=TIMER_MARGIN_MINUTES)
    # Heating cannot start during the turn-off hour; start at its end instead.
    if _quiet_hour(start):
        local = _pacific(start)
        start += timedelta(minutes=60 - local.minute, seconds=-local.second)
    return start


def _run_timer(item: dict) -> dict:
    """Start the heating if the timer says it is time.  Returns the tub item,
    re-read if anything changed.  Never raises: a timer problem must not stop
    the operator getting the desired state."""
    if "timer_ready_at" not in item:
        return item
    try:
        now_dt = datetime.now(timezone.utc)
        ready = estimate.parse(item["timer_ready_at"])
        if now_dt > ready + timedelta(hours=1):
            # Missed (the operator was away): too late to be useful.
            _clear_timer(item)
            print("Timer expired without starting")
            return _read()
        if now_dt < _timer_start(item, now_dt) or _quiet_hour(now_dt):
            return item
        if not _clear_timer(item):
            return _read()  # someone changed or cancelled it meanwhile
        target = int(item["timer_setpoint"])
        desired = {"heating_mode": "ready", "temperature_range": "high", "set_temperature": target}
        _set_desired(desired, source="timer", changed_by=item.get("timer_set_by"))
        print(f"Timer started heating to {target} °F")
        return _read()
    except Exception as e:
        print(f"Timer check failed: {type(e).__name__}: {e}")
        return item


def _clear_timer(item: dict) -> bool:
    """Remove this timer; False if it was replaced or removed meanwhile."""
    try:
        TABLE.update_item(
            Key=KEY,
            UpdateExpression="REMOVE " + ", ".join(_TIMER_FIELDS),
            ConditionExpression="timer_set_at = :a",
            ExpressionAttributeValues={":a": item["timer_set_at"]},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _parse_time(raw):
    """A UTC datetime from an ISO-8601 string with a zone, or None."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _pacific(dt_utc: datetime) -> datetime:
    """US Pacific local time.  The tub is in Pacific time, and the Lambda image
    may have no time zone database, so the US rule is applied directly:
    daylight time from 2 AM on the second Sunday of March to 2 AM on the first
    Sunday of November."""
    year = dt_utc.year
    march8 = datetime(year, 3, 8, 10, tzinfo=timezone.utc)      # 2 AM PST
    nov1 = datetime(year, 11, 1, 9, tzinfo=timezone.utc)        # 2 AM PDT
    dst_start = march8 + timedelta(days=(6 - march8.weekday()) % 7)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    offset = -7 if dst_start <= dt_utc < dst_end else -8
    return (dt_utc + timedelta(hours=offset)).replace(tzinfo=None)


def _quiet_hour(dt_utc: datetime) -> bool:
    """Is this within the nightly turn-off hour, midnight to 1 AM Pacific?"""
    return _pacific(dt_utc).hour == 0


# ---------------------------------------------------------------------------
# Routes for the operator
# ---------------------------------------------------------------------------

def get_desired(event, user):
    return respond(200, _desired_response(_run_timer(_read())))


def put_report(event, user):
    """Record what the operator saw.

    Body:
      tub             null if the operator could not reach the tub, else
                        {current_temperature, set_temperature, heating_mode,
                         temperature_range, heating}
      panel_change    true if the tub's controls were changed at the front
                      panel since the operator last looked
      desired_version the desired_version the operator last read (required
                      with panel_change)

    A panel change becomes the new desired state — unless a user changed the
    setpoint after the operator read it (desired_version no longer matches),
    in which case the user's newer change stands and "adopted" is false.
    The response always carries the current desired state.
    """
    body = json_body(event)
    tub = body.get("tub")
    reported_at = now()
    updates = {"operator_last_seen_at": reported_at}

    if tub is not None:
        tub = _validate_tub(tub)
        updates.update({
            "tub_last_seen_at": reported_at,
            "tub_set_temperature": tub["set_temperature"],
            "tub_heating_mode": tub["heating_mode"],
            "tub_temperature_range": tub["temperature_range"],
            "tub_heating": tub["heating"],
        })
        # The tub stops reporting a temperature after a while at rest; keep
        # the last real reading (and its timestamp) rather than erase it.
        if tub["current_temperature"] is not None:
            updates["current_temperature"] = tub["current_temperature"]
            updates["temperature_measured_at"] = reported_at
            history.record_temperature(reported_at, tub["current_temperature"], tub["heating"])

    TABLE.update_item(
        Key=KEY,
        UpdateExpression="SET " + ", ".join(f"{name} = :{name}" for name in updates),
        ExpressionAttributeValues={f":{name}": value for name, value in updates.items()},
    )

    adopted = False
    if body.get("panel_change") is True:
        if tub is None:
            raise ApiError(400, "'panel_change' requires 'tub'")
        seen = body.get("desired_version")
        if seen is not None and (not isinstance(seen, int) or isinstance(seen, bool)):
            raise ApiError(400, "'desired_version' must be an integer or null")
        panel = {
            "heating_mode": "ready" if tub["heating_mode"] == "ready" else "rest",
            "temperature_range": tub["temperature_range"],
            "set_temperature": tub["set_temperature"],
        }
        try:
            _set_desired(panel, source="panel", changed_by=None, only_if_version=seen)
            adopted = True
            _remove_timer()  # one request at a time, as for a change in the UI
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    return respond(200, {
        "reported_at": reported_at,
        "adopted": adopted,
        **_desired_response(_read()),
    })


# ---------------------------------------------------------------------------
# Scheduled turn-off
# ---------------------------------------------------------------------------

def auto_off():
    """Turn the tub off unless it already is.  Invoked by the nightly schedule."""
    desired = _desired(_read())
    if desired is None or desired["heating_mode"] != "ready":
        return {"changed": False}
    _set_desired(OFF, source="schedule", changed_by=None)
    print("Automatic turn-off: tub was on, now set to off")
    return {"changed": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read() -> dict:
    return TABLE.get_item(Key=KEY, ConsistentRead=True).get("Item", {})


def _desired(item: dict):
    if "desired_version" not in item:
        return None
    return {
        "heating_mode": item["desired_heating_mode"],
        "temperature_range": item["desired_temperature_range"],
        "set_temperature": int(item["desired_set_temperature"]),
    }


def _desired_response(item: dict) -> dict:
    version = item.get("desired_version")
    return {
        "desired": _desired(item),
        "desired_version": None if version is None else int(version),
    }


def _setpoint(desired):
    """The setpoint as users see it: "off", or the temperature as a string."""
    if desired is None:
        return None
    if desired["heating_mode"] != "ready":
        return "off"
    return str(desired["set_temperature"])


_ANY = object()


def _set_desired(desired: dict, source: str, changed_by, only_if_version=_ANY) -> str:
    """Write a new desired state and return its timestamp.

    only_if_version, if given, is the desired_version the caller last saw
    (None = no desired state existed yet).  The write then only happens if
    that is still the current version; otherwise DynamoDB raises
    ConditionalCheckFailedException.
    """
    changed_at = now()
    names = {"#by": "setpoint_changed_by"}
    values = {
        ":mode": desired["heating_mode"],
        ":range": desired["temperature_range"],
        ":temp": desired["set_temperature"],
        ":at": changed_at,
        ":source": source,
        ":one": 1,
    }
    expression = (
        "SET desired_heating_mode = :mode, desired_temperature_range = :range, "
        "desired_set_temperature = :temp, setpoint_changed_at = :at, "
        "setpoint_source = :source"
    )
    if changed_by is None:
        expression += " REMOVE #by"
    else:
        expression += ", #by = :by"
        values[":by"] = changed_by
    expression += " ADD desired_version :one"

    kwargs = {}
    if only_if_version is None:
        kwargs["ConditionExpression"] = "attribute_not_exists(desired_version)"
    elif only_if_version is not _ANY:
        kwargs["ConditionExpression"] = "desired_version = :seen"
        values[":seen"] = only_if_version

    TABLE.update_item(
        Key=KEY,
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        **kwargs,
    )
    history.record_change(changed_at, _setpoint(desired), source, changed_by)
    return changed_at


def _validate_tub(tub) -> dict:
    if not isinstance(tub, dict):
        raise ApiError(400, "'tub' must be an object or null")

    current = tub.get("current_temperature")
    if current is not None:
        if not _is_number(current) or not 32 <= current <= 130:
            raise ApiError(400, "'current_temperature' must be a number from 32 to 130, or null")
        current = Decimal(str(current))

    set_temperature = tub.get("set_temperature")
    if not _is_number(set_temperature) or set_temperature != int(set_temperature) \
            or not 40 <= set_temperature <= 110:
        raise ApiError(400, "'set_temperature' must be a whole number from 40 to 110")

    if tub.get("heating_mode") not in HEATING_MODES:
        raise ApiError(400, "'heating_mode' must be ready, rest or ready_in_rest")
    if tub.get("temperature_range") not in TEMPERATURE_RANGES:
        raise ApiError(400, "'temperature_range' must be high or low")
    if not isinstance(tub.get("heating"), bool):
        raise ApiError(400, "'heating' must be true or false")

    return {
        "current_temperature": current,
        "set_temperature": int(set_temperature),
        "heating_mode": tub["heating_mode"],
        "temperature_range": tub["temperature_range"],
        "heating": tub["heating"],
    }


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
