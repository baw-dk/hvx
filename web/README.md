# TAIL label web app

A page that turns one CSV file with a year of indoor measurements into a TAIL label: the
rating of the thermal, acoustic, indoor-air and luminous environment (I best … IV), and a
BAW-branded sticker to download as SVG or PNG.

- **Same code as the package.** The rating is `hvx.tail_label.label_from_csv` from this
  repository, running in the browser with [Pyodide](https://pyodide.org). Offices and hotels
  follow TAIL (Wargocki et al. 2021); schools follow the TAIL scheme for schools (Tran 2024).
- **Nothing is uploaded.** Pyodide, its packages and the hvx wheel are served by the site
  itself (`npm run vendor`); the page makes no third-party requests.
- **UI:** React, [shadcn/ui](https://ui.shadcn.com) components (`src/components/ui`) styled
  with the BAW design system tokens (`src/index.css`); fonts are self-hosted.

## Develop

```bash
npm ci
npm run vendor      # Pyodide + wheels into public/ (needs Python with `build`)
npm run dev         # http://localhost:5173/hvx/
```

`npm run build` writes `dist/` for the base path `/hvx/` (set `HVX_BASE=/` for a root
deploy). `node scripts/e2e.mjs` runs the built app in Chromium: example year → label →
downloads. `node scripts/smoke-pyodide.mjs file.csv school` rates a CSV under Pyodide in Node.

## CSV format

One row per time stamp, a time column and any of: temperature, CO₂, relative humidity,
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
