# Job Scraper (Render + Docker + Playwright)

Micro-service HTTP qui scrape des pages d'offres d'emploi (statique ou dynamique) et renvoie un JSON normalisé.

## Endpoints

- `GET /healthz` → retourne `ok`
- `POST /echo` → renvoie le payload reçu (utile pour tester Render et Make)
- `POST /scrape` (body JSON) :
  ```json
  {
    "urls": [
      "https://example.com/jobs"
    ]
  }
  ```

## Déploiement (Render)

1. Poussez ce dossier dans un repo GitHub/GitLab
2. Sur Render, "New +" → "Web Service" → connectez le repo
3. Render détecte le `Dockerfile` (aucun build/start command à saisir)
4. Une fois déployé, testez `https://<votre-service>.onrender.com/healthz`

## Dev local

```bash
docker build -t job-scraper .
docker run -p 8000:8000 job-scraper
curl -s http://localhost:8000/healthz
```
