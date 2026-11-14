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

function post(msg: unknown) {
  self.postMessage(msg);
}

async function boot(): Promise<PyodideAPI> {
  post({ type: "progress", step: "runtime" });
  const { loadPyodide } = (await import(/* @vite-ignore */ base + "pyodide/pyodide.mjs")) as typeof import("pyodide");
  const py = await loadPyodide({ indexURL: base + "pyodide/" });
  const manifest = await (await fetch(base + "py/manifest.json")).json();
  post({ type: "progress", step: "packages" });
  await py.loadPackage(manifest.pyodide, { messageCallback: () => {} });
  await py.loadPackage(manifest.wheels.map((w: string) => base + "py/" + w), { messageCallback: () => {} });
  post({ type: "progress", step: "hvx" });
  await py.runPythonAsync("import json\nfrom hvx import tail_label");
  return py;
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
