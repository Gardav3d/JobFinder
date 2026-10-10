import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

TEACHING_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", "physical science", "science"
]

AIDE_KEYWORDS = [
    "aide", "instructional assistant", "paraeducator", 
    "paraprofessional", "lab tech", "science tech"
]

EXCLUDE_KEYWORDS = ["elementary", "k-5", "k-6", "kindergarten", "preschool"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
    has_science = any(re.search(r"\b" + re.escape(kw) + r"\b", t) for kw in TEACHING_KEYWORDS)
    has_aide = any(re.search(r"\b" + re.escape(kw) + r"\b", t) for kw in AIDE_KEYWORDS)

    if not (has_science or has_aide):
        return False

    if any(ex in t for ex in EXCLUDE_KEYWORDS) and "high school" not in t:
        return False

    return True

# Named EDJOIN vanity portal URLs for districts on the Peninsula
DISTRICT_PAGES = [
    # San Mateo County (High Schools & Unified)
    "https://www.edjoin.org/sequhsd",         # Sequoia Union High School District (Menlo Park / Redwood City / San Carlos)
    "https://www.edjoin.org/smuhsd",      # San Mateo Union High School District (San Mateo / Burlingame / Aragon / Hillsdale)
    "https://www.edjoin.org/juhsd",       # Jefferson Union High School District (Daly City / Pacifica)
    "https://www.edjoin.org/cabrillo",    # Cabrillo Unified (Half Moon Bay / Coastside)
    "https://www.edjoin.org/ssfusd",      # South San Francisco Unified
    "https://www.edjoin.org/smcoe",       # San Mateo County Office of Education

    # Immediate Neighbors (Bordering 94025 / Silicon Valley)
    "https://www.edjoin.org/pausd",       # Palo Alto Unified (Directly adjacent to Menlo Park 94025)
    "https://www.edjoin.org/mvla",        # Mountain View-Los Altos High School District
    "https://www.edjoin.org/fuhsd",       # Fremont Union High School District (Cupertino / Sunnyvale)
]

def scrape_districts():
    seen_ids = load_seen()
    new_jobs = []

    print(f"Checking {len(DISTRICT_PAGES)} targeted Peninsula districts...")

    for district_url in DISTRICT_PAGES:
        try:
            r = requests.get(district_url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                print(f"Skipping {district_url} (status: {r.status_code})")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            
            # Extract district name from header
            district_name = soup.find("h1") or soup.find("title")
            d_name = district_name.get_text(strip=True) if district_name else "Peninsula District"
            d_name = re.sub(r"EDJOIN.*", "", d_name).strip()

            # Find all job links on this district's portal
            job_links = soup.select("a[href*='JobPosting'], a[href*='jobPosting']")

            for a in job_links:
                title = a.get_text(strip=True)
                href = a.get("href", "")

                if not title or len(title) < 4:
                    continue

                id_match = re.search(r"\d{5,}", href)
                jid = id_match.group(0) if id_match else href

                if jid in seen_ids:
                    continue

                if is_match(title):
                    full_url = f"https://www.edjoin.org{href}" if href.startswith("/") else href
                    seen_ids.add(jid)
                    new_jobs.append({
                        "title": title,
                        "district": d_name,
                        "url": full_url
                    })

            time.sleep(0.5)

        except Exception as e:
            print(f"Error checking {district_url}: {e}")

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
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Alert sent: {job['title']} ({job['district']})")

    save_seen(seen_ids)
    print(f"Scan finished. Sent {len(new_jobs)} alerts.")

if __name__ == "__main__":
    scrape_districts()
