# API Sentinel — bieżący plan

Aktualizacja: 2026-11-18. React/Vite pozostaje frontendem, FastAPI backendem. Warianty: lokalny oraz GitHub Pages + Render Free + Neon. Darmowy hosting nie zapewnia ciągłego monitoringu podczas uśpienia.

## Zaimplementowane

- Dashboard, CRUD monitorów, historia, percentyle, timeline, incydenty, kanały Discord i publiczne strony statusowe.
- Konta, Argon2id, sesje i izolacja właścicieli; klucz API służy do pierwszego utworzenia właściciela, nie zwykłego logowania.
- Potwierdzanie adresu i reset hasła przez Gmail API; kolejka, szyfrowanie tokenów i diagnostyka błędów. Dostarczenie rzeczywistego maila wymaga osobnego potwierdzenia.
- Migracje, frontend lockfile, Compose oraz konfiguracja Pages/Render/Neon.

## Dowody z audytu 2026-11-18

- [x] Python: 142 PASS; 5 testów integracyjnych pominiętych.
- [x] Frontend: 17 PASS; build PASS; Ruff i mypy PASS.
- [ ] Powtórzyć integracje na izolowanej bazie sentinel_test i E2E obecnego commita.
- [ ] Clean install Compose i upgrade z kopii istniejącej bazy.
- [ ] Rzeczywista dostawa Gmail → potwierdzenie → reset → unieważnienie sesji i zużytego linku.

Historyczne wyniki pozostają w [VERIFICATION.md](VERIFICATION.md); nie zastępują aktualnych testów wdrożenia.

## Najbliższe poprawki

1. **P1 AS-01:** stan świeżości pomiarów na publicznych stronach; stary UP nie może wyglądać jak aktualna obserwacja. Test zatrzymania workera bez tworzenia sztucznego DOWN.
2. **P1 AS-02:** oddzielić budżety potwierdzeń/resetów; nieprawidłowy link A nie może zużyć wspólnego limitu prawidłowego linku B. Testy równoległości i limitów.
3. **P1 AS-04:** zakończyć konfigurację i test Gmail według [GMAIL_SETUP.md](GMAIL_SETUP.md), bez zapisywania sekretów w raporcie.
4. **P2 AS-03:** pokazać pokrycie okresu i retencję; 7 dni zachowanych prób nie oznacza pełnej historii 30 dni.
5. **P2 AS-05:** zamrozić zależności Pythona, używać npm ci w CI, dodać kontrolę zależności.

Aktualizacja 2026-11-19: AS-01/02/03 zaimplementowane wraz z testami regresji;
AS-04 ma kod diagnostyki i migrację 0006, ale rzeczywista dostawa Gmail pozostaje
otwartą bramką. Testy PostgreSQL/E2E wymagają uruchomienia poza sandboxem.
AS-05 (zamrożenie zależności) pozostaje osobnym otwartym zadaniem.
Szczegóły aktualnego wykonania: [VERIFICATION.md](VERIFICATION.md).

## Później

TLS expiry, maintenance windows, pełne DNS/connect/TTFB/download, wiele lokalizacji i kolejne kanały alertów. Konta wielu użytkowników już istnieją; poczta odzyskiwania kont nie oznacza kanału email dla alertów monitoringu. Każde rozszerzenie wymaga własnego kontraktu i testów.
