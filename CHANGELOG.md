# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- MCP server (`hvx mcp`, `mcp` extra): AI assistants can load data (CSV, Climify/DMI,
  live sites), build reports, inspect buildings/actions/rooms and export HTML/PDF/JSON/CSV;
  `HVX_MCP_ROOT` confines file access. Works with MCP Python SDK 1.x and 2.x.
- Report branding: white-label by default (no company details anywhere); a brand adds
  logo or wordmark, accent colour and a company block with CVR number to the HTML report
  and the PDF footer. Built-in `baw` template (`--brand baw`, `ReportConfig(branding="baw")`,
  API `brand`) or any brand YAML file; required fields such as the CVR number must be filled
  before a branded report renders. `render(..., brand=None)` white-labels an existing report.
- TAIL rating (Thermal, Acoustic, Indoor air, Luminous) in reports: a left-to-right hierarchy
  (overall → domains → measured parameters, unmeasured parameters collapsed per domain), a
  building comparison table with the spread of room ratings, and TAIL badges on room cards.
- `load_climify_folder(..., parameters=...)` loads only the listed parameters.
- Report languages: `ReportConfig(language="da")` gives a Danish report (texts, recommendations,
  key findings, Danish number and date formats); `introduction` and `notes` for client-specific text.
- PDF output (`.pdf` / `render(report, "pdf")`) via headless Chromium; `pdf` extra.
- Heatmaps of CO₂ > 1000 ppm by hour of day and by month, and hours > 26 °C by month.
- Reports assess **occupied hours only** by default (building-type opening hours,
  public holidays, configurable school/holiday periods via `ReportConfig.occupancy`,
  `holiday_periods` or `metadata["holiday_periods"]`); `occupied_only=False` restores 24/7.
- Hours above limits per room and building (CO₂ > 1000/2000 ppm, > 26/27 °C),
  morning/afternoon breakdown, failing BR18 rules named in reports and CSV.
- `hvx.connectors.climify`: Climify room exports and DMI weather files (UTC → local time).
- ChirpStack (LoRaWAN) live source: MQTT integration, gRPC API backfill, HTTP
  integration webhook; `hvx chirpstack listen`.
- Live data layer (`hvx.live`): Home Assistant REST and push sources, rolling
  EN 16798 assessment, live limit checks, YAML site files.
- Home Assistant integration `hvx_ieq` (HACS).
- `hvx` command line; Python package layout under `src/hvx`.
- Reporting pipeline (`hvx.reporting`) with HTML, JSON and CSV output.
- IFC and Brick Schema alignment with an IEQ extension ontology.
- Contributor License Agreement, Code of Conduct, security and release policies.

### Changed
- **License: MPL-2.0** (previously GPL-3.0 in `LICENSE`, "Proprietary" in package metadata).
- Imports move to the `hvx` namespace (`from hvx.core ...`).

### Fixed
- CI: hassfest rejected uppercase selector option keys; the HACS job is skipped for private
  repositories; the MQTT test broker failed on Python 3.10; actions updated to Node 24 versions.
- Rooms below EN 16798 Category IV in a season were shown as Category IV or left out of
  "rooms needing attention"; they now rank first and count against building categories.
- "Increase ventilation" was recommended for every room with a low after-hours CO₂ decay
  rate; it now follows measured CO₂ during use.
- Overheating and scenario analyses used all hours (including empty holidays).
- Public holidays were never excluded (`holidays` calendar created without years).
- Home Assistant integration defaults to "residential" (24/7) instead of "office".
- EN 16798: rooms missing a parameter got no category; missing samples counted
  as violations; `assess_timeseries_compliance` always raised.
- Full-year reports reused the winter result for summer.
