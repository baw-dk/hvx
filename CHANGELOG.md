# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.4.0] - 2026-11-14

### Added
- `hvx.connectors.dmi` and `hvx dmi stations|fetch`: DMI open-data climate data (quality-controlled
  hourly station values, no API key) in the file format buildings use as `climate_file`.
- EN 16798-1 adaptive model for buildings without mechanical cooling
  (`ReportConfig(mechanical_cooling=False)` or building metadata `mechanical_cooling: false`):
  outside the heating season temperature limits follow the running mean of daily outdoor
  temperature (computed from all hours, not the assessed slice). Seasons show "(adaptive)".

### Fixed
- Adaptive limits used a symmetric ±2/3/4 K band without pythermalcomfort; now EN 16798-1's
  −3/−4/−5 and +2/+3/+4 K around 0.33·θrm + 18.8 °C with its validity ranges, vectorised.
Found by an audit against EN 16798-1, BR18, the TAIL reference implementation and the
tracer-gas decay literature, with synthetic data of known answer and real school data.

- **EN 16798-1**: a parameter reaches a category when it is within the limits in 95 % of its
  measured occupied hours (was 80-90 %, taken from rule tolerances); parameters are rated on
  their own and the room takes the worst; missing values no longer count as compliant;
  Category IV is everything outside III (no invented IV limits, no "below IV"); relative
  humidity counts only for humidity-controlled rooms; running-mean weighting; timestamps
  with a UTC offset are read in local time.
- **TAIL** now follows the authors' reference script (tail.R, Wargocki et al. 2021): temperature and
  RH are rated by time shares instead of the worst sample (tail.R's share rule read cumulatively
  to close its gaps), temperature bands are chosen per sample by month (heating October–May), and
  RH, CO₂ (P95, outdoor 420 ppm configurable), PM2.5, formaldehyde, benzene, radon, noise (P5 by
  room type), illuminance, daylight factor, ventilation (from persons and floor area; not rated
  without them) and mould use the script's thresholds, now kept in `standards/tail/config.yaml`.
  PM10 and VOC are reported as hvx extensions outside the TAIL rating. Reports no longer apply
  opening hours a second time inside TAIL, timezone-aware timestamps are rated in local time
  instead of UTC, and the group "typical room" is labelled as an hvx summary, not a TAIL
  building rating.
- **BR18**: checked once over all occupied hours (each season had its own 100 h allowance);
  hours from sample durations; § 447 and the 26/27 °C hours are labelled as indicators.
- **After-hours air change** from CO₂ decay: log-linear fit with a per-room background,
  unoccupied time only, fast decays no longer underestimated (5 h⁻¹ read as 3.9), median and
  interquartile range, no unsourced quality bands.
- **Recommendations** rebuilt on measured evidence: CO₂ above 1000 ppm, temperatures outside
  the target range per season, hours above 26 °C, humidity. Removed rules that the data
  could not support (envelope from a correlation sign, winter "overheating" above 23 °C,
  summer "undercooling", kWh solar figures from a default window area, +1 ACH what-if on the
  after-hours rate, fixed −1.5 °C shading effect). Effects are stated estimates; priority
  actions show the range over the rooms instead of one room's text.
- RC thermal and operational EPC API endpoints return 501 (they could not work).

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

### Fixed (earlier in this release)
- CI: hassfest rejected uppercase selector option keys; the HACS job is skipped for private
  repositories; the MQTT test broker failed on Python 3.10; actions updated to Node 24 versions.
- Overheating and scenario analyses used all hours (including empty holidays).
- Public holidays were never excluded (`holidays` calendar created without years).
- Home Assistant integration defaults to "residential" (24/7) instead of "office".
- EN 16798: rooms missing a parameter got no category; missing samples counted
  as violations; `assess_timeseries_compliance` always raised.
- Full-year reports reused the winter result for summer.
