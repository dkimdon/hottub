// A simple thermometer drawn in SVG.

import { useId } from "react";
import { TemperatureGradient } from "./temperatureColours";

const MIN = 60;
const MAX = 110;
const TOP = 12;
const BOTTOM = 150;

// The column is a gradient fixed to the scale, so a hot tub shows the whole
// range of colours.  The bulb stays white.  A marker on the left points at
// the setpoint, and bubbles rise in the column while the heater is on.

// Horizontal positions and start delays (s) of the bubbles.
const BUBBLES = [
  [26.5, 0],
  [29.5, 0.9],
  [27.5, 1.8],
];

function y(temperature) {
  const clamped = Math.min(MAX, Math.max(MIN, temperature));
  return BOTTOM - ((clamped - MIN) / (MAX - MIN)) * (BOTTOM - TOP);
}

export default function Thermometer({ value, setpoint = null, heating = false }) {
  const gradient = useId();
  const known = typeof value === "number";
  const target = typeof setpoint === "number" ? setpoint : null;
  const ticks = [];
  for (let t = MIN; t <= MAX; t += 10) ticks.push(t);

  let label = known ? `Water temperature ${value} degrees Fahrenheit` : "Water temperature unknown";
  if (target !== null) label += `, set to ${target}`;
  if (known && heating) label += ", heating";

  return (
    <svg className="thermometer" viewBox="0 0 90 190" role="img" aria-label={label}>
      <defs>
        <TemperatureGradient id={gradient} y={y} />
      </defs>
      <rect className="thermometer-tube" x="20" y={TOP - 8} width="16" height={BOTTOM - TOP + 16} rx="8" />
      <circle className="thermometer-tube" cx="28" cy="168" r="12" />
      {known && (
        <>
          <rect
            className="thermometer-fill"
            x="24"
            y={y(value)}
            width="8"
            height={BOTTOM - y(value) + 10}
            rx="4"
            fill={`url(#${gradient})`}
          />
          <circle className="thermometer-fill" cx="28" cy="168" r="8" fill="#ffffff" />
          {heating &&
            BUBBLES.map(([x, delay]) => (
              <circle
                key={x}
                className="thermometer-bubble"
                cx={x}
                cy={BOTTOM + 4}
                r="1.4"
                style={{ "--rise": `${y(value) - BOTTOM - 2}px`, animationDelay: `${delay}s` }}
              />
            ))}
        </>
      )}
      {target !== null && (
        <path className="thermometer-target" d={`M 17 ${y(target)} l -8 -5 v 10 z`} />
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
