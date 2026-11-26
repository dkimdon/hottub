# CLAUDE.md — ui/

The web app: React, built with Vite, plain JavaScript (JSX) and plain CSS.
Runtime dependencies are `react`, `react-dom` and `aws-amplify` (sign-in only).
`sharp` is a dev dependency, used only to make the WebP pictures.
Keep it that way unless there is a strong reason.

## Files

```
src/App.jsx          start-up, signed-in shell, Tub / History / Help / Users tabs (no header)
src/SignIn.jsx       sign in, first-time password, forgotten password
src/TubPanel.jsx     status card: temperature and status lines (nothing to tap)
src/HeatControl.jsx  "Heat to [Off] [102]…[106]" buttons, schedule button + form, Cancel timer
src/Help.jsx         Help tab: how changes and timers work
src/HistoryPanel.jsx      History tab: period buttons, graph, table of changes
                          (10 per page, newest first)
src/TemperatureChart.jsx  the graph: hand-written SVG, no chart library
src/UsersPanel.jsx   admin-only user management
src/TubFooter.jsx    under the tub card: phrases about soaking with friends
                     (change every 9 s, or tap) and the only Sign out
src/Thermometer.jsx  SVG thermometer: bubbles while heating; snow cap, icicles
                     and falling snowflakes when the tub is off
src/Snowflake.jsx    snowflake shapes and placements, shared by the frozen
                     thermometer and the frozen ducklings
src/TubArt.jsx       duckling picture for the tub's state (heating / hot / off /
                     waiting), beside the thermometer, with CSS animation
src/temperatureColours.jsx  colour scale (icy white → blue → purple → red)
                     shared by the thermometer and the graph
src/preview.jsx      development only: every screen with made-up data
                     (preview.html); not part of the production build
src/auth.js          the only file that imports aws-amplify
src/api.js           the only file that calls the API
src/format.js        "5 minutes ago"
src/styles.css       all styling; light and dark from the system setting
src/ui.test.jsx      component tests (vitest + Testing Library)
src/app.test.jsx     the whole app starting up: catches a blank-page crash
src/features.test.jsx  thermometer marker/bubbles, forecast, stats, heat control timer
art/                 duckling artwork masters (Gemini, 1024 px, white background;
                     make_images.ps1 cuts the background away)
scripts/webp.mjs     turns the cut-out tub pictures into WebP (dev only; uses
                     the sharp dev dependency)
public/              pictures (tub-*.webp, about 40 KB each) and icons, made from
                     art/ by ../scripts/make_images.ps1,
                     and manifest.json, for the browser tab and "Add to Home Screen"
```

## Commands

```bash
npm install
npm test          # component tests, no network
npm run build     # production build into dist/
npm run dev       # local dev server on http://localhost:5174
```

For `npm run dev`, first run `python ../scripts/deploy.py ui-config test`, which
writes `public/config.json` pointing at the test stack.  The test API allows
`http://localhost:5173` and `http://localhost:5174` as browser origins; the
live API does not.

Deploy with `python ../scripts/deploy.py ui test`.

## How it fits together

- `config.json` (API URL, user pool IDs) is fetched at start-up and written at
  deploy time, so one build serves both environments.  Nothing
  environment-specific is compiled in.
- The Cognito ID token is sent as `Authorization: Bearer ...`.  A 401 from the
  API returns the user to the sign-in page.
- Whether to show the Users tab comes from the `cognito:groups` claim.  That is
  a convenience only: the API enforces admin rights itself.
- The tub panel refreshes every 30 seconds and when the page becomes visible.
  It passes its state up to `App`, which hands it to the History tab for
  the forecast (a dashed line to the setpoint at the estimated time, day
  view only).
- The graph is one line (water temperature) on one axis.  It is drawn at the
  container's real pixel width, breaks where readings are missing, labels only
  the latest value, and shows other values on hover, touch or the arrow keys.
- The status card says what the tub is doing; the controls are below it and
  look like controls; they come first, the status card after them.  One request at a time: a "Heat to" button sets the
  setpoint (and the API drops any timer); "Schedule for later…" sets the
  shared timer (and the API turns the tub off until the timer starts it).
  The current setting's button is highlighted; while a timer waits the
  schedule button ("Scheduled: 104° by 7:00 PM") is highlighted instead.
- Explanations (changes take a few minutes, the midnight turn-off, timers,
  the tub's own buttons) live on the Help page, not the main screen.
- Users cannot register themselves.  An admin adds them; Cognito emails a
  temporary password; the first sign-in forces a new password.

## Conventions

- Function components and hooks; no router, no state library.
- Components get data through `api.js`; tests mock `./api` and `./auth`.
- Wording matters to these users: keep the status sentences plain and close to
  the old UI's ("The water temperature was last measured 3 minutes ago.").
