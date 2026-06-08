---
name: run-valuation-app
description: >-
  Launch and drive the McKinsey Valuation app (this repo, D:\bin) — FastAPI
  backend + React/Vite frontend + cli.py. Use when asked to run, start, serve,
  or screenshot the app, or to confirm a change works in the real app. Covers
  the backend API, the web UI (with a Playwright screenshot driver), and the
  offline CLI. Verified on Windows (PowerShell + Git-Bash), Python 3.14,
  Node 24.
---

# Running the McKinsey Valuation app

Project root is `D:\bin`. Three ways to run it; pick by what you're verifying.
All commands assume cwd `D:\bin` (the API package `api.main:app` only resolves
from the root, and `sample_company.json` lives there).

## Gotchas this skill exists to save you (read first)

1. **Port 8000 is taken by a Jupyter Server on this machine.** The Vite proxy
   (`web/vite.config.ts`) hardcodes `/api → http://localhost:8000`. If you run
   the backend on 8000 it fails with WinError 10048, and the UI's `/api/*`
   calls hit Jupyter and 404. **Run the backend on `8123`** and point the proxy
   there (see web steps). Don't kill the Jupyter process — it isn't ours.
2. **Korean renders fine in the browser.** If you pipe API JSON through the
   terminal (`json.tool`, `curl | python`) the Hangul looks like broken
   surrogates (`媛\udc80…`) — that's the Windows console codepage, NOT a
   bug. Decode the raw bytes in-process (`json.load` then `print`) to confirm.
3. **Playwright is not a project dependency.** Use the bundled `shot.mjs`, which
   imports `playwright-core` from a scratch install and drives **system Chrome**
   via `channel: "chrome"` — nothing gets added to `web/node_modules` or
   `package.json`.
4. The UI shows nothing on load — it defaults to manual mode with the sample
   financials pre-filled and waits for the **가치평가 실행** button.

## A) Offline CLI — fastest smoke, no keys, no server

```bash
cd /d/bin
python cli.py --from-json sample_company.json --price 30
```

Prints the target price to the console. No API keys needed.

## B) Backend API — drive the engine a client would hit

Launch on 8123 (NOT 8000 — see gotcha 1), background it, poll `/health`:

```bash
cd /d/bin
python -m uvicorn api.main:app --port 8123 > /tmp/uvicorn.log 2>&1 &
for i in $(seq 1 20); do curl -s http://localhost:8123/health | grep -q ok && break; sleep 0.5; done
```

Smoke the offline valuation endpoint (sample company, price 30). Decode
in-process so Korean rationale prints correctly:

```bash
cd /d/bin
BODY="{\"base\": $(cat sample_company.json), \"revenue_growth\": 0.06, \"current_price\": 30}"
curl -s -X POST http://localhost:8123/valuation -H "Content-Type: application/json" -d "$BODY" \
  | python -c "import sys,json; r=json.load(sys.stdin); print('target_price', round(r['result']['target_price'],2), '| upside', round(r['upside'],3), '| value_trap', r['result']['value_trap']); print(r['rationale'][0])"
```

Expected (price 30, growth 0.06, β default 1.0 → WACC 8.70%): `target_price ≈
66.3`, `upside ≈ +1.21`, `value_trap False`, and a clean Korean rationale line.
Endpoints:
`GET /health`, `POST /valuation`, `GET /valuation/{ticker}` (needs
`DART_API_KEY`), `POST /valuation/from-pdf` (needs `ANTHROPIC_API_KEY`),
`POST /sensitivity`.

## C) Web UI + screenshot — the full experience

The backend MUST be running (step B, on 8123). Then point the proxy at it and
start Vite. **Restore the proxy when done** — `:8000` is the committed value.

```bash
# 1. Backend on 8123 (step B) must be up first.
# 2. Repoint the Vite proxy 8000 -> 8123 (temporary; revert after).
#    Edit web/vite.config.ts:  target: "http://localhost:8123"
# 3. Start Vite (auto-restarts when the config changes):
cd /d/bin/web
npm run dev -- --port 5173 > /tmp/vite.log 2>&1 &
sleep 2
curl -s http://localhost:5173/api/health    # expect {"status":"ok"} via the proxy
```

Then screenshot with the bundled driver (one-time scratch install of
`playwright-core`, reused thereafter):

```bash
[ -d /c/Users/$USER/pw-scratch/node_modules/playwright-core ] || \
  (mkdir -p /c/Users/$USER/pw-scratch && cd /c/Users/$USER/pw-scratch && npm install playwright-core)
cd /d/bin/.claude/skills/run-valuation-app
node shot.mjs
```

`shot.mjs` loads the UI, fills 현재가 = 30, clicks 가치평가 실행, waits for the
목표주가 stat + sensitivity heatmap, and writes `D:\bin\web\ui-screenshot.png`
(full page). **Read the screenshot** — a blank/error frame means the proxy or
backend isn't wired up. It also prints any browser console errors (a lone
favicon 404 is harmless).

If `shot.mjs` can't resolve `playwright-core`, fix the `file:///C:/Users/.../pw-scratch/...`
import path at the top of the file for the current user.

## Cleanup

Stop only what you launched — leave the Jupyter server on 8000 alone:

```bash
powershell -Command "Get-NetTCPConnection -LocalPort 5173,8123 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id \$_ -Force -ErrorAction Stop } catch {} }"
```

Revert `web/vite.config.ts` proxy target back to `http://localhost:8000`.
