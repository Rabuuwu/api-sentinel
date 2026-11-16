# Architektura API Sentinel

## Kontenery
```
                         +-----------------------+
Administrator --> localhost --> FastAPI (REST + panel)  |
                         +-----------+-----------+
                                     | SQLAlchemy
                          +----------v----------+
                          | PostgreSQL           |
                          +----------^----------+
                                     |
                         +-----------+----------+
                         | Scheduler / Check Worker| ---> public HTTPS endpoints
                         +-----------+----------+       (DnD Companion itd.)
                                     |
                             Alert Outbox Worker ---> Discord webhook
```
W MVP worker i outbox sender mogą być w jednym procesie, ale powinny mieć oddzielne moduły. W bieżącym wariancie panel i API są dostępne wyłącznie lokalnie na 127.0.0.1.

## Pierwotny podział koncepcyjny (rzeczywiste pliki poniżej)
```
src/api_sentinel/
  api/{routes_monitors,routes_checks,routes_incidents,routes_stats}.py
  core/{config,security,logging}.py
  domain/{models,schemas,incident_state}.py
  infrastructure/{db,repositories,http_checker,webhooks}.py
  services/{monitor_service,check_service,stats_service}.py
  workers/{scheduler,runner,alert_outbox}.py
migrations/  tests/{unit,integration}/
```

## Przepływ pojedynczego checka
1. Scheduler wybiera aktywne monitory z `next_run_at <= now()`.
2. Rezerwuje wykonanie (`execution_id`, blokada lub lease) i przesuwa `next_run_at` atomowo.
3. Checker waliduje URL i rozwiązuje DNS zgodnie z polityką SSRF, wykonuje request z ograniczonym timeoutem, bez automatycznych redirectów w MVP.
4. Zapisuje wynik checka (`SUCCESS`, `HTTP_ERROR`, `TIMEOUT`, `DNS_ERROR`, `TLS_ERROR`, `NETWORK_ERROR`).
5. State machine inkrementuje liczniki kolejnych sukcesów/awarii i ewentualnie zmienia status monitora.
6. Przy zmianie stanu zapisuje rekord incydentu i zdarzenie w `alert_outbox` **w tej samej transakcji**.
7. Sender wysyła alert i zapisuje wynik. Retry z backoff i idempotency key logiczną po stronie aplikacji. Discord webhook nie zapewnia pełnej deduplikacji end-to-end: przy awarii po wysyłce możliwe są duplikaty fizycznych wiadomości.

## State machine
- `UNKNOWN -> UP`: pierwszy sukces.
- `UNKNOWN/UP -> DOWN`: osiągnięto próg kolejnych porażek.
- `DOWN -> UP`: osiągnięto próg kolejnych sukcesów; zamknij incydent.
- `UP -> DEGRADED`: opcjonalnie, jeśli zbyt wysoka latencja przez N checków.
- `* -> PAUSED`: nie planuj kolejnych checków, nie otwieraj automatycznie incydentu.
- Pojedynczy sukces resetuje licznik błędów, pojedynczy błąd resetuje licznik sukcesów.

## Architektura decyzji
- **ADR-001** Oddzielamy FastAPI od workera, aby restart HTTP nie zatrzymywał długotrwałych checków.
- **ADR-002** W MVP jeden scheduler; skalowanie później przez lease + SELECT FOR UPDATE SKIP LOCKED.
- **ADR-003** Alert przez transactional outbox, aby zapis incydentu i intencji alertu był atomowy.
- **ADR-004** Rozróżniamy `DOWN` od `DEGRADED`, a Render cold start od faktycznej awarii dopiero po odpowiedniej konfiguracji.
- **ADR-005** Endpoint `/health` monitorowanej aplikacji może raportować stan DB; API Sentinel nie dostaje credentials do jej bazy.

## Metryki
- Success rate: `successful_checks / completed_checks * 100%`; osobno raportuj `unknown` i brak pomiarów.
- Latencja: p50/p95 na udanych checkach w okresie.
- Czas incydentu: `resolved_at - started_at` lub `now - started_at` dla otwartych.
- Nie utożsamiaj czasu między checkami z udowodnioną dostępnością.

## Wariant zaimplementowany: jedna maszyna

Dashboard React buduje Vite; w Compose serwuje go Nginx z proxy do FastAPI, a natywnie FastAPI z `frontend/dist`. Poprzedni panel `static/` pozostaje pod `/legacy`. Brak CDN i zewnętrznych zasobów runtime. Skrypt `scripts/local.py` zarządza własnym klastrem PostgreSQL, migracją oraz procesami API i workera. Docker Compose jest alternatywą lokalną. Zewnętrzny reverse proxy i VPS nie należą do bieżącego wdrożenia.

- Worker trzyma sesyjny advisory lock na dedykowanym połączeniu; drugi worker odmawia startu. Rezerwacje i harmonogram zapisują się w krótkiej transakcji. W MVP checki wykonują się w ograniczonych paczkach; rzeczywisty interwał może wydłużyć się przy obciążeniu.
- `generation` oddziela bieżącą konfigurację od checków będących w locie podczas edycji/pauzy. Wynik starszej generacji pozostaje w historii, lecz nie zmienia stanu monitora.
- Rezerwacje porzucone po utracie workera otrzymują `ABORTED`; nie są fałszywą awarią targetu.
- Warstwa transportu używa [publicznego interfejsu backendu sieciowego HTTPCore](https://www.encode.io/httpcore/network-backends/) pod `httpx.AsyncClient`; zweryfikowane IP trafia bezpośrednio do połączenia TCP, a domena zostaje zachowana dla TLS SNI i Host.
- Sesja REST używa [zależności FastAPI z `scope="function"`](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope), aby commit zakończył się przed wysłaniem odpowiedzi.
- `worker_heartbeat` pozwala panelowi odróżnić działające API od działającego workera.

## Rozszerzenie 0.2

`app.py` zachowuje dotychczasowe API; `dashboard.py` dodaje zasoby dashboardu, `dashboard_schemas.py` ich kontrakty, `metrics.py` agregacje PostgreSQL, `vault.py` lokalne sekrety. React pozostaje warstwą wizualną. Worker wykonuje scheduler i sender jako oddzielne zadania asyncio w jednym procesie pod wspólną blokadą singletona.

Metryki: 60 przedziałów czasowych, okna 24h/7d/30d, poprzednie okno, percentyle `percentile_cont` z udanych i degraded odpowiedzi. DEGRADED to poprawna odpowiedź HTTP przekraczająca próg; wchodzi do uptime, ale nie potwierdza zdrowego recovery. Brak próbek daje null; przerwa pracy hosta nie tworzy fikcyjnych checków.

Kanały i strony statusowe używają list UUID z walidacją istnienia po stronie API. Publiczny kontrakt jawnie wybiera tylko nazwy, statusy, uptime i czasy incydentów; nie serializuje obiektów administracyjnych. Timeline utrwala zmiany i dostarczenie alertu w transakcjach. Historyczne metryki pochodzą z checków; migracja nie wymyśla dawnych zdarzeń.
