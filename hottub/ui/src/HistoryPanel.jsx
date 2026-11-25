import { useEffect, useState } from "react";
import { getHistory } from "./api";
import TemperatureChart from "./TemperatureChart";

const PERIODS = [
  [24, "Day"],
  [168, "Week"],
  [720, "30 days"],
];

const when = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const setpointText = (setpoint) => (setpoint === "off" ? "Rest (off)" : `${setpoint} °F`);

function whoText(change) {
  if (change.source === "panel") return "at the tub";
  if (change.source === "schedule") return "automatic turn-off";
  if (change.source === "timer") return change.changed_by ? `timer set by ${change.changed_by}` : "timer";
  return change.changed_by || "unknown";
}

// The dashed line on the day view, from the latest reading to the setpoint at
// the estimated time; null when there is no estimate.
function forecastFor(tub) {
  const estimate = tub && tub.heating_estimate;
  if (!estimate || !tub.temperature_measured_at || tub.current_temperature == null) return null;
  return {
    from: Date.parse(tub.temperature_measured_at),
    fromTemperature: Number(tub.current_temperature),
    to: Date.parse(estimate.ready_at),
    target: Number(tub.setpoint),
  };
}

const PERIOD_TEXT = { 24: "in the last day", 168: "in the last week", 720: "in the last 30 days" };

// "Heater on for 23 hours in the last 30 days · Set to a temperature 14 times"
function Stats({ stats, hours }) {
  const h = stats.heating_hours;
  const heated = h < 1 ? `${Math.round(h * 60)} minutes` : `${h < 10 ? h.toFixed(1) : Math.round(h)} hours`;
  const used = stats.times_used === 1 ? "once" : `${stats.times_used} times`;
  return (
    <p className="stats">
      <span>
        Heater on for <strong>{heated}</strong> {PERIOD_TEXT[hours] || ""}
      </span>
      <span>
        Set to a temperature <strong>{used}</strong>
      </span>
    </p>
  );
}

export default function HistoryPanel({ tub = null }) {
  const [hours, setHours] = useState(24);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getHistory(hours)
      .then((loaded) => {
        if (cancelled) return;
        setHistory(loaded);
        setError(null);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [hours]);

  return (
    <>
      <div className="history-head">
        <h2>Water temperature</h2>
        <div className="segmented" role="group" aria-label="Period">
          {PERIODS.map(([value, label]) => (
            <button key={value} aria-pressed={hours === value} onClick={() => setHours(value)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error" role="alert">{error}</p>}
      {!history && !error && <p className="muted">Loading…</p>}

      {history && (
        <>
          <TemperatureChart history={history} forecast={hours === 24 ? forecastFor(tub) : null} />
          {history.stats && <Stats stats={history.stats} hours={hours} />}

          <h2 className="changes-title">Changes</h2>
          {history.changes.length === 0 ? (
            <p className="muted">No changes in this period.</p>
          ) : (
            <table className="changes">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Set to</th>
                  <th>By</th>
                </tr>
              </thead>
              <tbody>
                {history.changes.map((change) => (
                  <tr key={change.at}>
                    <td>{when.format(Date.parse(change.at))}</td>
                    <td>{setpointText(change.setpoint)}</td>
                    <td>{whoText(change)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}
