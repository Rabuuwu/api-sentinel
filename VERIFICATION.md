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
