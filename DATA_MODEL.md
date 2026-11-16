# Model danych — API Sentinel

PostgreSQL; `UUID` jako PK; wszystkie daty `TIMESTAMPTZ` w UTC. Migracje Alembic.

## Tabele

### monitors
`id`, `name`, `url`, `method`, `interval_seconds`, `timeout_seconds`, `expected_status_min`, `expected_status_max`, `failure_threshold`, `recovery_threshold`, `mode`, `status`, `consecutive_failures`, `consecutive_successes`, `last_checked_at`, `next_run_at`, `paused_at`, `deleted_at`, `created_at`, `updated_at`.

Indeksy: `(next_run_at) WHERE paused_at IS NULL AND deleted_at IS NULL`; `(status)`.

### check_executions
`id`, `monitor_id` (FK), `scheduled_for`, `started_at`, `finished_at`, `result` (enum), `http_status` nullable, `latency_ms` nullable, `error_type` nullable, `error_message_sanitized` nullable, `created_at`.

Unique `(monitor_id, scheduled_for)` (przy założeniu jednej rezerwacji slotu); indeks `(monitor_id, finished_at DESC)`.

### incidents
`id`, `monitor_id`, `state` (`OPEN`, `RESOLVED`), `started_at`, `detected_at`, `resolved_at`, `failure_count_at_open`, `reason`, `created_at`.

Unikalny indeks częściowy `UNIQUE(monitor_id) WHERE state = 'OPEN'`.

### alert_outbox
`id`, `incident_id`, `event_type` (`INCIDENT_OPENED`, `INCIDENT_RESOLVED`), `channel`, `delivery_state` (`PENDING`, `SENT`, `FAILED`), `attempts`, `next_attempt_at`, `last_error_sanitized`, `sent_at`, `created_at`.

Unikalny `(incident_id,event_type,channel)`; indeks `(delivery_state,next_attempt_at)`.

## Transakcje i konkurencja
- Zapis wyniku checka + aktualizacja liczników monitora + utworzenie incydentu + enqueue alertu w jednej transakcji.
- W trakcie przetwarzania stanu monitora `SELECT ... FOR UPDATE` na rekordzie monitora.
- Wielokrotne wykonanie `execution_id` / slotu nie może utworzyć drugiego wyniku.
- Retencja MVP: checki przez 30 dni, incydenty bez automatycznego kasowania; retencja konfigurowana przez RETENTION_DAYS.

## Przykładowe relacje
`monitors 1:N check_executions`, `monitors 1:N incidents`, `incidents 1:N alert_outbox`.

## Uzupełnienia implementacji 0.1

- `monitors.generation INTEGER`: zwiększany przy edycji, pauzie, wznowieniu i soft-delete.
- `monitors.failure_started_at TIMESTAMPTZ`: początek serii porażek, osobno od czasu wykrycia incydentu.
- `check_executions.generation INTEGER`: konfiguracja przy rezerwacji; `id` pełni rolę execution_id.
- `worker_heartbeat(id INTEGER PRIMARY KEY, updated_at TIMESTAMPTZ)`: pojedynczy rekord workera.
- `result` przechowuje bezpieczny kod błędu; nie zapisujemy surowych komunikatów wyjątków ani odpowiedzi. Wyniki obejmują dodatkowo `BLOCKED_TARGET`, `RESPONSE_TOO_LARGE` i `ABORTED`. W tej wersji nie ma redundantnych pól `error_type/error_message_sanitized`.
- Daty historii checków i paginacja używają `finished_at,id`; monitorów i incydentów `created_at,id`.
- Faktyczny początkowy schemat: `migrations/versions/0001_initial.sql`. UUID v4 generuje aplikacja; migracja nie wymaga rozszerzeń PostgreSQL.

## Migracja 0002 — dashboard

- `monitors`: description, degraded_latency_ms, degraded_threshold, consecutive_degraded, notification_channel_ids (UUID[]); status dopuszcza DEGRADED.
- `incidents`: failed_checks, recovery_successes. Backfill uwzględnia zachowane błędy i co najmniej próg otwarcia; po wcześniejszej retencji historyczny licznik nie jest pełny.
- `monitor_events`: monitor_id FK, action, information JSONB, created_at; indeks (monitor_id, created_at, id).
- `notification_channels`: nazwa, provider, enabled, on_down, on_recovered, deleted_at, created_at. Webhook **nie jest kolumną**.
- `status_pages`: unique slug, nazwa, opis, published, monitor_ids UUID[], created_at.
- `alert_outbox.incident_id` nullable dla testów, channel VARCHAR(80) mieści `discord:<UUID>`.

Migracja zachowuje dotychczasowe pomiary. Backfill timeline tworzy jedynie MONITOR_CREATED na podstawie rzeczywistych dat. Downgrade usuwa nowe funkcje i testowe alerty, konwertuje DEGRADED do UP; wymaga wcześniejszego backupu. Retencja usuwa stare checki oraz powtarzalne zdarzenia błędów/degraded, zachowuje incydenty i zdarzenia administracyjne.

## Migracja 0003 — trwałe szyfrowane webhooki

`notification_channels.webhook_ciphertext VARCHAR(4096) NULL` przechowuje ciphertext Fernet powiązany z UUID kanału. Klucz nie jest w bazie. Wartość nigdy nie jest polem ChannelOut ani publicznego API. NULL zachowuje zgodność z lokalnym magazynem plikowym; migracja nie odczytuje ani nie przenosi plików. Downgrade usuwa ciphertext, dlatego wymaga wcześniejszego odtworzenia kanałów lub backupu.
