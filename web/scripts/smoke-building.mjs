/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Runs hvx.building_csv (labels and report) under Pyodide in Node with the vendored files:
//   node scripts/smoke-building.mjs room1.csv room2.csv ... [--type school]
import { readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const typeAt = args.indexOf("--type");
const buildingType = typeAt >= 0 ? args.splice(typeAt, 2)[1] : "school";
const rooms = args.map((f) => ({ name: basename(f).replace(/\.csv$/, ""), csv: readFileSync(f, "utf8") }));

const { loadPyodide } = await import(join(web, "public/pyodide/pyodide.mjs"));
const manifest = JSON.parse(readFileSync(join(web, "public/py/manifest.json"), "utf8"));
let t0 = Date.now();
const py = await loadPyodide({ indexURL: join(web, "public/pyodide") + "/" });
await py.loadPackage(manifest.pyodide);
await py.loadPackage(manifest.wheels.map((w) => join(web, "public/py", w)));
console.log(`engine ready in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
py.globals.set("payload", JSON.stringify({ rooms, building_type: buildingType }));

t0 = Date.now();
const labels = JSON.parse(py.runPython(`
import json
from hvx import building_csv
_p = json.loads(payload)
json.dumps(building_csv.labels(_p["rooms"], "Smoke test", building_type=_p["building_type"]), default=str)
`));
console.log(`labels in ${((Date.now() - t0) / 1000).toFixed(1)} s:`, labels.rooms.map((r) => `${r.name} ${r.overall}`).join(", "),
  "| building", labels.building?.overall, labels.building?.domains);

t0 = Date.now();
await py.loadPackage(manifest.report);
console.log(`report packages in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
t0 = Date.now();
const report = JSON.parse(py.runPython(`
_r = building_csv.report(_p["rooms"], "Smoke test", _p["building_type"], mechanical_cooling=False)
json.dumps({"html": len(_r["html"]), "rooms": len(_r["data"]["rooms"]), "category": _r["data"]["summary"]["category"],
            "occupancy": _r["data"]["rooms"][0]["occupancy"]})
`));
console.log(`report in ${((Date.now() - t0) / 1000).toFixed(1)} s:`, report);
