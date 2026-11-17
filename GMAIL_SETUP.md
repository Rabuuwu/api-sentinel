# Gmail: potwierdzanie kont i reset hasła

Nadawca: `adam.bielas.praca@gmail.com`. Aplikacja korzysta z **Gmail API przez HTTPS**.
Render Free blokuje SMTP 25/465/587, dlatego nie używamy hasła aplikacji ani SMTP.
Nie potrzeba własnego serwera pocztowego ani płatnego dostawcy. Obowiązują limity Gmaila/Google.

## 1. Google Cloud — jednorazowa konfiguracja właściciela

1. Wejdź do https://console.cloud.google.com/ na konto nadawcy. Utwórz projekt, np. `API Sentinel Mail`.
2. **APIs & Services → Library → Gmail API → Enable**.
3. W **Google Auth Platform** skonfiguruj Branding/Audience (zewnętrzna aplikacja / External).
   Nazwa: API Sentinel Mail; adres kontaktowy: Twój Gmail.
4. W Data Access dodaj wyłącznie zakres `https://www.googleapis.com/auth/gmail.send`.
   Nie dodawaj dostępu do czytania poczty, kontaktów ani pełnego `mail.google.com`.
5. Jeśli aplikacja jest w trybie Testing, dodaj swój Gmail jako test user.
   **Testing daje refresh token ważny tylko 7 dni** dla tego zakresu. Do trwałego działania
   ustaw Audience / Publishing status na **In production**, a następnie wygeneruj nowy token.
   Google może pokazać ostrzeżenie o nieweryfikowanej aplikacji lub wymagać dodatkowych kroków.
   To autoryzacja Twojego własnego projektu przez Ciebie; użytkownicy Sentinel nie logują się do Google.
   Stosuj wymagania widoczne w konsoli. Nie obiecujemy, że samo ustawienie Production usuwa
   wymagania weryfikacji albo gwarantuje bezterminową ważność tokenu.
6. **Clients → Create client → Desktop app**. Pobierz JSON klienta OAuth.
   Nie twórz konta usługi — zwykły Gmail wymaga zgody użytkownika.

## 2. Autoryzacja na Twoim Macu

Zapisz pobrany plik jako:
`/Users/macminisk/Projekty/api-sentinel/.local/google-oauth-client.json`.
Folder `.local/` jest ignorowany przez Git. Nie wysyłaj pliku ani jego zawartości na czat.

```sh
cd /Users/macminisk/Projekty/api-sentinel
.venv/bin/python -m pip install -e '.[gmail-setup]'
.venv/bin/python scripts/gmail_authorize.py
```

Skrypt otworzy stronę autoryzacji Google. Wybierz **adam.bielas.praca@gmail.com** i potwierdź
uprawnienie do wysyłki. Lokalny callback działa na loopback; nie konfigurujesz go w Renderze.
Sekrety zapiszą się w `.local/gmail-render.env` z uprawnieniami `600` — nie zostaną wypisane do konsoli.
Skrypt nie wysyła wiadomości, nie czyta skrzynki i nie dodaje sekretów do repozytorium.

## 3. Render → api-sentinel → Environment

Dodaj **razem** poniższe wartości, a następnie wybierz **Save, rebuild, and deploy**:

| Zmienna | Wartość |
|---|---|
| `GMAIL_CLIENT_ID` | z `.local/gmail-render.env` |
| `GMAIL_CLIENT_SECRET` | z `.local/gmail-render.env` |
| `GMAIL_REFRESH_TOKEN` | z `.local/gmail-render.env` |
| `MAIL_FROM` | `adam.bielas.praca@gmail.com` |
| `PUBLIC_APP_URL` | `https://rabuuwu.github.io/api-sentinel/` — faktyczny adres panelu, bez `#`, query ani `/api/v1` |
| `WEBHOOK_ENCRYPTION_KEY` | **Zachowaj istniejącą wartość**, używana też do szyfrowania kolejki e-mail |

Nie umieszczaj sekretów w GitHub Actions Variables, `VITE_*`, render.yaml ani frontendzie.
W Render `Add from .env` możesz wkleić tylko trzy wiersze z pliku OAuth; nie importuj całego
lokalnego `.env`, który może wskazywać inną bazę. Hasło aplikacji Gmail nie jest potrzebne.
Brak wszystkich trzech sekretów oznacza wyłączoną pocztę. Częściowe ustawienie daje czytelny błąd
konfiguracji. Login istniejących kont pozostaje dostępny bez poczty.

## 4. Wdrożenie kodu i pierwsze sprawdzenie

Przed migracją zrób backup bazy. Najpierw testy na izolowanej bazie:

```sh
bash scripts/test_accounts.sh
```

Migracja `0005` dodaje pola e-mail oraz tabele `email_actions` i `mail_deliveries`.
Nie przypisuje Twojego adresu do żadnego konta automatycznie i nie blokuje istniejących kont.
Wdróż najnowszy backend i frontend. Render launcher wykona migrację.

1. Zaloguj się do Sentinel → **Settings → Recovery email**.
2. Wpisz swój adres i aktualne hasło → **Send confirmation email**.
3. Odbierz wiadomość (sprawdź Spam), otwórz link i kliknij **Confirm email**.
   Samo otwarcie linku przez skaner poczty nie zużywa tokenu.
4. Po potwierdzeniu zaloguj się ponownie. Adres powinien być pokazany jako zweryfikowany.
5. Wyloguj się → **Forgot password?** → podaj zweryfikowany adres.
6. Link resetu pozwoli ustawić nowe hasło i unieważni wszystkie dotychczasowe sesje.
7. Utwórz zaproszenie dla dodatkowego użytkownika: rejestracja wymaga teraz e-maila;
   konto nie zaloguje się przed potwierdzeniem adresu. W razie potrzeby użyj **Resend confirmation**.

## Bezpieczeństwo i zachowanie

- Adres nadawcy jest tylko konfiguracją transportu, nie automatycznie adresem konta właściciela.
- Rejestracja nadal wymaga zaproszenia. Początkowy bootstrap nadal wymaga klucza instalacji.
- Przy włączonej poczcie nowe konta (również pierwszy właściciel) wymagają potwierdzenia adresu.
  Istniejące konta nie tracą dostępu; dodają adres w Settings po ponownym podaniu hasła.
- Reset działa wyłącznie dla **potwierdzonego** adresu. Taki sam komunikat dla nieistniejącego adresu;
  wysyłka poza żądaniem HTTP i minimalny czas odpowiedzi ograniczają ujawnianie istnienia konta.
- Token 256 bitów, w bazie SHA-256, związany z użytkownikiem, adresem i konkretną operacją.
  Reset ważny 15 minut, potwierdzenie 60 minut. Nowy link tego samego typu unieważnia poprzedni.
- Zużycie tokenu i zmiana danych są atomowe. Reset, potwierdzenie adresu, zmiana hasła
  i reset operatorski unieważniają odpowiednie sesje/tokeny. Reset anuluje oczekującą zmianę adresu.
- Dotychczasowy zweryfikowany adres pozostaje aktywny do potwierdzenia nowego.
- Linki zawierają token we fragmencie `#`, nie w żądaniach HTTP. Panel usuwa go z widocznego URL.
  Żaden link nie bierze adresu docelowego z Host header ani danych żądania.
- Kolejka trwała w PostgreSQL; treść/link szyfrowane Fernet i związane z ID wiadomości.
  Po przyjęciu przez Gmail albo trwałym błędzie ciphertext jest usuwany, a po wygaśnięciu
  akcji cała pozycja jest czyszczona. Nie zapisujemy tokenów ani odpowiedzi Google do logów.
- Maks. 3 żądania wysyłki na adres/godzinę, 30 globalnie/godzinę. Nie przekazuj kodów/linków innym.
- Maks. 5 prób dostarczenia, odstęp rośnie. Przy awarii po akceptacji przez Gmail może przyjść duplikat;
  token nadal jest jednorazowy. HTTP 200 Gmail oznacza przyjęcie, nie dowód doręczenia do Inbox.
- Administrator widzi liczniki kolejki w Settings. Logi mają wyłącznie ogólne kody błędów.

## Problemy i odzyskiwanie

- `GMAIL_AUTH_FAILED`: sprawdź klienta, refresh token i zgodę konta; wygeneruj nowy token.
  Token może zostać unieważniony m.in. po cofnięciu zgody lub zmianie hasła Google.
- `GMAIL_SEND_FAILED`: sprawdź, czy Gmail API jest włączone, zakres `gmail.send` zaakceptowany,
  konto nadawcy zgodne z MAIL_FROM oraz limity Google. Wyślij nowy link po naprawie konfiguracji.
- `GMAIL_NETWORK_ERROR`: kolejka spróbuje ponownie. `MAIL_DECRYPT_FAILED`: sprawdź klucz
  szyfrowania; nie zmieniaj go podczas zwykłego redeployu.
- Render Free usypia worker. Żądanie do API go budzi, ale dostarczenie nie jest gwarantowane
  w konkretnym czasie. Wygasły link zastąp nowym.
- Dopóki nie potwierdzisz adresu, odzyskanie starego konta wymaga operatora:
  `.venv/bin/python -m api_sentinel.reset_password` na komputerze z właściwą konfiguracją DB.
- Brak publicznej rejestracji, zmian modelu zaproszeń, MFA i logowania przez Google.
  Google OAuth służy tylko autoryzacji nadawcy wiadomości.

Źródła: [Render Free](https://render.com/docs/free),
[Google OAuth i wygasanie tokenów](https://developers.google.com/identity/protocols/oauth2),
[Gmail API — wysyłka](https://developers.google.com/workspace/gmail/api/guides/sending),
[Zakresy Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes).
