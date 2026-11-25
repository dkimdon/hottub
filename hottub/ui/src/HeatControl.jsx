// The controls under the status card:
//
//   Heat to:  [Off] [102] [103] [■104■] [105] [106]
//   [ Schedule for later… ]
//
// A temperature button heats to it straight away, and Off turns the tub off;
// the button for the current setting is highlighted, like a radio button.
// While a timer waits, the schedule button is the highlighted one instead
// ("Scheduled: 104° by 7:00 PM"), with Cancel timer beside it.
// "Schedule for later…" opens a small form: "Have it at [104 °F] by [time]
// [Schedule]".  There is one request at a time: heating now drops any timer,
// and a timer leaves the tub off (ready mode at 50 °F, so it keeps reporting
// the water temperature) until the timer starts the heating.  See "Timer" in
// api/function/tub.py.

import { useState } from "react";
import { cancelTimer, setSetpoint, setTimer } from "./api";
import { aboutWhen } from "./format";

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

const label = (setpoint) => (setpoint === "off" ? "Off" : `${setpoint}°`);

function ScheduleForm({ tub, now, onDone, onCancel }) {
  const temperatures = tub.allowed_setpoints.filter((s) => s !== "off");
  const choices = timeChoices(now);
  const timer = tub.timer;
  const [temperature, setTemperature] = useState(
    timer ? timer.setpoint : temperatures.includes("104") ? "104" : temperatures[0]
  );
  const [time, setTime] = useState(timer ? timer.ready_at : choices[0] && choices[0][0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // Keep the timer's own time selectable even if it is not on the half hour.
  if (time && !choices.some(([iso]) => iso === time)) choices.unshift([time, aboutWhen(time, now)]);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await setTimer(Number(temperature), time);
      await onDone();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <form className="schedule" aria-label="Schedule for later" onSubmit={submit}>
      <div className="schedule-row">
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
            {choices.map(([iso, text]) => (
              <option key={iso} value={iso}>
                {text}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="hint">The tub stays off until it is time to start heating.</p>
      <div className="schedule-row">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Scheduling…" : "Schedule"}
        </button>
        <button type="button" className="link" onClick={onCancel} disabled={busy}>
          Never mind
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}

export default function HeatControl({ tub, now, onChanged }) {
  const [pending, setPending] = useState(null);
  const [error, setError] = useState(null);
  const [scheduling, setScheduling] = useState(false);

  // With a timer waiting, no button is "current": the status card says what
  // will happen instead.
  const current = pending || (tub.timer ? null : tub.setpoint);

  async function act(which, action) {
    setPending(which);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (e) {
      setError(e.message);
    }
    setPending(null);
  }

  function heat(setpoint) {
    if (setpoint !== current) act(setpoint, () => setSetpoint(setpoint));
  }

  const timer = tub.timer;

  return (
    <section className="heat-control" aria-label="Change the tub">
      <h2 id="heat-to">Heat to</h2>
      <div className="heat-buttons" role="group" aria-labelledby="heat-to">
        {tub.allowed_setpoints.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={current === s}
            aria-label={s === "off" ? "Off" : `${s} °F`}
            disabled={pending !== null}
            onClick={() => heat(s)}
          >
            {label(s)}
          </button>
        ))}
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      {scheduling ? (
        <ScheduleForm
          tub={tub}
          now={now}
          onCancel={() => setScheduling(false)}
          onDone={async () => {
            await onChanged();
            setScheduling(false);
          }}
        />
      ) : (
        <div className="schedule-buttons">
          <button
            type="button"
            className="schedule-button"
            aria-pressed={Boolean(timer)}
            disabled={pending !== null}
            onClick={() => setScheduling(true)}
          >
            {timer ? `Scheduled: ${timer.setpoint}° by ${aboutWhen(timer.ready_at, now)}` : "Schedule for later…"}
          </button>
          {timer && (
            <button type="button" disabled={pending !== null} onClick={() => act("cancel", cancelTimer)}>
              Cancel timer
            </button>
          )}
        </div>
      )}
    </section>
  );
}
