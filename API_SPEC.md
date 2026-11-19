# REST API — kontrakt MVP (v1)

Prefix: `/api/v1`; JSON; timestamps UTC ISO 8601; auth nagłówek `Authorization: Bearer <token>` (wyłącznie za HTTPS poza localhost). Response błędu: `{ "error": { "code": "VALIDATION_ERROR", "message": "...", "request_id": "..." } }`.

## Monitory
- `POST /monitors` — utwórz monitor (201).
- `GET /monitors?status=UP&limit=20&cursor=...` — lista.
- `GET /monitors/{id}` — szczegóły.
- `PATCH /monitors/{id}` — aktualizacja.
- `POST /monitors/{id}/pause` — pauza.
- `POST /monitors/{id}/resume` — wznowienie.
- `DELETE /monitors/{id}` — soft-delete (204).

Request `POST /monitors`:
```json
{
  "name": "DnD Companion API",
  "url": "https://example-api.onrender.com/health",
  "method": "GET",
  "interval_seconds": 300,
  "timeout_seconds": 20,
  "expected_status_min": 200,
  "expected_status_max": 299,
  "failure_threshold": 3,
  "recovery_threshold": 2,
  "mode": "standard"
}
```
`example-api.onrender.com` to **placeholder**, nie rzeczywisty adres. `mode`: `standard` (MVP), `sleep_aware` (rozszerzenie).

Response:
```json
{
  "id": "08f8de26-83be-4b25-8530-613ef5ff5ea2",
  "name": "DnD Companion API",
  "status": "UNKNOWN",
  "next_run_at": "2026-11-14T09:00:00Z",
  "created_at": "2026-11-14T08:55:00Z"
}
```

## Checki, incydenty i statystyki
- `GET /monitors/{id}/checks?limit=50&cursor=...`
- `GET /monitors/{id}/incidents?state=open&limit=50&cursor=...`
- `GET /monitors/{id}/stats?window=24h` (dozwolone: `24h`, `7d`, `30d`)
- `GET /incidents/{id}`
- `GET /health/live` — liveness własnego API Sentinel, bez sekretów
- `GET /health/ready` — readiness API Sentinel do obsługi requestów (np. DB)

Przykładowe stats:
```json
{
  "monitor_id": "08f8de26-83be-4b25-8530-613ef5ff5ea2",
  "window": "24h",
  "completed_checks": 96,
  "successful_checks": 95,
  "success_rate_percent": 98.96,
  "latency_p50_ms": 135,
  "latency_p95_ms": 420,
  "open_incidents": 0
}
```

## Błędy
`400` zły parametr, `401` brak/nieprawidłowy API key, `404` brak rekordu, `409` konflikt stanu, `422` niepoprawne dane, `429` limit żądań, `500` błąd serwera. Paginacja cursor-based po `checked_at,id`.

## Przykłady cURL
```bash
curl -H "X-API-Key: $SENTINEL_API_KEY" http://localhost:8000/api/v1/monitors
```

## Szczegóły implementacji 0.1

- Lokalny adres: `http://127.0.0.1:8000`. Health endpoints są pod `/health/live` i `/health/ready`, bez prefiksu `/api/v1`.
- `GET /api/v1/openapi.json`: schemat OpenAPI z wymaganą autoryzacją. Publiczne `/docs` i `/openapi.json` są wyłączone.
- `GET /api/v1/system`: `worker_alive`, `worker_last_seen`, `pending_alerts`, `failed_alerts`, `alert_channel`.
- Listy pierwotnego API zwracają `{ "items": [...], "next_cursor": "..." }`; brak następnej strony to `null`. Limit 1–100. Cursor dotyczy `finished_at,id` dla checków i `created_at,id` dla monitorów/incydentów.
- `success_rate_percent` i percentyle są `null`, gdy brak odpowiednich pomiarów. Stats zawierają również `aborted_checks`.
- PATCH waliduje kompletną konfigurację po scaleniu. Jawne `null` dla wymaganego pola jest błędem 422. Zmiana URL przy otwartym incydencie: 409.
- Pauza/wznowienie są idempotentne. Soft-delete nie zamyka incydentu ani nie emituje fałszywego recovery.
- Dodatkowe odpowiedzi: 413 przy body większym niż 16 KiB, 503 przy niedostępnej bazie. Limit API: 300 żądań/min na proces (jeden administrator).
- URL monitorów nie dopuszcza query string, fragmentów i credentiali. Pozostawiono wyłącznie porty 80/443 oraz tryb `standard`.

## Endpointy dashboardu 0.2

Poniższe ścieżki są względne wobec `/api/v1`. Wymagają X-API-Key poza jawnie publiczną ostatnią trasą. Szczegółowe typy i walidacja są generowane w chronionym OpenAPI.

| Metoda | Ścieżka | Przeznaczenie |
| --- | --- | --- |
| GET | /overview | Podsumowanie i tabela; window, q, status, sort, direction, offset, limit |
| GET | /monitors/{id}/metrics | Bieżące/poprzednie okno, 5 percentyli, 60 bucketów |
| GET | /monitors/{id}/timeline | Zdarzenia z paginacją cursor |
| GET | /incidents | Globalna historia z filtrem state i cursor |
| GET, POST | /notifications | Lista i utworzenie kanału |
| PATCH, DELETE | /notifications/{id} | Nazwa/przełączniki i soft-delete kanału |
| POST | /notifications/{id}/test | Zlecenie testu (202), limit raz/min |
| GET | /notifications/{id}/deliveries | Ostatnie 20 dostarczeń |
| GET, POST | /status-pages | Lista i utworzenie strony |
| PUT, DELETE | /status-pages/{id} | Aktualizacja i usunięcie |
| GET | /public/status-pages/{slug} | Publiczny, ograniczony kontrakt opublikowanej strony |

Monitor POST/PATCH dodatkowo: description, degraded_latency_ms (nullable wyłącza próg), degraded_threshold, notification_channel_ids. Dotychczasowe pola zachowują domyślne wartości. Kanał POST przyjmuje webhook_url jako sekret zapisu; PATCH nie ujawnia ani nie zmienia webhooka. Strona przyjmuje name, slug, description, published, monitor_ids.

Metryki nie oferują regionów ani niemierzonych etapów DNS/connect/download. `latency_series` deklaruje dostępne serie. Brak historii oznacza wartości null; DEGRADED wlicza się do udanych HTTP. Overview używa paginacji offsetowej, listy kanałów i stron są zwykłymi listami; nie zakładaj dla nich formatu cursor. `/system` dodaje wersję, lokalizację, retencję i limit monitorów.


## Konta (migracja 0004)

Nagłówek `X-API-Key` nie uwierzytelnia już żądań. `SENTINEL_API_KEY` jest wyłącznie
jednorazowym dowodem uprawnień podczas tworzenia pierwszego konta.

| Endpoint `/api/v1/auth` | Kontrakt |
|---|---|
| GET `/setup` | Publiczne `{setup_required: boolean}` |
| POST `/bootstrap` | `{username,password,setup_key}`; 201, jednorazowo przypisuje stare dane właścicielowi |
| POST `/register` | `{username,password,invitation}`; 201, atomowo zużywa zaproszenie |
| POST `/login` | `{username,password}`; 200 |
| GET `/me` | `{id,username,is_admin}`; aktywna sesja |
| POST `/logout` | Unieważnia bieżącą sesję; 204 |
| POST `/logout-all` | Unieważnia wszystkie własne sesje; 204 |
| POST `/password` | `{current_password,new_password}`; zmienia hasło i unieważnia wszystkie sesje; 204 |
| POST `/invitations` | Tylko administrator; `{invitation,expires_at}`, 201; kod pokazany raz |
| GET `/users` | Tylko administrator; lista identyfikatorów, loginów i roli (maks. 100) |
| DELETE `/users/{id}/sessions` | Tylko administrator; unieważnia sesje użytkownika, 204 |

Login/bootstrap/register zwracają `{token,expires_at,user:{id,username,is_admin}}`.
Login 3–40 znaków ASCII: litery, cyfry, `_`, `.`, `-`, zapisany małymi literami.
Hasło 15–128 znaków, bez przycinania/normalizacji. Pola hasła są write-only.
Hasło, jego hash, tokeny innych sesji i hash zaproszenia nigdy nie trafiają do odpowiedzi.

Zasoby chronione są filtrowane po właścicielu wynikającym z sesji; `owner_id` nie jest
akceptowany w wejściu. Próba dostępu do cudzego ID zwraca 404, przypisania cudzego
monitora/kanału — 422. Administrator także widzi tylko własne zasoby monitoringu.
Publiczne strony statusowe zachowują dotychczasowy, ograniczony kontrakt.
Błędy logowania są ogólne (401), limit prób zwraca 429. Sesja trwa maksymalnie 8 godzin,
wygasa po 30 minutach bez żądań. Tokeny nie są przyjmowane w query string ani cookies.


## Opcjonalne wiadomości kont (0005)

`GET /auth/setup` dodatkowo zwraca `mail_enabled`. Przy włączonej poczcie bootstrap/register
wymaga pola `email` i zwraca 201 `{verification_required:true,message}` zamiast sesji.
Login niepotwierdzonego nowego konta zwraca 403 po poprawnym sprawdzeniu hasła.
Stare konta nie są automatycznie blokowane. `GET /auth/me` dodaje własne `email`, `pending_email`
i `mail_enabled`; lista użytkowników administratora nadal nie zawiera adresów.

| Endpoint `/api/v1/auth` | Kontrakt |
|---|---|
| POST `/email` | Sesja + `{email,current_password}`; 202, kolejkuje potwierdzenie adresu |
| POST `/email/resend` | Publiczny `{username,email}`; 202, ogólny komunikat |
| POST `/email/verify` | Publiczny `{token}`; 200, potwierdza adres, unieważnia sesje; nie działa przez GET |
| POST `/password-reset/request` | Publiczny `{email}`; zawsze taki sam komunikat 202 dla poprawnego formatu i dozwolonego limitu |
| POST `/password-reset/confirm` | Publiczny `{token,new_password}`; 200, zmienia hasło, unieważnia wszystkie sesje i akcje |
| GET `/email/status` | Administrator; `{enabled,deliveries:{PENDING?,SENT?,FAILED?}}`, wyłącznie liczniki |

Nieaktywny moduł poczty daje 503. Limity wysyłki: 3/adres/godz., 30/globalnie/godz.; 429 po przekroczeniu.
Niepoprawny, przeterminowany lub zużyty token daje 400. Reset: 15 minut, potwierdzenie: 60 minut.
Tokeny write-only, nie są zwracane przez API. Adresy ASCII, maks. 254 znaki, kanonizowane małymi literami.
Nowe hasło 15–128 znaków. Żądania nie przyjmują własnego redirect URL, From ani szablonu wiadomości.

## Observation metadata and recovery hardening — 2026-11-19

Monitor resources retain the stored `status` for compatibility and add:
`last_observed_status`, `effective_status`, `freshness` (`FRESH`, `STALE`, `AWAITING`,
`PAUSED`) and `stale_after_seconds`. Freshness expires after
`2 * interval_seconds + timeout_seconds + 30`; future timestamps fail closed as stale.
Paused monitors remain paused. These are derived fields and never change incidents.
Overview filtering, sorting and status counts use effective status. Public monitor
`status` also uses effective status, so an old UP becomes UNKNOWN rather than DOWN.

Overview, monitor metrics and each public monitor expose `history`:
`requested_start`, `requested_end`, `retention_days`, `retention_limited`,
`first_check_at`, `last_check_at`, `completed_checks`. Bounds describe actual retained
observations, not uninterrupted monitoring. Missing data is not success. Percentiles
still cover successful checks only; success rate is not wall-clock uptime.

Metrics expose `comparison_available`. `previous` is null unless both windows fit
within retention, contain observations near both boundaries (two current intervals
plus 30 seconds), and each contains at least 90% of the sample count expected at the
current interval. This conservative heuristic may hide comparisons after interval
changes; it does not assert continuous time coverage.

`GET /api/v1/auth/email/status` remains admin-only and adds nullable `last_failure`:
`{code, at}`. Both values come from active delivery rows; older rows may have no
attempt timestamp. No address, token, ciphertext or provider response body is returned.
Expired/consumed links remove their diagnostics with the queue entry.

Confirmation/reset budgets are isolated by purpose and token digest. Invalid,
expired and wrong-purpose links consume a separate invalid-link budget and cannot
consume valid confirmation or login budgets. Within five minutes: invalid links
30/ASGI peer and 240/global per purpose; valid links 8/token, 120/peer and 240/global
per purpose. Global limits remain intentional overload protection, not guaranteed
availability during a distributed attack. Counters remain transactional PostgreSQL
records across processes/restarts; no raw tokens or IP addresses are stored as keys.
