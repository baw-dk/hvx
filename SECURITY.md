# Security policy

## Reporting a vulnerability

Please **do not open a public issue**. Report privately through GitHub:
**Security → Report a vulnerability** on the repository
([private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).
If that is not possible, email the maintainer at the address under `authors` in
`pyproject.toml`.

Include what is affected (package version, Home Assistant integration version,
API endpoint), how to reproduce it, and the impact you expect. You will get an
acknowledgement within 5 working days. Please give us reasonable time to release
a fix before disclosing publicly; we will credit you unless you prefer otherwise.

## Supported versions

Security fixes go into the latest release of the `hvx` package and the
`hvx_ieq` integration.

## Scope notes

- `hvx serve` (FastAPI) is meant to run on a trusted network or behind an
  authenticating reverse proxy. Only the ChirpStack webhook has its own
  authentication (`HVX_WEBHOOK_TOKEN`).
- Credentials for live sources (Home Assistant tokens, ChirpStack API keys, MQTT
  passwords) belong in environment variables referenced by `*_env` keys in site
  files, never in the files themselves.
