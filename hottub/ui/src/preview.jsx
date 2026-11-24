// Development only: renders every screen with made-up data, so the look of
// the UI can be checked without AWS.  See preview.html.

import { useState } from "react";
import { createRoot } from "react-dom/client";
import { configureApi } from "./api";
import HistoryPanel from "./HistoryPanel";
import SignIn from "./SignIn";
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

const fixtures = {
  "GET /tub": () => ({
    setpoint: "104",
    setpoint_changed_at: ago(42),
    setpoint_changed_by: "pat.example@example.com",
    setpoint_source: "ui",
    current_temperature: 101,
    temperature_measured_at: ago(1),
    heating: true,
    tub_last_seen_at: ago(1),
    operator_last_seen_at: ago(1),
    allowed_setpoints: ["off", "102", "103", "104", "105", "106"],
    heating_estimate: {
      ready_at: new Date(Date.now() + 47 * 60_000).toISOString(),
      rate_per_hour: 3.8,
      based_on: "this_heating",
    },
    timer: null,
  }),
  "PUT /tub/timer": (body) => ({
    timer: {
      setpoint: String(body.setpoint),
      ready_at: body.ready_at,
      set_by: "you@example.com",
      starts_at: new Date(Date.parse(body.ready_at) - 100 * 60_000).toISOString(),
    },
  }),
  "DELETE /tub/timer": () => ({ timer: null }),
  "PUT /tub/setpoint": (body) => ({
    setpoint: String(body.setpoint),
    setpoint_changed_at: ago(0),
    setpoint_changed_by: "you@example.com",
    setpoint_source: "ui",
  }),
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
      <main className="card"><TubPanel onTub={setTub} /></main>
      <section className="card"><HistoryPanel tub={tub} /></section>
    </>
  );
}

createRoot(document.getElementById("root")).render(
  <>
    <TubAndHistory />
    <section className="card"><UsersPanel me={me} /></section>
    <SignIn onSignedIn={() => {}} />
  </>
);
