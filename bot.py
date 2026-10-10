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

def get_san_mateo_district_urls():
    """
    Scrapes EDJOIN's Region/County directory to find all authentic
    district job URLs under San Mateo County.
    """
    district_urls = set()
    
    # Direct EDJOIN vanity/county portal for San Mateo
    county_portal_urls = [
        "https://www.edjoin.org/sequhsd",  # Verified Sequoia Union High School District
        "https://www.edjoin.org/pausd",    # Palo Alto Unified (Next to 94025)
    ]
    for url in county_portal_urls:
        district_urls.add(url)

    # Let's inspect EDJOIN's Region list page for San Mateo
    region_urls = [
        "https://www.edjoin.org/Home/RegionDistricts?regionID=41",
        "https://www.edjoin.org/Home/DistrictsInCounty?county=San%20Mateo"
    ]

    for r_url in region_urls:
        try:
            res = requests.get(r_url, headers=HEADERS, timeout=12)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                # Collect all district links listed on the county page
                for a in soup.select("a[href]"):
                    href = a.get("href", "")
                    text = a.get_text(strip=True).lower()
                    
                    # Match links that point to districts or EDJOIN district portals
                    if any(term in text for term in ["union high", "unified", "sequoia", "san mateo", "jefferson", "cabrillo"]):
                        full_link = f"https://www.edjoin.org{href}" if href.startswith("/") else href
                        district_urls.add(full_link)
        except Exception as e:
            print(f"Error fetching directory {r_url}: {e}")

    return list(district_urls)

def scrape_districts():
    seen_ids = load_seen()
    new_jobs = []

    district_urls = get_san_mateo_district_urls()
    print(f"Scanning {len(district_urls)} district pages: {district_urls}")

    for district_url in district_urls:
        try:
            print(f"Checking: {district_url}")
            r = requests.get(district_url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                print(f"Skipping {district_url} - status {r.status_code}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            
            # Find district name from page header
            d_header = soup.find("h1") or soup.find("title")
            district_name = d_header.get_text(strip=True) if d_header else "District"
            district_name = re.sub(r"EDJOIN.*", "", district_name).strip()

            # Find all job links
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
                        "district": district_name,
                        "url": full_url
                    })

            time.sleep(0.5)

        except Exception as e:
            print(f"Error reading {district_url}: {e}")

    # Send alerts to Discord
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
    print(f"Run completed. Total new notifications sent: {len(new_jobs)}")

if __name__ == "__main__":
    scrape_districts()
