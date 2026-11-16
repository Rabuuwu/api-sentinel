# Dashboard na GitHub Pages

Frontend React może działać na Pages, niezależnie od miejsca uruchomienia FastAPI. GitHub Pages nie uruchamia Pythona, schedulera ani PostgreSQL. Monitoring wymaga działającego backendu i workera.

## Przygotowane w repozytorium

- `npm run build:pages --prefix frontend`: osobny build `frontend/dist-pages`, bez nadpisywania lokalnego `frontend/dist`.
- Domyślna ścieżka `/api-sentinel/`; `VITE_BASE_PATH` pozwala ją zmienić.
- HashRouter w trybie pages: podstrony mają adres np. `/api-sentinel/#/monitors`. Odświeżanie i bezpośrednie linki nie wymagają serwerowego SPA fallback.
- `VITE_API_BASE_URL` jest wymaganym adresem HTTPS zakończonym `/api/v1`. Build odrzuca adres z loginem/hasłem, query lub fragmentem.
- Klucz administratora nadal wpisuje użytkownik. Nie zapisuj go jako zmiennej VITE, w URL, workflow ani artefaktach.
- `.github/workflows/pages.yml`: testy, build i publikacja samego `dist-pages`.

## Ustawienia backendu

W środowisku API ustaw:

```dotenv
CORS_ORIGINS=https://rabuuwu.github.io
```

Origin nie zawiera `/api-sentinel/` ani końcowego ukośnika. CORS ufa całemu originowi konta Pages, nie jednej ścieżce. API nadal wymaga X-API-Key; CORS nie zastępuje autoryzacji. `ALLOWED_HOSTS` musi dopuszczać hostname API używany przez proxy/hosting. Nie wpisuj tam domeny panelu tylko dlatego, że wykonuje żądania.

W Compose CORS_ORIGINS jest przekazywane do aplikacji. Lokalny tryb działa jak wcześniej; domyślna lista CORS jest pusta. Zmiany zmiennych wymagają restartu API.

## Konfiguracja GitHub

1. Zapewnij działający backend HTTPS i sprawdź jego `/health/ready` oraz heartbeat workera w panelu lokalnym.
2. Repozytorium → Settings → Pages → Source: **GitHub Actions**.
3. Settings → Secrets and variables → Actions → **Variables**: dodaj `SENTINEL_API_BASE_URL`, np. `https://twoje-api.onrender.com/api/v1`. To publiczny adres, nie sekret. Nie kopiuj przykładowego hosta jako prawdziwego.
4. Wypchnij kod i w Actions uruchom **Deploy dashboard to GitHub Pages**. Kolejne zmiany frontendu na main uruchamiają workflow automatycznie.
5. Po udanym deployu otwórz URL zwrócony przez workflow. Dla tego repo powinien mieć postać `https://rabuuwu.github.io/api-sentinel/`.

Prywatne repozytorium wymaga planu GitHub obsługującego Pages dla prywatnych repozytoriów. Samo posiadanie publicznego portfolio nie zapewnia Pages dla innego prywatnego repo. Nie zmieniono widoczności repozytorium automatycznie. Publiczne pliki panelu nie zawierają historii pomiarów ani klucza API; dane pobierane są z backendu po uwierzytelnieniu (opublikowane strony statusowe mają osobny publiczny kontrakt).

## Wybrany hosting backendu

Użytkownik wybrał Render Free dla API/schedulera oraz osobny PostgreSQL Neon Free. Gotowy Blueprint i pełna instrukcja: [RENDER_NEON.md](RENDER_NEON.md). GitHub Pages hostuje wyłącznie frontend. Usługa Render Free może zasypiać; w tym czasie monitoring nie działa. Nie utworzono zasobów z tej sesji.

## Weryfikacja

Build Pages sprawdzony z jawnym przykładowym adresem HTTPS (nie jest wdrożeniem). Testy CORS sprawdzają poprawny preflight, brak zgody dla obcych originów oraz zachowanie 401 bez klucza. Nie potwierdzono publikacji na Pages ani dostępu z telefonu. Odbiór wymaga rzeczywistego adresu API i udanego workflow.

Źródła: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [Vite](https://vite.dev/guide/static-deploy), [Render Free](https://render.com/docs/free).
