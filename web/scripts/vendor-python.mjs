/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Puts everything the browser needs to run hvx into public/, so the app makes no
// third-party requests at run time:
//   public/pyodide/  Pyodide core (from npm) + the wheels hvx.tail_label needs (from the
//                    Pyodide CDN, resolved through pyodide-lock.json)
//   public/py/       the hvx wheel built from this repository and the pure-Python
//                    `holidays` wheel (from PyPI), listed in manifest.json
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const repo = resolve(web, "..");
const pyodideDir = join(web, "node_modules", "pyodide");
const version = JSON.parse(readFileSync(join(pyodideDir, "package.json"), "utf8")).version;
const cdn = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
const outPyodide = join(web, "public", "pyodide");
const outPy = join(web, "public", "py");
const python = process.env.PYTHON || (existsSync(join(repo, ".venv", "bin", "python")) ? join(repo, ".venv", "bin", "python") : "python3");

// What hvx.tail_label imports (no scipy): see src/hvx/tail_label.py
const WANTED = ["numpy", "pandas", "pydantic", "pyyaml", "python-dateutil", "pytz"];

async function download(url, file) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  writeFileSync(file, Buffer.from(await res.arrayBuffer()));
}

rmSync(outPyodide, { recursive: true, force: true });
rmSync(outPy, { recursive: true, force: true });
mkdirSync(outPyodide, { recursive: true });
mkdirSync(outPy, { recursive: true });

// 1. Pyodide core
for (const f of readdirSync(pyodideDir)) {
  if (/^pyodide(\.asm)?\.(m?js|wasm)$/.test(f) || f === "python_stdlib.zip" || f === "pyodide-lock.json") {
    copyFileSync(join(pyodideDir, f), join(outPyodide, f));
  }
}

// 2. Wheels from the lock file, with their dependencies
const lock = JSON.parse(readFileSync(join(outPyodide, "pyodide-lock.json"), "utf8"));
const norm = (n) => n.toLowerCase().replace(/_/g, "-");
const byName = new Map(Object.entries(lock.packages).map(([k, v]) => [norm(k), v]));
const needed = new Set();
const visit = (name) => {
  const pkg = byName.get(norm(name));
  if (!pkg) throw new Error(`Pyodide has no package ${name}`);
  if (needed.has(pkg.name)) return;
  needed.add(pkg.name);
  for (const dep of pkg.depends || []) visit(dep);
};
WANTED.forEach(visit);
let bytes = 0;
for (const name of needed) {
  const pkg = byName.get(norm(name));
  const file = join(outPyodide, pkg.file_name);
  await download(cdn + pkg.file_name, file);
  bytes += readFileSync(file).length;
}
console.log(`Pyodide ${version}: ${needed.size} packages (${(bytes / 1e6).toFixed(1)} MB): ${[...needed].sort().join(", ")}`);

// 3. hvx wheel from this repository, and the pure-Python `holidays` wheel
execFileSync(python, ["-m", "build", "--wheel", "--outdir", outPy, repo], { stdio: ["ignore", "ignore", "inherit"] });
const pypi = await (await fetch("https://pypi.org/pypi/holidays/json")).json();
const wheel = pypi.urls.find((u) => u.packagetype === "bdist_wheel" && u.filename.endsWith("py3-none-any.whl"));
if (!wheel) throw new Error("No pure-Python wheel for holidays on PyPI");
await download(wheel.url, join(outPy, wheel.filename));
const wheels = readdirSync(outPy).filter((f) => f.endsWith(".whl"));
writeFileSync(join(outPy, "manifest.json"), JSON.stringify({ pyodide: [...needed].sort(), wheels }, null, 2));
console.log(`Wheels: ${wheels.join(", ")}`);
