import json
import os
import re
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

# Science keywords for your father
TARGET_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", "physical science"
]

# Ensure it's secondary / high school
EXCLUDE_KEYWORDS = ["elementary", "k-5", "k-6", "middle school", "grade 6", "grade 7", "grade 8"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.edjoin.org/"
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

def is_match(title, description=""):
    combined = f"{title} {description}".lower()
    
    # Must match at least one science subject
    has_subject = any(re.search(r"\b" + re.escape(kw) + r"\b", combined) for kw in TARGET_KEYWORDS)
    if not has_subject:
        return False
        
    # Skip obvious elementary / middle school postings if present
    is_excluded = any(ex in combined for ex in EXCLUDE_KEYWORDS) and "high school" not in combined
    return not is_excluded

def scrape_region():
    seen_ids = load_seen()
    new_jobs = []

    # EDJOIN California County Search:
    # San Mateo County is regionID=41 (or county name "San Mateo")
    # catID=1 specifies Certificated teaching positions
    search_urls = [
        # San Mateo County (All districts)
        "https://www.edjoin.org/Home/Jobs?regionID=41&catID=1&sort=postingDate&order=DESC",
        # Santa Clara County (North county borders San Mateo)
        "https://www.edjoin.org/Home/Jobs?regionID=43&catID=1&sort=postingDate&order=DESC"
    ]

    from bs4 import BeautifulSoup

    for url in search_urls:
        county_name = "San Mateo" if "regionID=41" in url else "Santa Clara"
        print(f"Scanning {county_name} County districts...")

        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
        except Exception as e:
            print(f"Failed to fetch {county_name}: {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        
        # Pull cards or links
        cards = soup.select(".job-list-item, .search-result, .row.item, tr")
        
        # Fallback to direct job links if list items aren't wrapped in standard card classes
        if not cards:
            links = soup.select("a[href*='JobPosting'], a[href*='DistrictJobPosting']")
            for a in links:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                job_id = re.search(r"\d{5,}", href)
                jid = job_id.group(0) if job_id else href

                if jid not in seen_ids and is_match(title):
                    full_url = f"https://www.edjoin.org{href}" if href.startswith("/") else href
                    seen_ids.add(jid)
                    new_jobs.append({
                        "title": title,
                        "district": f"{county_name} County District",
                        "url": full_url
                    })
            continue

        for card in cards:
            link = card.select_one("a[href*='JobPosting'], a[href*='DistrictJobPosting']")
            if not link:
                continue

            href = link.get("href", "")
            title = link.get_text(strip=True)
            text = card.get_text(" ", strip=True)

            job_id_match = re.search(r"\d{5,}", href)
            jid = job_id_match.group(0) if job_id_match else href

            if jid in seen_ids:
                continue

            if is_match(title, text):
                full_url = f"https://www.edjoin.org{href}" if href.startswith("/") else href
                seen_ids.add(jid)
                new_jobs.append({
                    "title": title,
                    "district": f"{county_name} County",
                    "url": full_url,
                    "details": text[:200]
                })

    # Dispatch to Discord
    for job in new_jobs:
        payload = {
            "embeds": [{
                "title": f"🔬 {job['title']}",
                "url": job["url"],
                "description": f"**Region:** {job['district']}\n{job.get('details', '')}",
                "color": 3066993
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Notified: {job['title']}")

    save_seen(seen_ids)
    print(f"County scan complete. Sent {len(new_jobs)} new notifications.")

if __name__ == "__main__":
    scrape_region()
