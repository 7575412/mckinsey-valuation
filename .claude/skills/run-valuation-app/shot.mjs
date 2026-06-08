// Screenshot driver for the McKinsey Valuation web UI.
// Uses playwright-core from a scratch install + the system Chrome (channel:
// "chrome"), so nothing is added to the project's node_modules.
//
//   one-time:  mkdir ~/pw-scratch && cd ~/pw-scratch && npm install playwright-core
//   run:       node shot.mjs            (backend on :8123 + Vite on :5173 must be up)
//
// Writes D:\bin\web\ui-screenshot.png (full page) and prints browser console errors.

import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const pwPath = path.join(os.homedir(), "pw-scratch", "node_modules", "playwright-core", "index.js");
const pwMod = await import(pathToFileURL(pwPath).href);
const chromium = pwMod.chromium ?? pwMod.default.chromium;

const url = "http://localhost:5173/";
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1280, height: 1600 }, deviceScaleFactor: 2 });

const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

await page.goto(url, { waitUntil: "networkidle" });

// Fill 현재가 (선택) so upside + reverse-DCF show, then run the valuation.
await page.locator('label.num:has(span:text-is("현재가 (선택)")) input').fill("30");
await page.getByRole("button", { name: /가치평가 실행/ }).click();

// Wait for the result stats (목표주가) and the sensitivity heatmap to paint.
await page.getByText("목표주가", { exact: false }).first().waitFor({ timeout: 15000 });
await page.waitForTimeout(800);

await page.screenshot({ path: "D:/bin/web/ui-screenshot.png", fullPage: true });

console.log("SCREENSHOT_OK -> D:\\bin\\web\\ui-screenshot.png");
console.log("CONSOLE_ERRORS: " + JSON.stringify(errors));
await browser.close();
