// The duckling picture in the status card, to the right of the thermometer, one per state, with a little
// animation on top: kettle steam and ripples while heating, bubbles when
// hot, snow when off, floating z's while a timer waits.  The pictures
// are in public/ (made by ../scripts/make_images.ps1); the animation is CSS
// and stops for people who ask their phone for reduced motion.

const ART = {
  heating: ["tub-heating.png", "A duckling pours a steaming kettle into the tub"],
  hot: ["tub-hot.png", "Ducklings relaxing in a warm, bubbly wooden tub"],
  off: ["tub-off.png", "Ducklings in hats and scarves in a frozen tub with icicles"],
  waiting: ["tub-waiting.png", "Ducklings asleep in the tub, an alarm clock on the rim"],
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
  off: [0, 1, 2, 3, 4, 5, 6, 7].map((i) => <span key={i} className="art-snow" style={{ "--i": i }} />),
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
      <img src={`/${src}`} alt={alt} width="400" height="355" />
      <div className="art-effects" aria-hidden="true">
        {EFFECTS[state]}
      </div>
    </div>
  );
}
