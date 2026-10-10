import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

# Broader science keywords
TEACHING_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", 
    "physical science", "science"
]

# Broader aide / assistant keywords
AIDE_KEYWORDS = [
    "aide", "instructional assistant", "paraeducator", 
    "paraprofessional", "instructional aide", "lab tech", 
    "science tech", "classroom assistant"
]

# Exclude elementary-specific positions unless high school is explicitly stated
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

def is_match(title, text=""):
    combined = f"{title} {text}".lower()

    has_science = any(re.search(r"\b" + re.escape(kw) + r"\b", combined) for kw in TEACHING_KEYWORDS)
    has_aide = any(re.search(r"\b" + re.escape(kw) + r"\b", combined) for kw in AIDE_KEYWORDS)

    if not (has_science or has_aide):
        return False

    if any(ex in combined for ex in EXCLUDE_KEYWORDS) and "high school" not in combined:
        return False

    return True

def auto_discover_district_urls():
    county_directory_urls = [
        "https://www.edjoin.org/Home/RegionDistricts?countyID=41",
        "https://www.edjoin.org/Home/DistrictsInCounty?county=San%20Mateo",
        "https://www.edjoin.org/Home/RegionDistricts?countyID=43",
        "https://www.edjoin.org/Home/DistrictsInCounty?county=Santa%20Clara"
    ]

    discovered = set()
    base_url = "https://www.edjoin.org"

    print("Auto-discovering all district portals in San Mateo and Santa Clara counties...")

    for portal_url in county_directory_urls:
        try:
            resp = requests.get(portal_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith("#") or "javascript:" in href:
                    continue

                is_district_link = any([
                    "districtID=" in href,
                    "/Home/DistrictJobPosting/" in href,
                    "/Home/Jobs?districtID=" in href,
                ])

                is_named_slug = (
                    href.startswith("/") 
                    and not any(x in href for x in ["Home", "Account", "Help", "Faq", "Search", "api"]) 
                    and len(href.split("/")) == 2
                    and len(href) > 2
                )

                if is_district_link or is_named_slug:
                    clean_link = urljoin(base_url, href)
                    separator = "&" if "?" in clean_link else "?"
                    final_link = f"{clean_link}{separator}catID=0"
                    discovered.add(final_link)

        except Exception as e:
            print(f"Error checking directory {portal_url}: {e}")

    # Primary high school / unified districts in the SF-to-SJ corridor
    seed_districts = [
        "https://www.edjoin.org/sequhsd?catID=0",       # Sequoia Union High (Menlo Park / 94025)
        "https://www.edjoin.org/pausd?catID=0",         # Palo Alto Unified
        "https://www.edjoin.org/mvla?catID=0",          # Mountain View-Los Altos High
        "https://www.edjoin.org/fuhsd?catID=0",         # Fremont Union High (Sunnyvale/Cupertino)
        "https://www.edjoin.org/juhsd?catID=0",         # Jefferson Union High (Daly City/Pacifica)
        "https://www.edjoin.org/cabrillo?catID=0",      # Cabrillo Unified (Coastside)
        "https://www.edjoin.org/ssfusd?catID=0",        # South San Francisco Unified
        "https://www.edjoin.org/smcoe?catID=0",         # San Mateo County Office of Ed
        "https://www.edjoin.org/sjusd?catID=0",         # San Jose Unified
        "https://www.edjoin.org/esuhsd?catID=0",        # East Side Union High (San Jose)
        "https://www.edjoin.org/cuhsd?catID=0"          # Campbell Union High (West SJ)
    ]
    discovered.update(seed_districts)

    return sorted(list(discovered))

def scrape_all():
    seen_ids = load_seen()
    district_urls = auto_discover_district_urls()
    print(f"Found {len(district_urls)} unique school district URLs. Beginning scan...")

    new_jobs = []

    for district_url in district_urls:
        try:
            resp = requests.get(district_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            h_tag = soup.find(["h1", "h2", "title"])
            d_name = h_tag.get_text(strip=True) if h_tag else "Peninsula District"
            d_name = re.sub(r"EDJOIN.*", "", d_name).strip() or "Peninsula School District"

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

                # Inspect surrounding card text if available
                parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""

                if is_match(title, parent_text):
                    full_url = urljoin("https://www.edjoin.org", href)
                    seen_ids.add(jid)
                    new_jobs.append({
                        "title": title,
                        "district": d_name,
                        "url": full_url
                    })

            time.sleep(0.3)

        except Exception as e:
            print(f"Skipping {district_url} due to error: {e}")

    # Dispatch alerts to Discord
    for job in new_jobs:
        payload = {
            "embeds": [{
                "title": f"📋 {job['title']}",
                "url": job["url"],
                "description": f"🏫 **District:** {job['district']}\n🏷️ **Category:** All (catID=0)",
                "color": 3066993
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Alert sent: {job['title']} ({job['district']})")

    save_seen(seen_ids)
    print(f"Scan complete. Alerted {len(new_jobs)} positions.")

if __name__ == "__main__":
    scrape_all()
