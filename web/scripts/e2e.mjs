/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// End-to-end check of the built app (npm run build first): serves dist/ under /hvx/, loads the
// example building, creates the labels, the report and the dashboard, and checks the results. Usage: node scripts/e2e.mjs [outdir]
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

  // an example building: four classroom files
  await page.getByRole("button", { name: /example|eksempel/i }).click();
  await page.getByText(/^4 (rooms|rum)$/).waitFor();
  await page.getByRole("button", { name: /Create labels|Lav mærkerne/ }).click();
  await page.locator("#labels-result").waitFor({ timeout: 120_000 });
  const rows = (await page.locator("#labels-result tbody tr").allInnerTexts()).map((r) => r.replace(/\s+/g, " ").trim());
  const aria = await page.locator("aside svg[role=img]").getAttribute("aria-label");
  await page.screenshot({ path: `${out}/2-labels.png`, fullPage: true });
  await page.locator("aside svg[role=img]").screenshot({ path: `${out}/3-sticker.png` });
  const [png] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /^(Download|Hent) PNG$/ }).click()]);
  await png.saveAs(`${out}/${png.suggestedFilename()}`);
  const [archive] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /ZIP/ }).click()]);
  await archive.saveAs(`${out}/${archive.suggestedFilename()}`);

  // the report and the dashboard (loads scipy and jinja2 the first time)
  await page.getByRole("button", { name: /Create the report|Lav rapporten/ }).first().click();
  await page.locator("#report iframe").waitFor({ timeout: 300_000 });
  const reportTitle = await page.frameLocator("#report iframe").locator("h1").first().innerText();
  await page.locator("#dashboard table").first().locator("tbody tr").first().waitFor();
  const dashboardRooms = await page.locator("#dashboard table").first().locator("tbody tr").count();
  await page.locator("#dashboard").screenshot({ path: `${out}/4-dashboard.png` });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${out}/5-mobile.png`, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(JSON.stringify({ label: aria, labels: rows, downloads: [png.suggestedFilename(), archive.suggestedFilename()],
    reportTitle, dashboardRooms, horizontalOverflowPx: overflow, pageErrors: errors, externalRequests: external }, null, 2));
  if (rows.length !== 5 || dashboardRooms !== 4 || overflow > 0) process.exitCode = 1;
  if (errors.length || external.length) process.exitCode = 1;
} finally {
  await browser.close();
  process.kill(-server.pid); // the whole group: npx and vite
}
