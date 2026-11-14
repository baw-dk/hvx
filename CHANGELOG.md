# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
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
- EN 16798: rooms missing a parameter got no category; missing samples counted
  as violations; `assess_timeseries_compliance` always raised.
- Full-year reports reused the winter result for summer.
