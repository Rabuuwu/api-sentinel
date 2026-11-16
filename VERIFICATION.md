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
