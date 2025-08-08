from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import re
from datetime import datetime

app = Flask(__name__)

# =====================
# Helpers
# =====================
class JobItem(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.update({
            "commentaires": "",
            "competences": [],
            "date": datetime.today().strftime("%Y-%m-%d"),
            "date_candidature": "",
            "date_reponse": "",
            "delai_reponse": "",
            "entreprise": "",
            "experience_demandee": "",
            "localisation": "",
            "pitch": "",
            "poste": "",
            "score": 0,
            "secteur": "",
            "source": "",
            "statut": "À traiter",
            "taille_entreprise": ""
        })

def set_if(job, field, value):
    if value and value.strip():
        job[field] = value.strip()

def uniq(jobs):
    seen = set()
    out = []
    for j in jobs:
        key = j["commentaires"]
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out

# =====================
# Scraper HelloWork
# =====================
def fetch_hellowork(url: str) -> list:
    jobs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(locale="fr-FR")
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=90000)

        # Accepter cookies si bouton présent
        for txt in ["Tout accepter", "Accepter", "J’accepte", "J'accepte", "OK"]:
            try:
                page.get_by_role("button", name=txt, exact=False).click(timeout=2000)
                break
            except:
                pass

        # Scroll pour charger toutes les offres
        for _ in range(12):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(300)

        links = page.locator("a[href*='/fr-fr/emplois/']")
        count = links.count()
        print(f"[DEBUG] Liens détectés HelloWork: {count}")

        for i in range(count):
            href = links.nth(i).get_attribute("href") or ""
            if not re.search(r"/emplois/\d+\.html$", href):
                continue  # Garde uniquement les vraies annonces

            if href.startswith("/"):
                href = f"https://www.hellowork.com{href}"

            # Remonter à l'article parent
            container = links.nth(i).locator("xpath=ancestor::article[1]")

            title = ""
            try:
                title = (container.locator("h3, h2").first.inner_text() or "").strip()
            except:
                pass

            company = ""
            try:
                company = (container.locator(".company, [data-testid='company-name']").first.inner_text() or "").strip()
            except:
                pass

            location = ""
            try:
                location = (container.locator(".location, [data-testid='location']").first.inner_text() or "").strip()
            except:
                pass

            if not title:
                continue

            job = JobItem(source="hellowork", poste=title)
            set_if(job, "entreprise", company)
            set_if(job, "localisation", location)
            job["commentaires"] = href
            jobs.append(job)

        browser.close()
    return uniq(jobs)

# =====================
# Scraper Makesense (exemple)
# =====================
def fetch_makesense(url: str) -> list:
    jobs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(locale="fr-FR")
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=90000)

        for _ in range(8):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(300)

        cards = page.locator("a[href*='/fr/s/jobs/']")
        count = cards.count()
        print(f"[DEBUG] Liens détectés Makesense: {count}")

        for i in range(count):
            href = cards.nth(i).get_attribute("href") or ""
            if not href.startswith("http"):
                href = f"https://jobs.makesense.org{href}"

            title = ""
            try:
                title = (cards.nth(i).inner_text() or "").strip().split("\n")[0]
            except:
                pass

            if not title:
                continue

            job = JobItem(source="makesense", poste=title)
            job["commentaires"] = href
            jobs.append(job)

        browser.close()
    return uniq(jobs)

# =====================
# Routes Flask
# =====================
@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})

@app.route("/scrape", methods=["POST"])
def scrape():
    data = request.get_json(force=True)
    urls = data.get("urls", [])
    all_jobs = []

    for url in urls:
        if "hellowork.com" in url:
            all_jobs.extend(fetch_hellowork(url))
        elif "makesense" in url:
            all_jobs.extend(fetch_makesense(url))
        else:
            print(f"[WARN] Source non gérée: {url}")

    return jsonify(all_jobs)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)