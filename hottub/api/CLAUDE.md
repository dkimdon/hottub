# CLAUDE.md — api/

The backend: one Python Lambda behind an API Gateway HTTP API (payload format
2.0), storing everything in one DynamoDB item.  The only dependency is boto3,
which the Lambda runtime provides — nothing is bundled.

## Files

```
function/handler.py   entry point: routing and who-may-call-what
function/tub.py       desired state, operator reports, nightly turn-off
function/history.py   log of setpoint changes and temperature readings
function/estimate.py  when the tub should reach its setpoint (pure functions)
function/users.py     user administration (Cognito)
function/common.py    ApiError, JSON body parsing, responses
tests/test_api.py     tests; DynamoDB and Cognito faked in-process by moto
tests/test_estimate.py  the estimate's calculation, and GET /tub using it
tests/test_timer.py   the timer, and Pacific time for the turn-off hour
```

`GET /tub` includes `heating_estimate` (`ready_at`, `rate_per_hour`,
`based_on`) while the tub is below a numeric setpoint and its last reading is
recent; otherwise null.  The rate comes from the heating run in progress, else
the past week's runs (cached in the tub item for six hours), else 4 °F/hour.
See the docstring in `function/estimate.py`.  Like history, it must never
break the request: any failure gives null.

The AWS resources are in `../infra/template.yaml`; deploy with
`../scripts/deploy.py`.

## Routes

| Route | Caller | Purpose |
|---|---|---|
| `GET /tub` | signed-in user | State shown in the UI |
| `PUT /tub/setpoint` | signed-in user | `{"setpoint": "off" \| 102..106}` |
| `PUT /tub/timer` | signed-in user | `{"setpoint": 102..106, "ready_at": ISO-8601}` — have it hot by then |
| `DELETE /tub/timer` | signed-in user | Cancel the timer |
| `GET /history?hours=24\|168\|720` | signed-in user | Temperature readings (averaged down to at most 240 points), setpoint changes, and `stats` (heater hours, times used) |
| `GET /users` | admin | List users |
| `POST /users` | admin | `{"email", "admin"}` — emails a temporary password |
| `PATCH /users/{username}` | admin | `{"admin": bool}` |
| `DELETE /users/{username}` | admin | Remove a user |
| `POST /users/{username}/reset-password` | admin | Re-send invitation or send a reset code |
| `GET /operator/desired` | operator | Desired tub controls and their version |
| `PUT /operator/report` | operator | Tub state; optionally a front-panel change |

## Authorization

- **Users**: API Gateway's JWT authorizer validates the Cognito token before
  the Lambda runs.  The Lambda reads the caller from
  `requestContext.authorizer.jwt.claims`.
- **Admins**: membership of the Cognito group `admin`, checked with Cognito on
  every admin request (`users.is_admin`) rather than read from the token, so
  revoking admin rights takes effect immediately.  An admin cannot remove their
  own admin rights or delete themselves, which guarantees one admin always
  remains.
- **Operator**: `X-Operator-Key` header compared with the `OPERATOR_KEY`
  environment variable in constant time.  These routes have no API Gateway
  authorizer; the check in `handler._authorize` is the only one.
- Removing a user does not cancel a token they already hold; it stays valid for
  up to an hour (the ID token lifetime in the template).

## State and "most recent change wins"

See the docstring at the top of `function/tub.py` for every attribute.
`desired_version` increases on each change of desired state.  When the operator
reports a front-panel change it sends the version it last read; the change is
only adopted if that is still the current version.  If a user changed the
setpoint in between, the user's change stands and the response says
`"adopted": false` along with the current desired state.

**Timer**: one at a time, shared, kept in the tub item.  It starts the
heating when `GET /operator/desired` is called at or after the computed start
time (ready time minus heating time minus 20 minutes), so no extra scheduler
is needed; the change has source `"timer"`.  It never starts during the
midnight turn-off hour.  One request at a time: setting a timer turns the
tub off until then, and a setpoint from the UI or the tub's panel removes the
timer (the nightly turn-off does not).  "Off until then" is the `WAITING`
state, ready mode at 50 °F, shown to users as "off": it never heats, but the
tub keeps reporting its temperature (at rest it can go hours without one), so
the start time uses a real reading.  A reading over an hour old is not used;
80 °F is assumed instead, starting early rather than late.  Cancelling or
missing the timer puts the tub back to rest; the nightly turn-off leaves
`WAITING` alone.  See "Timer" in `function/tub.py`.

The nightly turn-off is an EventBridge schedule that invokes the same Lambda
with `{"source": "hottub.schedule"}`.

## History

A second table (`hottub-history-<env>`, key `kind` + `at`) holds one item per
setpoint change and per temperature reading.  Items expire by DynamoDB TTL.
Recording history must never block control of the tub: `history.record_*`
catch and log every error.  Items are keyed to the second, so two changes in
the same second keep only the later one.

## Conventions

- Handlers take `(event, user)` and return `respond(status, body)`; they raise
  `ApiError(status, message)` for anything the caller got wrong.  Bad input
  must produce a 400, never a 500.
- Do not name a module after a standard-library module (`http`, `json`, ...):
  boto3 imports them and the Lambda breaks at start-up.
- Tests go through `handler.handler` with API Gateway-shaped events, so they
  cover routing and authorization as well as the logic.
