// The Help tab.

export default function Help() {
  return (
    <div className="help">
      <h2>Help</h2>

      <h3>Heating the tub</h3>
      <p>
        Tap a temperature under <strong>Heat to</strong> and the tub starts heating to it. Tap{" "}
        <strong>Off</strong> to turn the tub off. The highlighted button is the current setting.
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
        request at a time: heating now, turning off, or scheduling again replaces the timer. To call off a
        timer, tap <strong>Cancel timer</strong>; the tub stays off.
      </p>

      <h3>The tub turns off at midnight</h3>
      <p>
        The tub turns itself off automatically at midnight, so it is never left heating overnight. The tub cannot be
        turned on, and timers cannot start, between midnight and 1 AM.
      </p>

      <h3>The buttons on the tub</h3>
      <p>
        A change made with the tub's own buttons replaces whatever was set on this page, and the page shows that it
        was made at the tub. Whoever changes it last wins.
      </p>
    </div>
  );
}
