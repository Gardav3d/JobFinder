import json
import os
import re
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DB_FILE = "seen_jobs.json"

# Science keywords
TEACHING_KEYWORDS = [
    "biology", "bio", "chemistry", "chem",
    "environmental science", "apes", "life science", 
    "physical science", "science teacher"
]

# Aide / associate keywords
AIDE_KEYWORDS = [
    "aide", "instructional", "associate", 
    "paraeducator", "para educator", "paraprofessional", 
    "lab tech", "science tech", "supervision aide"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
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

def is_match(title):
    t = title.lower()
    for kw in TEACHING_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", t):
            return True
    for kw in AIDE_KEYWORDS:
        if kw in t:
            return True
    return False

def scrape_edjoin_api():
    seen_ids = load_seen()
    new_jobs = []

    # EDJOIN API endpoint used by the frontend search interface
    api_url = "https://www.edjoin.org/Home/LoadJobs"
    
    # Counties: 41 = San Mateo County, 43 = Santa Clara County
    # catID = 0 (All Categories)
    target_counties = [
        ("San Mateo County", 41),
        ("Santa Clara County", 43)
    ]

    for county_name, county_id in target_counties:
        print(f"Querying EDJOIN backend for {county_name} (ID: {county_id})...")

        # Payload matching EDJOIN's AJAX request
        payload = {
            "keywords": "",
            "location": "",
            "searchType": "all",
            "countyID": county_id,
            "regionID": 0,
            "districtID": 0,
            "catID": 0,
            "page": 1,
            "pageSize": 100,  # Grab up to 100 most recent postings
            "sort": "postingDate",
            "order": "DESC"
        }

        try:
            resp = requests.post(api_url, json=payload, headers=HEADERS, timeout=15)
            
            # If the JSON endpoint returned HTML or rejected the format, fall back to form-encoded
            if resp.status_code != 200 or not resp.text.strip().startswith(("{", "[")):
                resp = requests.post(
                    api_url, 
                    data={
                        "countyID": county_id,
                        "catID": 0,
                        "sort": "postingDate",
                        "order": "DESC",
                        "pageSize": 100
                    },
                    headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                    timeout=15
                )

            data = resp.json()
            # Handle different JSON structures returned by EDJOIN
            job_list = data.get("data") or data.get("Jobs") or data.get("rows") or []
            if isinstance(data, list):
                job_list = data

            print(f"[{county_name}] API returned {len(job_list)} live job records.")

            for job in job_list:
                # Extract fields across possible EDJOIN schema keys
                title = job.get("JobTitle") or job.get("title") or job.get("PositionTitle") or ""
                jid = str(job.get("PostingId") or job.get("JobPostingId") or job.get("id") or "")
                district = job.get("DistrictName") or job.get("Employer") or county_name
                url_slug = job.get("PostingUrl") or job.get("url") or f"/Home/JobPosting/{jid}"

                if not title or not jid:
                    continue

                if jid in seen_ids:
                    continue

                if is_match(title):
                    full_url = f"https://www.edjoin.org{url_slug}" if url_slug.startswith("/") else url_slug
                    seen_ids.add(jid)
                    new_jobs.append({
                        "title": title,
                        "district": district,
                        "url": full_url
                    })
                    print(f"--> MATCH FOUND: {title} ({district})")

        except Exception as e:
            print(f"API query failed for {county_name}: {e}")

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
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            print(f"Alert sent to Discord: {job['title']}")
        except Exception as e:
            print(f"Discord dispatch error: {e}")

    save_seen(seen_ids)
    print(f"Finished run. Sent {len(new_jobs)} notifications.")

if __name__ == "__main__":
    scrape_edjoin_api()
