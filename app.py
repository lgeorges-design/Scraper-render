import os
from flask import Flask, request, jsonify
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup
import requests, re
from tenacity import retry, wait_exponential, stop_after_attempt
from datetime import date
from playwright.sync_api import sync_playwright

app = Flask(__name__)

class JobItem(BaseModel):
    date: str = Field(default_factory=lambda: date.today().isoformat())
    source: str = ""
    entreprise: str = ""
    localisation: str = ""
    secteur: str = ""
    taille_entreprise: str = ""
    poste: str = ""
    experience_demandee: str = ""
    competences: list[str] = []
    score: int = 0
    pitch: str = ""
    statut: str = "À traiter"
    date_candidature: str = ""
    date_reponse: str = ""
    delai_reponse: str = ""
    commentaires: str = ""

def normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

# -------- Static adapter (requests + BS) ----------
@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
def fetch_static(url: str) -> list[JobItem]:
    resp = requests.get(url, timeout=30, headers={"User-Agent":"Mozilla/5.0"})
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobItem] = []
    # Generic selectors (to customize per site later)
    for card in soup.select("[data-job-card], .job-card, article"):
        title_el = card.select_one("[data-testid='job-title'], .title, h2, a")
        company_el = card.select_one(".company, .employer, [data-testid='company-name']")
        loc_el = card.select_one(".location, [data-testid='location']")
        poste = normalize(title_el.get_text() if title_el else "")
        entreprise = normalize(company_el.get_text() if company_el else "")
        localisation = normalize(loc_el.get_text() if loc_el else "")
        if poste:
            jobs.append(JobItem(source=url, poste=poste, entreprise=entreprise, localisation=localisation))
    return jobs

# -------- Dynamic adapter (Playwright) ------------
def fetch_dynamic(url: str) -> list[JobItem]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent="Mozilla/5.0")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Scroll to trigger lazy loading
        for _ in range(8):
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(400)
        jobs: list[JobItem] = []
        # Generic selectors (customize per site)
        cards = page.query_selector_all("[data-job-card], .job-card, article")
        for c in cards:
            title = c.query_selector("[data-testid='job-title'], .title, h2, a")
            poste = normalize(title.inner_text() if title else (c.inner_text().splitlines()[0] if c.inner_text() else ""))
            if poste:
                jobs.append(JobItem(source=url, poste=poste))
        browser.close()
    return jobs

def select_adapter(url: str):
    dynamic_domains = ["jobs.makesense.org", "welcometothejungle.com"]
    return fetch_dynamic if any(d in url for d in dynamic_domains) else fetch_static

@app.get("/healthz")
def health():
    return "ok", 200

@app.post("/echo")
def echo():
    # Utility endpoint for quick testing from Make/Postman
    try:
        data = request.get_json(force=True)
    except Exception:
        data = {"raw": request.data.decode("utf-8", errors="ignore")}
    return jsonify({"received": data})

@app.post("/scrape")
def scrape():
    payload = request.get_json(force=True) or {}
    urls: list[str] = payload.get("urls", [])
    out: list[dict] = []
    for u in urls:
        try:
            adapter = select_adapter(u)
            items = adapter(u)
            out.extend([i.model_dump() for i in items])
        except Exception as e:
            out.append(JobItem(source=u, commentaires=f"ERROR: {type(e).__name__}: {e}").model_dump())
    return jsonify(out)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
