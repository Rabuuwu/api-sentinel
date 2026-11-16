# API Sentinel: Render Free + Neon Free + GitHub Pages

To opcjonalne wdrożenie niezależne od lokalnego Sentinela. Nie modyfikuje DnDCompanion ani jego bazy. Kod jest przygotowany; zasoby w kontach użytkownika nie zostały utworzone.

## 1. Utwórz osobny projekt Neon

W [Neon Console](https://console.neon.tech) utwórz projekt **api-sentinel**, plan **Free**, PostgreSQL 17 i region możliwie blisko Frankfurtu (Render). Utwórz osobną bazę `sentinel`. Nie używaj bazy DnDCompanion.

W **Connect** wybierz bazę i rolę, wyłącz **Connection pooling** i skopiuj zwykły connection string PostgreSQL. Host nie może zawierać `-pooler.`: scheduler używa sesyjnej blokady advisory, której transaction pooler nie zachowuje.

Adres wpiszesz bezpośrednio w panelu Render jako sekret `DATABASE_URL`, nie do repozytorium, frontendu ani czatu. Wartość ma format:

```text
postgresql://USER:PASSWORD@DIRECT_NEON_HOST/sentinel?sslmode=require
```

Zachowaj `channel_binding=require` i kodowanie hasła w URL. Aplikacja używa wtedy asynchronicznego psycopg 3 z weryfikacją certyfikatu i nazwy hosta (`verify-full`, jawnie wskazany pakiet CA `certifi`). Dotychczasowe połączenia bez wymaganego channel binding nadal używają asyncpg. `DATABASE_URL_UNPOOLED`, jeśli ustawione, ma pierwszeństwo przed `DATABASE_URL` dla API, migracji i workera.

## 2. Przygotuj klucz szyfrowania webhooków

W swoim terminalu wygeneruj osobny sekret:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Zapisz wynik w menedżerze haseł. W Render ustaw go jako `WEBHOOK_ENCRYPTION_KEY`. Musi mieć 64 znaki szesnastkowe. **Nie zmieniaj go przy redeployu**: utrata klucza uniemożliwi odczyt zapisanych kanałów Discord. Ten klucz jest inny niż klucz logowania `SENTINEL_API_KEY`.

## 3. Wyślij zmiany i utwórz usługę Render

Z katalogu nadrzędnego:

```sh
cd /Users/macminisk/Projekty
python3 _tools/github-sync.py --project api-sentinel
```

W [Render Dashboard](https://dashboard.render.com): **New → Blueprint**, wybierz repozytorium API Sentinel i gałąź `main`. Jeżeli repo jest prywatne, udziel integracji Render dostępu tylko do potrzebnego repozytorium.

Blueprint `render.yaml` deklaruje wyłącznie **jedną Web Service na planie Free**. Nie deklaruje płatnego workera, dysku ani bazy Render. Przed zatwierdzeniem sprawdź plan Free w podsumowaniu. Podaj:

| Zmienna | Wartość |
| --- | --- |
| `DATABASE_URL` | Sekretny, bezpośredni adres bazy Neon z poprzedniego kroku |
| `WEBHOOK_ENCRYPTION_KEY` | Wygenerowane 64 znaki hex |
| `SENTINEL_API_KEY` | Blueprint generuje automatycznie; skopiuj z Environment do menedżera haseł |
| `CORS_ORIGINS` | `https://rabuuwu.github.io` (ustawione w Blueprint) |

Alternatywnie **New → Web Service**, repo API Sentinel, runtime **Docker**, plan **Free**, region Frankfurt, Docker Command `python -m api_sentinel.hosted`, Health Check Path `/health/ready`. Ustaw powyższe sekrety, a także `CHECK_CONCURRENCY=2`, `MAX_MONITORS=10`, `RETENTION_DAYS=7`, `WORKER_LOCK_WAIT_SECONDS=120`. Przy ręcznym wariancie wygeneruj własny `SENTINEL_API_KEY` (minimum 32 losowe znaki).

Launcher wykonuje migracje Alembic przed startem API i workera, obsługuje port Rendera i zamyka obydwa procesy przy awarii jednego. Nie jest to dodatkowa płatna Background Worker Service. Hostname Rendera zostaje dodany do listy dozwolonych hostów. Przy zmianie domeny ustaw również `ALLOWED_HOSTS`.

Po deployu skopiuj rzeczywisty adres usługi, np. `https://api-sentinel-XYZ.onrender.com`. Nie zakładaj, że nazwa bez sufiksu będzie wolna. Sprawdź `/health/ready`; odpowiedź powinna mieć status `ready`. To potwierdza bazę i schemat, a działanie schedulera potwierdzisz w panelu po zalogowaniu (heartbeat i nowy pomiar).

## 4. Podłącz GitHub Pages

W repo API Sentinel:

1. **Settings → Secrets and variables → Actions → Variables → New repository variable**.
2. Nazwa: `SENTINEL_API_BASE_URL`.
3. Wartość: `https://RZECZYWISTY-HOST.onrender.com/api/v1`.
4. **Settings → Pages → Source: GitHub Actions**.
5. **Actions → Deploy dashboard to GitHub Pages → Run workflow**.

Otwórz URL zwrócony przez workflow, docelowo `https://rabuuwu.github.io/api-sentinel/`. Zaloguj się `SENTINEL_API_KEY` z Rendera. Klucz nie jest zapisywany w buildzie ani localStorage. Pierwsze połączenie z uśpionym serwerem może potrwać około minuty; formularz czeka do dwóch minut.

GitHub Free udostępnia Pages dla publicznych repozytoriów; Pages dla prywatnego repo wymaga odpowiedniego planu. Jeżeli w Settings → Pages widzisz blokadę planu, nie uda się wdrożyć z tego prywatnego repo w GitHub Free. Możesz świadomie upublicznić repo po przeglądzie albo użyć oddzielnego publicznego repo z samym frontendem. **Nie zmieniono widoczności ani portfolio automatycznie.**

Więcej o buildzie i CORS: [GITHUB_PAGES.md](GITHUB_PAGES.md).

## 5. Pierwszy pomiar i dane lokalne

Nowa baza Neon zaczyna pusta. Dodaj w panelu DnDCompanion i portfolio z ich rzeczywistymi publicznymi adresami. Obserwuj pierwszy pomiar i heartbeat. Następnie skonfiguruj kanał Discord i świadomie użyj Test notification.

**Lokalne monitory, pomiary i sekrety nie są automatycznie przesyłane do Neon.** Istniejąca lokalna baza i `.env` pozostają bez zmian. Przeniesienie historii wymaga oddzielnego eksportu i kontrolowanego odtworzenia; nie wykonuj restore do bazy DnDCompanion. Starsze kanały lokalne korzystają z katalogu sekretów; przy przenoszeniu najprościej odtworzyć kanały w nowym panelu i ponownie przypisać je do monitorów.

Po pobraniu tej wersji dla lokalnego startu zainstaluj zależności (`.venv/bin/python -m pip install -e '.[dev]'`) i uruchom launcher. Migracja `0003` dodaje nullable ciphertext; starsze lokalne kanały dalej odczytują pliki. Nie usuwaj `.local/secrets`.

## Limity darmowego wariantu

- Render Free usypia usługę po 15 minutach bez ruchu. Wtedy **nie ma pomiarów ani wysyłania alertów**. Po wznowieniu nie dopisujemy fikcyjnych pomiarów za przerwę. Panel pokazuje informację o ograniczeniu.
- 750 godzin instancji/miesiąc jest wspólne dla workspace Render, również z DnDCompanion. Wiele stale aktywnych aplikacji może przekroczyć pulę.
- Render może ograniczyć lub zawiesić Free przy nadmiernym ruchu inicjowanym przez usługę, w tym do zewnętrznej bazy/API. Nie ma keepalive ani wzajemnego pingowania aplikacji w celu omijania usypiania.
- Neon Free ma limity czasu compute, pamięci i transferu. Scheduler utrzymuje sesyjną blokadę i regularnie korzysta z DB, więc aktywny worker utrzymuje compute w pracy. Ten wariant nie gwarantuje bezpłatnego monitoringu 24/7. Sprawdzaj Usage w obu panelach.
- Domyślne ograniczenia Blueprint: 10 monitorów, współbieżność 2, retencja 7 dni. Do dwóch pierwszych monitorów zacznij od interwału 300 sekund.
- Webhooki są szyfrowane w DB (Fernet); backup DB bez klucza szyfrowania nie wystarczy do odtworzenia kanałów. Klucz ma być zapisany osobno.
- Nie skaluj tej konfiguracji powyżej jednej instancji. Nowy worker czeka maksymalnie 120 sekund na zwolnienie blokady przez poprzedni deploy.

## Weryfikacja i źródła

Przed pierwszym użyciem wymagane są udany build Rendera, migracja na nowej bazie i realny pomiar. Nie wykonano tych operacji z tej sesji. Testy szyfrowania wymagają nowej zależności `cryptography`; brak instalacji oznacza jawny skip, nie wynik pozytywny.

[Render Free](https://render.com/docs/free), [Blueprint](https://render.com/docs/blueprint-spec), [Neon — połączenia](https://neon.com/docs/connect/connect-from-any-app), [Neon — pooling](https://neon.com/docs/connect/connection-pooling), [Fernet](https://cryptography.io/en/stable/fernet/).


## Konfiguracja przez Neon CLI

`neon init` / `neon deploy` zapisuje sekrety wyłącznie do ignorowanego `.env` (lub `.env.local`).
Konfiguracja projektu jest w `neon.ts`; `.neon` nie trafia do Git.
Wybrany projekt: `quiet-sea-10461963`, branch `production`, tylko Postgres.
Nie potrzeba Neon Auth ani Functions — backend nadal działa w FastAPI.

Po `neon deploy`, z katalogu repozytorium:

```sh
.venv/bin/python -m pip install -e '.[dev]'
npm ci --prefix frontend
npm run build
npm start
```

`npm start` uruchamia istniejące migracje Alembic, API i worker z bazą Neon.
Panel lokalny: http://127.0.0.1:8000, klucz logowania: istniejący `SENTINEL_API_KEY` w `.env`.
Zatrzymaj poprzednią lokalną instancję, jeśli zajmuje port 8000.
Nie używaj `scripts/local.py run` dla bazy Neon — ten skrypt wymaga lokalnego klastra.
Lokalne dane nie są automatycznie kopiowane do Neon.

Weryfikacja odczytu bazy przez aplikację (po uruchomieniu):

```sh
curl --fail http://127.0.0.1:8000/health/ready
```

Oczekiwane HTTP 200 potwierdza dostęp do wymaganych tabel. Nie zastępuje testu całego monitoringu.
Testy z zapisem danych uruchamiaj wyłącznie na osobnej bazie/gałęzi testowej, nigdy `production`.
Na Render ustaw sekretny bezpośredni URL jako `DATABASE_URL` lub `DATABASE_URL_UNPOOLED`,
ponieważ lokalne pliki `.env` nie są wysyłane do hostingu.
