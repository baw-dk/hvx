# TAIL label web app

A page that turns one CSV file per room (a year of indoor measurements each) into:

- **TAIL labels** for every room and, with more than one room, for the building: the rating of
  the thermal, acoustic, indoor-air and luminous environment (I best … IV) as BAW-branded
  stickers, each downloadable as SVG or PNG, or all of them as one ZIP.
- **The full hvx report** of the building (EN 16798-1 per season, BR18 indicators, TAIL,
  recommendations) as self-contained HTML, to download, open or print as PDF.
- **An interactive dashboard** of the report data: building figures, a sortable room table
  and, per room, CO₂ by hour and month, warm hours, measured values and recommendations.

The assessed hours are an occupancy schedule shared by the labels and the report: the TAIL
profile's hours by default (offices 09–17, hotels 22–06, schools 08–17), editable per weekday
with several periods per day (breaks), holiday periods (typical Danish school holidays can be
added), single closed days and public holidays.

- **Same code as the package.** Labels are `hvx.building_csv.labels` and the report
  `hvx.building_csv.report` from this repository, running in the browser with
  [Pyodide](https://pyodide.org). Offices and hotels follow TAIL (Wargocki et al. 2021, the
  building from its rooms by Eq. 1); schools follow the TAIL scheme for schools (Tran 2024).
- **Nothing is uploaded.** Pyodide, its packages and the hvx wheel are served by the site
  itself (`npm run vendor`); the page makes no third-party requests. The report packages
  (SciPy, Jinja2, about 13 MB) are fetched only when a report is asked for.
- **UI:** React, [shadcn/ui](https://ui.shadcn.com) components (`src/components/ui`) styled
  with the BAW design system tokens (`src/index.css`) and laid out like the BAW website;
  fonts are self-hosted.

## Develop

```bash
npm ci
npm run vendor      # Pyodide + wheels into public/ (needs Python with `build`)
npm run dev         # http://localhost:5173/hvx/
```

`npm run build` writes `dist/` for the base path `/hvx/` (set `HVX_BASE=/` for a root
deploy). `node scripts/e2e.mjs` runs the built app in Chromium: example building → labels →
downloads → report → dashboard. Under Pyodide in Node: `node scripts/smoke-pyodide.mjs file.csv
school` rates one CSV, `node scripts/smoke-building.mjs room1.csv room2.csv --type school` makes
the labels and the report of a building.

## CSV format

One file per room (the file name becomes the room name, editable). One row per time stamp, a time column and any of: temperature, CO₂, relative humidity,
noise, illuminance (lux), PM2.5, NO₂, formaldehyde, benzene, radon. English and Danish
column names are recognised (`tid`, `temperatur`, `fugtighed`, `støj`, `lys`, …), `,` `;` or
tab separators and decimal commas too. An outdoor temperature column (`outdoor_temperature`,
`udetemperatur`) enables the adaptive summer bands for buildings without mechanical cooling.

## Deploy at app.brunoadam.eu/hvx

`.github/workflows/web.yml` builds on every change and publishes `dist/` to GitHub Pages
from `main` (repository Settings → Pages → Source: GitHub Actions). It is then served at
`https://baw-dk.github.io/hvx/`. To serve it at `https://app.brunoadam.eu/hvx/`, add a
rewrite to the project that serves app.brunoadam.eu, e.g. on Vercel (`vercel.json`):

```json
{ "rewrites": [{ "source": "/hvx/:path*", "destination": "https://baw-dk.github.io/hvx/:path*" }] }
```

(or point the organisation's Pages site at app.brunoadam.eu: project pages are then served at
`/hvx/` automatically).
