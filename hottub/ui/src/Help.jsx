// The Help tab.  Sign out is here too, so everyone can reach it (admins also
// have it on the Users tab).

export default function Help({ onSignOut }) {
  return (
    <div className="help">
      <h2>Help</h2>

      <h3>Heating the tub</h3>
      <p>
        Tap a temperature under <strong>Heat to</strong> and the tub starts heating to it. Tap{" "}
        <strong>Off</strong> to turn it off. The highlighted button is the current setting.
      </p>

      <h3>Changes take a few minutes</h3>
      <p>
        The tub picks up a change within about 2 minutes. The page shows the new setting straight away, and the
        temperature and heating follow once the tub has it.
      </p>

      <h3>Scheduling for later</h3>
      <p>
        <strong>Schedule for later…</strong> lets you choose a temperature and the time you want the tub ready.
        The tub stays off until it is time to start, then heats so it is ready by the time you chose. There is one
        request at a time: heating now, turning off, or scheduling again replaces the timer. Use{" "}
        <strong>Cancel timer</strong> to drop it.
      </p>

      <h3>It turns off at midnight</h3>
      <p>
        The tub turns itself off automatically at midnight, so it is never left heating overnight. It cannot be
        turned on, and timers cannot start, between midnight and 1 AM.
      </p>

      <h3>The buttons on the tub</h3>
      <p>
        A change made with the tub's own buttons replaces whatever was set on this page, and the page shows that it
        was made at the tub. Whoever changes it last wins.
      </p>

      <p className="sign-out">
        <button type="button" onClick={onSignOut}>
          Sign out
        </button>
      </p>
    </div>
  );
}
