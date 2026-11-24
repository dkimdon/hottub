// The temperature colour scale shared by the thermometer and the history graph:
// icy white when cold, through blues and purple, to red at 100°F and above.

export const COLOURS = [
  [60, "#ffffff"],
  [70, "#d4effb"],
  [78, "#8ccdf0"],
  [86, "#2f6fd6"],
  [94, "#7b3fc4"],
  [100, "#d62828"],
  [110, "#a3121c"],
];

const LOW = COLOURS[0][0];
const HIGH = COLOURS[COLOURS.length - 1][0];

// A vertical SVG gradient pinned to the drawing's temperature axis, so each
// height is painted the colour of the temperature it stands for.  `y` maps a
// temperature to the drawing's y coordinate.
export function TemperatureGradient({ id, y }) {
  return (
    <linearGradient id={id} gradientUnits="userSpaceOnUse" x1="0" x2="0" y1={y(LOW)} y2={y(HIGH)}>
      {COLOURS.map(([t, colour]) => (
        <stop key={t} offset={(t - LOW) / (HIGH - LOW)} stopColor={colour} />
      ))}
    </linearGradient>
  );
}

function rgb(hex) {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
}

// The colour of one temperature, interpolated between the stops above.
export function colourFor(temperature) {
  const t = Math.min(HIGH, Math.max(LOW, temperature));
  let i = 1;
  while (i < COLOURS.length - 1 && COLOURS[i][0] < t) i++;
  const [t0, c0] = COLOURS[i - 1];
  const [t1, c1] = COLOURS[i];
  const f = (t - t0) / (t1 - t0);
  const [a, b] = [rgb(c0), rgb(c1)];
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(", ")})`;
}
