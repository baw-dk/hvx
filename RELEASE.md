# Releasing

One version number covers the `hvx` package and the Home Assistant integration.
It appears in three places, kept in step by `scripts/check_versions.py` (CI):

- `pyproject.toml` → `version`
- `custom_components/hvx_ieq/manifest.json` → `version`
- `custom_components/hvx_ieq/manifest.json` → `requirements: ["hvx==<version>"]`

## Steps

1. Update `CHANGELOG.md`: move **Unreleased** entries under a new heading
   `## [X.Y.Z] - YYYY-MM-DD`.
2. Set the version: `python scripts/check_versions.py --set X.Y.Z`.
3. Open a release pull request; CI must be green (tests, Home Assistant tests,
   hassfest, HACS, license headers, versions).
4. After merge, tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
5. `.github/workflows/release.yml` checks that the tag matches the version, builds
   the sdist and wheel and publishes them to PyPI with **trusted publishing** (no
   stored token), then creates the GitHub release with the files attached.

   One-time setup: on pypi.org, *Your account → Publishing → Add a new pending
   publisher*: project `hvx`, owner `baw-dk`, repository `hvx`, workflow
   `release.yml`, environment `pypi`. On GitHub, *Settings → Environments → New
   environment* `pypi` (optionally require a reviewer, so every upload needs a click).
6. Paste the changelog section into the GitHub release notes. HACS offers
   the integration update from GitHub releases; Home Assistant then installs the
   matching `hvx` version from PyPI.

Versioning follows [SemVer](https://semver.org): breaking API or data-model
changes bump the major version (minor while below 1.0).
