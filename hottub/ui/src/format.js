// Small formatting helpers.

// "3 minutes", "1 hour", "2 days" — the largest whole unit, like the old UI.
export function duration(seconds) {
  const units = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [name, size] of units) {
    const n = Math.floor(seconds / size);
    if (n >= 1) return `${n} ${name}${n === 1 ? "" : "s"}`;
  }
  return "less than a minute";
}

// Seconds since an ISO timestamp; null if there is none.
export function secondsSince(iso, now = Date.now()) {
  if (!iso) return null;
  return Math.max(0, Math.floor((now - Date.parse(iso)) / 1000));
}

export function ago(iso, now) {
  const seconds = secondsSince(iso, now);
  return seconds === null ? null : `${duration(seconds)} ago`;
}
