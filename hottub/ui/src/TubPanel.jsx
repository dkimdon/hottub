import { useCallback, useEffect, useState } from "react";
import { getTub, setSetpoint } from "./api";
import { ago, secondsSince } from "./format";
import Thermometer from "./Thermometer";

const REFRESH_MS = 30_000;
const STALE_SECONDS = 30 * 60;

function setpointSentence(setpoint) {
  if (setpoint === null) return "The tub has not reported in yet.";
  if (setpoint === "off") return "The tub is at rest (off).";
  return `The tub is set to heat to or maintain ${setpoint} °F.`;
}

function changedBySentence(tub, now) {
  if (!tub.setpoint_changed_at) return null;
  const who = {
    ui: tub.setpoint_changed_by || "someone using this page",
    panel: "someone using the buttons on the tub itself",
    schedule: "the automatic turn-off at midnight",
  }[tub.setpoint_source];
  if (!who) return null;
  return `The last change was made by ${who}, ${ago(tub.setpoint_changed_at, now)}.`;
}

// Why the readings might not be trustworthy, or null if all is well.
function warning(tub, now) {
  const operator = secondsSince(tub.operator_last_seen_at, now);
  const reached = secondsSince(tub.tub_last_seen_at, now);
  if (operator === null || operator > STALE_SECONDS) {
    return operator === null
      ? "The tub's controller has not connected yet."
      : `Warning: the tub's controller last connected ${ago(tub.operator_last_seen_at, now)}. Changes will not reach the tub until it reconnects.`;
  }
  if (reached === null || reached > STALE_SECONDS) {
    return reached === null
      ? "Warning: the controller has not been able to reach the tub."
      : `Warning: the last communication with the tub was ${ago(tub.tub_last_seen_at, now)}. Changes will not take effect until it can be reached.`;
  }
  return null;
}

export default function TubPanel() {
  const [tub, setTub] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(null);
  const [now, setNow] = useState(Date.now());

  const refresh = useCallback(async () => {
    try {
      setTub(await getTub());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
    setNow(Date.now());
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    // Refresh straight away when someone comes back to the page.
    const onVisible = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  async function choose(setpoint) {
    setSaving(setpoint);
    try {
      const change = await setSetpoint(setpoint);
      setTub((current) => ({ ...current, ...change }));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
    setSaving(null);
    setNow(Date.now());
  }

  if (!tub) {
    return error ? <p className="error" role="alert">{error}</p> : <p className="muted">Loading…</p>;
  }

  const temperature = tub.current_temperature;
  const problem = warning(tub, now);
  const changedBy = changedBySentence(tub, now);
  // Highest temperature first, "off" last, as on the old page.
  const choices = [...tub.allowed_setpoints].sort((a, b) =>
    a === "off" ? 1 : b === "off" ? -1 : Number(b) - Number(a)
  );

  return (
    <>
      <section className="tub-status">
        <Thermometer value={temperature} />
        <div>
          <p className="temperature">
            {temperature === null ? "—" : `${temperature}°F`}
            {tub.heating && <span className="badge heating">heating</span>}
          </p>
          <ul className="status-lines">
            <li>
              {tub.temperature_measured_at
                ? `The water temperature was last measured ${ago(tub.temperature_measured_at, now)}.`
                : "The water temperature has not been measured yet."}
            </li>
            <li>{setpointSentence(tub.setpoint)}</li>
            {changedBy && <li>{changedBy}</li>}
          </ul>
        </div>
      </section>

      {problem && <p className="error" role="alert">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <fieldset className="setpoints" disabled={saving !== null}>
        <legend>Set the tub to</legend>
        {choices.map((choice) => (
          <label key={choice} className={saving === choice ? "saving" : undefined}>
            <input
              type="radio"
              name="setpoint"
              value={choice}
              checked={tub.setpoint === choice}
              onChange={() => choose(choice)}
            />
            <span>{choice === "off" ? "Rest (off)" : `${choice} °F`}</span>
          </label>
        ))}
      </fieldset>
      <p className="hint">
        Changes reach the tub within a few minutes. The tub turns off automatically at midnight.
      </p>
    </>
  );
}
