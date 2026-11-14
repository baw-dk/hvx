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

The old `hvx.simulations.models.reporting.HTMLReportService` still works and now delegates to this pipeline.

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
- **Category determination**: Automatic category achievement based on measurements

**Categories**: I (High), II (Normal), III (Moderate), IV (Low)

### 2. TAIL Standard Module (`src/hvx/standards/tail/calculator.py`)

TAIL rating scheme for comprehensive indoor environmental quality:

- **Four categories**: Thermal, Acoustic, Indoor Air Quality (IAQ), Luminous
- **Rating scale**: I (Excellent ≥95%), II (Good 70-95%), III (Fair 50-70%), IV (Poor <50%)
- **Parameter classification**: Automatic categorization of parameters
- **Time series analysis**: Compliance over time
- **Aggregation**: Portfolio-level aggregation with "worst" or "average" methods

### 3. Ventilation Simulation Model (`src/hvx/simulations/models/ventilation/model.py`)

Estimate ventilation rates from CO2 decay analysis:

- **CO2 decay analysis**: Exponential decay curve fitting
- **ACH estimation**: Air changes per hour
- **Quality categories**: Excellent (≥6 ACH), Good (≥4), Fair (≥2), Poor (<2)
- **Confidence metrics**: R² goodness of fit and confidence intervals
- **Multiple period averaging**: Weighted by fit quality

### 4. Occupancy Simulation Model (`src/hvx/simulations/models/occupancy/model.py`)

Detect occupancy patterns from CO2 data:

- **Pattern detection**: Identify occupied vs unoccupied periods
- **Occupancy rate**: Fraction of time occupied
- **Typical hours**: When space is typically occupied
- **Occupant estimation**: Estimate number of occupants from CO2 levels
- **CO2 mass balance**: Physics-based occupant count estimation

### 5. RC Thermal Simulation (`src/hvx/simulations/models/rc_thermal/model.py`)

### 6. Real EPC Simulation (`src/hvx/simulations/models/real_epc/model.py`)

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
- TAIL Rating Scheme: ALDREN project
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

