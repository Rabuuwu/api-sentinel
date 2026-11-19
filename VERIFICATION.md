## Gmail verification and password recovery — 2026-11-17

Implemented: Gmail API over HTTPS (Render Free blocks SMTP), optional OAuth sender config,
operator-only OAuth setup script, verified recovery addresses, activation for new accounts,
resend, password reset, durable encrypted mail queue with bounded retries, sanitized logs,
email limits and owner-only queue counters. Migration `0005` preserves existing account access.
Frontend includes recovery settings and explicit POST confirmation/reset (GET never consumes tokens).

Actual checks:
- `devhouse test api-sentinel`: **131 Python tests passed, 5 PostgreSQL tests skipped**;
  **17 frontend tests passed**. One existing Starlette/httpx deprecation warning.
- Local build: **exit 0**, 2.32s. Pages build with dummy API URL: **exit 0**, 2.29s.
- Ruff passed; mypy passed for 27 source files; diff whitespace check passed.
- `alembic upgrade head --sql`: SQL generated successfully (not applied).
- Provider calls tested through httpx.MockTransport only; no actual email was sent.

Still unverified: applying 0005 and running PostgreSQL integration tests, real Gmail OAuth
setup/send/delivery, live Render/Neon end-to-end reset. Local dedicated test DB on port 54339
is unavailable to this session; tests were not redirected to production.

Run `bash scripts/test_accounts.sh` in the normal terminal for the dedicated DB checks.
Configure Gmail using GMAIL_SETUP.md, then verify one real activation and reset with your account.
No deployment, Google account changes or production DB mutation were performed by this change.

---

## Accounts and ownership — 2026-11-17

Implemented locally: username/password entry, invitation-only registration, one-time owner
bootstrap with legacy resource assignment, Argon2id PHC password hashes, opaque server-side
sessions stored as SHA-256, logout/revoke/password change, operator recovery command,
owner filtering on monitors/history/metrics/incidents/channels/status pages and summaries.
Migration `0004` adds accounts, sessions, invitations, budgets and indexed owner foreign keys.
Old API-key access is removed; legacy dashboard returns 410. No production deployment or
production migration was performed in this change.

Actual verification:
- `pytest -q`: **117 passed, 4 skipped**, one pre-existing Starlette/httpx deprecation warning.
- `npm test --prefix frontend`: **14 passed**, including sign-in, errors and bootstrap validation.
- `npm run build`: **exit 0**, built in 2.23s.
- Pages build with an explicitly dummy HTTPS endpoint: **exit 0**, built in 2.00s.
- Ruff: **All checks passed**. Mypy: **no issues in 24 source files**.
- `alembic upgrade head --sql`: **exit 0**, offline SQL generated, not applied.
- `git diff --check`: passed. Shell test harness passes `bash -n`.

Not verified: all four PostgreSQL integration tests, migration application/schema parity,
real browser E2E against PostgreSQL, deployed Render/Neon authentication.
The isolated cluster init failed with `could not create shared memory segment: Operation not
permitted`; localhost:54339 remains unavailable. No database test was redirected to Neon.

Next verification from the normal terminal:

```sh
cd /Users/macminisk/Projekty/api-sentinel
bash scripts/test_accounts.sh
```

This starts only a dedicated local `sentinel_test` cluster and API, applies migrations, runs
`alembic check`, Python/frontend tests, build and Playwright. Requires installed PostgreSQL
CLI tools and a Playwright Chromium browser. Do not count skipped integration tests as success.
Account usage, upgrade and recovery: ACCOUNTS.md. API contracts: API_SPEC.md.

---

## Neon CLI integration — 2026-11-16

User terminal confirmed authenticated `neon deploy` on `production`:
`No changes — branch production already matches the policy.`
`Pulled 5 Neon variables into .env` (Postgres only provisioned).
This confirms configuration, not application connectivity or migration success.

Changes: root build/start/test scripts; prefer direct Neon URL; preserve required
SCRAM channel binding with async psycopg/libpq, verified TLS; retain asyncpg for
existing configurations. Explicit process database settings override dotenv files.
No new schema migration, no local data import, no Render/Pages publication.

Verified:
- `npm run build`: exit 0, `✓ built in 3.92s`; dependency `use client` warnings.
- `./_tools/devhouse test api-sentinel`: 11 frontend tests passed (before root test
  script was expanded to also include pytest).
- Final Python suite: 107 passed, 4 skipped.
- Final focused config/hosted tests: 19 passed, 1 skipped.
- Ruff: `All checks passed!`; mypy: no issues in 19 source files.
- `git diff --check`: passed.

Blocked:
- Agent npm install/init: registry DNS unavailable; user completed CLI setup separately.
- Python dependency download failed: psycopg and cryptography unavailable in session.
- `npm start`: exit 1, `ModuleNotFoundError: No module named 'psycopg'`.
- Neon hostname resolution: `gaierror`. No database connection, migrations or live
  end-to-end test verified. Production has not been used for test writes.
- Three PostgreSQL integration tests and crypto test skipped; do not count as passed.

Follow RENDER_NEON.md to install dependencies and start from a network-enabled terminal.

---

# Aktualizacja: GitHub Pages + Render Free + Neon Free (2026-11-16)

- Backend: pełny przebieg przed ostatnim testem integracyjnym **103 passed, 3 skipped**. Dodany następnie test trwałości zaszyfrowanego kanału również został jawnie pominięty bez testowej DB (łącznie obecnie 4 testy wymagają niedostępnych zależności/usług).
- Frontend: **11 passed**; strict TypeScript, lokalny build i osobny build Pages zakończone powodzeniem. Build Pages używał jawnego przykładowego hosta, nie połączenia z produkcją.
- Ruff: zaliczone. Mypy: brak błędów w 19 plikach. `git diff --check`: zaliczone.
- SQL migracji 0001–0003 wygenerowany offline. Nie wykonano migracji na lokalnej bazie użytkownika ani Neon.
- Nowe testy sprawdzają CORS, verified TLS, odrzucanie transaction poolera Neon, walidację klucza, zakończenie obydwu procesów przy awarii oraz porządkowanie po błędzie startu workera.
- **Szyfrowanie niezweryfikowane lokalnie:** instalacja `cryptography>=46,<51` nie powiodła się; test realnego Fernet jest pominięty. Biblioteka jest zadeklarowana w zależnościach i ma być instalowana w CI/obrazie Render. Nie użyto zastępczej implementacji kryptografii.
- Testy PostgreSQL nadal pominięte bez izolowanej bazy. Nowy test integracyjny sprawdza zapis kanału, restart API, odszyfrowanie z DB i brak plików sekretów.
- Nie potwierdzono builda obrazu Docker, walidacji Blueprint przez Render, deployu na Render/Pages, połączenia z Neon ani przeglądarkowego E2E między originami. Te kroki wymagają zasobów/konta użytkownika.
- Nie zmieniono DnDCompanion, realnego `.env`, danych lokalnych ani widoczności repozytorium.

Instrukcja uruchomienia: [RENDER_NEON.md](RENDER_NEON.md). Poniżej zachowany raport historyczny; jego blokada npm/TypeScript została już usunięta.

---

# Weryfikacja 0.2 — 2026-11-13

## Wykonane

- `./_tools/devhouse test api-sentinel`: **85 passed, 2 skipped, 1 warning**, 3.78 s. Pominięte dwa testy integracyjne wymagają izolowanej bazy. Ostrzeżenie dotyczy przyszłego wycofania httpx w Starlette TestClient.
- `.venv/bin/ruff check .`: wszystkie kontrole zaliczone.
- `.venv/bin/mypy`: brak błędów w 17 plikach źródłowych.
- `.venv/bin/ruff format --check src tests scripts migrations`: 32 pliki poprawnie sformatowane.
- `python -m compileall -q src scripts migrations`: zaliczone.
- `alembic upgrade head --sql`: wygenerowano SQL obu migracji offline; **nie wykonano go na bazie**.
- Składnia TS/TSX sprawdzona lokalnie dostępnym TypeScript 7 w trybie `noCheck`. To **nie jest strict typecheck**, build ani dowód zgodności typów bibliotek.

Testy backendu obejmują SSRF/DNS/SNI, timeouty, klasyfikację wolnych odpowiedzi, stany/incydenty, percentyle referencyjne i uptime, walidację, redakcję sekretów, prywatność publicznych odpowiedzi, autoryzację nowych tras, commit przed odpowiedzią oraz retry/Retry-After alertów. Transport Discord jest symulowany, nie wysłano prawdziwego powiadomienia.

## Blokady i niewykonane kontrole

1. npm install: `ENOTFOUND registry.npmjs.org`. Brak pełnych node_modules i package-lock.json; **build, strict typecheck, Vitest i Playwright nie zostały uruchomione**. Nie ma zweryfikowanego screenshota ani odbioru wizualnego.
2. Izolowany PostgreSQL: initdb kończy się `shmget: Operation not permitted`. Nie uruchomiono migracji ani integracji na działającym PostgreSQL. Istniejącej bazy użytkownika nie używano do testów.
3. Brak polecenia Docker. Compose i obrazy nie zostały zbudowane ani uruchomione.
4. Workflow CI jest przygotowany, ale nie ma wyniku jego wykonania.

Zależności Pythona są obecnie dostępne — wcześniejsza blokada SQLAlchemy/asyncpg/mypy z wersji 0.1 już nie obowiązuje. Nie zmieniono realnego `.env`, nie dodano produkcyjnych monitorów ani nie wdrożono niczego zewnętrznie.

## Dalsza weryfikacja

1. Zainstalować npm dependencies, zachować lockfile; `npm run build --prefix frontend` i `npm test --prefix frontend`.
2. Na osobnej bazie `sentinel_test` wykonać migracje, `alembic check`, testy integration zgodnie z README/CI.
3. Uruchomić izolowaną instancję i Playwright zgodnie z frontend/README.md; ocenić desktop/tablet/mobile, klawiaturę i wykresy.
4. Sprawdzić Compose od pustych wolumenów oraz upgrade kopii istniejącej bazy. Dopiero potem odbierać całość jako działający system.

## 2026-11-19 — recovery, freshness, history and Gmail diagnostics

Implemented:

- Separate persisted invalid/valid confirmation budgets, per purpose/token/ASGI peer;
  no raw forwarding-header trust in the hosted launcher. Invalid reset guesses do not
  consume confirmation or login budgets. Hashing occurs after token preflight.
- Derived freshness for monitor resources, effective status filtering/counts in
  Overview, neutral badges/dots for stale data, and public UNKNOWN for stale UP.
  Incident records are unchanged.
- Actual history bounds/counts and retention warning in Overview/details/public views;
  period comparisons hidden when retention, boundaries or sample density are insufficient.
- Admin-only latest active delivery error code/time, nullable migration 0006,
  request-new-link guidance and updated operational/API docs.

Checks executed in the restricted local session:

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **155 passed, 6 skipped**, 1 pre-existing TestClient deprecation warning |
| `npm test --prefix frontend` | **22 passed**, 6 test files |
| `.venv/bin/ruff check .` | PASS |
| `.venv/bin/mypy` | PASS, 28 source files |
| `npm run build` | PASS, TypeScript + Vite; dependency `use client` warnings |
| `alembic upgrade head --sql` | PASS, includes nullable timestamptz addition in 0006; no DB connection |
| `git diff --check` | PASS |
| `bash scripts/test_accounts.sh` | BLOCKED at test PostgreSQL startup: `shmat ... Operation not permitted` |

The six PostgreSQL integration cases were skipped without an explicit test URL.
New DB tests cover concurrent invalid guesses, persisted limits after app restart,
one-use reset under concurrency, stale public status/Overview filtering and admin-only
mail diagnostics. These cases are implemented but **not verified against PostgreSQL
in this session**. E2E could not start because its test database did not start.
No production migrations, push, deploy or real emails were performed.

### Remaining acceptance steps

In a normal terminal, after the code changes are complete:

```sh
cd /Users/macminisk/Projekty/api-sentinel
bash scripts/test_accounts.sh
```

This harness explicitly selects the dedicated localhost `sentinel_test`, applies
migrations there, checks metadata, runs Python/frontend tests, builds and runs Playwright.
It does not use the Neon URL from the application's .env. If Chromium is missing:
`cd frontend && npx playwright install chromium`, then rerun the harness from the repo.

Before production deploy: take a DB backup, confirm CI for the exact commit, deploy the
backend (hosted launcher applies 0006) and frontend, then complete the Gmail acceptance
sequence in GMAIL_SETUP.md. A successful provider acceptance is not inbox-delivery proof.
Preserve the current encryption key. The live mail flow remains unverified until the
owner records delivery, successful reset, old-session rejection and single-use link.

The prior README/IMPLEMENTATION_PLAN edits were preserved. Dependency locking (AS-05)
is a separate open backlog item, outside these four corrections.

### macOS 12 browser fallback

The current Playwright browser installer rejects macOS 12. An installed Google Chrome
was found in /Applications. Opt into it without downloading bundled Chromium:

```sh
SENTINEL_E2E_BROWSER_CHANNEL=chrome bash scripts/test_accounts.sh
```

This uses Playwright's Chrome channel; it does not guarantee compatibility between
an older Chrome on macOS 12 and the installed Playwright. If browser launch or protocol
compatibility fails, run the unchanged default Chromium suite on supported CI/Linux.
Do not downgrade the application dependencies just to silence the installer error.
The fallback configuration alone is not evidence of a passing browser test.
