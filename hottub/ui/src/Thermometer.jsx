// A simple thermometer drawn in SVG.

import { useId } from "react";
import { FlakeShape, THERMOMETER_FLAKES } from "./Snowflake";
import { TemperatureGradient } from "./temperatureColours";

const MIN = 60;
const MAX = 110;
const TOP = 12;
const BOTTOM = 150;

// The column is a gradient fixed to the scale, so a hot tub shows the whole
// range of colours.  The bulb stays white.  A marker on the left points at
// the setpoint, and bubbles rise in the column while the heater is on.  When
// the tub is off it is frozen like the ducklings: a snow cap, icicles and
// falling snowflakes.

// Horizontal position, start delay (s) and radius of the bubbles.
const BUBBLES = [
  [26.5, 0, 1.4],
  [29.5, 0.35, 1.0],
  [27.5, 0.7, 1.6],
  [30, 1.05, 1.1],
  [26, 1.4, 0.9],
  [28.5, 1.75, 1.3],
  [27, 2.1, 1.0],
  [29.8, 2.45, 1.5],
];

// Icicles: where they hang from (x, y), and how long they are.
const ICICLES = [
  [18.5, TOP - 2, 10],
  [23, TOP - 2, 17],
  [28, TOP - 2, 8],
  [33, TOP - 2, 14],
  [37.5, TOP - 2, 9],
  [21, 177, 8],
  [27.5, 180, 10],
  [34, 177, 7],
];

function Flake([across, size, kind, duration, delay]) {
  return (
    <g
      key={across}
      className="thermometer-flake-fall"
      style={{ animationDuration: `${duration}s`, animationDelay: `${delay}s` }}
    >
      <g className="snowflake" transform={`translate(${across * 90} 0)`}>
        <FlakeShape kind={kind} size={size} />
      </g>
    </g>
  );
}

function y(temperature) {
  const clamped = Math.min(MAX, Math.max(MIN, temperature));
  return BOTTOM - ((clamped - MIN) / (MAX - MIN)) * (BOTTOM - TOP);
}

export default function Thermometer({ value, setpoint = null, heating = false, frozen = false }) {
  const gradient = useId();
  const known = typeof value === "number";
  const target = typeof setpoint === "number" ? setpoint : null;
  const ticks = [];
  for (let t = MIN; t <= MAX; t += 10) ticks.push(t);

  let label = known ? `Water temperature ${value} degrees Fahrenheit` : "Water temperature unknown";
  if (target !== null) label += `, set to ${target}`;
  if (known && heating) label += ", heating";
  if (frozen) label += ", off";

  return (
    <svg className={frozen ? "thermometer frozen" : "thermometer"} viewBox="0 0 90 190" role="img" aria-label={label}>
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
            BUBBLES.map(([x, delay, r]) => (
              <circle
                key={delay}
                className="thermometer-bubble"
                cx={x}
                cy={BOTTOM + 4}
                r={r}
                style={{ "--rise": `${y(value) - BOTTOM - 2}px`, animationDelay: `${delay}s` }}
              />
            ))}
        </>
      )}
      {frozen && (
        <g aria-hidden="true">
          {THERMOMETER_FLAKES.map(Flake)}
          <path className="thermometer-snowcap" d="M 17 10 C 15 4, 21 1, 24 3 C 26 0, 32 0, 33 3 C 38 2, 41 7, 39 10 Z" />
          {ICICLES.map(([x, top, length]) => (
            <path key={`${x},${top}`} className="thermometer-icicle" d={`M ${x - 2.4} ${top} L ${x + 2.4} ${top} L ${x} ${top + length} z`} />
          ))}
        </g>
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
