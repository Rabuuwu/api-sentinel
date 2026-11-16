# Uruchamianie, bezpieczeństwo i monitoring DnD Companion

## Sposób wdrożenia
Bieżące wdrożenie: wyłącznie maszyna użytkownika. Natywnie `scripts/local.py` uruchamia PostgreSQL, API z panelem i worker; alternatywą jest lokalny Docker Compose (`frontend`, `api`, `worker`, `postgres`, `migrate`). Nie korzystamy z VPS ani zewnętrznej bazy. **Jeżeli Sentinel działa tylko na wyłączonym komputerze, nie będzie monitorował 24/7.** Aby wykrywać awarię hosta Sentinel, potrzebny jest niezależny zewnętrzny watchdog.

## Zmienne `.env.example`
```dotenv
DATABASE_URL=postgresql+asyncpg://sentinel:change-me@postgres:5432/sentinel
SENTINEL_API_KEY=replace-with-random-secret
CHECK_CONCURRENCY=10
DEFAULT_INTERVAL_SECONDS=300
DEFAULT_TIMEOUT_SECONDS=20
DISCORD_WEBHOOK_URL=
LOG_LEVEL=INFO
```
Nigdy nie commituj realnego `.env` ani webhooka. W produkcji używaj secret managera i ograniczeń sieciowych.

## Konfiguracja DnD Companion
1. Utwórz monitor **DnD Companion PWA**: publiczny adres GitHub Pages, oczekiwane 200, interwał 5 min.
2. Utwórz monitor **DnD Companion API**: faktyczny publiczny URL backendu Render + `/health`, oczekiwane 200. Nie zakładaj adresu z przykładu w dokumentacji.
3. Sprawdź semantykę `/health`: liveness (`proces żyje`) vs readiness (`API i jego wymagane zależności są gotowe`). Najlepiej mieć `/health/live` i `/health/ready`; endpoint gotowości może sprawdzać połączenie z PostgreSQL przez backend, bez ujawniania connection string.
4. Upewnij się, że endpoint nie ujawnia tokenów, danych użytkowników, wersji wrażliwych zależności czy connection string.
5. Testy awarii wykonuj na mock serverze/stagingu, a nie przez celowe wyłączanie produkcyjnej aplikacji.

## Render i usypianie
Na planach z cold startami pierwsza odpowiedź może przekroczyć zwykły timeout. W MVP można wybrać dłuższy timeout (np. 20–30 s), rzadsze checki i 3 kolejne porażki przed alertem. `sleep-aware` to funkcja po MVP: konfiguracja oczekiwanego okna uśpienia, oddzielna klasyfikacja `COLD_START`, retry i ograniczenie alertów. Nie da się w pełni rozpoznać cold startu z samego HTTP bez dodatkowych sygnałów. Krótkie interwały mogą zmieniać zachowanie usypiania i zużycie limitu darmowego hostingu — sprawdź aktualne warunki Render.

## Security checklist — szczególnie SSRF
- Publicznie konfigurowalne URL w monitoringu są ryzykowne. W MVP dostęp tworzenia/edycji tylko dla administratora.
- Tylko `http`/`https`; blokuj localhost, loopback, private, link-local, multicast, IPv6 ULA, adresy metadata cloud, nieprawidłowe hosty i porty niezgodne z allowlist.
- Sprawdzaj **wszystkie** wyniki DNS i kontroluj docelowe IP także przy nawiązywaniu połączenia, aby ograniczyć DNS rebinding / TOCTOU. Preferuj bezpieczny transport, który łączy się ze zweryfikowanym IP zachowując Host/SNI.
- W MVP wyłącz przekierowania HTTP. Jeśli je kiedyś dodasz, waliduj każdy kolejny cel.
- Ogranicz response body, rozmiar nagłówków, timeout, concurrency i request rate.
- Nie wykonuj checków metodami zmieniającymi stan (POST/PUT/DELETE) w MVP.
- Nie zapisuj pełnych query params, credentiali z URL ani wrażliwej treści odpowiedzi.
- API klucz porównuj w sposób odporny na timing; rotuj sekret; rate limit; sieciowy allowlist przy publicznym API.
- Monitoring może mieć wpływ na dostępność targetu; nie testuj cudzych usług bez uprawnienia.

## Eksploatacja
- Health własnego systemu, logi JSON z `request_id`, `monitor_id`, `execution_id`.
- Backup Postgresa + regularna próbna procedura odtwarzania.
- Automatyczne migracje przy deployu lub osobny krok migracyjny, bez równoległego uruchamiania w każdej replice.
- Definiuj retencję pomiarów oraz limity maks. liczby monitorów.

## Obowiązujący wariant lokalny

Na życzenie użytkownika aktualna wersja działa wyłącznie na jego maszynie; wcześniejszy opis VPS/reverse proxy jest kierunkiem przyszłego wdrożenia, nie wymaganiem bieżącej instalacji. Użyj procedury `setup`/`run` z README. Domyślnie nie otwieramy portów do LAN ani internetu. PostgreSQL i panel nie korzystają z usług chmurowych.

Natywny klaster znajduje się w `.local/postgres`, działa na `127.0.0.1:54329` z SCRAM. Konfiguracja `.env` ma uprawnienia 600. API sprawdza nagłówek Host, klucz administratora, rozmiar body i budżet żądań; panel nie utrwala klucza w pamięci przeglądarki poza bieżącą kartą. Wyłączenie komputera przerywa monitoring.

Kopie zapasowe: podczas pracy lokalnego klastra można wykonać `pg_dump -h 127.0.0.1 -p 54329 -U sentinel -W -Fc sentinel -f /wybrana/sciezka/sentinel.dump`. Hasło wpisz interaktywnie. Weryfikację odtworzenia wykonuj na osobnym testowym klastrze, nigdy na bazie z pomiarami. Automatyczny backup i autostart systemowy nie zostały skonfigurowane.

Prawdziwe adresy DnD Companion i Discord webhook nie są zaszyte w kodzie. Brak webhooka wybiera ConsoleNotifier; nie wysłano żadnych rzeczywistych powiadomień w trakcie implementacji.

## Dashboard i sekrety 0.2

`FRONTEND_BIND`/`FRONTEND_PORT` sterują publikacją lokalnego Nginx. `ALLOWED_HOSTS` musi odpowiadać wybranym nazwom hosta. `API_UPSTREAM` w Compose wskazuje wewnętrzne API; klient używa względnych URL. VPS wymaga osobnego TLS, kontroli dostępu i backupów; nie jest wdrażany w tym zadaniu.

Kanały Discord przyjmują tylko kanoniczne HTTPS discord.com/api/webhooks/… bez query. `SECRETS_DIR` ma uprawnienia 700, pliki 600, zapis atomowy. To lokalne pliki jawne dostępne właścicielowi procesu, nie szyfrowany secret manager. Sekret nigdy nie wraca w odpowiedzi API. Rotacja: nowy kanał, przepięcie monitorów, usunięcie starego kanału. Soft-delete nie kasuje pliku; rollback utworzenia może pozostawić osierocony plik. Backup i kontrola dostępu do katalogu są obowiązkiem operatora.

Pusta lista kanałów monitora zachowuje dotychczasowy fallback env Discord/console. Jawne przypisanie usuniętego lub wyłączonego kanału nie przekieruje alertu do fallbacku. Test notification zapisuje outbox, wymaga działającego sendera i ma limit raz/min/kanał.

Publiczna strona statusowa jest dostępna bez klucza dopiero po ustawieniu published; nadal tylko przez interfejs sieciowy hosta. Nie wpisuj sekretów ani wewnętrznych adresów w publiczne nazwy/opisy. Jej API nie zwraca URL monitorów, powodów awarii, nagłówków ani konfiguracji.
