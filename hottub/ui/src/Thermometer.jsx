// A simple thermometer drawn in SVG.

const MIN = 60;
const MAX = 110;
const TOP = 12;
const BOTTOM = 150;

function y(temperature) {
  const clamped = Math.min(MAX, Math.max(MIN, temperature));
  return BOTTOM - ((clamped - MIN) / (MAX - MIN)) * (BOTTOM - TOP);
}

export default function Thermometer({ value }) {
  const known = typeof value === "number";
  const ticks = [];
  for (let t = MIN; t <= MAX; t += 10) ticks.push(t);

  return (
    <svg
      className="thermometer"
      viewBox="0 0 90 190"
      role="img"
      aria-label={known ? `Water temperature ${value} degrees Fahrenheit` : "Water temperature unknown"}
    >
      <rect className="thermometer-tube" x="20" y={TOP - 8} width="16" height={BOTTOM - TOP + 16} rx="8" />
      <circle className="thermometer-tube" cx="28" cy="168" r="16" />
      {known && (
        <>
          <rect className="thermometer-fill" x="24" y={y(value)} width="8" height={BOTTOM - y(value) + 10} rx="4" />
          <circle className="thermometer-fill" cx="28" cy="168" r="11" />
        </>
      )}
      {ticks.map((t) => (
        <g key={t}>
          <line className="thermometer-tick" x1="40" x2="47" y1={y(t)} y2={y(t)} />
          <text className="thermometer-label" x="51" y={y(t) + 4}>
            {t}°
          </text>
        </g>
      ))}
    </svg>
  );
}
