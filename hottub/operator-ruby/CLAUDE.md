# CLAUDE.md — operator-ruby/

The operator that is actually deployed, for now: a Ruby port of
`../operator/` (Python).  It exists because the Android/Termux device by the
tub has Ruby and the `balboa_worldwide_app` gem installed, but no Python.
The plan is still to move to the Python operator once Python is on the device;
until then **this is the one that runs, and the two must behave the same**.

## Files

```
hottub_operator.rb   everything: API client, state file, control cycle, main
test_operator.rb     minitest suite; no tub or network needed
run-termux.sh        runs one cycle every two minutes under Termux
```

## How it differs from the Python operator

- It runs **one cycle per invocation** and exits; `run-termux.sh` loops and
  wraps each run in `timeout`, as the old system did.
- It uses the Ruby `bwa` library from `../../balboa_worldwide_app/` (installed
  on the device as the `balboa_worldwide_app` gem), not `../operator/bwa/`.
  That library has no timeouts and reports a closed connection as a
  `NoMethodError`; `wait_for_status` wraps it with `Timeout` and turns both
  into "no status" / `TubUnreachable`.
- Do not modify `../../balboa_worldwide_app/`; work around the library here.

The control logic (`run_cycle`, `apply`, `control_state`) is a line-for-line
port of `../operator/controller.py`, and `test_operator.rb` mirrors
`../operator/tests/test_controller.py`.  A change to the logic in one must be
made in the other, with its test.

## Running

```sh
export HOTTUB_API_URL=https://...     # python ../scripts/deploy.py outputs test
export HOTTUB_OPERATOR_KEY=...        # python ../scripts/deploy.py operator-key test
ruby hottub_operator.rb               # one cycle
ruby hottub_operator.rb --report-only # never change the tub
```

Optional: `HOTTUB_SPA_IP` (skip discovery), `HOTTUB_STATE_FILE`.

Only one controller may manage the tub at a time.  While the old
`bwa_aws_iot_thing` is still running, use `--report-only`.

## Tests

```sh
ruby test_operator.rb                                   # with the gem installed
ruby -I ../../balboa_worldwide_app/lib test_operator.rb # against the checkout
```

## Compatibility

The Ruby version on the device is old and unknown.  Keep to plain Ruby that
works from 2.5 up: no pattern matching, no endless methods, no `it`, no
numbered block parameters.  Standard library only (`json`, `net/http`,
`timeout`, `uri`) plus the `bwa` gem and its dependency `digest-crc`.
