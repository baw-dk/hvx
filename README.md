# HVX — indoor environmental quality analytics

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](LICENSE)

Assess indoor climate (temperature, CO₂, humidity) in rooms, buildings and
portfolios against **EN 16798-1**, **TAIL** and **BR18**, from CSV files or
**live data** (Home Assistant, push APIs), and report on it as HTML, JSON or CSV.
The data model is aligned with **IFC** and **Brick Schema**.

Three ways to use it:

| | For | Get started |
|---|---|---|
| **Python package** `hvx` | analysts, back-ends, notebooks | `pip install hvx` |
| **`hvx` command line** | reports from a site file or CSV folder, live status | `hvx --help` |
| **Home Assistant integration** `hvx_ieq` | homes and small buildings already in Home Assistant | install via HACS, see below |

## 📦 Install

```bash
pip install hvx                 # core: standards, reporting, live monitoring, CLI
pip install "hvx[brick,ifc]"    # + Brick RDF and IFC import/write-back
pip install "hvx[chirpstack]"   # + LoRaWAN sensors through ChirpStack
pip install "hvx[api]"          # + FastAPI backend (hvx serve)
pip install "hvx[mcp]"          # + MCP server for AI assistants (hvx mcp)
pip install "hvx[pdf]"          # + PDF reports (then: playwright install chromium)
pip install "hvx[all]"          # everything (incl. pythermalcomfort / numba)
```

The core deliberately avoids heavy native dependencies (numba, IfcOpenShell) so it
installs on Home Assistant OS (Alpine/musl) and other small hosts. EN 16798's
adaptive model uses `pythermalcomfort` when the `comfort` extra is installed and a
built-in implementation otherwise.

Package layout (`src/hvx/`): `core` (data model, IFC/Brick semantics),
`standards`, `simulations`, `reporting`, `live`, `connectors` (CSV, Climify/DMI), `app`
(FastAPI + Streamlit), `cli`.

## ⚡ Live data

HVX reads live data through **sources** and maps their points onto rooms with
**bindings** stored on the data model (`SensorDefinition.sources`), so a site
file, a Brick/IFC import and the Home Assistant integration all bind the same way.

| Source | How it gets data |
|---|---|
| `HomeAssistantSource` | pulls history and current states from Home Assistant's REST API (long-lived token) |
| `InMemorySource` | you push readings (MQTT callbacks, webhooks, BMS exports); used by the HA integration |
| `ChirpStackMQTTSource` | LoRaWAN sensors via ChirpStack's MQTT integration, with optional backfill from its gRPC API |
| `ChirpStackAPISource` | ChirpStack device metrics (`DeviceService.GetMetrics`) for history |
| ChirpStack HTTP integration | ChirpStack posts uplinks to `POST /api/integrations/chirpstack` on `hvx serve` |
| your own | subclass `TimeSeriesSource` and implement `history(points, start, end)` |

`LiveMonitor` keeps a bounded rolling window, fetches **incrementally** (only data
newer than what it holds), and produces snapshots with current values, live
checks against the EN 16798 category limits (read from the same config as the
batch assessment) and a rolling EN 16798 assessment per room.

Change-driven sources such as Home Assistant only record a value when it changes, so
HVX treats a value as valid until the next one; `unavailable` ends it. Periodic sources
treat silence as missing data.

```bash
export HA_TOKEN=...                                         # long-lived access token
hvx check  --site examples/site.example.yaml                # config + connectivity, per sensor
hvx watch  --site examples/site.example.yaml --every 300    # live status table
hvx report --site examples/site.example.yaml --days 14 -o report.html
hvx site from-ifc building.ifc -o site.yaml                 # rooms from BIM, fill in sensor ids
```

```python
from datetime import timedelta
from hvx.live import LiveMonitor, load_site

site = load_site("site.yaml")
monitor = LiveMonitor(*site.entities, sources=site.build_sources(),
                      window=timedelta(days=7), timezone=site.timezone)
monitor.refresh()                       # call periodically; incremental
snapshot = monitor.snapshot()
for room in snapshot.rooms.values():
    print(room.room_name, room.category_now, room.window.ieq_score, room.alerts)
```

### LoRaWAN through ChirpStack

`pip install "hvx[chirpstack]"`. ChirpStack decodes uplinks with each device's codec;
every numeric field becomes a point `<devEui>/<field>`, and common IEQ fields from
any vendor (`co2`, `TempC_SHT`, `Hum_SHT`, `humidity`, `light`, `tvoc`...) are also
published as `<devEui>/temperature`, `/co2`, `/humidity`, so a room binds a whole device:

```yaml
sources:
  lorawan:
    type: chirpstack-mqtt                    # or chirpstack-api, or chirpstack-http (webhook)
    host: chirpstack.local
    username: hvx
    password_env: CHIRPSTACK_MQTT_PASSWORD
    backfill: {server: chirpstack.local:8080, token_env: CHIRPSTACK_API_TOKEN}
...
rooms:
  - id: r-102
    name: Office 1.02
    devices: [{source: lorawan, dev_eui: a84041000181c061}]
```

`hvx chirpstack listen --host chirpstack.local` prints the devices and fields it
receives, with ready-to-paste `devices:` lines. For the HTTP integration, run
`hvx serve` with `HVX_WEBHOOK_TOKEN` set, load the site with `POST /api/live/site`,
and point ChirpStack at `/api/integrations/chirpstack` with the header
`Authorization: Bearer <token>` (JSON or Protobuf). `GET /api/live/snapshot` and
`POST /api/live/report` then serve live status and reports.

## 🏠 Home Assistant integration

`custom_components/hvx_ieq` turns Home Assistant **areas** into rooms and assesses them continuously.

- **Setup:** Settings → Devices & services → Add integration → *HVX Indoor Environment*.
  Areas that have temperature, CO₂ or humidity sensors are pre-selected, and the sensors
  in each are pre-filled. HA floors become building floors.
- **Per room:** IEQ score, comfort category (rolling window), current category, temperature,
  CO₂ and humidity compliance, and an *IEQ problem* binary sensor that reacts to state
  changes within seconds.
- **Per building:** IEQ score, rooms meeting target, comfort category.
- **Action** `hvx_ieq.generate_report`: writes the full HTML/JSON/CSV report to
  `/config/www/hvx_ieq/` (served at `/local/hvx_ieq/...`) and returns its path and URL.
- **Data:** history comes from the recorder; nothing leaves Home Assistant.
- **Building type** sets the assessed hours: *residential* (default) is 24/7,
  *office*/*school* use opening hours.

Install with HACS (custom repository → this repo → *Integration*), or copy
`custom_components/hvx_ieq` into your `config/custom_components/`. Home Assistant
installs the `hvx` package from PyPI on first load.

## 📑 Reporting

The `reporting` package turns a portfolio into one structured report model
(`PortfolioReport`, schema `hvx.ieq-report/2.0`) that is rendered as HTML,
JSON or CSV — the three formats are views of the same data and cannot disagree.

```python
from hvx.reporting import ReportConfig, ReportBuilder, generate_report, render

config = ReportConfig(
    seasons=("winter", "summer"),  # full year: heating/cooling months assessed separately
    target_category="II",          # EN 16798-1 target used for compliance % and the IEQ score
)
generate_report(portfolio, buildings, floors, rooms, "out/report.html", config=config)

report = ReportBuilder(config).build(portfolio, buildings, floors, rooms)
render(report, "csv")  # one row per room, with Brick class and IFC GlobalId
```

**Occupied hours.** Standards are applied "during use": by default the building
type's opening hours (schools: weekdays 07:30–16:00) minus public holidays. Set
your own hours and holiday periods, e.g. for a municipality's school calendar:

```python
from hvx.core.schedules import OccupancySchedule
ReportConfig(occupancy=OccupancySchedule(start="08:00", end="16:00",
             holiday_periods=(("2024-06-22", "2024-08-11"), ("2024-10-14", "2024-10-18"))))
```

Assessing 24/7 instead (`occupied_only=False`) lets nights and holidays dilute
the results: on a 58-classroom dataset it raised CO₂ compliance from 73% to 94%
and inflated hours above 26 °C tenfold (empty, sun-heated summer holidays).

**Languages and PDF.** `ReportConfig(language="da")` renders the whole report in
Danish (Danish number formats, translated recommendations); add a client
`introduction` and method `notes`. Write `report.pdf` as well as `.html` with
`pip install "hvx[pdf]"` and `playwright install chromium` (or point
`HVX_CHROMIUM_PATH` at an existing Chromium):

```bash
hvx report --csv data/ --lang da -o rapport.html -o rapport.pdf
```

What the report contains: KPIs, key findings, category distribution, IEQ-score
histogram, priority actions merged across rooms, a building table, detailed
cards for the rooms furthest from target, a sortable/filterable table of all
rooms, data-coverage notes and a method section.

Design for scale:

- **Parallel** — rooms are analysed independently in a process pool
  (`max_workers`, `parallel_backend`); ~3.7× faster on 4 cores for 200 rooms.
- **Side-effect free** — input entities are never modified; standards run on private copies.
- **Fault-isolated** — a room that fails or has no data is reported as such; the rest of the report still builds.
- **Readable at any size** — distributions and per-building rows instead of one bar per room; HTML is self-contained (no CDN) and autoescaped.
- **Consistent numbers** — compliance % comes from the same EN 16798-1 run as the category, per season.

API: `POST /api/reports` with `{"format": "html" | "json" | "csv", "seasons": [...], "target_category": "II"}`.

Branding: reports are white-label by default; `--brand baw` / `ReportConfig(branding=...)`
adds a logo, accent colour and company details incl. CVR number (`src/hvx/reporting/brands/`).

The old `hvx.simulations.models.reporting.HTMLReportService` still works and now delegates to this pipeline.

### 🤖 Building reports with an AI assistant (MCP)

`hvx mcp` runs a [Model Context Protocol](https://modelcontextprotocol.io) server, so an
assistant such as Claude can load data, build reports and export them on request:

```bash
pip install "hvx[mcp,pdf]"
claude mcp add hvx -- hvx mcp                  # Claude Code
```

For Claude Desktop, add to `claude_desktop_config.json`:

```json
{"mcpServers": {"hvx": {"command": "hvx", "args": ["mcp"], "env": {"HVX_MCP_ROOT": "/path/to/projects"}}}}
```

| Tool | Does |
|---|---|
| `load_csv_folder`, `load_climify_export`, `load_site` | Load data (hvx CSV layout, Climify + DMI exports, live site YAML) |
| `describe_data` | Buildings, rooms, parameters, period, missing climate data |
| `build_report` | Language, seasons, target, occupied hours, holidays, branding → key figures |
| `report_details` | Buildings, priority actions, rooms needing attention, one room |
| `export_report` | HTML, PDF, JSON or CSV, branded or white-label |
| `list_brands` | Built-in brands and whether their details are filled in |

The `ieq_report` prompt walks through the whole flow. Tools run with your file
permissions; `HVX_MCP_ROOT` confines all paths to one folder, and existing files are
only overwritten when asked.

## 🧱 Semantic data model (IFC + Brick)

Spatial entities carry their IFC/Brick identity and IEQ requirements:

| HVX | IFC 4 | Brick 1.4 |
|-----|-------|-----------|
| Portfolio | – | `brick:Portfolio` |
| Building | `IfcBuilding` | `brick:Building` |
| Floor | `IfcBuildingStorey` | `brick:Floor` |
| Room | `IfcSpace` | `brick:Room` subclass by usage (e.g. `brick:Conference_Room`) |
| Zone | `IfcZone` | `brick:Zone` |
| Sensor (temperature, CO₂, RH, lux, noise…) | `IfcSensor` + `IfcSensorTypeEnum` | `brick:*_Sensor` + QUDT unit |
| `IEQRequirements` | `Pset_SpaceThermalRequirements`, `Pset_SpaceLightingRequirements`, `Pset_SpaceOccupancyRequirements`, `HVX_Pset_SpaceIEQRequirements` | `ieq:IEQRequirement` |
| `IEQAssessment` | `HVX_Pset_IEQAssessment` | `ieq:IEQAssessment` |

New fields on every `SpatialEntity`: `ifc_guid`, `brick_class` (optional
override), `ieq_requirements`; plus `ifc_class` and `semantic_brick_class()`.

**IEQ extension.** Brick has no notion of requirements, assessments or comfort
categories, and lacks some IEQ-relevant classes. `src/hvx/core/semantics/ontology/hvx_ieq.ttl`
adds them (`ieq:Classroom`, `ieq:Patient_Room`, `ieq:Sound_Pressure_Level_Sensor`,
`ieq:IEQAssessment`, `ieq:Category_I…IV`, …) as subclasses of Brick classes, so
plain Brick tools still understand the data. Links to IFC and time series use
Brick's own `ref:IFCReference` / `ref:TimeseriesReference`.

```python
from hvx.core.semantics.brick import export_brick, import_brick
from hvx.core.semantics.ifc import load_ifc, write_ieq_to_ifc   # pip install 'hvx[ifc]'

ttl = export_brick(portfolio, buildings, floors, rooms, "out/model.ttl")
model = load_ifc("building.ifc")              # IfcSpace → Room, GUIDs kept
write_ieq_to_ifc("building.ifc", model.rooms, assessments, output_path="building_ieq.ifc")
```

API: `GET /api/semantics/brick`, `POST /api/semantics/brick/import`, `POST /api/semantics/ifc/import`.

All mappings are checked in the tests against the official Brick 1.4 ontology
and the IFC4 schema.

## 🧪 Tests

```bash
pip install -e ".[dev]"
pytest -q                                   # library: standards, reporting, live, IFC/Brick, CLI, API

pip install pytest-homeassistant-custom-component -e .
cd tests_ha && pytest -q                    # Home Assistant integration in a real HA instance
```

CI (`.github/workflows/tests.yml`) runs the library tests on Python 3.10–3.13, the
Home Assistant tests, `hassfest` and HACS validation.

## 🚀 Releasing

Tagging `v*` runs `.github/workflows/release.yml`, which builds the sdist and wheel and uploads them to PyPI
(needs the `PYPI_API_TOKEN` secret). Keep `version` in `pyproject.toml`,
`custom_components/hvx_ieq/manifest.json` (`version` and the `hvx==` requirement) in step.

## 🎯 Features

### 1. EN 16798-1 Standard Module (`src/hvx/standards/en16798/analysis.py`)

Complete implementation of EN 16798-1 indoor environmental input parameters:

- **Temperature thresholds**: Fixed (heating/cooling seasons) and adaptive comfort model
- **CO2 limits**: Category-based concentration thresholds
- **Humidity thresholds**: Relative humidity ranges for each category
- **Ventilation requirements**: Required ventilation rates based on occupancy and building pollution
- **Compliance assessment**: Instant values and time series analysis
- **Category determination**: each parameter reaches the best category whose limits it meets in
  at least 95 % of its measured occupied hours (`assessment.pass_share`); the room takes its
  worst parameter. Relative humidity counts only for rooms with `humidity_controlled: true`.

**Categories**: I (High), II (Normal), III (Moderate), IV (everything outside III)

### 2. TAIL Standard Module (`src/hvx/standards/tail/calculator.py`)

TAIL rating (Wargocki et al. 2021, doi:10.1016/j.enbuild.2021.111029), following the
authors' reference script `tail.R` ([TAILRatingScheme](https://github.com/asitkm76/TAILRatingScheme),
commit c71b8b5). All thresholds live in `src/hvx/standards/tail/config.yaml`, with the
script's line numbers.

- **Labels I–IV** (Green, Yellow, Orange, Red) per parameter; a domain (Thermal, Acoustic,
  Indoor air, Luminous) takes its worst parameter and the overall rating its worst domain.
  Unmeasured parameters stay out.
- **Temperature** (Thermal) and **relative humidity** (Indoor air): each occupied sample is
  coloured, the label follows from the time shares. Temperature bands depend on each sample's
  month (heating season October–May: Green 21–23 °C; June–September: Green 23.5–25.5 °C).
  tail.R's share rule has gaps (e.g. 99.5 % Green + 0.5 % Red rates IV); hvx reads it
  cumulatively: I if Green ≥ 94 %, Orange ≤ 1 % and Red = 0; otherwise II if Orange ≤ 5 % and
  Red ≤ 1 %; otherwise III if Red ≤ 5 %; otherwise IV. Shares count samples with a value.
- **CO₂**: 95th percentile, Green ≤ outdoor + 550 ppm (970 ppm with the default 420 ppm outdoor).
- **PM2.5, formaldehyde, benzene, radon**: any Red sample IV, any Yellow II, else I.
- **Noise**: 5th percentile by room type (small office, open office, hotel room); **illuminance**:
  share of time within 300–500 lx (offices) or ≥ 100 lx (hotels); **daylight factor**,
  **ventilation** (from persons and floor area) and **mould** (visible area): worst value.
- **PM10 and VOC** are not TAIL parameters: rated as hvx extensions, outside the domains.
- **Building types.** Three profiles (`profiles` in the config), picked from the building type:

  | | Offices | Hotels | Schools |
  |---|---|---|---|
  | Source | TAIL paper, tail.R | TAIL paper, tail.R | TAIL for schools (M.-T. Tran, PhD thesis, IMT Atlantique 2024) |
  | Assessed hours | Mon–Fri 09–17 | every night 22–06 | Mon–Fri 08–17 |
  | Noise (P5) | small office 30/35/40, open office 35/40/45 dB(A) | 25/30/35 dB(A) | classroom 30/34/38 dB(A) |
  | Added parameters | – | – | reverberation time (by classroom volume), NO₂ |
  | CO₂ | P95 | P95 | time shares (≥ 94 %) |
  | PM2.5 | < 10 / < 25 µg/m³ | < 10 / < 25 µg/m³ | < 5 / < 15 µg/m³ (WHO 2021) |
  | Illuminance | share of time 300–500 lx | share of night ≥ 100 lx | ≥ 500 / 300 / 200 lx (time shares) |
  | Building rating | mean of the rooms' parameter ratings (paper Eq. 1) | same | mean of the classrooms' domain ratings |

- **No mechanical cooling** (`mechanical_cooling: false` and outdoor temperature): outside the
  heating season the temperature bands follow the adaptive model of the TAIL paper (Table 2),
  0.33·θrm + 18.8 °C with Green −3/+2, Yellow −4/+3, Orange −5/+4 K.
- In reports TAIL runs per room on the occupied hours the report selected (no second
  opening-hours filter); buildings and portfolios are rated from their rooms with the profile's rule.
- **TAIL label from one CSV**: `hvx.tail_label.label_from_csv(text, building_type="school")`
  (light enough to run in the browser; used by the web app in `web/`).

### 3. Ventilation Simulation Model (`src/hvx/simulations/models/ventilation/model.py`)

After-hours air change rate from CO2 decays (tracer-gas decay, cf. ASTM E741 / D6245):

- **Log-linear fit** of the excess over a per-room background CO2, free intercept, peak sample dropped
- **Unoccupied time only** (no CO2 source during the decay); decays too fast for the sampling
  interval are skipped and the fastest resolvable rate is reported
- **Median and interquartile range** over the decays; no quality rating
- Describes the empty room (ventilation may be reduced or off), **not ventilation during use**

Recommendations (`simulations/models/recommendations`) fire on measured occupied time against
published limits (1000 ppm, the target category's EN 16798-1 ranges, BR18 26 °C guidance);
effects are given only as stated estimates (airflow factor from steady state, hours above 26 °C
avoided from a solar regression controlled for outdoor temperature).

### 4. Occupancy Simulation Model (`src/hvx/simulations/models/occupancy/model.py`) — not validated, not used in reports

Detect occupancy patterns from CO2 data:

- **Pattern detection**: Identify occupied vs unoccupied periods
- **Occupancy rate**: Fraction of time occupied
- **Typical hours**: When space is typically occupied
- **Occupant estimation**: Estimate number of occupants from CO2 levels
- **CO2 mass balance**: Physics-based occupant count estimation

### 5. RC Thermal Simulation (`src/hvx/simulations/models/rc_thermal/model.py`) — experimental

Not used in reports and not validated: 2R2C/3R3C currently run the 1R1C model and there is no
ventilation heat-loss term. The API endpoint returns 501 until it is reworked.

### 6. Real EPC Simulation (`src/hvx/simulations/models/real_epc/model.py`) — experimental

Convert delivered energy intensity to an operational EPC rating:

- **Config-backed thresholds**: Loads EU member state limits from YAML (`hvx/core/config/data/standards/epc_thresholds.yaml` — **not yet included in the repository**, so EPC calculation currently raises)
- **Country resolution**: Supports ISO country codes and fallbacks to EU defaults
- **Simple helper**: `calculate_epc_rating(primary_energy_kwh_m2, country_code)` returns EPC label + input intensity
- **Data alignment**: Intended for *real* EPC snapshots computed from measured energy; theoretical EPC remains a `Building` metadata property per the data model

Building thermal dynamics simulation:

- **Model types**: 1R1C, 2R2C, 3R3C resistance-capacitance models
- **Temperature prediction**: Indoor temperature based on outdoor conditions
- **HVAC loads**: Heating and cooling power requirements
- **Solar gains**: Window solar heat gain calculation
- **Parameter estimation**: Auto-estimate from building properties
- **Thermal metrics**: U-value, time constant

## ⚙️ Simulation Model Catalog

Each telemetry-driven simulation model now exposes a machine-readable configuration describing:

- **Requirements** – mandatory sensors/metadata (`co2`, `volume_m3`, `primary_energy_kwh_m2`, etc.)
- **Applicability** – supported `building_type`, `room_type`, and spatial levels (room, floor, building, portfolio)
- **Dependencies** – prerequisite models (e.g., RC thermal can optionally consume occupancy / ventilation)
- **Outputs & aggregation** – key metrics plus roll-up strategy (metric id + aggregation type & weights)

Configs live alongside each model under `src/hvx/simulations/models/<model>/config.yaml` and can be queried programmatically:

```python
from hvx.simulations.config import applicable_models_for_entity

applicable = applicable_models_for_entity(
    entity=my_room,
    available_parameters=["co2", "outdoor_temperature"],
)
```

The helper returns all models that can run directly on the entity or via child roll-ups so orchestration layers can select the right simulations automatically.

## 📚 References

- EN 16798-1: Energy performance of buildings - Indoor environmental input parameters
- TAIL rating scheme: Wargocki et al. (2021), Energy & Buildings 244, 111029; reference script
  https://github.com/asitkm76/TAILRatingScheme
- pythermalcomfort: https://github.com/CenterForTheBuiltEnvironment/pythermalcomfort

## 🤝 Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Contributors sign
the [Contributor License Agreement](CLA.md) once, by commenting on their first pull
request ([why](docs/contributing/cla.md)), and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Security issues: [SECURITY.md](SECURITY.md).

## 📄 License

[MPL-2.0](LICENSE): use, modify and redistribute, including in proprietary
products. Files you modify must stay under MPL-2.0 and their source must be made
available; your own separate files can use any license. Source files carry the
notice described in [LICENSE_HEADER.md](LICENSE_HEADER.md).

Under the [CLA](CLA.md), the maintainer can also offer HVX under other terms (for
example a commercial license) while every contribution stays available under
MPL-2.0.

