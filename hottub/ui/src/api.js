// Calls to the hot tub API.

import { idToken } from "./auth";

let apiUrl = "";
let onSessionExpired = () => {};
let getToken = idToken;

// `token` is only overridden by the preview page, which has no real sign-in.
export function configureApi(config, { sessionExpired, token = idToken }) {
  apiUrl = config.apiUrl.replace(/\/$/, "");
  onSessionExpired = sessionExpired;
  getToken = token;
}

async function request(method, path, body) {
  const token = await getToken();
  if (!token) {
    onSessionExpired();
    throw new Error("Your session has ended. Please sign in again.");
  }

  let response;
  try {
    response = await fetch(apiUrl + path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Could not reach the server. Check your connection.");
  }

  if (response.status === 401) {
    onSessionExpired();
    throw new Error("Your session has ended. Please sign in again.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || `Request failed (${response.status})`);
  }
  return data;
}

const user = (username) => `/users/${encodeURIComponent(username)}`;

export const getTub = () => request("GET", "/tub");
export const setSetpoint = (setpoint) => request("PUT", "/tub/setpoint", { setpoint });
export const setTimer = (setpoint, readyAt) =>
  request("PUT", "/tub/timer", { setpoint, ready_at: readyAt });
export const cancelTimer = () => request("DELETE", "/tub/timer");
export const getHistory = (hours) => request("GET", `/history?hours=${hours}`);

export const listUsers = () => request("GET", "/users").then((r) => r.users);
export const createUser = (email, admin) => request("POST", "/users", { email, admin });
export const setAdmin = (username, admin) => request("PATCH", user(username), { admin });
export const deleteUser = (username) => request("DELETE", user(username));
export const resetPassword = (username) => request("POST", `${user(username)}/reset-password`);
