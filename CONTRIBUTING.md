# Contributing to HVX

Thanks for helping! This guide covers what a pull request needs.

## Before you start

- **CLA.** Contributions need a signed [HVX Contributor License Agreement](CLA.md);
  you sign once, by commenting on your first pull request. It is a license, not a
  copyright transfer: you keep ownership. Why we ask: [docs/contributing/cla.md](docs/contributing/cla.md).
- **License.** Your contributions are licensed under the repository license,
  [MPL-2.0](LICENSE). New source files carry the MPL notice, see [LICENSE_HEADER.md](LICENSE_HEADER.md).
- **Conduct.** By contributing you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
- **Security issues** go through [SECURITY.md](SECURITY.md), not public issues.
- For larger changes, open an issue first so we can agree on the approach.

## Development setup

```bash
git clone https://github.com/Koto-Labs/hvx && cd hvx
python -m venv .venv && . .venv/bin/activate     # Python 3.10–3.13
pip install -e ".[dev]"
pytest -q                                         # library tests
```

The Home Assistant integration is tested against a real Home Assistant core,
in its own environment (Python 3.13):

```bash
python -m venv .venv-ha && . .venv-ha/bin/activate
pip install pytest-homeassistant-custom-component -e .
cd tests_ha && pytest -q
```

The flow editor (`flow-editor/`, Next.js) uses `npm install && npm run dev`.

## Repository layout

| Path | What |
|---|---|
| `src/hvx/` | the `hvx` Python package (published to PyPI) |
| `custom_components/hvx_ieq/` | Home Assistant integration (HACS) |
| `tests/`, `tests_ha/` | library tests, Home Assistant tests |
| `flow-editor/` | web UI for building portfolios |
| `examples/` | example scripts and site files |
| `scripts/` | repository tooling (license headers, version checks) |

## Pull requests

- Branch from `main`; keep one focused change per pull request.
- Add or update tests. Bugs get a regression test that fails without the fix.
- Run before pushing:

  ```bash
  pytest -q
  python scripts/license_headers.py --check
  python scripts/check_versions.py
  ```

- User-visible changes get a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
  Do not change version numbers; that happens at release time ([RELEASE.md](RELEASE.md)).
- Keep client, building and personal identifiers (names, addresses, sensor ids,
  tokens) out of code, test data, commit messages and pull request text. Use
  synthetic data in tests.
- Third-party code keeps its own license notice; say in the pull request where it
  comes from and under which license (CLA §4.4).

## Conventions

- Python: type hints, `from __future__ import annotations`, `logging` not `print`
  in library code, no new hard dependencies without discussion (the core must keep
  installing on Home Assistant OS; heavy features go into extras).
- Standards logic lives in `src/hvx/standards/<standard>/` with its `config.yaml`;
  thresholds come from config, not literals spread through code.
- Reports, the Home Assistant entities and the API all read from the same models
  (`hvx.reporting.PortfolioReport`, `hvx.live.LiveSnapshot`): add fields there,
  not in one renderer.
