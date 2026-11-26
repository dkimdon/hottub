// Under the tub card: a little phrase about soaking with friends on the left,
// changing every few seconds (or tap it for the next), and the only Sign out,
// on the right.

import { useEffect, useState } from "react";

export const PHRASES = [
  "Warm water, good friends.",
  "Everything is better with a soak and a chat.",
  "Save a seat for a neighbour.",
  "The best conversations happen at 104°.",
  "Come for the bubbles, stay for the company.",
  "Starry skies and warm water.",
  "A soak shared is a soak doubled.",
  "Good friends, warm water, no hurry.",
  "Some of the best talks happen in the tub.",
  "Slide over, there's room for one more.",
  "Quiet laughter over warm water.",
  "Soak, talk, repeat.",
  "Leave your worries on the towel rack.",
  "Friends who soak together, stay together.",
  "The ducklings say: invite someone along.",
];

const EVERY = 9000; // ms

export default function TubFooter({ onSignOut }) {
  const [phrase, setPhrase] = useState(() => Math.floor(Math.random() * PHRASES.length));
  const next = () => setPhrase((p) => (p + 1) % PHRASES.length);

  // Restarts after a tap, so a phrase you chose stays for the full time.
  useEffect(() => {
    const timer = setInterval(next, EVERY);
    return () => clearInterval(timer);
  }, [phrase]);

  return (
    <footer className="tub-footer">
      <button type="button" className="tub-tip" title="Another one" onClick={next}>
        <img src="/favicon-32.png" alt="" width="20" height="20" />
        <span key={phrase} className="tub-phrase">
          {PHRASES[phrase]}
        </span>
      </button>
      <button type="button" className="link-button" onClick={onSignOut}>
        Sign out
      </button>
    </footer>
  );
}
