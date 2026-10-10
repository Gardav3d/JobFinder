import json
import os
import re
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

STATUS_WEBHOOK_URL = os.environ.get("STATUS_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

# 1. Science Teaching Roles (Natural & Physical Sciences only)
SCIENCE_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", 
    "physical science", "science teacher"
]

# 2. Administrative Roles
ADMIN_KEYWORDS = [
    "principal", "vice principal", "assistant principal"
]

# Excluded subjects and levels
# Explicitly strips out Social Science, Social Studies, and non-secondary levels
EXCLUDE_KEYWORDS = [
    "social science", "social sciences", "social studies",
    "history", "civics", "government", "economics", "sociology",
    "elementary", "k-5", "k-6", "middle school", "kindergarten", "preschool"
]

# High School & Unified Districts along the SF to San Jose corridor
DISTRICT_URLS = [
    ("Sequoia Union High School District (Menlo Park 94025)", "https://www.edjoin.org/sequhsd"),
    ("San Mateo Union High School District", "https://www.edjoin.org/SanMateoUnion"),
    ("Palo Alto Unified School District", "https://www.edjoin.org/pausd"),
    ("Mountain View-Los Altos High School District", "https://www.edjoin.org/mvla"),
    ("Fremont Union High School District", "https://www.edjoin.org/fuhsd"),
    ("Jefferson Union High School District", "https://www.edjoin.org/juhsd"),
    ("Cabrillo Unified School District", "https://www.edjoin.org/cabrillo"),
    ("South San Francisco Unified", "https://www.edjoin.org/ssfusd"),
    ("San Mateo County Office of Education", "https://www.edjoin.org/SMCOE"),
    ("Campbell Union High School District", "https://www.edjoin.org/cuhsd"),
    ("East Side Union High School District", "https://www.edjoin.org/esuhsd"),
    ("San Jose Unified School District", "https://www.edjoin.org/sjusd")
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

    # Immediate drop if it references social science/studies, history, etc.
    if any(ex in t for ex in EXCLUDE_KEYWORDS):
        # Allow pass-through only if it's an admin role at a middle school (if desired),
        # but completely block anything containing social science/studies
        if any(ss in t for ss in ["social science", "social sciences", "social studies", "history", "civics", "economics"]):
            return False
        # For grade-level exclusions (k-5, middle school, etc.), check if high school is specified
        if "high school" not in t:
            return False

    # Match Natural/Physical Science
    is_science = any(re.search(r"\b" + re.escape(kw) + r"\b", t) for kw in SCIENCE_KEYWORDS)

    # Match Principal / Vice Principal
    is_admin = any(re.search(r"\b" + re.escape(kw) + r"\b", t) for kw in ADMIN_KEYWORDS)

    if not (is_science or is_admin):
        return False

    role_type = "🔬 Science" if is_science else "🏛️ Principal / Vice Principal"
    return role_type

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
                page.wait_for_timeout(2000)

                job_elements = page.locator("a[href*='JobPosting'], a[href*='jobPosting']").all()
                print(f"[{district_name}] Rendered {len(job_elements)} job links.")

                for elem in job_elements:
                    title = elem.inner_text().strip()
                    href = elem.get_attribute("href") or ""

                    if not title or len(title) < 4:
                        continue

                    id_match = re.search(r"\d{5,}", href)
                    jid = id_match.group(0) if id_match else href

                    if jid in seen_ids:
                        continue

                    match_type = is_match(title)
                    if match_type:
                        full_url = urljoin("https://www.edjoin.org", href)
                        seen_ids.add(jid)
                        new_jobs.append({
                            "title": title,
                            "district": district_name,
                            "url": full_url,
                            "type": match_type
                        })
                        print(f"--> MATCH FOUND ({match_type}): {title}")

            except Exception as e:
                print(f"Failed to process {district_name}: {e}")

        browser.close()

    # Dispatch alerts to Discord
    for job in new_jobs:
        payload = {
            "embeds": [{
                "title": f"{job['type']}: {job['title']}",
                "url": job["url"],
                "description": f"🏫 **District:** {job['district']}",
                "color": 3447003 if "Science" in job["type"] else 15844367
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
