# REST API — kontrakt MVP (v1)

Prefix: `/api/v1`; JSON; timestamps UTC ISO 8601; admin auth nagłówek `X-API-Key: <secret>` (wyłącznie za HTTPS poza localhost). Response błędu: `{ "error": { "code": "VALIDATION_ERROR", "message": "...", "request_id": "..." } }`.

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
