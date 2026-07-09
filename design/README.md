# Remy v2 design reference

- `remy-v2-design.html` — the Claude Design interactive prototype export (open in a browser; fully clickable, all screens/states).
- `src/remy-app-source.html` — extracted source document: font-face rules, compiled markup, and the readable `Component` app class (screen/state logic + sample data) in the inline script at the bottom.
- `src/*.woff2` — Hanken Grotesk (sans, UI) and Newsreader (serif, display) font files for self-hosting.
- `src/*.js` — bundled runtime libs (React, dc-runtime); reference only.

Frontend tasks (V2_PLAN T7/T8): treat the prototype as the visual source of truth
(DESIGN_BRIEF.md is the intent/state checklist). Open the prototype in a browser to
inspect each screen; mine `remy-app-source.html` for exact type/color/spacing values.
