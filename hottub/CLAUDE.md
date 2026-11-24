# CLAUDE.md

Guidance for Claude Code when working in this directory.

## What this is

A hot tub control system for about a dozen users.  It replaces the old system
in `../hottub-app/` (UI, AppSync, AWS IoT) and `../balboa_worldwide_app/` (Ruby
operator), which stays in service until this one goes live.  Do not modify
those directories; they are reference only.  The old operator's logic is in
`bin/bwa_aws_iot_thing` on the `origin/master` branch of `balboa_worldwide_app`.

Priorities, in order: simple, easy to maintain, few dependencies.  It will
never be more than a small application.

## Layout

```
api/            Python Lambda behind an API Gateway HTTP API
operator-ruby/  Ruby operator — the one deployed on the device by the tub
operator/       Python operator and Balboa protocol library — the intended
                replacement, once the device has Python
ui/             React web app (Vite)
infra/          CloudFormation: template.yaml (one stack per environment),
                certificate.yaml and email.yaml (shared by both)
scripts/        deploy.py (deploy everything), manage_users.py (bootstrap admins)
```

`api/`, `operator/`, `operator-ruby/` and `ui/` each have their own `CLAUDE.md`.

There are two operators with the same behaviour.  The device by the tub has
Ruby but not Python, so `operator-ruby/` is what runs.  Any change to the
control logic must be made in both, with tests in both.

## Architecture

```
[React UI] ──► [HTTP API + Lambda] ──► [DynamoDB: one item]
  Cognito            ▲      ▲
                     │      └── EventBridge schedule (nightly turn-off)
                [Operator] ──► [Tub, Balboa wifi module, TCP 4257]
```

- **Users** sign in with Cognito (email + password).  There is no
  self-registration.  Members of the Cognito group `admin` can add and remove
  users and grant admin rights, from the Users tab of the same web UI.
- **Desired state** is stored as the tub's three controls (heating mode,
  temperature range, set temperature).  "Off" means rest mode, low range, 50°F.
  The UI offers off and 102–106°F.
- **The most recent change wins.**  A change can come from the web UI, from
  the buttons on the tub (the operator notices and reports it; it becomes the
  desired state until someone next uses the UI), or from the nightly turn-off.
  `desired_version` in DynamoDB makes this safe when changes race.
- **The operator** authenticates with a shared key (`X-Operator-Key`), kept in
  SSM Parameter Store at `/hottub/<env>/operator-key`.
- **The nightly turn-off** runs every five minutes between midnight and 1am
  Pacific, as the old system did: the tub cannot be left on during that hour.
- **History**: every setpoint change (kept 400 days) and temperature reading
  (kept 35 days) is logged to a second DynamoDB table and shown in the UI.
- **Domain names**: `hottub-test.cohoecovillage.org` and
  `hottub.cohoecovillage.org`.  The live name belongs to the old system's
  CloudFront distribution until cut-over, so deploy live with `--no-domain`
  until then.  **Email** is sent through SES from `hottub@cohoecovillage.org`
  once the domain is verified; before that Cognito's built-in sender is used.

## Environments

Two independent stacks, `hottub-test` and `hottub-live`, from the same
template, in us-west-2.  Always deploy and check `test` first.

```bash
python scripts/deploy.py shared test                    # certificate + SES; prints DNS records
python scripts/deploy.py all test                       # stack, then UI
python scripts/manage_users.py create test you@example.com --admin   # first admin
python scripts/deploy.py operator-key test              # key for the operator
```

`deploy.py` asks for confirmation before changing `live`.  Never deploy unless
the user has asked for it in this session and said which AWS credentials to use.

## Tests

```bash
cd operator && python -m unittest discover -s tests -p "test_[cm]*.py"   # no hardware needed
cd operator-ruby && ruby -I ../../balboa_worldwide_app/lib test_operator.rb
cd api && python -m unittest discover -s tests       # needs: pip install -r requirements-dev.txt
cd ui && npm test
```

To see the UI without AWS: `npm run dev` in `ui/`, then open
`http://localhost:5174/preview.html` (made-up data).

`operator/tests/test_live.py` talks to the real tub and changes its settings;
run it only on request.

## Rules

- Edit files with the editor tools, not by reading and rewriting them in
  PowerShell: Windows PowerShell corrupts the non-ASCII characters (°, —).
- No AWS IoT, AppSync or MySQL.  DynamoDB is the only store.
- All AWS resources are declared in `infra/template.yaml`; nothing is created
  by hand in the console.
- `operator/` uses the Python standard library only — it runs on a small
  device.  The Lambda uses only boto3, which AWS provides.
- When adding an API route, change three places together: `ROUTES` in
  `api/function/handler.py`, the route resources in `infra/template.yaml`, and
  `ui/src/api.js`.
