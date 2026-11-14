# License headers

HVX is licensed under the [Mozilla Public License 2.0](LICENSE). MPL-2.0 is a
*file-level* copyleft: it applies per file, so every source file carries the
notice from the license's Exhibit A.

## The notice

Python, Turtle (`.ttl`) and other `#`-comment files:

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
```

TypeScript, JavaScript and CSS:

```ts
/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
```

## Rules

- New source files get the notice at the top, normally from line 1.
- If a file starts with a shebang (`#!`), the notice goes directly after it.
- `# SPDX-License-Identifier: MPL-2.0` is an accepted alternative. Use **either**
  the prose notice **or** the SPDX line, never both. Prefer the prose notice
  unless the neighbouring files use SPDX.
- Comments before a Python module docstring or a `'use client'` directive are fine.
- Generated and third-party trees (`node_modules`, `.next`, `build`, `dist`,
  virtual environments) are exempt.
- Files you copy from other projects keep their original notice and license;
  mention them in your pull request (see [CLA.md](CLA.md) §4.4).

## Tooling

```bash
python scripts/license_headers.py --check   # CI runs this
python scripts/license_headers.py --fix     # add the notice where it is missing
```

The file types in scope and the exempt paths are defined in
`scripts/license_headers.py`.
