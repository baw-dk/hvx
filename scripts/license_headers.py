#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Check or add the MPL-2.0 notice on source files (see LICENSE_HEADER.md).

    python scripts/license_headers.py --check   # CI: list files missing it, exit 1
    python scripts/license_headers.py --fix     # add it where missing
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NOTICE_LINES = (
    "This Source Code Form is subject to the terms of the Mozilla Public",
    "License, v. 2.0. If a copy of the MPL was not distributed with this",
    "file, You can obtain one at https://mozilla.org/MPL/2.0/.",
)
HASH_NOTICE = "".join(f"# {line}\n" for line in NOTICE_LINES)
BLOCK_NOTICE = f"/* {NOTICE_LINES[0]}\n * {NOTICE_LINES[1]}\n * {NOTICE_LINES[2]} */\n"
SPDX = "SPDX-License-Identifier: MPL-2.0"

STYLES = {
    ".py": HASH_NOTICE,
    ".ttl": HASH_NOTICE,
    ".ts": BLOCK_NOTICE,
    ".tsx": BLOCK_NOTICE,
    ".js": BLOCK_NOTICE,
    ".mjs": BLOCK_NOTICE,
    ".cjs": BLOCK_NOTICE,
    ".css": BLOCK_NOTICE,
}
# Generated or third-party trees.
EXEMPT_PARTS = {"node_modules", ".next", ".venv", "venv", "build", "dist", "__pycache__", ".git"}
EXEMPT_FILES = {"flow-editor/next-env.d.ts"}


def tracked_files() -> list[Path]:
    """Files git knows about (tracked + untracked, not ignored)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.split("\n")
    return [ROOT / p for p in out if p]


def in_scope(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return (
        path.suffix in STYLES
        and path.is_file()
        and not (set(rel.parts) & EXEMPT_PARTS)
        and rel.as_posix() not in EXEMPT_FILES
    )


def has_notice(text: str) -> bool:
    head = "\n".join(text.splitlines()[:8])
    return NOTICE_LINES[0] in head or SPDX in head


def add_notice(text: str, notice: str) -> str:
    if text.startswith("#!"):
        first, _, rest = text.partition("\n")
        return f"{first}\n{notice}{rest}"
    return notice + text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv)

    missing, both = [], []
    for path in sorted(p for p in tracked_files() if in_scope(p)):
        text = path.read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:8])
        if NOTICE_LINES[0] in head and SPDX in head:
            both.append(path)
        if has_notice(text):
            continue
        missing.append(path)
        if args.fix:
            path.write_text(add_notice(text, STYLES[path.suffix]), encoding="utf-8")

    for path in both:
        print(f"both prose notice and SPDX line (use one): {path.relative_to(ROOT)}")
    if args.check and missing:
        for path in missing:
            print(f"missing MPL-2.0 notice: {path.relative_to(ROOT)}")
        print(f"\n{len(missing)} file(s) need the notice. Run: python scripts/license_headers.py --fix")
    elif args.fix:
        print(f"Added the notice to {len(missing)} file(s).")
    return 1 if (args.check and missing) or both else 0


if __name__ == "__main__":
    sys.exit(main())
