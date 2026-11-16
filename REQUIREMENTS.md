# Wymagania i kryteria akceptacji — API Sentinel

## Role i założenia
- MVP: pojedynczy administrator, prywatne REST API zabezpieczone kluczem, bez publicznej rejestracji.
- Monitorowany serwis nie musi instalować agenta; wystarczy publiczny HTTP(S) endpoint.
- Monitoring z zewnątrz nie gwarantuje stanu wszystkich komponentów wewnętrznych.

## Wymagania funkcjonalne MVP
- **FR-01** Administrator tworzy, edytuje, pauzuje, usuwa monitory HTTP(S).
- **FR-02** Parametry: nazwa, URL, metoda GET/HEAD, interwał >=60 s, timeout 2–30 s, lista akceptowanych kodów (domyślnie 200–299), próg kolejnych porażek i sukcesów.
- **FR-03** Każdy check przechowuje czas wykonania (UTC), HTTP status lub typ błędu, czas odpowiedzi, identyfikator monitora.
- **FR-04** Statusy: `UNKNOWN`, `UP`, `DEGRADED` (opcjonalny próg latency), `DOWN`, `PAUSED`; pojedyncza porażka nie musi oznaczać `DOWN`.
- **FR-05** Incydent powstaje po 3 kolejnych niepowodzeniach; po 2 kolejnych sukcesach zostaje zamknięty (wartości konfigurowalne).
- **FR-06** Jeden incydent otwarty na monitor; alert otwarcia i odzyskania wysyłany jednokrotnie logicznie (z deduplikacją).
- **FR-07** Endpoint historii z paginacją oraz statystyki 24h/7d/30d.
- **FR-08** Bezpieczne uruchamianie checków zewnętrznych: SSRF policy, ograniczenie czasu i przekierowań.
- **FR-09** Alert Discord webhook z retry i zapisem statusu dostarczenia.
- **FR-10** Dokumentacja OpenAPI generowana z FastAPI.

## Wymagania niefunkcjonalne
- Python 3.12+, FastAPI, httpx AsyncClient, SQLAlchemy 2 async, asyncpg, PostgreSQL, Alembic.
- Nie uruchamiaj schedulerów w wielu replikach API bez locka/koordynacji. W MVP: **osobny worker** schedulera, dokładnie jedna instancja.
- Idempotencja zapisu wyniku checka przez `execution_id`, ochrona przed dublowaniem incydentów.
- Checki nie mogą blokować pętli zdarzeń, limit globalnej równoległości, timeouty.
- Sekrety w env lub prywatnym lokalnym magazynie webhooków; logi bez tokenów i payloadów użytkowników.
- Każdy request admin API wymaga autoryzacji; dokumentacja API może być niepubliczna.
- Uptime to udział udanych **prób monitorujących** w okresie, a nie dowód ciągłej dostępności każdej sekundy.

## Poza zakresem MVP
- Multi-tenant, billing, SSO, agent host-level, monitoring prywatnej bazy bez adaptera, zaawansowana analiza RUM, automatyczny restart aplikacji, skanowanie portów.

## Kryteria odbioru
- [ ] Nowy monitor może zostać utworzony przez API i sprawdzony przez worker.
- [ ] 3 kolejne błędy HTTP 500 tworzą dokładnie 1 incydent.
- [ ] 2 kolejne poprawne odpowiedzi zamykają incydent.
- [ ] Dwa równoległe wykonania tego samego checka nie powodują podwójnych rekordów/alertów.
- [ ] Timeout i błąd DNS są poprawnie zapisane z kodem błędu (bez fałszywego statusu HTTP).
- [ ] API wymaga klucza; hosty prywatne/loopback/metadata nie są osiągalne przez checki.
- [ ] Dashboard/API pokazuje realne pomiary backendu DnD Companion, bez ujawniania danych użytkowników.
- [ ] `docker compose up --build` oraz `pytest` działają według README.

## Aktualizacja implementacyjna — lokalny self-hosting

Całość (panel, API, worker i PostgreSQL) jest hostowana na maszynie użytkownika. Domyślny dostęp do panelu: `127.0.0.1:8000`; osobny natywny klaster PostgreSQL: `127.0.0.1:54329`, katalog `.local/postgres`. Nie wdrażamy usług na VPS ani w chmurze. Panel lokalny wchodzi do bieżącej implementacji; dashboard React jest częścią wersji 0.2.

W FR-02 „lista akceptowanych kodów” jest na tym etapie ciągłym zakresem `expected_status_min`–`expected_status_max`, zgodnie z API_SPEC. `DEGRADED` jest zaimplementowane jako opcjonalny próg latencji i seria wolnych odpowiedzi. Kryteria integracyjne powyżej pozostają nieodhaczone do rzeczywistego uruchomienia stosu; aktualne wyniki znajdują się w VERIFICATION.md.
