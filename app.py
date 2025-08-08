import os, sys, re
from datetime import date

from flask import Flask, request, jsonify
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup
import requests
from tenacity import retry, wait_exponential, stop_after_attempt
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# =========
# Data model
# =========
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
    commentaires: str = ""  # j'y mets le lien de l'offre pour l’instant


# =========
# Helpers
# =========
def normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def uniq(seq: list[JobItem]) -> list[JobItem]:
    seen = set()
    out: list[JobItem] = []
    for x in seq:
        key = (x.poste, x.entreprise, x.localisation, x.commentaires)
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out

def set_if(obj: JobItem, name: str, value: str | None):
    if value and isinstance(value, str):
        setattr(obj, name, normalize(value))


# =========================
# Generic static/dynamic fetch
# =========================
@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
def fetch_static(url: str) -> list[JobItem]:
    """Requests + BS4 for simple/static pages (fallback)."""
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    jobs: list[JobItem] = []

    # Sélecteurs génériques (peuvent matcher sur certains sites)
    for card in soup.select("[data-job-card], .job-card, article"):
        title_el = card.select_one("[data-testid='job-title'], .title, h2, a")
        company_el = card.select_one(".company, .employer, [data-testid='company-name']")
        loc_el = card.select_one(".location, [data-testid='location']")
        poste = normalize(title_el.get_text()) if title_el else ""
        entreprise = normalize(company_el.get_text()) if company_el else ""
        localisation = normalize(loc_el.get_text()) if loc_el else ""
        if poste:
            item = JobItem(source=url, poste=poste, entreprise=entreprise, localisation=localisation)
            jobs.append(item)

    return jobs


def fetch_dynamic(url: str) -> list[JobItem]:
    """Playwright pour pages dynamiques (fallback générique)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent="Mozilla/5.0")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # scroll pour lazy-load
        for _ in range(8):
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(400)

        jobs: list[JobItem] = []
        cards = page.query_selector_all("[data-job-card], .job-card, article")
        for c in cards:
            title = c.query_selector("[data-testid='job-title'], .title, h2, a")
            poste = normalize(title.inner_text() if title else (c.inner_text().splitlines()[0] if c.inner_text() else ""))
            if poste:
                jobs.append(JobItem(source=url, poste=poste))

        browser.close()
    return jobs


# =========================
# Adapter: HelloWork (listing)
# =========================
def fetch_hellowork(url: str) -> list[JobItem]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent="Mozilla/5.0")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Cookies (essaye divers libellés)
        for txt in ["Tout accepter", "Accepter", "J’accepte", "J'accepte", "OK"]:
            try:
                page.get_by_role("button", name=txt, exact=False).click(timeout=2000)
                break
            except Exception:
                pass

        # Lazy load
        for _ in range(10):
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(350)

        jobs: list[JobItem] = []

        selectors = [
            "article[data-testid='job-card']",
            "article[data-qa='job-card']",
            "article.card-offer, article",
        ]
        cards = []
        for sel in selectors:
            nodes = page.query_selector_all(sel)
            if nodes:
                cards = nodes
                break

        for c in cards:
            title = (c.query_selector("[data-testid='job-title']") or
                     c.query_selector("h3, h2, .title, a[title]"))
            poste = normalize(title.inner_text()) if title else ""

            company = (c.query_selector("[data-testid='company-name']") or
                       c.query_selector(".company, .recruiter, [itemprop='hiringOrganization']"))
            entreprise = normalize(company.inner_text()) if company else ""

            loc = (c.query_selector("[data-testid='location']") or
                   c.query_selector(".location, [itemprop='addressLocality']"))
            localisation = normalize(loc.inner_text()) if loc else ""

            link = (c.query_selector("a[href*='/emploi/']") or
                    c.query_selector("a[href*='offre']") or
                    c.query_selector("a"))
            lien = link.get_attribute("href") if link else ""
            if lien and lien.startswith("/"):
                base = page.url.split("/", 3)
                if len(base) >= 3:
                    lien = f"{base[0]}//{base[2]}{lien}"

            if poste:
                item = JobItem(source="hellowork", poste=poste)
                set_if(item, "entreprise", entreprise)
                set_if(item, "localisation", localisation)
                item.commentaires = lien or ""
                jobs.append(item)

        browser.close()
        return uniq(jobs)


# ==================================
# Adapter: Jobs That Make Sense (JMS)
# ==================================
def fetch_makesense(url: str) -> list[JobItem]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent="Mozilla/5.0")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        for txt in ["Tout accepter", "Accepter", "J’accepte", "J'accepte", "OK"]:
            try:
                page.get_by_role("button", name=txt, exact=False).click(timeout=2000)
                break
            except Exception:
                pass

        for _ in range(12):
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(300)

        jobs: list[JobItem] = []
        selectors = [
            "[data-testid='job-card']",
            "article[data-testid='listing-card']",
            "article.card, div.job-card, article"
        ]
        cards = []
        for sel in selectors:
            nodes = page.query_selector_all(sel)
            if nodes:
                cards = nodes
                break

        for c in cards:
            title = (c.query_selector("[data-testid='job-title']") or
                     c.query_selector("h3, h2, a"))
            poste = normalize(title.inner_text()) if title else ""

            company = (c.query_selector("[data-testid='company-name']") or
                       c.query_selector(".company, .employer"))
            entreprise = normalize(company.inner_text()) if company else ""

            loc = (c.query_selector("[data-testid='location']") or
                   c.query_selector(".location"))
            localisation = normalize(loc.inner_text()) if loc else "Paris (75)"

            link = (c.query_selector("a[href*='/fr/s/jobs/']") or c.query_selector("a"))
            lien = link.get_attribute("href") if link else ""
            if lien and lien.startswith("/"):
                base = page.url.split("/", 3)
                if len(base) >= 3:
                    lien = f"{base[0]}//{base[2]}{lien}"

            if poste:
                item = JobItem(source="jobs.makesense", poste=poste)
                set_if(item, "entreprise", entreprise)
                set_if(item, "localisation", localisation)
                item.commentaires = lien or ""
                jobs.append(item)

        browser.close()
        return uniq(jobs)


# =========================
# Adapter selector (router)
# =========================
def select_adapter(url: str):
    if "hellowork.com" in url:
        return fetch_hellowork
    if "jobs.makesense.org" in url:
        return fetch_makesense
    dynamic_domains = ["welcometothejungle.com"]
    return fetch_dynamic if any(d in url for d in dynamic_domains) else fetch_static


# =========
# Routes
# =========
@app.get("/")
def root():
    return "ok", 200

@app.get("/healthz")
def health():
    return "ok", 200

@app.post("/echo")
def echo():
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


# =========
# Main
# =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"[boot] Starting Flask on 0.0.0.0:{port}", file=sys.stderr, flush=True)
    app.run(host="0.0.0.0", port=port)
