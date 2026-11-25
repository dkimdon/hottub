// Tests for the thermometer's setpoint marker and bubbles, the graph's
// forecast and stats, and the heat control's timer.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import HistoryPanel from "./HistoryPanel";
import { timeChoices } from "./HeatControl";
import Thermometer from "./Thermometer";
import TubPanel from "./TubPanel";

vi.mock("./api");
vi.mock("./auth");

afterEach(cleanup);

const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();
const minutesAhead = (n) => new Date(Date.now() + n * 60_000).toISOString();

function tubState(overrides = {}) {
  return {
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
    ...overrides,
  };
}

function history(overrides = {}) {
  return {
    hours: 24,
    from: minutesAgo(24 * 60),
    to: minutesAgo(0),
    stats: { heating_hours: 3.4, times_used: 2 },
    temperatures: [
      { at: minutesAgo(10), temperature: 98.5, heating: true },
      { at: minutesAgo(2), temperature: 101, heating: true },
    ],
    changes: [],
    ...overrides,
  };
}

describe("Thermometer", () => {
  it("marks the setpoint and bubbles while heating", () => {
    const { container } = render(<Thermometer value={101} setpoint={104} heating />);
    expect(screen.getByRole("img", { name: /101 degrees Fahrenheit, set to 104, heating/ })).toBeTruthy();
    expect(container.querySelector(".thermometer-target")).toBeTruthy();
    expect(container.querySelectorAll(".thermometer-bubble").length).toBe(3);
  });

  it("has no marker when off and no bubbles when not heating", () => {
    const { container } = render(<Thermometer value={90} setpoint={null} heating={false} />);
    expect(container.querySelector(".thermometer-target")).toBeNull();
    expect(container.querySelectorAll(".thermometer-bubble").length).toBe(0);
  });
});

describe("Graph forecast and stats", () => {
  const tub = tubState({
    heating_estimate: { ready_at: minutesAhead(45), rate_per_hour: 4, based_on: "typical" },
  });

  it("draws the forecast on the day view", async () => {
    api.getHistory.mockResolvedValue(history());
    const { container } = render(<HistoryPanel tub={tub} />);
    expect(await screen.findByRole("img", { name: /Expected to reach 104 degrees/ })).toBeTruthy();
    expect(container.querySelector(".chart-forecast")).toBeTruthy();
  });

  it("has no forecast without an estimate, or on longer periods", async () => {
    api.getHistory.mockResolvedValue(history());
    const { container, unmount } = render(<HistoryPanel tub={tubState()} />);
    await screen.findByRole("img");
    expect(container.querySelector(".chart-forecast")).toBeNull();
    unmount();

    api.getHistory.mockResolvedValue(history({ hours: 168, from: minutesAgo(168 * 60) }));
    const week = render(<HistoryPanel tub={tub} />);
    await userEvent.click(await screen.findByText("Week"));
    await screen.findByRole("img");
    expect(week.container.querySelector(".chart-forecast")).toBeNull();
  });

  it("shows heater time and use count", async () => {
    api.getHistory.mockResolvedValue(history());
    render(<HistoryPanel />);
    const stats = await screen.findByText(/Heater on for/);
    expect(stats.closest("p").textContent).toMatch(/Heater on for 3.4 hours in the last day/);
    expect(stats.closest("p").textContent).toMatch(/Set to a temperature 2 times/);
  });

  it("names timer changes", async () => {
    api.getHistory.mockResolvedValue(
      history({ changes: [{ at: minutesAgo(5), setpoint: "104", source: "timer", changed_by: "sam@example.com" }] })
    );
    const { container } = render(<HistoryPanel />);
    await screen.findByRole("img");
    const rows = within(container.querySelector("table.changes")).getAllByRole("row");
    expect(rows[1].textContent).toMatch(/timer set by sam@example.com/);
  });
});

describe("Heat control with a time", () => {
  it("offers half-hour times over the next day, skipping the midnight hour", () => {
    const now = new Date(2026, 10, 23, 18, 0).getTime();
    const choices = timeChoices(now);
    const first = new Date(choices[0][0]);
    expect([first.getHours(), first.getMinutes()]).toEqual([18, 30]);
    expect(choices.some(([iso]) => new Date(iso).getHours() === 0)).toBe(false);
    expect(choices.some(([, label]) => label.startsWith("tomorrow at"))).toBe(true);
    const last = new Date(choices[choices.length - 1][0]);
    expect(last.getTime() - now).toBeLessThanOrEqual(24 * 3600_000);
  });

  it("sets a timer, and shows the tub off until it starts", async () => {
    const choices = timeChoices(Date.now());
    const [readyAt] = choices[10];
    const timer = { setpoint: "105", ready_at: readyAt, set_by: "me@example.com", set_at: minutesAgo(0), starts_at: minutesAhead(90) };
    api.getTub.mockResolvedValueOnce(tubState()).mockResolvedValue(tubState({ setpoint: "off", heating: false, timer }));
    api.setTimer.mockResolvedValue({ timer });
    render(<TubPanel />);

    await userEvent.click(await screen.findByText("Schedule for later…"));
    await userEvent.selectOptions(screen.getByLabelText("Have it at"), "105");
    await userEvent.selectOptions(screen.getByLabelText("by"), readyAt);
    await userEvent.click(screen.getByText("Schedule"));

    expect(api.setTimer).toHaveBeenCalledWith(105, readyAt);
    expect(await screen.findByText(/The tub is off until about .*, then heats to 105 °F to be ready by/)).toBeTruthy();
    expect(screen.getByText(/The timer was set by me@example.com/)).toBeTruthy();
    // The form closes; while the timer waits no button is highlighted.
    expect(screen.queryByLabelText("by")).toBeNull();
    // While the timer waits, the schedule button is the highlighted one.
    const group = screen.getByRole("group", { name: "Heat to" });
    expect(within(group).queryAllByRole("button", { pressed: true })).toEqual([]);
    const scheduled = screen.getByRole("button", { name: /^Scheduled: 105° by / });
    expect(scheduled.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Cancel timer")).toBeTruthy();
  });

  it("starts the form from the timer, and can close it", async () => {
    const readyAt = minutesAhead(300);
    const timer = { setpoint: "106", ready_at: readyAt, set_by: "pat@example.com", set_at: minutesAgo(5), starts_at: minutesAhead(200) };
    api.getTub.mockResolvedValue(tubState({ setpoint: "off", heating: false, timer }));
    render(<TubPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /^Scheduled: 106°/ }));
    expect(screen.getByLabelText("Have it at").value).toBe("106");
    expect(screen.getByLabelText("by").value).toBe(readyAt);
    await userEvent.click(screen.getByText("Never mind"));
    expect(screen.queryByLabelText("by")).toBeNull();
    expect(api.setTimer).not.toHaveBeenCalled();
  });

  it("cancels a timer", async () => {
    const timer = { setpoint: "104", ready_at: minutesAhead(300), set_by: "pat@example.com", set_at: minutesAgo(5), starts_at: minutesAhead(200) };
    api.getTub.mockResolvedValueOnce(tubState({ setpoint: "off", heating: false, timer })).mockResolvedValue(
      tubState({ setpoint: "off", heating: false })
    );
    api.cancelTimer.mockResolvedValue({ timer: null });
    render(<TubPanel />);

    expect(await screen.findByText(/The timer was set by pat@example.com, 5 minutes ago/)).toBeTruthy();
    await userEvent.click(screen.getByText("Cancel timer"));
    expect(api.cancelTimer).toHaveBeenCalled();
    expect(await screen.findByText("The tub is at rest (off).")).toBeTruthy();
  });

  it("shows the API's reason when a timer is refused", async () => {
    api.getTub.mockResolvedValue(tubState());
    api.setTimer.mockRejectedValue(new Error("Choose a time at least 10 minutes from now"));
    render(<TubPanel />);
    await userEvent.click(await screen.findByText("Schedule for later…"));
    await userEvent.click(screen.getByText("Schedule"));
    expect((await screen.findByRole("alert")).textContent).toMatch(/at least 10 minutes/);
  });

  it("says when a timer started the heating", async () => {
    api.getTub.mockResolvedValue(tubState({ setpoint_source: "timer", setpoint_changed_by: "sam@example.com" }));
    render(<TubPanel />);
    expect(await screen.findByText(/made by a timer sam@example.com set/)).toBeTruthy();
  });
});
