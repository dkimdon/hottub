"""The operator's control logic: one cycle of keeping the tub and the cloud in step.

Each cycle:

  1. Ask the API what the tub should be doing (the "desired" state).
  2. Connect to the tub and read what it is doing.
  3. If the tub's controls differ from how we left them last cycle, someone
     used the front panel.  Report that; it becomes the new desired state —
     unless a user changed the setpoint in the web UI in the same moment, in
     which case the API tells us the UI's change stands.
  4. Otherwise, if the tub differs from the desired state, change the tub.
  5. Report the tub's temperature and state.

"The tub's controls" are the three things this system manages, represented
the way the tub itself does:

    {"heating_mode": "ready" | "rest",
     "temperature_range": "high" | "low",
     "set_temperature": 104}

The most recent change wins, whether it came from the web UI or the panel.
"""

import json
import logging
import os

from bwa.messages.status import HeatingMode, Status, TemperatureScale

log = logging.getLogger("operator")

# How long to wait for the tub to confirm a change we asked for.
CONFIRM_TIMEOUT = 5.0


class TubUnreachable(Exception):
    """The tub did not answer, or stopped answering part-way through."""


def control_state(status: Status) -> dict:
    """The tub's controls, as compared against the desired state."""
    return {
        # "Ready in rest" is rest mode with the jets temporarily on; it goes
        # back to rest by itself, so it is not a change anyone asked for.
        "heating_mode": "ready" if status.heating_mode == HeatingMode.READY else "rest",
        "temperature_range": status.temperature_range.value,
        "set_temperature": int(status.set_temperature),
    }


def tub_report(status: Status) -> dict:
    """What we tell the API about the tub."""
    return {
        "current_temperature": status.current_temperature,
        "set_temperature": int(status.set_temperature),
        "heating_mode": status.heating_mode.value,
        "temperature_range": status.temperature_range.value,
        "heating": status.heating,
    }


class StateFile:
    """Remembers, between cycles, how we last left the tub's controls."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)


def run_cycle(api, connect, state: StateFile, report_only: bool = False) -> str:
    """Run one control cycle and return a one-word outcome for the log.

    api      an ApiClient
    connect  a function returning a connected bwa Client (a context manager)
    state    where the tub's last known controls are kept

    In report-only mode the tub is never changed and nothing it does is
    treated as a panel change; use it to run alongside another controller.

    Raises ApiError if the API cannot be reached.
    """
    answer = api.get_desired()
    desired, version = answer["desired"], answer["desired_version"]

    try:
        with connect() as spa:
            status = _read_status(spa)
            if status.temperature_scale != TemperatureScale.FAHRENHEIT:
                # Everything here assumes Fahrenheit; do not guess.
                log.error("Tub is set to Celsius; not controlling it")
                api.report(None)
                return "celsius"

            tub = control_state(status)
            if report_only:
                api.report(tub_report(status))
                return "reported"

            saved = state.load()
            last = saved.get("controls")

            # No desired state at all means a brand new system: start from
            # whatever the tub is doing now.
            if desired is None or (last is not None and tub != last):
                log.info("Tub controls changed at the panel: %s -> %s", last, tub)
                answer = api.report(tub_report(status), panel_change=True, desired_version=version)
                if answer["adopted"]:
                    state.save({**saved, "controls": tub})
                    return "panel-change"
                log.info("A newer change was made in the web UI; it takes priority")
                desired = answer["desired"]

            outcome = "in-step"
            if tub != desired:
                log.info("Changing tub controls: %s -> %s", tub, desired)
                status = _apply(spa, status, desired)
                tub = control_state(status)
                outcome = "changed" if tub == desired else "change-failed"
                if tub != desired:
                    log.warning("Tub did not accept the change; it is at %s", tub)

            # Save before reporting: if the report fails, the next cycle must
            # not mistake our own change for someone using the panel.
            state.save({**saved, "controls": tub})
            api.report(tub_report(status))
            return outcome

    except (OSError, TubUnreachable) as e:
        log.warning("Could not talk to the tub: %s", e or type(e).__name__)
        api.report(None)
        return "tub-unreachable"


def _read_status(spa) -> Status:
    status = spa.poll_until_status(timeout=CONFIRM_TIMEOUT)
    if status is None:
        raise TubUnreachable("connected, but the tub sent no status")
    return status


def _apply(spa, status: Status, desired: dict) -> Status:
    """Change the tub's controls to `desired`; return the tub's status afterwards.

    Order matters: the tub only accepts a set temperature that lies inside
    its current range, so the range is changed first.
    """
    def change(description, send, confirmed):
        nonlocal status
        log.info("  %s", description)
        send()
        new = spa.wait_for_status(confirmed, timeout=CONFIRM_TIMEOUT)
        # If the change was not confirmed, carry on with a fresh reading.
        status = new if new is not None else _read_status(spa)

    if control_state(status)["temperature_range"] != desired["temperature_range"]:
        change(
            f"temperature range -> {desired['temperature_range']}",
            spa.toggle_temperature_range,
            lambda s: s.temperature_range.value == desired["temperature_range"],
        )

    if control_state(status)["set_temperature"] != desired["set_temperature"]:
        change(
            f"set temperature -> {desired['set_temperature']}",
            lambda: spa.set_temperature(desired["set_temperature"]),
            lambda s: int(s.set_temperature) == desired["set_temperature"],
        )

    if control_state(status)["heating_mode"] != desired["heating_mode"]:
        change(
            f"heating mode -> {desired['heating_mode']}",
            spa.toggle_heating_mode,
            lambda s: control_state(s)["heating_mode"] == desired["heating_mode"],
        )

    return status
