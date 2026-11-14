/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Runs hvx.tail_label under Pyodide in Node with the vendored files (no browser needed):
//   node scripts/smoke-pyodide.mjs some.csv [building_type]
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const { loadPyodide } = await import(join(web, "public/pyodide/pyodide.mjs"));
const manifest = JSON.parse(readFileSync(join(web, "public/py/manifest.json"), "utf8"));
const t0 = Date.now();
const py = await loadPyodide({ indexURL: join(web, "public/pyodide") + "/" });
await py.loadPackage(manifest.pyodide);
await py.loadPackage(manifest.wheels.map((w) => join(web, "public/py", w)));
console.log(`engine ready in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
const csv = readFileSync(process.argv[2], "utf8");
py.globals.set("csv_text", csv);
py.globals.set("building_type", process.argv[3] || "school");
const t1 = Date.now();
const out = py.runPython(`
import json
from hvx.tail_label import label_from_csv
json.dumps(label_from_csv(csv_text, building_type=building_type))
`);
const label = JSON.parse(out);
console.log(`rated in ${((Date.now() - t1) / 1000).toFixed(1)} s:`, label.profile, label.overall, label.domains,
  Object.fromEntries(Object.entries(label.parameters).map(([k, v]) => [k, v.rating])), label.coverage.days, "days");
