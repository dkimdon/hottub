// A simple thermometer drawn in SVG.

import { useId } from "react";
import { TemperatureGradient } from "./temperatureColours";

const MIN = 60;
const MAX = 110;
const TOP = 12;
const BOTTOM = 150;

// The column is a gradient fixed to the scale, so a hot tub shows the whole
// range of colours.  The bulb stays white.

function y(temperature) {
  const clamped = Math.min(MAX, Math.max(MIN, temperature));
  return BOTTOM - ((clamped - MIN) / (MAX - MIN)) * (BOTTOM - TOP);
}

export default function Thermometer({ value }) {
  const gradient = useId();
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
