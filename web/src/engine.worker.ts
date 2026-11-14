/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// Runs hvx (this repository's Python package) in the browser with Pyodide. The CSV never
// leaves the visitor's machine: all files are served by this site (see scripts/vendor-python.mjs).
/// <reference lib="webworker" />
import type { PyodideAPI } from "pyodide";

declare const self: DedicatedWorkerGlobalScope;
const base = new URL(import.meta.env.BASE_URL, self.location.origin).href;
let ready: Promise<PyodideAPI> | null = null;
let reportReady: Promise<void> | null = null;
let manifest: { pyodide: string[]; report?: string[]; wheels: string[] };

function post(msg: unknown) {
  self.postMessage(msg);
}

async function boot(): Promise<PyodideAPI> {
  post({ type: "progress", step: "runtime" });
  const { loadPyodide } = (await import(/* @vite-ignore */ base + "pyodide/pyodide.mjs")) as typeof import("pyodide");
  const py = await loadPyodide({ indexURL: base + "pyodide/" });
  manifest = await (await fetch(base + "py/manifest.json")).json();
  post({ type: "progress", step: "packages" });
  await py.loadPackage(manifest.pyodide, { messageCallback: () => {} });
  await py.loadPackage(manifest.wheels.map((w: string) => base + "py/" + w), { messageCallback: () => {} });
  post({ type: "progress", step: "hvx" });
  await py.runPythonAsync("import json\nfrom hvx import tail_label, building_csv\nfrom hvx.core import schedules");
  return py;
}

// The report needs scipy and jinja2 (about 13 MB more): fetched the first time a report is made.
async function loadReport(py: PyodideAPI) {
  post({ type: "progress", step: "report" });
  await py.loadPackage(manifest.report ?? [], { messageCallback: () => {} });
  await py.runPythonAsync("import hvx.reporting");
}

self.onmessage = async (event: MessageEvent) => {
  const { id, type, payload } = event.data;
  try {
    ready ??= boot();
    const py = await ready;
    if (type === "init") {
      const version = py.runPython("import hvx; hvx.__version__");
      post({ id, ok: true, result: { version } });
      return;
    }
    py.globals.set("payload_json", JSON.stringify(payload ?? {}));
    let code = "";
    if (type === "detect") {
      code = "_p = json.loads(payload_json)\njson.dumps(tail_label.detected_columns(_p['csv']))";
    } else if (type === "rate") {
      code = [
        "_p = json.loads(payload_json)",
        "_o = dict(_p.get('options') or {})",
        "json.dumps(tail_label.label_from_csv(_p['csv'], columns=_p.get('columns'), **_o), default=str)",
      ].join("\n");
    } else if (type === "labels") {
      code = [
        "_p = json.loads(payload_json)",
        "json.dumps(building_csv.labels(_p['rooms'], _p.get('building_name'), **(_p.get('options') or {})), default=str)",
      ].join("\n");
    } else if (type === "report") {
      reportReady ??= loadReport(py);
      await reportReady;
      code = [
        "_p = json.loads(payload_json)",
        "_r = building_csv.report(_p['rooms'], **(_p.get('options') or {}))",
        "json.dumps({'html': _r['html'], 'data': _r['data']}, default=str)",
      ].join("\n");
    } else if (type === "holidays") {
      code = "_p = json.loads(payload_json)\njson.dumps(schedules.danish_school_holidays(_p['years']))";
    } else if (type === "hours") {
      code = "_p = json.loads(payload_json)\njson.dumps(tail_label.default_hours(_p['building_type']))";
    } else {
      throw new Error("Unknown request " + type);
    }
    const out = await py.runPythonAsync(code);
    post({ id, ok: true, result: JSON.parse(out) });
  } catch (error) {
    // Python errors: keep the last line (the exception message), not the traceback
    const text = String((error as Error)?.message ?? error);
    const lines = text.trim().split("\n");
    post({ id, ok: false, error: lines[lines.length - 1].replace(/^\w+Error: /, "") });
  }
};
