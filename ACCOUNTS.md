# Konta użytkowników API Sentinel

Backend pozostaje FastAPI, baza PostgreSQL (lokalna lub Neon), dashboard React/Pages.
Nie używamy dodatkowej usługi logowania ani płatnych usług.

## Wdrożenie i stare dane

1. Wykonaj backup bazy przed zmianą. Najpierw zweryfikuj migracje i testy na odrębnej bazie.
2. Wdróż backend zawierający migrację `0004` i dashboard z tego samego commita.
   Launcher Render wykonuje `alembic upgrade head` przed uruchomieniem API/workera.
3. Przy pierwszym wejściu panel pokaże „Create owner account”. Podaj login, unikalną
   frazę hasła (15–128 znaków), potwierdzenie i aktualny `SENTINEL_API_KEY` z Render Environment.
   Jeżeli wcześniej ujawniłeś klucz, zmień go przed wdrożeniem.
4. Jedna transakcja tworzy konto administratora i przypisuje mu wszystkie stare monitory,
   kanały powiadomień oraz strony statusowe. Historia pozostaje przy monitorach.
   Równoczesna próba bootstrapu zostanie odrzucona. Samo otwarcie panelu nie przejmuje danych.
5. Od tej chwili używaj loginu i hasła. Klucz instalacji nie pozwala czytać API ani przejąć
   kolejnego konta. Zachowaj zmienną w konfiguracji — aktualny Settings nadal wymaga jej obecności.
6. Settings → Account security → Create invitation: skopiuj jednorazowy kod i przekaż
   go prywatnie wybranej osobie. Wygasa po 24 godzinach. Użytkownik wybiera
   „I have an invitation” i tworzy własne konto bez uprawnień administratora.

Pierwszy administrator widzi własne monitory oraz listę loginów/roli kont; nie otrzymuje dostępu
 do monitorów innych osób. Nie ma wspólnego workspace ani automatycznego dzielenia danych.
Nowe konto startuje puste. Publiczne strony statusowe pozostają świadomie publikowanym wyjątkiem.
Stary interfejs `/legacy` zwraca 410, a `X-API-Key` nie działa.

## Hasła i sesje

- Argon2id: 19 MiB, 2 iteracje, 1 lane, losowa sól 16 bajtów, wynik 32 bajty w formacie PHC.
  Implementacja biblioteki cryptography; brak własnego algorytmu kryptograficznego.
- Losowe tokeny sesji i zaproszeń mają 256 bitów entropii. Baza przechowuje tylko SHA-256 tokenów.
- Frontend trzyma token w pamięci i przesyła go w `Authorization: Bearer`. Nie używa localStorage,
  sessionStorage ani cookies; reload wymaga logowania. To działa także między Pages a Render bez
  polegania na cookies stron trzecich. Token jest dostępny dla JS: ochrona przed XSS nadal jest konieczna.
- Wylogowanie unieważnia sesję na serwerze. Zmiana hasła i „Sign out all sessions” unieważniają wszystkie.
- Maksymalnie 5 sesji na konto, 8 godzin bezwzględnego czasu życia i 30 minut bez żądań.
  Automatyczne odświeżanie panelu liczy się jako aktywność; zamknięcie karty nie wysyła logout.
- Limit prób zapisany w bazie: 8 / 5 minut na login, 60 / 5 minut globalnie. Budżet obejmuje także
  rejestrację, zmianę hasła i zaproszenia. Przetrwa restart; nie ufa nagłówkom z adresem IP.
- CORS dopuszcza wyłącznie skonfigurowane originy i Authorization. Nie przyjmujemy sesji z URL/cookies.
  Poza localhost wymagany jest HTTPS zapewniany przez hosting; CORS nie zastępuje autoryzacji.

## Izolacja i limity

Każda prywatna operacja sprawdza właściciela z sesji. Próby podmiany monitor_id, channel_id,
page_id lub przypisania cudzego zasobu są odrzucane. Widoki zbiorcze, percentyle, incydenty
 i alerty też są ograniczone do użytkownika. Worker pozostaje globalny, obsługuje wszystkie konta.
Globalny Discord webhook nie jest fallbackiem dla monitorów z przypisanym właścicielem:
przypisz własny kanał do monitora. Bez kanału zdarzenie trafia do logu konsoli serwera.

MAX_MONITORS jest nadal globalnym limitem instalacji (Free domyślnie 10). Maksymalnie
100 kont, 20 aktywnych zaproszeń, 50 aktywnych kanałów i 50 stron statusowych na konto. Nie jest to publiczny,
nieograniczony SaaS; rejestracja jest dostępna wyłącznie na zaproszenie.

## Odzyskanie dostępu

Opcjonalny reset przez potwierdzony e-mail opisuje [GMAIL_SETUP.md](GMAIL_SETUP.md). Bez skonfigurowanej poczty operator z dostępem do konfiguracji bazy
może uruchomić na swoim komputerze (z .env wskazującym właściwą bazę):

```sh
.venv/bin/python -m api_sentinel.reset_password
```

Skrypt pyta o login i dwukrotnie o nowe hasło przez ukryte wejście terminala, a następnie
unieważnia sesje tego konta. Nie wpisuj hasła do argumentów polecenia ani czatu.
Nie wywołuje migracji, nie przydziela roli administratora i nie przenosi danych między kontami.

## Testy i ograniczenia

`pytest` obejmuje testy haseł i kontraktów. Testy integracyjne sprawdzają HTTP + PostgreSQL:
bootstrap, migrację własności, jednorazowe zaproszenia, próby IDOR, hashe, logout, zmianę hasła,
limity prób i wygasanie sesji. Wymagają **dedykowanej pustej bazy localhost `sentinel_test`**.
Pełny lokalny test na osobnym klastrze (port PostgreSQL 54339, HTTP 54349):

```sh
bash scripts/test_accounts.sh
```

Skrypt wymaga lokalnych narzędzi PostgreSQL, zależności projektu i przeglądarki Playwright.
Tworzy wyłącznie `sentinel_test`, nie zmienia Neon. Zachowuje klaster testowy po zakończeniu.

Browser E2E obejmuje logowanie, zaproszenie drugiego konta i CRUD monitora.
Wyniki faktycznych uruchomień: VERIFICATION.md.

Brak MFA, self-service usuwania kont, blokowania kont i współdzielonych zespołów. Potwierdzanie e-maila jest opcjonalne przez Gmail API.
Admin może unieważnić sesje, ale nie blokuje to ponownego logowania poprawnym hasłem.
Globalny limit prób może czasowo zablokować innych użytkowników przy ataku — celowy limit kosztów
małej instalacji; większe wdrożenie wymaga dodatkowego rate limitera na brzegu sieci.
RLS nie jest włączone: autoryzację egzekwuje API, a dostęp operatora do DB nadal obejmuje wszystkie dane.
Nie deklarujemy niezależnego audytu bezpieczeństwa. Render Free nadal usypia monitoring.


Podstawa doboru zabezpieczeń: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[cryptography Argon2id](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/).

Po włączeniu Gmail API nowe konta wymagają potwierdzenia adresu przed logowaniem. Istniejące konta pozostają aktywne i dodają adres w Settings → Recovery email.
