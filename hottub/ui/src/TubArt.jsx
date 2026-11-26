// The duckling picture in the status card, to the right of the thermometer, one per state, with a little
// animation on top: kettle steam and ripples while heating, bubbles when
// hot, snow when off, floating z's while a timer waits.  The pictures
// are in public/ (made by ../scripts/make_images.ps1); the animation is CSS
// and stops for people who ask their phone for reduced motion.

import { FlakeShape, TUB_FLAKES } from "./Snowflake";

const ART = {
  heating: ["tub-heating.webp", "A duckling pours a steaming kettle into the tub"],
  hot: ["tub-hot.webp", "Ducklings relaxing in a warm, bubbly wooden tub"],
  off: ["tub-off.webp", "Ducklings in hats and scarves in a frozen tub with icicles"],
  waiting: ["tub-waiting.webp", "Ducklings asleep in the tub, an alarm clock on the rim"],
};

export function artState(tub) {
  if (tub.timer) return "waiting";
  if (!tub.setpoint || tub.setpoint === "off") return "off";
  return tub.heating ? "heating" : "hot";
}

const EFFECTS = {
  heating: (
    <>
      {[0, 1, 2].map((i) => (
        <span key={i} className="art-steam" style={{ "--i": i }} />
      ))}
      {[0, 1].map((i) => (
        <span key={`r${i}`} className="art-ripple" style={{ "--i": i }} />
      ))}
    </>
  ),
  hot: [0, 1, 2, 3, 4].map((i) => <span key={i} className="art-bubble" style={{ "--i": i }} />),
  // The same snowflakes as the frozen thermometer beside it.
  off: TUB_FLAKES.map(([across, size, kind, duration, delay]) => {
    const box = size * 2 + 4;
    return (
      <span
        key={across}
        className="art-snow"
        style={{ left: `${across * 100}%`, animationDuration: `${duration}s`, animationDelay: `${delay}s` }}
      >
        <svg className="snowflake" width={box} height={box} viewBox={`${-box / 2} ${-box / 2} ${box} ${box}`}>
          <FlakeShape kind={kind} size={size} />
        </svg>
      </span>
    );
  }),
  waiting: [0, 1, 2].map((i) => (
    <span key={i} className="art-z" style={{ "--i": i }}>
      z
    </span>
  )),
};

export default function TubArt({ state }) {
  const [src, alt] = ART[state];
  return (
    <div className={`tub-art tub-art-${state}`} data-state={state}>
      <img src={`/${src}`} alt={alt} width="500" height="443" />
      <div className="art-effects" aria-hidden="true">
        {EFFECTS[state]}
      </div>
    </div>
  );
}
