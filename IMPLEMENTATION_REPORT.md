# Raport wdrożenia API Sentinel 0.2

Zapisano implementację dashboardu i rozszerzenia backendu. **Nie zakończono odbioru całego produktu**: frontend, PostgreSQL i Compose wymagają uruchomienia w środowisku bez opisanych blokad. Python/FastAPI pozostaje sercem monitoringu; nie wprowadzono Next.js ani hostingu chmurowego.

## Funkcje

- Ciemny, gęsty layout inspirowany dostarczoną referencją: własna identyfikacja, zwijany sidebar, mobilna nawigacja, breadcrumbs, zakres czasu i odświeżanie.
- Overview: rzeczywiste podsumowanie, tabela, wyszukiwanie, sortowanie, statusy i paginacja.
- Szczegóły monitora: uptime/błędy/degraded/pingi, pięć percentyli, porównanie poprzedniego okna, histogram statusów, wykres mierzonej latencji, timeline.
- Formularze monitorów: opis, interwał, timeout, kody HTTP, progi błędów/recovery/degraded, przypisanie kanałów, pauza/wznowienie i potwierdzane usunięcie.
- Discord: kanały, sekret tylko do zapisu, test w outbox, przełączniki DOWN/RECOVERED i historia dostarczeń. Retry i deduplikacja logiczna zachowane.
- Incydenty: historia, czas trwania, przyczyna i liczniki; automatyczna maszyna stanów z ochroną przed duplikacją.
- Status Pages: tworzenie, edycja, publikacja lokalna, wybór monitorów i publiczne odpowiedzi bez prywatnych URL czy powodów awarii.
- Loading/skeleton, empty/error states, toast, formularze Radix, kontrolowane odświeżanie. Dostępność i responsywność są zaimplementowane, lecz wymagają testu przeglądarkowego.

## Pliki

Nowa warstwa `frontend/`: manifest, Vite/TypeScript/Tailwind, komponenty UI/layout/charts/editor, siedem widoków, klient API, typy, style, testy komponentów i Playwright, Dockerfile oraz Nginx.

Backend dodany: `dashboard.py`, `dashboard_schemas.py`, `metrics.py`, `vault.py`. Zmienione: `app.py`, `models.py`, `schemas.py`, `config.py`, `domain.py`, `checker.py`, `service.py`, `alerts.py`, `worker.py`. Ścieżki względem `src/api_sentinel/`.

Pozostałe: `migrations/versions/0002_dashboard.py`, nowe testy dashboardu/delivery/integracji, testy checkera, `docker-compose.yml`, `Dockerfile`, `.env.example`, `pyproject.toml`, `scripts/local.py`, `.github/workflows/test.yml`, ignorowanie artefaktów oraz dokumentacja projektu. Nie było dostępnego repozytorium Git do wygenerowania diffu; to zestawienie obszarów zmian, nie commit.

## API i migracja

Nowe zasoby: `/api/v1/overview`, `/monitors/{id}/metrics`, `/monitors/{id}/timeline`, globalne `/incidents`, CRUD `/notifications`, `/notifications/{id}/test`, `/notifications/{id}/deliveries`, CRUD `/status-pages`, publiczne `/public/status-pages/{slug}`. Wszystkie poza trasą publiczną wymagają klucza. Szczegóły metod: [API_SPEC.md](API_SPEC.md).

Migracja `0002_dashboard`: rozszerzenia monitorów i incydentów, `monitor_events`, `notification_channels`, `status_pages`, opcjonalny incident_id dla testu powiadomień. Zachowuje historię; nie fabrykuje dawnych zdarzeń. Webhooki są poza DB w prywatnym katalogu. Szczegóły: [DATA_MODEL.md](DATA_MODEL.md).

## Wyniki

**85 passed, 2 skipped**; Ruff, formatowanie i mypy zaliczone. SQL migracji wygenerowany offline. Pełny frontend typecheck/build/Vitest/E2E, integracja PostgreSQL i Compose **niezweryfikowane**. Przyczyny: DNS npm, odmowa shared memory PostgreSQL, brak Docker. Dokładne dowody: [VERIFICATION.md](VERIFICATION.md).

## Uruchomienie

Zachowaj istniejący `.env`; przy nowej instalacji skopiuj `.env.example`, ustaw własny klucz i hasło. Następnie:

```sh
docker compose up -d --build
```

Docelowy panel: `http://127.0.0.1:8000`. Compose uruchamia frontend, API, worker, PostgreSQL i migrację. Wolumeny `postgres-data` oraz `webhook-secrets` są trwałe. Nie używaj `down -v`, jeśli chcesz zachować dane. Obrazy wymagają dostępu do rejestrów pakietów podczas builda.

Alternatywa natywna: Python 3.12+, PostgreSQL 17+, Node 24/npm; `python3 scripts/local.py setup`, następnie `python3 scripts/local.py run`. Setup zachowuje istniejący `.env`. Po migracji 0002 stara wersja backendu nie powinna działać równolegle z nowym workerem.

DnD Companion i portfolio dodaj przez Add monitor, podając ich faktyczne publiczne URL; nie dodano przykładowych adresów jako prawdziwych monitorów. Domyślna polityka blokuje prywatne IP, localhost, przekierowania i URL z sekretami.

## Ograniczenia i przyszłość

- Brak potwierdzenia wizualnej jakości i pełnego działania do czasu zaliczenia builda i przeglądarki. Brak lockfile do pierwszego skutecznego npm install.
- Jedna lokalizacja pomiarowa; tylko rzeczywiście mierzone response-to-headers, bez sztucznych DNS/connect/TTFB/download.
- Jeden administrator i worker; brak kont użytkowników, Telegram/email, maintenance windows i sleep-aware.
- Uptime to udział udanych prób; wyłączony komputer nie wykonuje pomiarów. Degraded jest sukcesem HTTP, ale nie zdrowym recovery.
- Webhooki są plikami o ograniczonych prawach, bez szyfrowania aplikacyjnego. Backup obejmuje DB i katalog sekretów. Zobacz OPERATIONS_SECURITY.md.
- Nie wysłano rzeczywistego alertu, nie monitorowano automatycznie produkcji, nie wykonano wdrożenia VPS. Dawna historia licznika incydentów może być niepełna po retencji.
