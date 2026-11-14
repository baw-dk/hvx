/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// End-to-end check of the built app (npm run build first): serves dist/ under /hvx/, loads the
// example year, creates a label and checks the result. Usage: node scripts/e2e.mjs [outdir]
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

// Playwright: the project dependency if installed, else a globally installed one
const { chromium } = createRequire(import.meta.url)("playwright");

const out = process.argv[2] || "e2e-output";
mkdirSync(out, { recursive: true });
const server = spawn("npx", ["vite", "preview", "--port", "4317", "--strictPort"], { stdio: ["ignore", "pipe", "inherit"], detached: true });
await new Promise((resolve) => server.stdout.on("data", (d) => String(d).includes("4317") && resolve()));
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const external = [];
  page.on("request", (r) => { if (!/^(http:\/\/localhost:4317\/|blob:|data:)/.test(r.url())) external.push(r.url()); });
  await page.goto("http://localhost:4317/hvx/");
  await page.getByText(/Rating engine ready|Beregningen er klar/).waitFor({ timeout: 120_000 });
  await page.screenshot({ path: `${out}/1-start.png`, fullPage: true });
  await page.getByRole("button", { name: /example|eksempel/i }).click();
  await page.getByText("example-classroom-2024.csv").waitFor();
  await page.getByRole("button", { name: /Create label|Lav mærket/ }).click();
  await page.locator("#label svg[role=img]").waitFor({ timeout: 120_000 });
  const aria = await page.locator("#label svg[role=img]").getAttribute("aria-label");
  await page.screenshot({ path: `${out}/2-label.png`, fullPage: true });
  await page.locator("#label svg[role=img]").screenshot({ path: `${out}/3-sticker.png` });
  const [png] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /PNG/ }).click()]);
  await png.saveAs(`${out}/${png.suggestedFilename()}`);
  const [svg] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /^SVG$/ }).click()]);
  await svg.saveAs(`${out}/${svg.suggestedFilename()}`);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${out}/4-mobile.png`, fullPage: true });
  console.log(JSON.stringify({ label: aria, downloads: [png.suggestedFilename(), svg.suggestedFilename()], pageErrors: errors, externalRequests: external }, null, 2));
  if (errors.length || external.length) process.exitCode = 1;
} finally {
  await browser.close();
  process.kill(-server.pid); // the whole group: npx and vite
}
