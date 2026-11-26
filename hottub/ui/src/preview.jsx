// Development only: renders every screen with made-up data, so the look of
// the UI can be checked without AWS.  See preview.html.

import { useState } from "react";
import { createRoot } from "react-dom/client";
import { configureApi } from "./api";
import Help from "./Help";
import HistoryPanel from "./HistoryPanel";
import SignIn from "./SignIn";
import Thermometer from "./Thermometer";
import TubArt from "./TubArt";
import TubFooter from "./TubFooter";
import TubPanel from "./TubPanel";
import UsersPanel from "./UsersPanel";
import "./styles.css";

const ago = (minutes) => new Date(Date.now() - minutes * 60_000).toISOString();

function temperatures(hours) {
  const step = (hours * 60) / 240;
  const points = [];
  for (let i = 240; i >= 0; i--) {
    const minutes = i * step;
    if (minutes > 400 && minutes < 520) continue; // tub unreachable for a while
    const hourOfDay = new Date(Date.now() - minutes * 60_000).getHours();
    const heatingUp = hourOfDay >= 17 && hourOfDay < 19;
    const hot = hourOfDay >= 19 && hourOfDay < 24;
    const base = hot ? 104 : heatingUp ? 92 + (hourOfDay - 17) * 6 : 96 - ((hourOfDay + 24) % 24) * 0.5;
    points.push({
      at: ago(minutes),
      temperature: Math.round((base + Math.sin(i / 3) * 0.4) * 10) / 10,
      heating: heatingUp,
    });
  }
  return points;
}

const preview = {
  setpoint: "104",
  setpoint_changed_at: ago(42),
  setpoint_changed_by: "pat.example@example.com",
  setpoint_source: "ui",
  timer: null,
};

function changed(setpoint) {
  Object.assign(preview, {
    setpoint,
    setpoint_changed_at: ago(0),
    setpoint_changed_by: "you@example.com",
    setpoint_source: "ui",
  });
}

const fixtures = {
  // The tub remembers changes made on this page, as the real API would.
  "GET /tub": () => ({
    current_temperature: 101,
    temperature_measured_at: ago(1),
    heating: preview.setpoint !== "off",
    tub_last_seen_at: ago(1),
    operator_last_seen_at: ago(1),
    allowed_setpoints: ["off", "102", "103", "104", "105", "106"],
    ...preview,
    heating_estimate:
      preview.setpoint !== "off" && Number(preview.setpoint) > 101
        ? { ready_at: new Date(Date.now() + (Number(preview.setpoint) - 101) * 15 * 60_000).toISOString(), rate_per_hour: 3.8, based_on: "this_heating" }
        : null,
  }),
  "PUT /tub/timer": (body) => {
    preview.timer = {
      setpoint: String(body.setpoint),
      ready_at: body.ready_at,
      set_by: "you@example.com",
      set_at: ago(0),
      starts_at: new Date(Date.parse(body.ready_at) - 100 * 60_000).toISOString(),
    };
    changed("off");
    return { timer: preview.timer };
  },
  "DELETE /tub/timer": () => {
    preview.timer = null;
    return { timer: null };
  },
  "PUT /tub/setpoint": (body) => {
    preview.timer = null;
    changed(String(body.setpoint));
    return {};
  },
  "GET /history": (_body, url) => {
    const hours = Number(new URL(url, location.href).searchParams.get("hours"));
    return {
      hours,
      from: ago(hours * 60),
      to: ago(0),
      stats: { heating_hours: hours === 24 ? 3.4 : hours === 168 ? 14.2 : 61, times_used: hours === 24 ? 2 : hours === 168 ? 9 : 31 },
      temperatures: temperatures(hours),
      changes: [
        { at: ago(42), setpoint: "104", source: "ui", changed_by: "pat.example@example.com" },
        { at: ago(600), setpoint: "off", source: "schedule", changed_by: null },
        { at: ago(900), setpoint: "100", source: "panel", changed_by: null },
        { at: ago(1000), setpoint: "106", source: "ui", changed_by: "sam@example.com" },
        // More, so the table has pages.
        ...Array.from({ length: hours === 24 ? 9 : hours / 24 }, (_, i) => ({
              at: ago(hours === 24 ? 1100 + i * 35 : 1440 + i * 1440),
              setpoint: i % 3 ? "104" : "off",
              source: i % 3 ? "ui" : "schedule",
              changed_by: i % 3 ? "pat.example@example.com" : null,
            })),
      ],
    };
  },
  "GET /users": () => ({
    users: [
      { username: "u1", email: "you@example.com", admin: true, status: "CONFIRMED" },
      { username: "u2", email: "pat.example@example.com", admin: false, status: "CONFIRMED" },
      { username: "u3", email: "sam@example.com", admin: false, status: "FORCE_CHANGE_PASSWORD" },
    ],
  }),
};

window.fetch = async (url, options = {}) => {
  const path = new URL(url, location.href).pathname;
  const make = fixtures[`${options.method} ${path}`];
  const body = options.body ? JSON.parse(options.body) : undefined;
  return new Response(JSON.stringify(make ? make(body, url) : {}), { status: 200 });
};

configureApi({ apiUrl: "" }, { sessionExpired: () => {}, token: async () => "preview" });

const me = { username: "u1", email: "you@example.com", isAdmin: true };

// The tub panel shares its state with the graph, as in App.jsx.
function TubAndHistory() {
  const [tub, setTub] = useState(null);
  return (
    <>
      <main className="card wooden"><TubPanel onTub={setTub} /></main>
      <TubFooter onSignOut={() => {}} />
      <section className="card wooden"><HistoryPanel tub={tub} /></section>
    </>
  );
}

createRoot(document.getElementById("root")).render(
  <>
    <nav className="tabs" aria-label="Sections">
      <button aria-current="page">Tub</button>
      <button>History</button>
      <button>Help</button>
      <button>Users</button>
    </nav>
    <TubAndHistory />
    <section className="card">
      <h2>Every picture</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
        {["heating", "hot", "off", "waiting"].map((s) => (
          <div key={s} style={{ textAlign: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Thermometer value={s === "off" ? 68 : 101} setpoint={s === "off" ? null : 104} heating={s === "heating"} frozen={s === "off"} />
              <TubArt state={s} />
            </div>
            <span className="muted">{s}</span>
          </div>
        ))}
      </div>
    </section>
    <section className="card"><Help /></section>
    <section className="card"><UsersPanel me={me} /></section>
    <SignIn onSignedIn={() => {}} />
  </>
);
