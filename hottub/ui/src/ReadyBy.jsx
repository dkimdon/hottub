// "Have it ready by": a timer that starts heating in time for the tub to be
// at a temperature at a chosen time.  The API works out when to start (see
// "Timer" in api/function/tub.py); there is one timer, shared by everyone.

import { useState } from "react";
import { cancelTimer, setTimer } from "./api";
import { aboutWhen } from "./format";

// The next time the clock shows `hhmm` ("19:00"): today if that is still more
// than 10 minutes away, otherwise tomorrow.
export function nextOccurrence(hhmm, now = new Date()) {
  const [hours, minutes] = hhmm.split(":").map(Number);
  const when = new Date(now);
  when.setHours(hours, minutes, 0, 0);
  if (when.getTime() - now.getTime() < 10 * 60_000) when.setDate(when.getDate() + 1);
  return when;
}

export default function ReadyBy({ tub, onTimer, now }) {
  const temperatures = tub.allowed_setpoints.filter((s) => s !== "off");
  const [setpoint, setSetpoint] = useState(temperatures.includes("104") ? "104" : temperatures[0]);
  const [time, setTime] = useState("19:00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      onTimer((await action()).timer);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  const timer = tub.timer;
  if (timer) {
    return (
      <section className="ready-by" aria-label="Timer">
        <p>
          <strong>
            Timer: {timer.setpoint} °F by {aboutWhen(timer.ready_at, now)}
          </strong>
          {timer.set_by && <span className="muted"> (set by {timer.set_by})</span>}
        </p>
        {timer.starts_at && (
          <p className="muted">Heating will start at about {aboutWhen(timer.starts_at, now)}.</p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button type="button" disabled={busy} onClick={() => run(cancelTimer)}>
          Cancel timer
        </button>
      </section>
    );
  }

  const readyAt = time ? nextOccurrence(time, new Date(now)) : null;
  const day = readyAt && readyAt.getDate() !== new Date(now).getDate() ? "tomorrow" : "today";

  return (
    <form
      className="ready-by"
      aria-label="Timer"
      onSubmit={(event) => {
        event.preventDefault();
        if (readyAt) run(() => setTimer(Number(setpoint), readyAt.toISOString()));
      }}
    >
      <p className="ready-by-title">Or have it ready later</p>
      <div className="ready-by-row">
        <label>
          <span className="visually-hidden">Temperature</span>
          <select value={setpoint} onChange={(e) => setSetpoint(e.target.value)} disabled={busy}>
            {temperatures.map((t) => (
              <option key={t} value={t}>
                {t} °F
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>by</span>
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={busy} required />
        </label>
        <span className="muted">{readyAt ? day : ""}</span>
        <button type="submit" disabled={busy || !readyAt}>
          Set timer
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}
