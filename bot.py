import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
    "aide", "instructional assistant", "paraeducator", 
    "paraprofessional", "instructional aide", "lab tech", 
    "science tech", "classroom assistant", "para educator"
]

# Exclude only if explicitly preschool or kindergarten without high school context
EXCLUDE_KEYWORDS = ["kindergarten", "preschool", "infant", "toddler"]

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

def is_match(title, text=""):
    combined = f"{title} {text}".lower()

    has_science = any(re.search(r"\b" + re.escape(kw) + r"\b", combined) for kw in TEACHING_KEYWORDS)
    has_aide = any(re.search(r"\b" + re.escape(kw) + r"\b", combined) for kw in AIDE_KEYWORDS)

    if not (has_science or has_aide):
        return False

    if any(ex in combined for ex in EXCLUDE_KEYWORDS) and "high school" not in combined:
        return False

    return True

# Comprehensive roster across San Mateo County and northern Santa Clara County
# All set to catID=0 to include teaching, aides, classified, and certificated
DISTRICT_ROSTER = [
    # --- SAN MATEO COUNTY: High School & Unified Districts ---
    ("Sequoia Union High School District (Menlo Park 94025)", "https://www.edjoin.org/sequhsd?catID=0"),
    ("San Mateo Union High School District", "https://www.edjoin.org/SanMateoUnion?catID=0"),
    ("Jefferson Union High School District", "https://www.edjoin.org/juhsd?catID=0"),
    ("Cabrillo Unified School District", "https://www.edjoin.org/cabrillo?catID=0"),
    ("South San Francisco Unified School District", "https://www.edjoin.org/ssfusd?catID=0"),
    ("San Mateo County Office of Education (SMCOE)", "https://www.edjoin.org/SMCOE?catID=0"),
    ("San Mateo County Office of Education (Classified)", "https://www.edjoin.org/SMCOE-PC?catID=0"),

    # --- SAN MATEO COUNTY: K-8 Districts (Heavy Aide/Paraeducator Postings) ---
    ("San Mateo-Foster City School District", "https://www.edjoin.org/SanMateoFoster?catID=0"),
    ("Redwood City School District", "https://www.edjoin.org/rcsd?catID=0"),
    ("Belmont-Redwood Shores School District", "https://www.edjoin.org/brssd?catID=0"),
    ("San Carlos School District", "https://www.edjoin.org/scsdk8?catID=0"),
    ("Menlo Park City School District", "https://www.edjoin.org/mpcsd?catID=0"),
    ("Las Lomitas Elementary School District", "https://www.edjoin.org/llesd?catID=0"),
    ("Ravenswood City School District", "https://www.edjoin.org/rcsdca?catID=0"),
    ("Burlingame School District", "https://www.edjoin.org/bsd?catID=0"),
    ("Millbrae Elementary School District", "https://www.edjoin.org/MESD?catID=0"),
    ("San Bruno Park School District", "https://www.edjoin.org/sbpsd?catID=0"),
    ("Pacifica School District", "https://www.edjoin.org/pacificasd?catID=0"),
    ("Jefferson Elementary School District", "https://www.edjoin.org/jesd?catID=0"),
    ("Portola Valley School District", "https://www.edjoin.org/pvsd?catID=0"),
    ("Woodside Elementary School District", "https://www.edjoin.org/woodside?catID=0"),
    ("Brisbane School District", "https://www.edjoin.org/brisbanesd?catID=0"),
    ("Bayshore Elementary School District", "https://www.edjoin.org/bayshore?catID=0"),

    # --- SANTA CLARA COUNTY: Neighboring West Coast Districts (Palo Alto to San Jose) ---
    ("Palo Alto Unified School District (Directly borders 94025)", "https://www.edjoin.org/pausd?catID=0"),
    ("Mountain View-Los Altos High School District", "https://www.edjoin.org/mvla?catID=0"),
    ("Mountain View Whisman School District", "https://www.edjoin.org/mvwsd?catID=0"),
    ("Fremont Union High School District (Sunnyvale/Cupertino)", "https://www.edjoin.org/fuhsd?catID=0"),
    ("Cupertino Union School District", "https://www.edjoin.org/cusd?catID=0"),
    ("Sunnyvale School District", "https://www.edjoin.org/sesd?catID=0"),
    ("Santa Clara Unified School District", "https://www.edjoin.org/scusd?catID=0"),
    ("Campbell Union High School District", "https://www.edjoin.org/cuhsd?catID=0"),
    ("East Side Union High School District", "https://www.edjoin.org/esuhsd?catID=0"),
    ("San Jose Unified School District", "https://www.edjoin.org/sjusd?catID=0"),
]

def scrape_all():
    seen_ids = load_seen()
    print(f"Beginning crawl of {len(DISTRICT_ROSTER)} district portals across San Mateo & Santa Clara counties...")

    new_jobs = []

    for district_name, district_url in DISTRICT_ROSTER:
        try:
            resp = requests.get(district_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
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

                parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""

                if is_match(title, parent_text):
                    full_url = urljoin("https://www.edjoin.org", href)
                    seen_ids.add(jid)
                    new_jobs.append({
                        "title": title,
                        "district": district_name,
                        "url": full_url
                    })

            time.sleep(0.3)

        except Exception as e:
            print(f"Error checking {district_name}: {e}")

    # Dispatch alerts to Discord
    for job in new_jobs:
        payload = {
            "embeds": [{
                "title": f"📋 {job['title']}",
                "url": job["url"],
                "description": f"🏫 **District:** {job['district']}\n🏷️ **Category:** All Categories (catID=0)",
                "color": 3066993
            }]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            print(f"Alert sent: {job['title']} ({job['district']})")
        except Exception as e:
            print(f"Discord dispatch error: {e}")

    save_seen(seen_ids)
    print(f"Scan complete. Alerted {len(new_jobs)} positions.")

if __name__ == "__main__":
    scrape_all()
