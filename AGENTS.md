# Notes for coding agents

Read [CONTRIBUTING.md](CONTRIBUTING.md) first; everything there applies.

- **Layout:** library in `src/hvx/` (import as `hvx.*`), Home Assistant integration in
  `custom_components/hvx_ieq/`, tests in `tests/` (library) and `tests_ha/` (needs
  `pytest-homeassistant-custom-component`, run from `tests_ha/`).
- **Before finishing:** `pytest -q`, `python scripts/license_headers.py --check`,
  `python scripts/check_versions.py`; run `tests_ha` when touching the integration
  or `hvx.live`.
- **Every new source file** starts with the MPL-2.0 notice ([LICENSE_HEADER.md](LICENSE_HEADER.md)).
- **Never** edit version numbers by hand (see [RELEASE.md](RELEASE.md)); add a line
  under *Unreleased* in `CHANGELOG.md` for user-visible changes.
- **Dependencies:** the core must keep installing on Home Assistant OS (musl). New
  heavy or native dependencies go into an extra in `pyproject.toml` and are imported
  lazily with an error message naming the extra.
- **Standards:** thresholds come from `src/hvx/standards/*/config.yaml`. Missing
  samples are "not measured", never violations. Add a regression test in
  `tests/test_standards_en16798.py` for any assessment change.
- **External systems** (Home Assistant, ChirpStack, IFC, Brick): match their real
  schemas — the tests build payloads with the official libraries (`chirpstack_api`
  protobufs, IfcOpenShell, the Brick 1.4 ontology); do the same for new code.
- **Data:** synthetic only in tests and examples. No client, building or personal
  identifiers, no tokens, in code, commits or pull request text.
- **Attribution:** AI assistants credited in `Co-authored-by` lines do not sign the
  CLA; the human submitting the pull request does and is responsible for the work.
