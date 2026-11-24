// Water temperature over time: one line, drawn in SVG at the container's real
// pixel size so text stays readable on a phone.

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { TemperatureGradient, colourFor } from "./temperatureColours";

const HEIGHT = 200;
const MARGIN = { top: 14, right: 44, bottom: 24, left: 34 };

const timeOnly = new Intl.DateTimeFormat(undefined, { hour: "numeric" });
const dayOnly = new Intl.DateTimeFormat(undefined, { weekday: "short" });
const monthDay = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const full = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function useWidth(ref) {
  const [width, setWidth] = useState(480);
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

// Round, evenly spaced values covering [low, high].
function yTicks(low, high) {
  const step = [1, 2, 5, 10, 20].find((s) => (high - low) / s <= 5) || 20;
  const ticks = [];
  for (let t = Math.floor(low / step) * step; t <= Math.ceil(high / step) * step; t += step) {
    ticks.push(t);
  }
  return ticks;
}

// Tick times on local clock boundaries: every 6 hours for a day, every day
// for a week, every 5 days for a month.
function xTicks(from, to, hours) {
  const ticks = [];
  const t = new Date(from);
  t.setMinutes(0, 0, 0);
  if (hours <= 24) {
    t.setHours(Math.ceil((t.getHours() + 1) / 6) * 6);
    for (; t <= to; t.setHours(t.getHours() + 6)) ticks.push([+t, timeOnly.format(t)]);
  } else {
    const days = hours <= 168 ? 1 : 5;
    const label = hours <= 168 ? dayOnly : monthDay;
    t.setHours(24);
    for (; t <= to; t.setDate(t.getDate() + days)) ticks.push([+t, label.format(t)]);
  }
  return ticks;
}

export default function TemperatureChart({ history }) {
  const wrapper = useRef(null);
  const width = useWidth(wrapper);
  const [hover, setHover] = useState(null);
  const gradient = useId();

  const points = useMemo(
    () => history.temperatures.map((p) => ({ ...p, time: Date.parse(p.at) })),
    [history]
  );

  if (points.length === 0) {
    return <p className="muted">No temperature readings in this period yet.</p>;
  }

  const from = Date.parse(history.from);
  const to = Date.parse(history.to);
  const values = points.map((p) => p.temperature);
  const ticksY = yTicks(Math.min(...values) - 1, Math.max(...values) + 1);
  const low = ticksY[0];
  const high = ticksY[ticksY.length - 1];

  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 50);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (time) => MARGIN.left + ((time - from) / (to - from)) * plotWidth;
  const y = (value) => MARGIN.top + (1 - (value - low) / (high - low)) * plotHeight;

  // Break the line where readings are missing (the tub was unreachable),
  // rather than draw a straight line across the gap.
  const slot = (to - from) / 240;
  const segments = [];
  points.forEach((p, i) => {
    if (i === 0 || p.time - points[i - 1].time > slot * 4) segments.push([]);
    segments[segments.length - 1].push(p);
  });

  const last = points[points.length - 1];
  const active = hover === null ? null : points[hover];

  function nearest(clientX) {
    const box = wrapper.current.getBoundingClientRect();
    const time = from + ((clientX - box.left - MARGIN.left) / plotWidth) * (to - from);
    let best = 0;
    points.forEach((p, i) => {
      if (Math.abs(p.time - time) < Math.abs(points[best].time - time)) best = i;
    });
    return best;
  }

  function onKeyDown(event) {
    const move = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    if (!move) return;
    event.preventDefault();
    const start = hover === null ? points.length - 1 : hover;
    setHover(Math.min(points.length - 1, Math.max(0, start + move)));
  }

  return (
    <div className="chart" ref={wrapper}>
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        tabIndex={0}
        aria-label={`Water temperature over the period, most recently ${last.temperature} degrees. Use the left and right arrow keys to read values.`}
        onPointerMove={(e) => setHover(nearest(e.clientX))}
        onPointerDown={(e) => setHover(nearest(e.clientX))}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={onKeyDown}
      >
        {ticksY.map((t) => (
          <g key={t}>
            <line className="chart-grid" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(t)} y2={y(t)} />
            <text className="chart-label" x={MARGIN.left - 6} y={y(t) + 4} textAnchor="end">
              {t}°
            </text>
          </g>
        ))}
        {xTicks(from, to, history.hours).map(([time, label]) => (
          <text key={time} className="chart-label" x={x(time)} y={HEIGHT - 6} textAnchor="middle">
            {label}
          </text>
        ))}

        {/* The line takes the thermometer's colours: each height is painted
            the colour of its temperature.  A thin edge drawn underneath keeps
            the icy-white end visible on a white page. */}
        <defs>
          <TemperatureGradient id={gradient} y={y} />
        </defs>
        {segments.map((segment) => {
          if (segment.length === 1) {
            const p = segment[0];
            return (
              <circle key={p.at} className="chart-dot" cx={x(p.time)} cy={y(p.temperature)} r="2" fill={colourFor(p.temperature)} />
            );
          }
          const coordinates = segment.map((p) => `${x(p.time).toFixed(1)},${y(p.temperature).toFixed(1)}`).join(" ");
          return (
            <g key={segment[0].at}>
              <polyline className="chart-line-edge" points={coordinates} />
              <polyline className="chart-line" points={coordinates} stroke={`url(#${gradient})`} />
            </g>
          );
        })}

        {active && (
          <line className="chart-crosshair" x1={x(active.time)} x2={x(active.time)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />
        )}

        {/* The most recent reading, labelled; hovering moves the marker. */}
        <circle
          className="chart-marker"
          cx={x((active || last).time)}
          cy={y((active || last).temperature)}
          r="4"
          fill={colourFor((active || last).temperature)}
        />
        {!active && (
          <text className="chart-value" x={x(last.time) + 8} y={y(last.temperature) + 4}>
            {last.temperature}°
          </text>
        )}
      </svg>

      {active && (
        <div
          className="chart-tooltip"
          role="status"
          style={{
            left: Math.min(Math.max(x(active.time), 70), width - 70),
            top: MARGIN.top,
          }}
        >
          <strong>{active.temperature}°F</strong>
          {active.heating && " · heating"}
          <span>{full.format(active.time)}</span>
        </div>
      )}
    </div>
  );
}
