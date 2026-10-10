import json
import os
import re
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

# Science and teaching roles
TEACHING_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", 
    "physical science", "science"
]

# Aide and paraprofessional roles
AIDE_KEYWORDS = [
    "aide", "instructional", "associate", 
    "paraeducator", "para educator", "paraprofessional", 
    "lab tech", "science tech", "supervision"
]

# Key target districts covering Menlo Park (94025), San Mateo County, and North Santa Clara
DISTRICT_URLS = [
    ("Sequoia Union High School District (Menlo Park 94025)", "https://www.edjoin.org/sequhsd"),
    ("San Mateo Union High School District", "https://www.edjoin.org/SanMateoUnion"),
    ("Palo Alto Unified School District", "https://www.edjoin.org/pausd"),
    ("Mountain View-Los Altos High School District", "https://www.edjoin.org/mvla"),
    ("Fremont Union High School District", "https://www.edjoin.org/fuhsd"),
    ("San Mateo-Foster City School District", "https://www.edjoin.org/SanMateoFoster"),
    ("Redwood City School District", "https://www.edjoin.org/rcsd"),
    ("Belmont-Redwood Shores School District", "https://www.edjoin.org/brssd"),
    ("Menlo Park City School District", "https://www.edjoin.org/mpcsd"),
    ("Jefferson Union High School District", "https://www.edjoin.org/juhsd"),
    ("Cabrillo Unified School District", "https://www.edjoin.org/cabrillo"),
    ("San Mateo County Office of Education", "https://www.edjoin.org/SMCOE"),
]

def load_seen():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen_ids):
    with open(DB_FILE, "w") as f:
        json.dump(list(seen_ids), f, indent=2)

def is_match(title):
    t = title.lower()
    for kw in TEACHING_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", t):
            return True
    for kw in AIDE_KEYWORDS:
        if kw in t:
            return True
    return False

def run_scraper():
    seen_ids = load_seen()
    new_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for district_name, url in DISTRICT_URLS:
            print(f"Opening: {district_name}...")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Give dynamic rows a brief moment to finish populating
                page.wait_for_timeout(2000)

                # Locate all links pointing to JobPostings
                job_elements = page.locator("a[href*='JobPosting'], a[href*='jobPosting']").all()
                print(f"[{district_name}] Rendered {len(job_elements)} job links.")

                for elem in job_elements:
                    title = elem.inner_text().strip()
                    href = elem.get_attribute("href") or ""

                    if not title or len(title) < 4:
                        continue

                    # Extract the unique numerical Job ID
                    id_match = re.search(r"\d{5,}", href)
                    jid = id_match.group(0) if id_match else href

                    if jid in seen_ids:
                        continue

                    if is_match(title):
                        full_url = urljoin("https://www.edjoin.org", href)
                        seen_ids.add(jid)
                        new_jobs.append({
                            "title": title,
                            "district": district_name,
                            "url": full_url
                        })
                        print(f"--> MATCH FOUND: {title}")

            except Exception as e:
                print(f"Failed to process {district_name}: {e}")

        browser.close()

    # Dispatch alerts to Discord
    for job in new_jobs:
        payload = {
            "embeds": [{
                "title": f"📋 {job['title']}",
                "url": job["url"],
                "description": f"🏫 **District:** {job['district']}",
                "color": 3066993
            }]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            print(f"Discord alert dispatched: {job['title']}")
        except Exception as e:
            print(f"Discord error: {e}")

    save_seen(seen_ids)
    print(f"Scan complete. Delivered {len(new_jobs)} notifications.")

if __name__ == "__main__":
    run_scraper()
