import json
import os
import re
import requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

TARGET_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "science", "aid"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
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

def test_webhook():
    """Verifies that Discord actually receives messages."""
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL is not set!")
        return False
    
    payload = {
        "content": "📡 **EDJOIN Watcher is active!** Testing connection from GitHub runner."
    }
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    print(f"Discord ping response status: {resp.status_code}")
    return resp.status_code in [200, 204]

def scrape_edjoin():
    seen_ids = load_seen()

    # Search: Science in 94025 radius (certificated)
    search_url = (
        "https://www.edjoin.org/Home/Jobs?"
        "keywords=science"
        "&location=94025"
        "&distance=35"
        "&catID=1"
        "&sort=postingDate"
        "&order=DESC"
    )

    print(f"Fetching: {search_url}")
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        print(f"EDJOIN HTTP status: {response.status_code}")
    except Exception as e:
        print(f"EDJOIN fetch failed: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Find any links to job postings
    job_links = soup.select("a[href*='JobPosting'], a[href*='jobPosting']")
    print(f"Found {len(job_links)} raw job links on page.")

    matches_found = 0

    for link_tag in job_links:
        title = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        
        if not title or len(title) < 4:
            continue

        # Get unique ID
        id_match = re.search(r"\d{5,}", href)
        job_id = id_match.group(0) if id_match else href

        if job_id in seen_ids:
            continue

        # Check for keywords
        title_lower = title.lower()
        if any(kw in title_lower for kw in TARGET_KEYWORDS):
            full_link = f"https://www.edjoin.org{href}" if href.startswith("/") else href
            
            payload = {
                "embeds": [{
                    "title": f"🔬 {title}",
                    "url": full_link,
                    "description": "New science position detected near 94025.",
                    "color": 3447003
                }]
            }
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            seen_ids.add(job_id)
            matches_found += 1
            print(f"Sent alert for: {title}")

    save_seen(seen_ids)
    print(f"Finished scrape. New matching listings alerted: {matches_found}")

if __name__ == "__main__":
    test_webhook()
    scrape_edjoin()
