import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import * as auth from "./auth";
import { ago, duration } from "./format";
import HistoryPanel from "./HistoryPanel";
import SignIn from "./SignIn";
import TubPanel from "./TubPanel";
import UsersPanel from "./UsersPanel";

vi.mock("./api");
vi.mock("./auth");

afterEach(cleanup);

const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();

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
    ...overrides,
  };
}

describe("format", () => {
  it("uses the largest whole unit", () => {
    expect(duration(5)).toBe("less than a minute");
    expect(duration(60)).toBe("1 minute");
    expect(duration(59 * 60)).toBe("59 minutes");
    expect(duration(3600)).toBe("1 hour");
    expect(duration(3 * 86400 + 5)).toBe("3 days");
  });

  it("handles missing timestamps", () => {
    expect(ago(null)).toBeNull();
    expect(ago(minutesAgo(2))).toBe("2 minutes ago");
  });
});

describe("TubPanel", () => {
  it("shows the tub's state", async () => {
    api.getTub.mockResolvedValue(tubState());
    render(<TubPanel />);

    expect(await screen.findByText("101°F")).toBeTruthy();
    expect(screen.getByText("heating")).toBeTruthy();
    expect(screen.getByText(/set to heat to or maintain 104 °F/)).toBeTruthy();
    expect(screen.getByText(/last change was made by pat@example.com, 10 minutes ago/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();

    // One button per setting; the current one is highlighted.
    const buttons = within(screen.getByRole("group", { name: "Heat to" })).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Off", "102°", "103°", "104°", "105°", "106°"]);
    expect(screen.getByRole("button", { name: "104 °F" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Off" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByText("Schedule for later…").getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByText("Cancel timer")).toBeNull();
  });

  it("heats to a new temperature as soon as possible", async () => {
    api.getTub.mockResolvedValueOnce(tubState()).mockResolvedValue(
      tubState({ setpoint: "106", setpoint_changed_by: "me@example.com", setpoint_changed_at: minutesAgo(0) })
    );
    api.setSetpoint.mockResolvedValue({});
    render(<TubPanel />);

    await userEvent.click(await screen.findByRole("button", { name: "106 °F" }));

    expect(api.setSetpoint).toHaveBeenCalledWith("106");
    expect(await screen.findByText(/last change was made by me@example.com/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "106 °F" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("does nothing when the current setting is tapped again", async () => {
    api.getTub.mockResolvedValue(tubState());
    render(<TubPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "104 °F" }));
    expect(api.setSetpoint).not.toHaveBeenCalled();
  });

  it("can turn the tub off", async () => {
    api.getTub.mockResolvedValueOnce(tubState()).mockResolvedValue(tubState({ setpoint: "off", heating: false }));
    api.setSetpoint.mockResolvedValue({});
    render(<TubPanel />);

    await userEvent.click(await screen.findByRole("button", { name: "Off" }));

    expect(api.setSetpoint).toHaveBeenCalledWith("off");
    expect(await screen.findByText("The tub is at rest (off).")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Off" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("shows a failed change and keeps the old setpoint", async () => {
    api.getTub.mockResolvedValue(tubState());
    api.setSetpoint.mockRejectedValue(new Error("Could not reach the server."));
    render(<TubPanel />);

    await userEvent.click(await screen.findByRole("button", { name: "106 °F" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/Could not reach the server/);
    expect(screen.getByText(/set to heat to or maintain 104 °F/)).toBeTruthy();
  });

  it("describes a change made at the tub", async () => {
    api.getTub.mockResolvedValue(
      tubState({ setpoint: "100", setpoint_source: "panel", setpoint_changed_by: null })
    );
    render(<TubPanel />);

    expect(await screen.findByText(/buttons on the tub itself/)).toBeTruthy();
    expect(screen.getByText(/maintain 100 °F/)).toBeTruthy();
    // 100 is not offered, so no button is highlighted.
    const group = screen.getByRole("group", { name: "Heat to" });
    expect(within(group).queryAllByRole("button", { pressed: true })).toEqual([]);
  });

  it("describes the automatic turn-off", async () => {
    api.getTub.mockResolvedValue(
      tubState({ setpoint: "off", setpoint_source: "schedule", setpoint_changed_by: null })
    );
    render(<TubPanel />);
    expect(await screen.findByText(/automatic turn-off at midnight/)).toBeTruthy();
  });

  it("says when the tub should reach its setpoint", async () => {
    const readyAt = new Date(Date.now() + 90 * 60_000).toISOString();
    api.getTub.mockResolvedValue(
      tubState({ heating_estimate: { ready_at: readyAt, rate_per_hour: 3.8, based_on: "this_heating" } })
    );
    render(<TubPanel />);
    expect(
      await screen.findByText(/should reach 104 °F at about .*, at the rate it has been warming \(about 4 °F an hour\)/)
    ).toBeTruthy();
  });

  it("names a typical rate when there is no history to go on", async () => {
    const readyAt = new Date(Date.now() + 60 * 60_000).toISOString();
    api.getTub.mockResolvedValue(
      tubState({ heating_estimate: { ready_at: readyAt, rate_per_hour: 4, based_on: "typical" } })
    );
    render(<TubPanel />);
    expect(await screen.findByText(/at a typical 4 °F an hour/)).toBeTruthy();
  });

  it("says 'within a few minutes' when nearly there", async () => {
    const readyAt = new Date(Date.now() + 2 * 60_000).toISOString();
    api.getTub.mockResolvedValue(
      tubState({ heating_estimate: { ready_at: readyAt, rate_per_hour: 4, based_on: "typical" } })
    );
    render(<TubPanel />);
    expect(await screen.findByText("It should reach 104 °F within a few minutes.")).toBeTruthy();
  });

  it("gives no estimate without one, or while the readings are in doubt", async () => {
    api.getTub.mockResolvedValue(tubState({ heating_estimate: null }));
    const { unmount } = render(<TubPanel />);
    await screen.findByText("101°F");
    expect(screen.queryByText(/should reach/)).toBeNull();
    unmount();

    const readyAt = new Date(Date.now() + 60 * 60_000).toISOString();
    api.getTub.mockResolvedValue(
      tubState({
        tub_last_seen_at: minutesAgo(125),
        heating_estimate: { ready_at: readyAt, rate_per_hour: 4, based_on: "typical" },
      })
    );
    render(<TubPanel />);
    await screen.findByRole("alert");
    expect(screen.queryByText(/should reach/)).toBeNull();
  });

  it("warns when the tub has not been reached for a long time", async () => {
    api.getTub.mockResolvedValue(tubState({ tub_last_seen_at: minutesAgo(125) }));
    render(<TubPanel />);
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /last communication with the tub was 2 hours ago/
    );
  });

  it("warns when the controller itself has gone quiet", async () => {
    api.getTub.mockResolvedValue(tubState({ operator_last_seen_at: minutesAgo(45) }));
    render(<TubPanel />);
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /controller last connected 45 minutes ago/
    );
  });

  it("copes with a system that has no data yet", async () => {
    api.getTub.mockResolvedValue(
      tubState({
        setpoint: null,
        setpoint_changed_at: null,
        setpoint_source: null,
        current_temperature: null,
        temperature_measured_at: null,
        heating: null,
        tub_last_seen_at: null,
        operator_last_seen_at: null,
      })
    );
    render(<TubPanel />);
    expect(await screen.findByText("—")).toBeTruthy();
    expect(screen.getByText(/has not been measured yet/)).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/controller has not connected yet/);
  });
});

describe("HistoryPanel", () => {
  function history(overrides = {}) {
    return {
      hours: 24,
      from: minutesAgo(24 * 60),
      to: minutesAgo(0),
      temperatures: [
        { at: minutesAgo(10), temperature: 98.5, heating: true },
        { at: minutesAgo(6), temperature: 101, heating: true },
        { at: minutesAgo(2), temperature: 104, heating: false },
      ],
      changes: [
        { at: minutesAgo(60), setpoint: "off", source: "schedule", changed_by: null },
        { at: minutesAgo(200), setpoint: "100", source: "panel", changed_by: null },
        { at: minutesAgo(300), setpoint: "104", source: "ui", changed_by: "pat@example.com" },
      ],
      ...overrides,
    };
  }

  it("draws the graph and lists changes", async () => {
    api.getHistory.mockResolvedValue(history());
    const { container } = render(<HistoryPanel />);

    expect(await screen.findByRole("img", { name: /most recently 104 degrees/ })).toBeTruthy();
    expect(container.querySelectorAll("polyline.chart-line").length).toBe(1);
    expect(api.getHistory).toHaveBeenCalledWith(24);

    const rows = within(container.querySelector("table.changes")).getAllByRole("row");
    expect(rows[1].textContent).toMatch(/Rest \(off\).*automatic turn-off/);
    expect(rows[2].textContent).toMatch(/100 °F.*at the tub/);
    expect(rows[3].textContent).toMatch(/104 °F.*pat@example.com/);
  });

  it("pages through many changes, newest first", async () => {
    const changes = Array.from({ length: 23 }, (_, i) => ({
      at: minutesAgo(10 + i * 30),
      setpoint: "104",
      source: "ui",
      changed_by: `user${i}@example.com`,
    }));
    api.getHistory.mockResolvedValue(history({ changes }));
    const { container } = render(<HistoryPanel />);
    const rows = async () => within(container.querySelector("table.changes")).getAllByRole("row").slice(1);

    await screen.findByText("1–10 of 23");
    expect((await rows())[0].textContent).toMatch(/user0@/);
    expect(screen.getByRole("button", { name: "‹ Newer" }).disabled).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Older ›" }));
    await userEvent.click(screen.getByRole("button", { name: "Older ›" }));
    expect(screen.getByText("21–23 of 23")).toBeTruthy();
    expect((await rows()).length).toBe(3);
    expect(screen.getByRole("button", { name: "Older ›" }).disabled).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "‹ Newer" }));
    expect((await rows())[0].textContent).toMatch(/user10@/);
  });

  it("reads values from the keyboard", async () => {
    api.getHistory.mockResolvedValue(history());
    render(<HistoryPanel />);
    const chart = await screen.findByRole("img");
    chart.focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("status").textContent).toMatch(/101°F · heating/);
  });

  it("breaks the line across a gap in the readings", async () => {
    api.getHistory.mockResolvedValue(
      history({
        temperatures: [
          { at: minutesAgo(600), temperature: 100, heating: false },
          { at: minutesAgo(594), temperature: 100, heating: false },
          { at: minutesAgo(10), temperature: 102, heating: false },
          { at: minutesAgo(4), temperature: 102, heating: false },
        ],
      })
    );
    const { container } = render(<HistoryPanel />);
    await screen.findByRole("img");
    expect(container.querySelectorAll("polyline.chart-line").length).toBe(2);
  });

  it("changes the period", async () => {
    api.getHistory.mockResolvedValue(history());
    render(<HistoryPanel />);
    await userEvent.click(await screen.findByText("Week"));
    expect(api.getHistory).toHaveBeenLastCalledWith(168);
    expect(screen.getByText("Week").getAttribute("aria-pressed")).toBe("true");
  });

  it("copes with no data", async () => {
    api.getHistory.mockResolvedValue(history({ temperatures: [], changes: [] }));
    render(<HistoryPanel />);
    expect(await screen.findByText(/No temperature readings/)).toBeTruthy();
    expect(screen.getByText("No changes in this period.")).toBeTruthy();
  });
});

describe("UsersPanel", () => {
  const me = { username: "u-me", email: "me@example.com", isAdmin: true };
  const users = [
    { username: "u-me", email: "me@example.com", admin: true, status: "CONFIRMED" },
    { username: "u-pat", email: "pat@example.com", admin: false, status: "CONFIRMED" },
    { username: "u-sam", email: "sam@example.com", admin: false, status: "FORCE_CHANGE_PASSWORD" },
  ];

  beforeEach(() => {
    api.listUsers.mockResolvedValue(users);
  });

  const row = async (email) => (await screen.findByText(email)).closest("li");

  it("lists users and protects your own account", async () => {
    render(<UsersPanel me={me} />);

    const mine = within(await row("me@example.com"));
    expect(mine.getByLabelText("Admin").checked).toBe(true);
    expect(mine.getByLabelText("Admin").disabled).toBe(true);
    expect(mine.getByText("Remove").disabled).toBe(true);

    const sam = within(await row("sam@example.com"));
    expect(sam.getByText(/has not signed in yet/)).toBeTruthy();
    expect(sam.getByLabelText("Admin").checked).toBe(false);
  });

  it("adds a user", async () => {
    api.createUser.mockResolvedValue({});
    render(<UsersPanel me={me} />);
    await row("pat@example.com");

    await userEvent.type(screen.getByLabelText("Email address"), "new@example.com");
    await userEvent.click(screen.getByLabelText("Make them an admin"));
    await userEvent.click(screen.getByText("Add user"));

    expect(api.createUser).toHaveBeenCalledWith("new@example.com", true);
    expect((await screen.findByRole("status")).textContent).toMatch(/new@example.com has been added/);
    expect(screen.getByLabelText("Email address").value).toBe("");
    expect(api.listUsers).toHaveBeenCalledTimes(2);
  });

  it("keeps the form filled in when adding fails", async () => {
    api.createUser.mockRejectedValue(new Error("A user with that email address already exists"));
    render(<UsersPanel me={me} />);
    await row("pat@example.com");

    await userEvent.type(screen.getByLabelText("Email address"), "pat@example.com");
    await userEvent.click(screen.getByText("Add user"));

    expect((await screen.findByRole("alert")).textContent).toMatch(/already exists/);
    expect(screen.getByLabelText("Email address").value).toBe("pat@example.com");
  });

  it("grants admin rights", async () => {
    api.setAdmin.mockResolvedValue({});
    render(<UsersPanel me={me} />);
    await userEvent.click(within(await row("pat@example.com")).getByLabelText("Admin"));
    expect(api.setAdmin).toHaveBeenCalledWith("u-pat", true);
  });

  it("removes a user only after confirmation", async () => {
    api.deleteUser.mockResolvedValue({});
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<UsersPanel me={me} />);
    const pat = within(await row("pat@example.com"));

    await userEvent.click(pat.getByText("Remove"));
    expect(api.deleteUser).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    await userEvent.click(pat.getByText("Remove"));
    expect(api.deleteUser).toHaveBeenCalledWith("u-pat");
  });

  it("resets a password", async () => {
    api.resetPassword.mockResolvedValue({});
    render(<UsersPanel me={me} />);
    await userEvent.click(within(await row("sam@example.com")).getByText("Reset password"));
    expect(api.resetPassword).toHaveBeenCalledWith("u-sam");
    expect((await screen.findByRole("status")).textContent).toMatch(/new temporary password/);
  });
});

describe("SignIn", () => {
  async function fillAndSubmit(button) {
    await userEvent.type(screen.getByLabelText("Email address"), "pat@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "Secret123");
    await userEvent.click(screen.getByText(button));
  }

  it("signs in", async () => {
    auth.signIn.mockResolvedValue("done");
    const onSignedIn = vi.fn();
    render(<SignIn onSignedIn={onSignedIn} />);

    await fillAndSubmit("Sign in");

    expect(auth.signIn).toHaveBeenCalledWith("pat@example.com", "Secret123");
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled());
  });

  it("asks a new user to choose a password", async () => {
    auth.signIn.mockResolvedValue("new-password");
    auth.chooseNewPassword.mockResolvedValue("done");
    const onSignedIn = vi.fn();
    render(<SignIn onSignedIn={onSignedIn} />);

    await fillAndSubmit("Sign in");
    await userEvent.type(await screen.findByLabelText(/New password/), "MyOwnPass1");
    await userEvent.click(screen.getByText("Save password and sign in"));

    expect(auth.chooseNewPassword).toHaveBeenCalledWith("MyOwnPass1");
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled());
  });

  it("explains a wrong password", async () => {
    auth.signIn.mockRejectedValue(Object.assign(new Error("x"), { name: "NotAuthorizedException" }));
    render(<SignIn onSignedIn={vi.fn()} />);

    await fillAndSubmit("Sign in");

    expect((await screen.findByRole("alert")).textContent).toMatch(/do not match/);
  });

  it("resets a forgotten password", async () => {
    auth.sendResetCode.mockResolvedValue("reset");
    auth.finishReset.mockResolvedValue("done");
    const onSignedIn = vi.fn();
    render(<SignIn onSignedIn={onSignedIn} />);

    await userEvent.click(screen.getByText("Forgot your password?"));
    await userEvent.type(screen.getByLabelText("Email address"), "pat@example.com");
    await userEvent.click(screen.getByText("Send code"));
    await userEvent.type(await screen.findByLabelText("Code from the email"), "123456");
    await userEvent.type(screen.getByLabelText(/New password/), "MyOwnPass1");
    await userEvent.click(screen.getByText("Set password and sign in"));

    expect(auth.finishReset).toHaveBeenCalledWith("pat@example.com", "123456", "MyOwnPass1");
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled());
  });
});
