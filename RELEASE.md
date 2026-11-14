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
5. `.github/workflows/release.yml` builds the sdist and wheel and publishes them
   to PyPI (repository secret `PYPI_API_TOKEN`).
6. Create a GitHub release for the tag with the changelog section. HACS offers
   the integration update from GitHub releases; Home Assistant then installs the
   matching `hvx` version from PyPI.

Versioning follows [SemVer](https://semver.org): breaking API or data-model
changes bump the major version (minor while below 1.0).
