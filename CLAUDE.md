# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

This is the new version of a hot tub control system, being built in parallel with the existing production system (in `../hottub-app/` and `../balboa_worldwide_app/`).  The existing system continues to serve users while this one is developed.  Do not modify anything outside this repo when working here.

## Repository Layout

```
operator/   Python — spa protocol library (bwa/) and control loop
ui/         React — web UI (not yet started)
api/        Python — REST API on AWS API Gateway (not yet started)
```

Each subdirectory has its own `CLAUDE.md` with component-specific guidance.

## Architecture

The system has three components that communicate via a single REST API:

```
[React UI] ──► [API Gateway + Lambda] ──► [DynamoDB]
                                               ▲
                              [Operator] ──────┘
                                  │
                              [Spa / Tub]
                              10.0.0.105
```

**UI** (`ui/`) — React web app.  Users log in via AWS Cognito, set the desired temperature (102–106°F) or turn the tub off, and see the current water temperature and last-updated time.  Reuses the existing `react-ui-thermometer` component from the old system.

**API** (`api/`) — REST API built on AWS API Gateway + Python Lambda.  Single API consumed by both the UI and the Operator.  DynamoDB is the only persistence store.  No AppSync, no MySQL, no AWS IoT.

**Operator** (`operator/`) — Python process that runs on the local network alongside the tub.  Polls the REST API for the desired set point, applies it to the physical tub via the `bwa` library, and reports the current water temperature back to the API.  Also turns the tub off automatically around midnight.

## Key Technology Decisions

- **AWS Cognito** for user authentication
- **AWS API Gateway** (REST) replaces AppSync
- **DynamoDB** replaces AWS IoT and any MySQL usage
- **Python Lambda** replaces the existing Node.js lambda
- **React** for the UI; reuse the existing thermometer component
- **All AWS resources managed with CloudFormation** — declarative, infrastructure as code
- **`test` and `live` stacks** — separate CloudFormation stacks so changes can be validated in `test` before promoting to `live`

## What Not To Do

- Do not use AWS IoT, AppSync, or MySQL anywhere in this codebase.
- Do not modify the existing system (`../hottub-app/`, `../balboa_worldwide_app/`).
- Do not use third-party Python packages in `operator/` — standard library only.
