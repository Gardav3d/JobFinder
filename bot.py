import json
import os
import re
import requests
from bs4 import BeautifulSoup

# Replace with your Discord Webhook URL (Server Settings -> Integrations -> Webhooks)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1558366276420632637/mp89vOH9pXPTPhA3E8-5zpy4oVirjPoqpKP1IciQxGZmwKmmOhKf0lPoMD2-hkZuhp9P"
DB_FILE = "seen_jobs.json"

# Subjects to match
TARGET_KEYWORDS = [
    "biology", "bio", "chemistry", "chem", 
    "environmental science", "apes"
]

# High school indicators
LEVEL_KEYWORDS = ["high school", "hs", "secondary", "9-12"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen_ids):
    with open(DB_FILE, "w") as f:
        json.dump(list(seen_ids), f, indent=2)

def is_relevant(title, text):
    content = f"{title} {text}".lower()
    subject_match = any(re.search(r"\b" + re.escape(kw) + r"\b", content) for kw in TARGET_KEYWORDS)
    level_match = any(re.search(r"\b" + re.escape(lvl) + r"\b", content) for lvl in LEVEL_KEYWORDS)
    return subject_match and level_match

def scrape_edjoin():
    seen_ids = load_seen()
    
    # EDJOIN search: 35-mile radius around Menlo Park 94025 for Certificated Teacher roles
    # catID=1 specifies Certificated teaching positions
    search_url = (
        "https://www.edjoin.org/Home/Jobs?"
        "keywords=science"
        "&location=94025"
        "&distance=35"
        "&catID=1"
        "&sort=postingDate"
        "&order=DESC"
    )

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Fetch failed: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find listing containers
    job_cards = soup.select(".job-list-item, .search-result, .list-group-item")

    for card in job_cards:
        link_tag = card.select_one("a[href*='/Home/JobPosting/'], a[href*='/Home/DistrictJobPosting/']")
        if not link_tag:
            continue

        href = link_tag.get("href", "")
        # Extract unique Job ID from URL (e.g., /Home/JobPosting/2005234)
        job_id_match = re.search(r"JobPosting/(\d+)", href)
        job_id = job_id_match.group(1) if job_id_match else href

        if job_id in seen_ids:
            continue

        title = link_tag.get_text(strip=True)
        card_text = card.get_text(" ", strip=True)

        if is_relevant(title, card_text):
            full_link = f"https://www.edjoin.org{href}" if href.startswith("/") else href
            
            # Send notification
            payload = {
                "embeds": [{
                    "title": f"🔬 {title}",
                    "url": full_link,
                    "description": f"**Area:** SF to San Jose Corridor (94025 Radius)\n**Details:** {card_text[:200]}...",
                    "color": 3447003
                }]
            }
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
            seen_ids.add(job_id)
            print(f"Sent alert for: {title}")

    save_seen(seen_ids)

if __name__ == "__main__":
    scrape_edjoin()
