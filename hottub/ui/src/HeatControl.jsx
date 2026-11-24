// "Have it at [104 °F] by [As soon as possible / 7:00 PM ...]  [Set]"
//
// One request at a time.  "As soon as possible" sets the setpoint now; a time
// sets the shared timer, and the API turns the tub off until the timer starts
// the heating (see "Timer" in api/function/tub.py).  Either replaces the other.

import { useState } from "react";
import { setSetpoint, setTimer } from "./api";
import { aboutWhen } from "./format";

export const ASAP = "asap";
const SLOT_MINUTES = 30;
const HOURS_AHEAD = 24;

// Half-hour times over the next day, each at least 15 minutes away, as
// [ISO, label].  Times in the midnight turn-off hour are left out: the tub
// cannot be on then.
export function timeChoices(now = Date.now()) {
  const step = SLOT_MINUTES * 60_000;
  const first = Math.ceil((now + 15 * 60_000) / step) * step;
  const choices = [];
  for (let t = first; t <= now + HOURS_AHEAD * 3600_000; t += step) {
    if (new Date(t).getHours() === 0) continue;
    choices.push([new Date(t).toISOString(), aboutWhen(new Date(t).toISOString(), now)]);
  }
  return choices;
}

// What the controls start at: the current request, if there is one.
function current(tub) {
  if (tub.timer) return [tub.timer.setpoint, tub.timer.ready_at];
  if (tub.setpoint && tub.setpoint !== "off" && tub.allowed_setpoints.includes(tub.setpoint)) {
    return [tub.setpoint, ASAP];
  }
  return [null, ASAP];
}

export default function HeatControl({ tub, now, onChanged }) {
  const temperatures = tub.allowed_setpoints.filter((s) => s !== "off");
  const [startTemperature, startTime] = current(tub);
  const [temperature, setTemperature] = useState(
    startTemperature || (temperatures.includes("104") ? "104" : temperatures[0])
  );
  const [time, setTime] = useState(startTime);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const choices = timeChoices(now);
  // Keep the timer's own time selectable even if it is not on the half hour.
  if (time !== ASAP && !choices.some(([iso]) => iso === time)) {
    choices.unshift([time, aboutWhen(time, now)]);
  }
  const unchanged = temperature === startTemperature && time === startTime;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (time === ASAP) await setSetpoint(temperature);
      else await setTimer(Number(temperature), time);
      await onChanged();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  return (
    <form className="heat-control" aria-label="Heat the tub" onSubmit={submit}>
      <div className="heat-control-row">
        <label>
          <span>Have it at</span>
          <select value={temperature} onChange={(e) => setTemperature(e.target.value)} disabled={busy}>
            {temperatures.map((t) => (
              <option key={t} value={t}>
                {t} °F
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>by</span>
          <select value={time} onChange={(e) => setTime(e.target.value)} disabled={busy}>
            <option value={ASAP}>As soon as possible</option>
            {choices.map(([iso, label]) => (
              <option key={iso} value={iso}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="primary" disabled={busy || unchanged}>
          {busy ? "Setting…" : "Set"}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}
