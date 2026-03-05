"""
App Store Rejection Data Scraper - No Auth Version
Scrapes Reddit via Pushshift/old.reddit, Apple Dev Forums, and blogs
No API keys needed.
"""

import json, time, re, os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd

OUTPUT_DIR = "./rejection_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

REJECTION_KEYWORDS = ["rejected","rejection","app review","guideline","minimum functionality",
    "crashes","metadata","privacy policy","in-app purchase","paywall","binary rejected"]

def extract_guideline_codes(text):
    codes = re.findall(r'[Gg]uideline\s*(\d+\.\d*(?:\.\d+)?)', text)
    bare = re.findall(r'\b(\d\.\d{1,2}(?:\.\d+)?)\b', text)
    return list(set(codes + bare))

def classify_rejection_type(text):
    t = text.lower()
    if any(w in t for w in ["crash","bug","freeze","performance","memory"]): return "Technical"
    if any(w in t for w in ["privacy","permission","data collect","info.plist","usage description"]): return "Privacy"
    if any(w in t for w in ["metadata","screenshot","description","keyword","placeholder"]): return "Metadata"
    if any(w in t for w in ["in-app purchase","iap","subscription","paywall","payment"]): return "Payments/IAP"
    if any(w in t for w in ["minimum functionality","not enough","limited functionality","web wrapper","webview"]): return "Minimum Functionality"
    if any(w in t for w in ["design","ui","interface","hig"]): return "Design"
    if any(w in t for w in ["spam","duplicate","copycat","clone"]): return "Spam/Duplicate"
    return "Other"

def save_records(records, name):
    json_path = os.path.join(OUTPUT_DIR, f"{name}.json")
    csv_path = os.path.join(OUTPUT_DIR, f"{name}.csv")
    with open(json_path, "w") as f:
        json.dump(records, f, indent=2)
    if records:
        pd.DataFrame(records).to_csv(csv_path, index=False)
    print(f"  ✓ Saved {len(records)} records → {name}.json + .csv")
    return records

def scrape_reddit_no_auth():
    """Scrape Reddit via old.reddit.com search - no API key needed"""
    print("\n[1/4] Scraping Reddit (no auth)...")
    records = []
    seen = set()

    queries = [
        "app+store+rejection",
        "app+store+rejected+guideline",
        "rejected+minimum+functionality",
        "app+review+rejected+binary",
        "guideline+4.2+rejected",
        "guideline+2.1+rejected",
        "guideline+5.1+rejected",
        "app+store+rejection+paywall",
        "app+store+rejection+metadata",
        "app+store+rejection+privacy",
    ]

    subreddits = ["iOSProgramming", "swift", "SwiftUI", "appstore", "apple"]

    for sub in subreddits:
        for query in queries:
            url = f"https://old.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=1&sort=relevance&limit=25&t=all"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    time.sleep(2)
                    continue
                data = resp.json()
                posts = data.get("data", {}).get("children", [])

                for post in posts:
                    p = post.get("data", {})
                    pid = p.get("id","")
                    if pid in seen: continue
                    seen.add(pid)

                    title = p.get("title","")
                    body = p.get("selftext","")
                    full_text = f"{title} {body}"

                    if not any(kw in full_text.lower() for kw in REJECTION_KEYWORDS):
                        continue

                    records.append({
                        "source": "reddit",
                        "subreddit": sub,
                        "url": f"https://reddit.com{p.get('permalink','')}",
                        "title": title,
                        "body": body[:2000],
                        "guideline_codes": extract_guideline_codes(full_text),
                        "rejection_type": classify_rejection_type(full_text),
                        "upvotes": p.get("score", 0),
                        "num_comments": p.get("num_comments", 0),
                        "created_utc": datetime.utcfromtimestamp(p.get("created_utc", 0)).isoformat(),
                        "scraped_at": datetime.utcnow().isoformat(),
                    })

                time.sleep(1.5)  # be polite
            except Exception as e:
                print(f"    Skipping {sub}/{query}: {e}")
                time.sleep(2)
                continue

    print(f"  → Found {len(records)} Reddit posts")
    return save_records(records, "reddit_rejections")

def scrape_apple_dev_forums():
    print("\n[2/4] Scraping Apple Developer Forums...")
    records = []
    seen = set()

    search_terms = [
        "app store rejection",
        "rejected guideline",
        "binary rejected",
        "minimum functionality",
        "app review rejected",
    ]

    for term in search_terms:
        url = f"https://developer.apple.com/forums/search?q={term.replace(' ','+')}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.select("a[href*='/forums/thread/']")

            for link in links[:15]:
                href = link.get("href","")
                if not href.startswith("http"):
                    href = "https://developer.apple.com" + href
                if href in seen: continue
                seen.add(href)

                try:
                    tr = requests.get(href, headers=HEADERS, timeout=15)
                    ts = BeautifulSoup(tr.text, "html.parser")
                    title_el = ts.select_one("h1")
                    title = title_el.get_text(strip=True) if title_el else "Unknown"
                    posts = ts.select(".content-html, .thread-post-content")
                    full_text = " ".join(p.get_text(strip=True)[:500] for p in posts[:5])

                    if not any(kw in full_text.lower() for kw in REJECTION_KEYWORDS):
                        time.sleep(0.5)
                        continue

                    records.append({
                        "source": "apple_dev_forums",
                        "url": href,
                        "title": title,
                        "body": full_text[:3000],
                        "guideline_codes": extract_guideline_codes(full_text),
                        "rejection_type": classify_rejection_type(full_text),
                        "scraped_at": datetime.utcnow().isoformat(),
                    })
                    time.sleep(0.8)
                except Exception as e:
                    print(f"    Skipping thread: {e}")
                    continue
        except Exception as e:
            print(f"    Skipping term '{term}': {e}")

    print(f"  → Found {len(records)} Apple Dev Forum threads")
    return save_records(records, "apple_forum_rejections")

def scrape_blogs():
    print("\n[3/4] Scraping blog sources...")
    sources = [
        {"name": "revenuecat_ultimate_guide", "url": "https://www.revenuecat.com/blog/growth/the-ultimate-guide-to-app-store-rejections/"},
        {"name": "revenuecat_how_to_avoid", "url": "https://www.revenuecat.com/blog/engineering/how-to-avoid-app-store-rejections/"},
        {"name": "jesse_squires_rejection", "url": "https://www.jessesquires.com/blog/2024/01/03/app-store-rejection/"},
        {"name": "onemobile_14_rejections", "url": "https://onemobile.ai/common-app-store-rejections-and-how-to-avoid-them/"},
        {"name": "twinr_rejection_guide", "url": "https://twinr.dev/blogs/apple-app-store-rejection-reasons-2025/"},
    ]
    records = []
    for s in sources:
        try:
            resp = requests.get(s["url"], headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup.select("nav,footer,header,.sidebar,script,style"):
                tag.decompose()
            article = soup.select_one("article,main,.post-content,.entry-content,.blog-post") or soup.body
            text = article.get_text(separator=" ", strip=True) if article else ""
            records.append({
                "source": "blog", "name": s["name"], "url": s["url"],
                "body": text[:5000],
                "guideline_codes": extract_guideline_codes(text),
                "rejection_type": classify_rejection_type(text),
                "scraped_at": datetime.utcnow().isoformat(),
            })
            print(f"    ✓ {s['name']}")
            time.sleep(1)
        except Exception as e:
            print(f"    ✗ {s['name']}: {e}")

    print(f"  → Scraped {len(records)} blog sources")
    return save_records(records, "blog_rejections")

def scrape_apple_guidelines():
    print("\n[4/4] Snapshotting Apple Guidelines...")
    url = "https://developer.apple.com/app-store/review/guidelines/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")
        sections = []
        for h in soup.select("h2,h3,h4"):
            parts = []
            for sib in h.find_next_siblings():
                if sib.name in ["h2","h3","h4"]: break
                parts.append(sib.get_text(strip=True))
            content = " ".join(parts)[:2000]
            sections.append({"title": h.get_text(strip=True), "content": content,
                            "guideline_codes": extract_guideline_codes(f"{h.get_text()} {content}")})
        out = {"url": url, "scraped_at": datetime.utcnow().isoformat(),
               "version_hash": str(hash(resp.text)), "sections": sections}
        path = os.path.join(OUTPUT_DIR, "apple_guidelines_snapshot.json")
        with open(path,"w") as f: json.dump(out, f, indent=2)
        print(f"  ✓ Saved {len(sections)} guideline sections")
    except Exception as e:
        print(f"  ✗ Error: {e}")

def build_master():
    print("\n[Merging all sources...]")
    all_records = []
    for fname in ["reddit_rejections.json","apple_forum_rejections.json","blog_rejections.json"]:
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                recs = json.load(f)
                all_records.extend(recs)
                print(f"  Loaded {len(recs)} from {fname}")
    seen, deduped = set(), []
    for r in all_records:
        key = r.get("url", str(r))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    if deduped:
        df = pd.DataFrame(deduped)
        print(f"\n{'='*50}\nMASTER DATASET: {len(deduped)} unique records")
        if "rejection_type" in df.columns:
            print("\nRejection type breakdown:")
            print(df["rejection_type"].value_counts().to_string())
        print(f"{'='*50}")
    save_records(deduped, "master_rejections")

if __name__ == "__main__":
    print("\n🔍 App Store Rejection Data Collector (No Auth)")
    print("=" * 50)
    scrape_reddit_no_auth()
    scrape_apple_dev_forums()
    scrape_blogs()
    scrape_apple_guidelines()
    build_master()
    print(f"\n✅ Done! Data saved to ./{OUTPUT_DIR}/")
