// Snowflakes, shared by the frozen thermometer and the frozen ducklings so
// the same snow falls on both.  Each flake is drawn around (0, 0); `size` is
// the arm length in px (the thermometer is drawn at about 1 px per unit).

const ARMS = [0, 60, 120, 180, 240, 300];

export function FlakeShape({ kind, size }) {
  const s = size;
  switch (kind) {
    // Six plain arms.
    case "star":
      return [0, 60, 120].map((a) => <line key={a} x1={-s} y1="0" x2={s} y2="0" transform={`rotate(${a})`} />);
    // Six arms, each with a little V partway out.
    case "fern":
      return ARMS.map((a) => (
        <g key={a} transform={`rotate(${a})`}>
          <line x1="0" y1="0" x2={s} y2="0" />
          <polyline points={`${s * 0.45},${-s * 0.35} ${s * 0.6},0 ${s * 0.45},${s * 0.35}`} />
        </g>
      ));
    // Six arms ending in a dot.
    case "pom":
      return ARMS.map((a) => (
        <g key={a} transform={`rotate(${a})`}>
          <line x1="0" y1="0" x2={s * 0.75} y2="0" />
          <circle className="flake-dot" cx={s * 0.85} cy="0" r={Math.max(0.6, s * 0.16)} />
        </g>
      ));
    // A soft round clump.
    default:
      return <circle className="flake-dot" cx="0" cy="0" r={s * 0.55} />;
  }
}

// [across (0–1), size, kind, fall time (s), delay (s)]
export const THERMOMETER_FLAKES = [
  [0.08, 4.5, "fern", 6, 0],
  [0.5, 2.5, "dot", 7.5, -2.5],
  [0.69, 5.5, "star", 6.5, -4],
  [0.89, 3, "pom", 8, -1.2],
  [0.13, 2, "dot", 7, -5.5],
  [0.6, 4, "pom", 5.5, -3.3],
  [0.8, 3.5, "fern", 6.8, -0.6],
  [0.44, 6, "star", 7.2, -4.8],
];

export const TUB_FLAKES = [
  [0.04, 5, "star", 6.2, -1],
  [0.15, 2.5, "dot", 5.4, -3.6],
  [0.26, 4, "fern", 7, -0.2],
  [0.37, 3, "pom", 6, -4.4],
  [0.48, 6, "fern", 7.6, -2.2],
  [0.58, 2, "dot", 5, -0.9],
  [0.68, 4.5, "pom", 6.6, -5.2],
  [0.78, 3.5, "star", 5.8, -2.9],
  [0.88, 5.5, "fern", 7.3, -4],
  [0.95, 2.5, "dot", 6.4, -1.7],
];
