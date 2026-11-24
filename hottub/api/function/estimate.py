"""When will the tub reach its set temperature?

The estimate is the time left at a heating rate in °F per hour, taken from
the best evidence available:

  "this_heating"  the heating run in progress, once it has gone on long
                  enough to measure: at least MIN_RUN_MINUTES and MIN_RISE °F
  "past_week"     the average over heating runs in the past LEARN_DAYS days,
                  which follows the season (cold weather heats more slowly)
  "typical"       DEFAULT_RATE, observed on this tub

A heating run is a stretch of readings with the heater on and no gap longer
than MAX_GAP_MINUTES.  Its rate is the least-squares slope of temperature
against time, which copes with the tub reporting whole degrees.

Everything here is pure and works on history readings as stored:
{"at": ISO-8601 UTC, "temperature": number, "heating": bool}, oldest first.
"""

from datetime import datetime, timedelta, timezone

DEFAULT_RATE = 4.0
MIN_RATE, MAX_RATE = 1.0, 10.0
MIN_RUN_MINUTES = 40
MIN_RISE = 2.0
MAX_GAP_MINUTES = 10
RECENT_HOURS = 4
LEARN_DAYS = 7
# An estimate from a reading older than this would mislead.
STALE_MINUTES = 15

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse(iso: str) -> datetime:
    return datetime.strptime(iso, _TIME_FORMAT).replace(tzinfo=timezone.utc)


def heating_runs(readings: list) -> list:
    """Split readings into runs of consecutive heating readings."""
    runs, run, previous = [], [], None
    for reading in readings:
        at = parse(reading["at"])
        gap = previous is not None and at - previous > timedelta(minutes=MAX_GAP_MINUTES)
        if not reading.get("heating") or gap:
            if len(run) > 1:
                runs.append(run)
            run = []
        if reading.get("heating"):
            run.append((at, float(reading["temperature"])))
        previous = at
    if len(run) > 1:
        runs.append(run)
    return runs


def run_rate(run: list):
    """°F per hour over one run, or None if it is too short to measure."""
    minutes = (run[-1][0] - run[0][0]).total_seconds() / 60
    if minutes < MIN_RUN_MINUTES or run[-1][1] - run[0][1] < MIN_RISE:
        return None
    hours = [(at - run[0][0]).total_seconds() / 3600 for at, _ in run]
    temps = [t for _, t in run]
    mean_h, mean_t = sum(hours) / len(hours), sum(temps) / len(temps)
    spread = sum((h - mean_h) ** 2 for h in hours)
    slope = sum((h - mean_h) * (t - mean_t) for h, t in zip(hours, temps)) / spread
    return min(MAX_RATE, max(MIN_RATE, slope))


def current_rate(readings: list):
    """Rate of the heating run in progress (it includes the latest reading)."""
    runs = heating_runs(readings)
    if not runs or not readings or not readings[-1].get("heating"):
        return None
    if runs[-1][-1][0] != parse(readings[-1]["at"]):
        return None
    return run_rate(runs[-1])


def learned_rate(readings: list):
    """Average rate over all measurable runs, weighted by their length."""
    total, weight = 0.0, 0.0
    for run in heating_runs(readings):
        rate = run_rate(run)
        if rate is not None:
            hours = (run[-1][0] - run[0][0]).total_seconds() / 3600
            total += rate * hours
            weight += hours
    return total / weight if weight else None


def estimate(target: int, current, measured_at, rate: float, based_on: str, now: datetime):
    """{"ready_at", "rate_per_hour", "based_on"}, or None if not applicable."""
    if current is None or measured_at is None or float(current) >= target:
        return None
    measured = parse(measured_at)
    if now - measured > timedelta(minutes=STALE_MINUTES):
        return None
    ready = measured + timedelta(hours=(target - float(current)) / rate)
    return {
        "ready_at": max(ready, now).strftime(_TIME_FORMAT),
        "rate_per_hour": round(rate, 1),
        "based_on": based_on,
    }
