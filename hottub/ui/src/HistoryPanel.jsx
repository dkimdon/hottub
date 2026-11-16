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
  return change.changed_by || "unknown";
}

// At most `count` rows, evenly spread, always including the latest.
function thin(points, count) {
  if (points.length <= count) return points;
  const step = (points.length - 1) / (count - 1);
  return Array.from({ length: count }, (_, i) => points[Math.round(i * step)]);
}

export default function HistoryPanel() {
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
          <TemperatureChart history={history} />

          {history.temperatures.length > 0 && (
            <details>
              <summary>Show readings as a table</summary>
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Water</th>
                  </tr>
                </thead>
                <tbody>
                  {thin(history.temperatures, 24)
                    .slice()
                    .reverse()
                    .map((p) => (
                      <tr key={p.at}>
                        <td>{when.format(Date.parse(p.at))}</td>
                        <td>
                          {p.temperature} °F{p.heating ? ", heating" : ""}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </details>
          )}

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
