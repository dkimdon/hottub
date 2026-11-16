# CLAUDE.md — operator/

**Not what is deployed today.**  The Android/Termux device by the tub has no
Python, so `../operator-ruby/` runs there for now.  This Python operator is the
intended replacement and the reference for the logic; a change to
`controller.py` must also be made in `../operator-ruby/hottub_operator.rb`.

The operator runs on the tub's local network.  Every two minutes it reads the
tub, brings the tub and the cloud into step, and reports the water
temperature.  Python 3.10+, standard library only — do not add third-party
packages.

## Files

```
hottub_operator.py   entry point: configuration, logging, the loop
controller.py        one control cycle (the logic worth reading first)
api_client.py        the two API calls, over urllib
bwa/                 Balboa spa protocol library (TCP 4257, UDP discovery 30303)
run-termux.sh        keeps the operator running under Termux
tests/               unit tests, plus test_live.py for the real tub
```

## Running

```bash
export HOTTUB_API_URL=https://...        # from: python ../scripts/deploy.py outputs test
export HOTTUB_OPERATOR_KEY=...           # from: python ../scripts/deploy.py operator-key test
python3 hottub_operator.py --once        # one cycle
python3 hottub_operator.py               # loop forever
python3 hottub_operator.py --report-only # never change the tub
```

Optional: `HOTTUB_SPA_IP` (skip discovery), `HOTTUB_STATE_FILE`,
`HOTTUB_LOG_FILE`, `HOTTUB_INTERVAL`.

Only one controller may manage a tub at a time.  While the old Ruby operator
is still running, run this one with `--report-only`; otherwise each sees the
other's changes as someone pressing buttons on the tub.

## Tests

```bash
python3 -m unittest discover -s tests -p "test_[cm]*.py"   # no hardware; ~10 s
python3 -m unittest tests/test_live.py -v                   # real tub; changes settings
```

Run one group of tests with
`python3 -m unittest discover -s tests -p test_controller.py -k TestPanelChanges -v`.

The unit tests run against `bwa/server.py`, a simulated tub, and a fake API in
`tests/test_controller.py` that mimics the real API's version check.

## The control cycle (`controller.run_cycle`)

1. Get the desired controls and their version from the API.
2. Connect to the tub and read a status.
3. If the tub's controls differ from what was saved at the end of the last
   cycle (`operator-state.json`), someone used the front panel: report it.  The
   API adopts it as the desired state unless a user changed the setpoint in the
   meantime, in which case the UI's change is applied instead.
4. Otherwise, if the tub differs from the desired controls, change it: range
   first (the tub rejects a set temperature outside its current range), then
   set temperature, then heating mode.  Each change is confirmed by waiting for
   a status that shows it.
5. Save the tub's controls, then report.

Invariants worth keeping:

- State is saved **before** the final report, so a failed report cannot make
  the operator's own change look like a panel change next time.
- "Ready in rest" (rest mode with the jets on) is treated as rest.
- If the API is unreachable, the tub is left alone.
- If the tub is unreachable, that is reported so the UI can warn users.

## The `bwa` library

`bwa/message.py` — framing.  `build_frame` and `split_frames` are the only
places that know the frame layout
`[0x7e][L][type ×3][payload][CRC][0x7e]`, `L = len(payload) + 5`.  Message
subclasses register themselves by `MESSAGE_TYPE`.

`bwa/client.py` — every blocking call has a deadline, because the tub's wifi
module regularly stops responding:
- connecting raises `OSError` after `timeout` seconds
- `poll()` raises `TimeoutError`; a closed connection raises `ConnectionError`
- `poll_until_status()` / `wait_for_status()` return `None` on timeout and
  never return a status received before the call

`bwa/messages/status.py` — the status the tub sends about once a second.
Payload byte indices: `[2]` current temperature (0xFF = unknown), `[3]` hour,
`[4]` minute, `[5]` heating mode, `[9]` scale / 24h, `[10]` heating / range,
`[11]` pumps, `[13]` circulation pump, `[14]` light, `[20]` set temperature.
Celsius values are doubled on the wire.

The documented Fahrenheit limits are 50–80 (low range) and 80–104 (high), but
this tub accepts up to 106 in the high range, and the application depends on
that.

The full wire specification is `doc/protocol.md` in
`../../balboa_worldwide_app/`.
