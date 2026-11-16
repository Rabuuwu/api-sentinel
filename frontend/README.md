# API Sentinel dashboard

React + TypeScript + Vite. Tailwind CSS, shadcn-style Radix UI primitives, Lucide, Recharts 3, TanStack Query, React Router and date-fns. Inter fonts are bundled locally through `@fontsource/inter`.

## Development

Node.js 24 and npm are required. Start the migrated FastAPI backend separately, then:

```sh
npm install
npm run dev
```

Vite proxies `/api` and `/health` to `API_PROXY_TARGET` (development default `http://127.0.0.1:8000`). Set it in the shell or `frontend/.env`. Application requests use relative `/api/v1` URLs; no production hostname is hardcoded. `VITE_API_BASE_URL` is an optional build-time override, normally unnecessary behind the same-origin reverse proxy.

```sh
npm run typecheck
npm test
npm run build
```

The build produces `frontend/dist`, served by Nginx in Compose or FastAPI in the native local workflow. The backend needs migration `0002`. The old static interface remains under `/legacy` when accessing FastAPI directly.

## Architecture

- `components/shell.tsx`: navigation, sidebar, breadcrumbs, time range, global monitor editor.
- `components/ui/`: owned shadcn-style Button/Dialog source using CVA, Slot and Radix primitives. `components.json` configures future shadcn additions.
- `components/charts.tsx`: real historical buckets; grey explicitly means no measurements. Latency has only the measured response-to-headers series.
- `pages/`: overview, monitor details, incidents, notifications, status pages, public status, settings.
- `lib/api.ts`: same-origin client, in-memory key, cancellation and sanitized error messages.
- `lib/types.ts`: explicit client contracts. `lib/queries.ts`: shared cached resources.
- `src/test/`: component, validation and API-client tests.
- `e2e/`: Playwright workflow against a real isolated API/database, not fixture responses.

TanStack Query refreshes active views every 30 seconds and the sidebar list every 60 seconds, only while visible. Search is debounced. Expanded incident/timeline history pauses polling to avoid reloading an unbounded number of pages. Data errors preserve existing content and show a retry action; empty data is not treated as an error or 100% uptime.

## E2E

Requires a separate stack backed by `sentinel_test`, its migrations, built frontend and Playwright Chromium. Never use a production stack.

```sh
npx playwright install chromium
SENTINEL_E2E_ISOLATED=1 \
SENTINEL_E2E_URL=http://127.0.0.1:8000 \
SENTINEL_E2E_KEY='<key for the isolated test instance>' \
npm run test:e2e
```

The test logs in, creates its own monitor, pauses it, opens metrics, removes it, locks the workspace, and cleans up its own monitor even on failure. It does not intentionally fail any monitored production service. The test worker need not run for this UI flow; Python integration tests exercise result recording and incident transitions separately.

## Verification status

The full npm install/build, strict typecheck, component tests and browser E2E are **not yet verified** in this environment: registry.npmjs.org cannot resolve. Only TypeScript/TSX syntax was checked with the locally cached TypeScript compiler in `noCheck` mode; that is not a typecheck. No fake successful build or fabricated screenshot is supplied.

`package-lock.json` cannot be generated honestly until dependencies resolve. Generate and retain it after the first successful install; the Dockerfile will then use `npm ci`. See the root `VERIFICATION.md` for actual backend results and infrastructure blockers.
