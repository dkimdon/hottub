# CLAUDE.md — ui/

The web app: React, built with Vite, plain JavaScript (JSX) and plain CSS.
Runtime dependencies are `react`, `react-dom` and `aws-amplify` (sign-in only).
Keep it that way unless there is a strong reason.

## Files

```
src/App.jsx          start-up, signed-in shell, Tub / Users tabs
src/SignIn.jsx       sign in, first-time password, forgotten password
src/TubPanel.jsx     temperature, status lines, setpoint buttons
src/ReadyBy.jsx      "have it ready by": set or cancel the shared timer
src/HistoryPanel.jsx      period buttons, graph, table of changes
src/TemperatureChart.jsx  the graph: hand-written SVG, no chart library
src/UsersPanel.jsx   admin-only user management
src/Thermometer.jsx  SVG thermometer
src/temperatureColours.jsx  colour scale (icy white → blue → purple → red)
                     shared by the thermometer and the graph
src/preview.jsx      development only: every screen with made-up data
                     (preview.html); not part of the production build
src/auth.js          the only file that imports aws-amplify
src/api.js           the only file that calls the API
src/format.js        "5 minutes ago"
src/styles.css       all styling; light and dark from the system setting
src/ui.test.jsx      component tests (vitest + Testing Library)
src/features.test.jsx  thermometer marker/bubbles, forecast, stats, timer
public/              icons (drawn by ../scripts/make_icons.py) and
                     manifest.json, for the browser tab and "Add to Home Screen"
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
  It passes its state up to `App`, which hands it to the history panel for
  the forecast (a dashed line to the setpoint at the estimated time, day
  view only).
- The graph is one line (water temperature) on one axis.  It is drawn at the
  container's real pixel width, breaks where readings are missing, labels only
  the latest value, and shows other values on hover, touch or the arrow keys.
  The same readings are available as a table below it.
- Users cannot register themselves.  An admin adds them; Cognito emails a
  temporary password; the first sign-in forces a new password.

## Conventions

- Function components and hooks; no router, no state library.
- Components get data through `api.js`; tests mock `./api` and `./auth`.
- Wording matters to these users: keep the status sentences plain and close to
  the old UI's ("The water temperature was last measured 3 minutes ago.").
