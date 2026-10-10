import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

# Science teaching roles
TEACHING_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", 
    "physical science", "science teacher"
]

# Aide / associate / paraprofessional roles
AIDE_KEYWORDS = [
    "aide", "instructional", "associate", 
    "paraeducator", "para educator", "paraprofessional", 
    "lab tech", "science tech", "campus security aide", 
    "supervision aide"
]

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
    
    # Check if title matches teaching keywords
    for kw in TEACHING_KEYWORDS:
        if kw in t:
            return True

    # Check if title matches aide/associate keywords
    for kw in AIDE_KEYWORDS:
        if kw in t:
            return True

    return False

# Clean URLs without broken query strings
DISTRICT_ROSTER = [
    # High School & Unified Districts (SF to SJ Corridor)
    ("Sequoia Union High School District (Menlo Park 94025)", "https://www.edjoin.org/sequhsd"),
    ("San Mateo Union High School District", "https://www.edjoin.org/SanMateoUnion"),
    ("Palo Alto Unified School District", "https://www.edjoin.org/pausd"),
    ("Mountain View-Los Altos High School District", "https://www.edjoin.org/mvla"),
    ("Fremont Union High School District", "https://www.edjoin.org/fuhsd"),
    ("Jefferson Union High School District", "https://www.edjoin.org/juhsd"),
    ("Cabrillo Unified School District", "https://www.edjoin.org/cabrillo"),
    ("South San Francisco Unified", "https://www.edjoin.org/ssfusd"),
    ("San Mateo County Office of Education", "https://www.edjoin.org/SMCOE"),
    ("San Mateo County Office of Ed (Classified)", "https://www.edjoin.org/SMCOE-PC"),

    # Elementary & Middle Districts (High Volume Aide Postings)
    ("San Mateo-Foster City School District", "https://www.edjoin.org/SanMateoFoster"),
    ("Redwood City School District", "https://www.edjoin.org/rcsd"),
    ("Belmont-Redwood Shores School District", "https://www.edjoin.org/brssd"),
    ("San Carlos School District", "https://www.edjoin.org/scsdk8"),
    ("Menlo Park City School District", "https://www.edjoin.org/mpcsd"),
    ("Las Lomitas Elementary School District", "https://www.edjoin.org/llesd"),
    ("Ravenswood City School District", "https://www.edjoin.org/rcsdca"),
    ("Burlingame School District", "https://www.edjoin.org/bsd"),
    ("Millbrae Elementary School District", "https://www.edjoin.org/MESD"),
    ("San Bruno Park School District", "https://www.edjoin.org/sbpsd"),
    ("Pacifica School District", "https://www.edjoin.org/pacificasd"),
    ("Jefferson Elementary School District", "https://www.edjoin.org/jesd"),
    ("Portola Valley School District", "https://www.edjoin.org/pvsd"),
    ("Woodside Elementary School District", "https://www.edjoin.org/woodside"),

    # Neighboring Santa Clara Districts
    ("Cupertino Union School District", "https://www.edjoin.org/cusd"),
    ("Sunnyvale School District", "https://www.edjoin.org/sesd"),
    ("Santa Clara Unified School District", "https://www.edjoin.org/scusd"),
    ("Campbell Union High School District", "https://www.edjoin.org/cuhsd"),
    ("East Side Union High School District", "https://www.edjoin.org/esuhsd"),
    ("San Jose Unified School District", "https://www.edjoin.org/sjusd"),
]

def scrape_all():
    seen_ids = load_seen()
    print(f"Beginning crawl of {len(DISTRICT_ROSTER)} district portals...")

    new_jobs = []

    for district_name, district_url in DISTRICT_ROSTER:
        try:
            resp = requests.get(district_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                print(f"Skipping {district_name}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Catch all links pointing to a job posting
            job_links = soup.find_all("a", href=re.compile(r"JobPosting", re.IGNORECASE))
            print(f"[{district_name}] found {len(job_links)} total postings.")

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
                    full_url = urljoin("https://www.edjoin.org", href)
                    seen_ids.add(jid)
                    new_jobs.append({
                        "title": title,
                        "district": district_name,
                        "url": full_url
                    })
                    print(f"--> MATCH FOUND: {title}")

            time.sleep(0.3)

        except Exception as e:
            print(f"Error checking {district_name}: {e}")

    # Dispatch to Discord
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
            print(f"Alert sent to Discord: {job['title']}")
        except Exception as e:
            print(f"Discord dispatch error: {e}")

    save_seen(seen_ids)
    print(f"Finished run. Sent {len(new_jobs)} notifications.")

if __name__ == "__main__":
    scrape_all()
