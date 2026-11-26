// The whole app, start-up to tabs: guards against anything that breaks it
// before a panel even renders (a blank page in production).

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import App from "./App";
import * as auth from "./auth";

vi.mock("./api");
vi.mock("./auth");

const config = { environment: "live", apiUrl: "https://api.example", userPoolId: "p", userPoolClientId: "c" };
const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => config })));
  api.getTub.mockResolvedValue({
    setpoint: "104",
    setpoint_changed_at: minutesAgo(10),
    setpoint_changed_by: "pat@example.com",
    setpoint_source: "ui",
    current_temperature: 101,
    temperature_measured_at: minutesAgo(1),
    heating: true,
    tub_last_seen_at: minutesAgo(1),
    operator_last_seen_at: minutesAgo(1),
    allowed_setpoints: ["off", "102", "103", "104", "105", "106"],
    heating_estimate: null,
    timer: null,
  });
  api.getHistory.mockResolvedValue({ hours: 24, from: minutesAgo(1440), to: minutesAgo(0), temperatures: [], changes: [] });
  api.listUsers.mockResolvedValue([]);
  auth.signOut.mockResolvedValue();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("starts up and shows the tub, with Tub and Help tabs", async () => {
    auth.currentUser.mockResolvedValue({ username: "u", email: "me@example.com", isAdmin: false });
    render(<App />);
    expect(await screen.findByText("101°F")).toBeTruthy();
    const tabs = screen.getByRole("navigation", { name: "Sections" });
    expect([...tabs.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["Tub", "Help"]);
    // No email on the page.
    expect(screen.queryByText("me@example.com")).toBeNull();
  });

  it("signs out from the Help tab", async () => {
    auth.currentUser.mockResolvedValue({ username: "u", email: "me@example.com", isAdmin: false });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(auth.signOut).toHaveBeenCalled();
  });

  it("gives admins a Users tab with Sign out", async () => {
    auth.currentUser.mockResolvedValue({ username: "u", email: "me@example.com", isAdmin: true });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Users" }));
    expect(await screen.findByRole("heading", { name: "Users" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
  });
});
