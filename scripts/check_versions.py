#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Keep the package and Home Assistant integration versions in step.

    python scripts/check_versions.py              # CI: exit 1 on mismatch
    python scripts/check_versions.py --set 0.4.0  # release: update all three places
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
MANIFEST = ROOT / "custom_components" / "hvx_ieq" / "manifest.json"
VERSION_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.M)
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.]+)?$")


def read() -> dict:
    match = VERSION_RE.search(PYPROJECT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pins = [r.split("==", 1)[1] for r in manifest.get("requirements", []) if r.startswith("hvx==")]
    return {
        "pyproject.toml version": match.group(2) if match else None,
        "manifest.json version": manifest.get("version"),
        "manifest.json hvx requirement": pins[0] if pins else None,
    }


def write(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    PYPROJECT.write_text(VERSION_RE.sub(lambda m: f"{m.group(1)}{version}{m.group(3)}", text, count=1), encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["requirements"] = [f"hvx=={version}" if r.startswith("hvx==") else r for r in manifest.get("requirements", [])]
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", metavar="VERSION")
    args = parser.parse_args(argv)
    if args.set:
        if not SEMVER.match(args.set):
            parser.error(f"not a semantic version: {args.set}")
        write(args.set)
    found = read()
    for where, value in found.items():
        print(f"{where:32} {value}")
    if len(set(found.values())) != 1 or None in found.values():
        print("\nVersions differ. Run: python scripts/check_versions.py --set X.Y.Z")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
