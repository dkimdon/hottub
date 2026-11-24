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

// "9:40 PM", "tomorrow at 1:10 AM" or "Wednesday at 7:00 AM", rounded to
// five minutes: it is only ever an estimate.
export function aboutWhen(iso, now = Date.now()) {
  const step = 5 * 60_000;
  const when = new Date(Math.round(Date.parse(iso) / step) * step);
  const time = when.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(when) - startOfDay(new Date(now))) / 86_400_000);
  if (days <= 0) return time;
  if (days === 1) return `tomorrow at ${time}`;
  return `${when.toLocaleDateString(undefined, { weekday: "long" })} at ${time}`;
}

export function ago(iso, now) {
  const seconds = secondsSince(iso, now);
  return seconds === null ? null : `${duration(seconds)} ago`;
}
