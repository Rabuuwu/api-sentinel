# API Sentinel

Monitoring HTTP/HTTPS z panelem WWW. Domyślny wariant lokalny uruchamia PostgreSQL, API, worker i stronę na Twojej maszynie. Opcjonalny wariant wybrany do hostingu: **GitHub Pages + Render Free + Neon Free** — instrukcja w [RENDER_NEON.md](RENDER_NEON.md). Render Free nie zapewnia ciągłego monitoringu podczas uśpienia.

**Status: implementacja 0.2 z dashboardem React, częściowo zweryfikowana.** Testy jednostkowe przechodzą. Pełne uruchomienie API–PostgreSQL–worker oraz test przeglądarkowy wymagają weryfikacji poza obecną sesją; konkretne blokady opisuje [VERIFICATION.md](VERIFICATION.md). Nie traktuj obecności kodu ani workflow CI jako dowodu zaliczenia integracji.

## Funkcje i status

| Zakres | Status |
| --- | --- |
| Walidacja konfiguracji, progi 3 porażek / 2 sukcesów | Tested — testy jednostkowe |
| Checker async, timeout, DNS, TLS, błędy HTTP | Tested — transporty testowe, bez usług produkcyjnych |
| SSRF: wszystkie odpowiedzi DNS, przypięcie IP, Host/SNI, brak redirectów | Tested — testy jednostkowe |
| CRUD, pauza/wznowienie, API key, historia i paginacja | Implemented — integracja czeka na weryfikację |
| PostgreSQL, migracja, blokady, idempotencja, outbox | Implemented — integracja czeka na weryfikację |
| Discord: retry/backoff, Retry-After, deduplikacja logiczna | Implemented — integracja czeka na weryfikację |
| Panel WWW: monitory, statystyki, incydenty, stan workera | Implemented — test przeglądarkowy zablokowany |
| Skrypt lokalnego uruchamiania i opcjonalny Docker Compose | Implemented — uruchomienie czeka na weryfikację |
| Prawdziwe monitory DnD Companion | Planned — wymagają rzeczywistych adresów |
| TLS expiry, maintenance windows, sleep-aware, multi-user | Implemented — poza bieżącym MVP |

## Uruchamianie na Twojej maszynie

Wymagane: Python 3.12+, PostgreSQL 17+ (`initdb`, `pg_ctl`, `createdb`, `psql` w PATH), dostęp do PyPI przy pierwszej instalacji. Wymagany jest również Node.js 24 i npm. Docker nie jest wymagany w wariancie natywnym.

Z katalogu `api-sentinel`:

```sh
python3 scripts/local.py setup
python3 scripts/local.py run
```

`setup` instaluje zależności Pythona w `.venv`, zależności Reacta w `frontend/node_modules`, buduje frontend, tworzy `.env` z losowym hasłem i kluczem (uprawnienia `600`), inicjalizuje osobny klaster `.local/postgres`, tworzy bazę `sentinel` i uruchamia migracje. Nie nadpisuje istniejącego `.env`. Nie zmienia systemowego klastra PostgreSQL. Skrypt odrzuci adres bazy inny niż `sentinel@127.0.0.1:54329/sentinel`.

`run` uruchamia ten klaster, migracje, API i worker. Panel: **http://127.0.0.1:8000**. Przy pierwszym uruchomieniu utwórz konto właściciela, potwierdzając operację `SENTINEL_API_KEY` z własnego `.env`. Potem loguj się loginem i hasłem. Token sesji pozostaje w pamięci karty; nie zapisujemy go w cookies, localStorage ani sessionStorage. `Ctrl+C` zatrzymuje procesy i klaster uruchomione przez ten skrypt; dane pozostają na dysku.

Jeżeli port `54329` jest zajęty, skrypt zatrzyma się bez zmieniania istniejącej usługi. `.local/` i `.env` są ignorowane przez Git. Nie usuwaj `.local/postgres`, jeżeli chcesz zachować pomiary.

**Komputer musi być włączony, nieuśpiony i mieć dostęp do internetu, aby wykonywać pomiary publicznych usług.** Lokalny panel i baza nie wymagają hostingu zewnętrznego. Opcjonalny Discord jest jedynym zewnętrznym kanałem alertowym; bez webhooka alerty trafiają do konsoli workera.

## Opcjonalnie: wszystko lokalnie w Dockerze

To alternatywa dla skryptu natywnego, nie dodatkowy hosting. Nie uruchamiaj obu wariantów naraz na porcie 8000.

Skopiuj `.env.example` do `.env`, ustaw własne losowe `POSTGRES_PASSWORD` i `SENTINEL_API_KEY` (minimum 32 znaki). Dla hasła użyj znaków URL-safe, np. wyniku `secrets.token_urlsafe(32)`; nie zostawiaj wartości przykładowych.

```sh
docker compose up --build -d
# panel: http://127.0.0.1:8000
docker compose logs -f worker
docker compose down
```

Compose ma lokalne serwisy `frontend`, `postgres`, jednorazowe `migrate`, `api` i `worker`. Frontend Nginx publikuje domyślnie `127.0.0.1:8000` i przekazuje API przez ten sam origin. PostgreSQL i API nie publikują portów hosta. Dane znajdują się w nazwanym wolumenie `postgres-data`. `down` zachowuje dane; `down -v` je usuwa. Nie skaluj workera — drugi proces odrzuci blokada advisory w bazie.

## Pierwszy monitor

W panelu wybierz „Dodaj monitor”. Podaj prawdziwy publiczny URL strony lub endpointu zdrowia backendu; adresy z dokumentacji są przykładami. Domyślnie: GET, co 300 s, timeout 20 s, oczekiwane 200–299, awaria po 3 kolejnych błędach, poprawa po 2 sukcesach.

Monitorowane adresy mogą być zewnętrzne, mimo że **sam Sentinel jest w całości lokalny**. Zgodnie z pierwotną polityką SSRF checker blokuje localhost i prywatne adresy sieciowe, również w DNS. Nie wyłączaj tej ochrony na potrzeby testów: użyj transportów mock w testach lub własnego publicznego stagingu. Nie wywołuj awarii produkcyjnego DnD Companion.

## Decyzje MVP

- Akceptowane kody HTTP to ciągły zakres `expected_status_min`–`expected_status_max`.
- URL bez danych logowania, query string i fragmentu; porty 80/443. Nazwa hosta jest ponownie sprawdzana przy każdym połączeniu. Odpowiedzi nie są buforowane; latency to czas do otrzymania nagłówków.
- Pauza zachowuje otwarty incydent. Wznowienie zeruje serie sukcesów/błędów; otwarty incydent wymaga normalnego recovery.
- Zmiana ustawień unieważnia wpływ checka rozpoczętego ze starszą konfiguracją. Zmiana URL podczas otwartego incydentu daje 409; dodaj osobny monitor dla innego celu.
- Usunięcie jest miękkie. Historia i ostatni stan incydentu pozostają w bazie; usunięcie nie udaje odzyskania dostępności.
- Po restarcie workera niedokończone checki otrzymują `ABORTED`, zerują serie i nie wchodzą do mianownika success rate. Nie nadrabiamy sztucznych pomiarów za czas wyłączenia komputera.
- Uptime to udział udanych ukończonych prób, nie procent sekund dostępności. Przy braku pomiarów API zwraca `null`. Percentyle obejmują tylko sukcesy.
- Retencja checków: domyślnie 30 dni. Incydenty nie są automatycznie usuwane.
- Discord: maksymalnie 10 prób; 429 respektuje Retry-After; błędy trwałe 4xx kończą dostarczanie. `FAILED` widać w stanie systemu. Outbox gwarantuje jedną logiczną intencję alertu; awaria po wysyłce może spowodować duplikat wiadomości.
- Brak zewnętrznych fontów, skryptów i telemetrii w panelu. Publiczne strony statusowe mają osobną trasę i ograniczony kontrakt bez prywatnych URL oraz szczegółów awarii.

## API

Prefix `/api/v1`, nagłówek `Authorization: Bearer <token sesji>`. Kontrakt: [API_SPEC.md](API_SPEC.md). OpenAPI: autoryzowany `GET /api/v1/openapi.json`. `/health/live` i `/health/ready` są publiczne i nie ujawniają konfiguracji. `GET /api/v1/system` raportuje heartbeat workera i stan kolejki alertów.

```sh
curl -H "Authorization: Bearer $SENTINEL_SESSION_TOKEN" http://127.0.0.1:8000/api/v1/monitors
```

Nie wystawiaj domyślnego wariantu HTTP bezpośrednio do internetu. Projekt jest obecnie przeznaczony do pracy lokalnej; zdalny dostęp wymaga osobnej konfiguracji TLS i dostępu sieciowego.

## Weryfikacja

Z nadrzędnego katalogu `Projekty`:

```sh
./_tools/devhouse test api-sentinel
```

Z katalogu projektu:

```sh
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

Test integracyjny wymaga **osobnej, przeznaczonej wyłącznie na testy** lokalnej bazy `sentinel_test` z migracjami. Ustaw `SENTINEL_TEST_DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:.../sentinel_test`. Następnie wykonaj migracje z `DATABASE_URL` wskazującym **tę testową bazę**, a potem `pytest -m integration`. Test odrzuca inne nazwy baz i hosty. Nie używa aplikacyjnej bazy `sentinel` i nie wykonuje automatycznie migracji. Bez zmiennej lub zależności zostanie jawnie pominięty.

Workflow `.github/workflows/test.yml` przygotowuje izolowaną bazę PostgreSQL, sprawdza migracje, Ruff, mypy i pytest. Nie został jeszcze uruchomiony na GitHub.

Opcjonalny test panelu wymaga Playwright i przeglądarki:

```sh
python3 scripts/ui_smoke.py
# z zainstalowanym Chrome:
SENTINEL_BROWSER_CHANNEL=chrome python3 scripts/ui_smoke.py
```

Ten stary skrypt dotyczy panelu legacy i nie weryfikuje nowego Reacta. Testuje interfejs na jawnych fixture API, a nie rzeczywistą integrację z backendem. Zrzuty zapisuje w `.local/verification/`.

## Struktura

```text
src/api_sentinel/
  app.py                 REST API i serwowanie panelu
  schemas.py, config.py  konfiguracja i walidacja
  security.py, checker.py  bezpieczne asynchroniczne checki
  domain.py              czysta maszyna stanów
  models.py, db.py        modele PostgreSQL i sesje async
  service.py             rezerwacja, zapis, incydenty, retencja
  alerts.py, worker.py    outbox i singleton scheduler
  static/                poprzedni panel pod /legacy
frontend/                dashboard React/TypeScript/Vite
migrations/              Alembic i początkowy schemat SQL
tests/                   unit i integracja PostgreSQL
scripts/                 lokalny start oraz smoke test panelu
```

Więcej: [REQUIREMENTS.md](REQUIREMENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md), [OPERATIONS_SECURITY.md](OPERATIONS_SECURITY.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Dashboard 0.2

Nowy panel zawiera Overview, Monitors, szczegóły z P50/P75/P90/P95/P99, wykresy, timeline, Incidents, Notifications, Status Pages i Settings. Formularze obejmują opisy, próg degraded i przypisanie kanałów Discord. Brak pomiarów oznacza brak danych, nigdy sztuczne 100%. Latency oznacza czas do nagłówków; DNS/connect/TTFB/download nie są osobno mierzone.

Dla istniejącej instalacji: wykonaj kopię bazy, zainstaluj zależności frontendu (`npm install --prefix frontend`), zbuduj go (`npm run build --prefix frontend`), następnie uruchom migrację `alembic upgrade head` w środowisku projektu i zrestartuj API/worker. Launcher `run` wykonuje migracje automatycznie; Compose używa jednorazowej usługi `migrate`. Nie nadpisuj istniejącego `.env`.

Sekrety kanałów zapisują się w prywatnym katalogu `SECRETS_DIR` (Compose: wolumen `webhook-secrets`). Backup musi obejmować bazę **i ten katalog**. Panel nigdy nie odczytuje zapisanego webhooka.

Testy Reacta i rzeczywistego E2E: [frontend/README.md](frontend/README.md). Aktualny raport zmian, wyniki i blokady: [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md), [VERIFICATION.md](VERIFICATION.md). Brak builda frontendu daje HTTP 503 na stronie głównej; samo uruchomienie API nie oznacza gotowego dashboardu.

## Opcjonalny dashboard GitHub Pages

Przygotowano oddzielny build Pages i workflow publikacji. API pozostaje osobną usługą HTTPS. Instrukcja, wymagania prywatnego repo oraz aktualne ograniczenia hostingu: [GITHUB_PAGES.md](GITHUB_PAGES.md). Nie oznacza to wykonanego wdrożenia. Lokalny launcher i Compose pozostają dostępne.

## Wdrożenie Render Free + Neon

Dodano `render.yaml`, launcher API/workera, TLS dla PostgreSQL i migrację `0003` dla zaszyfrowanych webhooków. Nie ma automatycznego przenoszenia lokalnych danych ani zmian w DnDCompanion. [Instrukcja krok po kroku](RENDER_NEON.md).

## Konta i prywatne monitory

Migracja `0004` wprowadza konta, Argon2id, sesje i właścicieli danych. Pierwsze konto przejmuje istniejące monitory po potwierdzeniu kluczem instalacji. Kolejne konta powstają na jednorazowe zaproszenie. Instrukcja aktualizacji, odzyskiwania dostępu i ograniczenia: [ACCOUNTS.md](ACCOUNTS.md).
