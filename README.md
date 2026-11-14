# Refactored Building Analytics Service

A comprehensive, scalable service for building portfolio analytics that consolidates all calculation standards and special analyses into a unified architecture.

## 🏗️ Architecture

The refactored service follows a modular architecture with explicit separation between
standards compliance modules and telemetry-driven simulation models:

```
refactored_service/
├── standards/            # Standards-backed assessments
│   ├── en16798/
│   │   └── analysis.py            # EN 16798-1 standard
│   └── tail/
│       ├── calculator.py          # TAIL scoring logic
│       └── analysis.py            # Compliance orchestration
├── simulations/          # Telemetry-driven simulation models
│   └── models/
│       ├── occupancy.py           # Occupancy inference
│       ├── ventilation.py         # Ventilation rate estimation
│       ├── rc_thermal.py          # RC thermal modeling
│       └── real_epc.py            # EPC rating estimation
├── engine/              # Unified analysis orchestration
│   └── analysis_engine.py         # Main analysis engine
├── core/                # Data models
│   └── models/
├── examples/            # Usage examples
│   └── portfolio_analysis_example.py
└── README.md
```

## 🎯 Features

### 1. EN 16798-1 Standard Module (`standards/en16798/analysis.py`)

Complete implementation of EN 16798-1 indoor environmental input parameters:

- **Temperature thresholds**: Fixed (heating/cooling seasons) and adaptive comfort model
- **CO2 limits**: Category-based concentration thresholds
- **Humidity thresholds**: Relative humidity ranges for each category
- **Ventilation requirements**: Required ventilation rates based on occupancy and building pollution
- **Compliance assessment**: Instant values and time series analysis
- **Category determination**: Automatic category achievement based on measurements

**Categories**: I (High), II (Normal), III (Moderate), IV (Low)

### 2. TAIL Standard Module (`standards/tail/calculator.py`)

TAIL rating scheme for comprehensive indoor environmental quality:

- **Four categories**: Thermal, Acoustic, Indoor Air Quality (IAQ), Luminous
- **Rating scale**: I (Excellent ≥95%), II (Good 70-95%), III (Fair 50-70%), IV (Poor <50%)
- **Parameter classification**: Automatic categorization of parameters
- **Time series analysis**: Compliance over time
- **Aggregation**: Portfolio-level aggregation with "worst" or "average" methods

### 3. Ventilation Simulation Model (`simulations/models/ventilation/model.py`)

Estimate ventilation rates from CO2 decay analysis:

- **CO2 decay analysis**: Exponential decay curve fitting
- **ACH estimation**: Air changes per hour
- **Quality categories**: Excellent (≥6 ACH), Good (≥4), Fair (≥2), Poor (<2)
- **Confidence metrics**: R² goodness of fit and confidence intervals
- **Multiple period averaging**: Weighted by fit quality

### 4. Occupancy Simulation Model (`simulations/models/occupancy/model.py`)

Detect occupancy patterns from CO2 data:

- **Pattern detection**: Identify occupied vs unoccupied periods
- **Occupancy rate**: Fraction of time occupied
- **Typical hours**: When space is typically occupied
- **Occupant estimation**: Estimate number of occupants from CO2 levels
- **CO2 mass balance**: Physics-based occupant count estimation

### 5. RC Thermal Simulation (`simulations/models/rc_thermal/model.py`)

### 6. Real EPC Simulation (`simulations/models/real_epc/model.py`)

Convert delivered energy intensity to an operational EPC rating:

- **Config-backed thresholds**: Loads EU member state limits from YAML (`core/config/standards/epc_thresholds.yaml`)
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

Configs live alongside each model under `simulations/models/<model>/config.yaml` and can be queried programmatically:

```python
from simulations.config import applicable_models_for_entity

applicable = applicable_models_for_entity(
    entity=my_room,
    available_parameters=["co2", "outdoor_temperature"],
)
```

The helper returns all models that can run directly on the entity or via child roll-ups so orchestration layers can select the right simulations automatically.

## 🚀 Unified Analysis Engine

The `AnalysisEngine` orchestrates all calculations across a building portfolio:

```python
from refactored_service.engine import AnalysisEngine, AnalysisConfig
from refactored_service.engine.analysis_engine import SpaceData, AnalysisType

# Configure analysis
config = AnalysisConfig(
    analyses_to_run=[
        AnalysisType.EN16798,
        AnalysisType.TAIL,
        AnalysisType.VENTILATION,
        AnalysisType.OCCUPANCY,
    ],
    season="heating",
)

# Create engine
engine = AnalysisEngine(config)

# Analyze single space
space = SpaceData(
    id="room_1",
    name="Office 101",
    type="room",
    area_m2=25.0,
    volume_m3=75.0,
    temperature=temperature_series,
    co2=co2_series,
    humidity=humidity_series,
)

result = engine.analyze_space(space)

# Analyze portfolio
spaces = [...]  # List of SpaceData
portfolio_result = engine.analyze_portfolio(
    spaces=spaces,
    portfolio_id="my_portfolio",
    portfolio_name="My Building Portfolio"
)
```

## 📊 Example: Portfolio Analysis

See `examples/portfolio_analysis_example.py` for a complete example with:

- 3 buildings (Office, School, Retail)
- 2 floors per building
- 3-5 rooms per floor
- Generated environmental data (temperature, CO2, humidity)
- Complete analysis pipeline
- Portfolio-level aggregation

Run the example:

```bash
cd refactored_service/examples
python portfolio_analysis_example.py
```

## 📑 Reporting

The `reporting` package turns a portfolio into one structured report model
(`PortfolioReport`, schema `hvx.ieq-report/2.0`) that is rendered as HTML,
JSON or CSV — the three formats are views of the same data and cannot disagree.

```python
from reporting import ReportConfig, ReportBuilder, generate_report, render

config = ReportConfig(
    seasons=("winter", "summer"),  # full year: heating/cooling months assessed separately
    target_category="II",          # EN 16798-1 target used for compliance % and the IEQ score
)
generate_report(portfolio, buildings, floors, rooms, "out/report.html", config=config)

report = ReportBuilder(config).build(portfolio, buildings, floors, rooms)
render(report, "csv")  # one row per room, with Brick class and IFC GlobalId
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

The old `simulations.models.reporting.HTMLReportService` still works and now delegates to this pipeline.

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
categories, and lacks some IEQ-relevant classes. `core/semantics/ontology/hvx_ieq.ttl`
adds them (`ieq:Classroom`, `ieq:Patient_Room`, `ieq:Sound_Pressure_Level_Sensor`,
`ieq:IEQAssessment`, `ieq:Category_I…IV`, …) as subclasses of Brick classes, so
plain Brick tools still understand the data. Links to IFC and time series use
Brick's own `ref:IFCReference` / `ref:TimeseriesReference`.

```python
from core.semantics.brick import export_brick, import_brick
from core.semantics.ifc import load_ifc, write_ieq_to_ifc   # pip install "hvx[ifc]"

ttl = export_brick(portfolio, buildings, floors, rooms, "out/model.ttl")
model = load_ifc("building.ifc")              # IfcSpace → Room, GUIDs kept
write_ieq_to_ifc("building.ifc", model.rooms, assessments, output_path="building_ieq.ifc")
```

API: `GET /api/semantics/brick`, `POST /api/semantics/brick/import`, `POST /api/semantics/ifc/import`.

All mappings are checked in the tests against the official Brick 1.4 ontology
and the IFC4 schema.

## 🧪 Tests

```bash
pip install -e ".[dev,api]"
pytest -q
```

## 🎨 Key Design Principles

### 1. **Scalability**
- Modular standards/simulation design
- Independent modules that can be used standalone
- Hierarchical aggregation (room → floor → building → portfolio)

### 2. **Configurability**
- Config-driven analysis
- Flexible thresholds and parameters
- Optional analyses (run only what you need)

### 3. **Type Safety**
- Dataclasses for structured data
- Enums for categorical values
- Type hints throughout

### 4. **Extensibility**
- Easy to add new standards or simulation models
- Pluggable into analysis engine
- Standard interfaces

## 📈 Comparison: Core vs Refactored

| Aspect | Core (Legacy) | Refactored Service |
|--------|--------------|-------------------|
| **Size** | 1.2MB, 150+ files | Focused, ~20 key files |
| **Approach** | Object-oriented entities | Standards + simulation services |
| **Data** | pandas in entities | Separate data models |
| **Self-analysis** | Entities compute metrics | External standards/sim modules |
| **Standards** | Hardcoded | Modular standard modules |
| **Scalability** | Limited | Portfolio-scale ready |
| **Testing** | Entity-centric | Calculator-centric |

## 🔧 Technical Details

### Dependencies

```
pandas
numpy
scipy
pythermalcomfort (optional, for EN 16798 adaptive comfort)
```

### Data Flow

```
SpaceData (input)
    ↓
AnalysisEngine
    ↓
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  EN 16798   │    TAIL     │ Ventilation │  Occupancy  │
│ Calculator  │ Calculator  │ Calculator  │ Calculator  │
└─────────────┴─────────────┴─────────────┴─────────────┘
    ↓
SpaceAnalysisResult
    ↓
Portfolio Aggregation
    ↓
PortfolioAnalysisResult (output)
```

### Performance

- Designed for portfolio-scale analysis (1000+ rooms)
- Efficient time series operations using pandas
- Parallel-ready architecture (spaces can be analyzed independently)

## 📝 Usage Patterns

### Pattern 1: Single Room Analysis

```python
from refactored_service.standards.en16798.analysis import EN16798Calculator

calculator = EN16798Calculator()
result = calculator.assess_timeseries_compliance(
    temperature=temp_series,
    co2=co2_series,
    season="heating"
)
```

### Pattern 2: Portfolio Analysis

```python
from refactored_service.engine import AnalysisEngine

engine = AnalysisEngine()
result = engine.analyze_portfolio(spaces)
```

### Pattern 3: Custom Analysis

```python
from refactored_service.simulations import VentilationCalculator, OccupancyCalculator

# Estimate ventilation
vent_calc = VentilationCalculator()
vent_result = vent_calc.estimate_from_co2_decay(co2_series, volume_m3)

# Detect occupancy
occ_calc = OccupancyCalculator()
occ_pattern = occ_calc.detect_occupancy(co2_series)
```

## 🎯 Future Enhancements

- [ ] Add more standards (ASHRAE, WELL, etc.)
- [ ] Parallel processing for portfolio analysis
- [ ] Real-time streaming analysis
- [ ] Machine learning-based anomaly detection
- [ ] Cost optimization recommendations
- [ ] Integration with BMS/SCADA systems

## 📚 References

- EN 16798-1: Energy performance of buildings - Indoor environmental input parameters
- TAIL Rating Scheme: ALDREN project
- pythermalcomfort: https://github.com/CenterForTheBuiltEnvironment/pythermalcomfort

## 🤝 Contributing

This refactored service is designed to be maintainable and extensible. To add a new standard module or simulation model:

1. Create a new file under `standards/` (for rule-backed analyses) or `simulations/models/` (for physics/ML simulations)
2. Implement the calculation logic
3. Register it inside `engine/analysis_engine.py`
4. Update `AnalysisType` enum
5. Add tests and examples

---

**Built with ❤️ for scalable building analytics**
