"""
Extra sources: Hacker News + Stack Overflow + Apple Official Sources
No API keys needed, all free
"""
import json, time, os, re, requests, hashlib
from datetime import datetime
from bs4 import BeautifulSoup

OUTPUT_DIR = "./rejection_data"
OFFICIAL_DIR = "./rejection_data/official_sources"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OFFICIAL_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
KEYWORDS = ["rejected","rejection","guideline","app review","minimum functionality",
    "privacy policy","in-app purchase","metadata","binary rejected"]

def classify(text):
    t = text.lower()
    if any(w in t for w in ["crash","bug","freeze","performance"]): return "Technical"
    if any(w in t for w in ["privacy","permission","data collect","info.plist"]): return "Privacy"
    if any(w in t for w in ["metadata","screenshot","description","placeholder"]): return "Metadata"
    if any(w in t for w in ["in-app purchase","iap","subscription","paywall"]): return "Payments/IAP"
    if any(w in t for w in ["minimum functionality","not enough","web wrapper"]): return "Minimum Functionality"
    if any(w in t for w in ["design","ui","interface","hig"]): return "Design"
    return "Other"

def extract_codes(text):
    return list(set(re.findall(r'[Gg]uideline\s*(\d+\.\d*(?:\.\d+)?)', text)))

def save(records, name):
    jp = os.path.join(OUTPUT_DIR, f"{name}.json")
    cp = os.path.join(OUTPUT_DIR, f"{name}.csv")
    with open(jp,"w") as f: json.dump(records, f, indent=2)
    try:
        import pandas as pd
        if records: pd.DataFrame(records).to_csv(cp, index=False)
    except: pass
    print(f"  ✓ Saved {len(records)} records → {name}.json")

# ── Hacker News ──────────────────────────────────────────
def scrape_hn():
    print("\n[1/3] Hacker News...")
    queries = ["app store rejection","app store rejected guideline",
               "rejected apple review","guideline 4.2 rejected",
               "minimum functionality apple","app review binary rejected",
               "apple rejected my app","app store review guidelines rejected"]
    records = []
    seen = set()
    for q in queries:
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={q.replace(' ','+')}&tags=story&hitsPerPage=50"
        try:
            r = requests.get(url, timeout=15)
            for h in r.json().get("hits",[]):
                oid = h.get("objectID","")
                if oid in seen: continue
                seen.add(oid)
                title = h.get("title","")
                body = h.get("story_text","") or ""
                full = f"{title} {body}"
                if not any(k in full.lower() for k in KEYWORDS): continue
                records.append({
                    "source": "hacker_news",
                    "url": h.get("url","") or f"https://news.ycombinator.com/item?id={oid}",
                    "title": title, "body": body[:2000],
                    "guideline_codes": extract_codes(full),
                    "rejection_type": classify(full),
                    "upvotes": h.get("points",0),
                    "num_comments": h.get("num_comments",0),
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"    Skip: {e}")
    print(f"  → {len(records)} HN posts")
    save(records, "hn_rejections")
    return records

# ── Stack Overflow ───────────────────────────────────────
def scrape_stackoverflow():
    print("\n[2/3] Stack Overflow...")
    records = []
    seen = set()
    searches = [
        ("app-store-rejection", ""),
        ("ios", "app store rejection"),
        ("ios", "guideline rejected"),
        ("app-store", "rejected guideline"),
        ("ios", "app review binary rejected"),
    ]
    for tag, q in searches:
        params = {"order":"desc","sort":"votes","tagged":tag,
                  "site":"stackoverflow","pagesize":50,"filter":"withbody"}
        if q: params["intitle"] = q
        try:
            r = requests.get("https://api.stackexchange.com/2.3/questions",
                             params=params, timeout=15)
            for item in r.json().get("items",[]):
                qid = item.get("question_id","")
                if qid in seen: continue
                seen.add(qid)
                title = item.get("title","")
                body = re.sub(r'<[^>]+>',' ', item.get("body","") or "")
                full = f"{title} {body}"
                if not any(k in full.lower() for k in KEYWORDS): continue
                records.append({
                    "source": "stackoverflow",
                    "url": item.get("link",""),
                    "title": title, "body": body[:2000],
                    "guideline_codes": extract_codes(full),
                    "rejection_type": classify(full),
                    "upvotes": item.get("score",0),
                    "num_comments": item.get("answer_count",0),
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            time.sleep(1.5)
        except Exception as e:
            print(f"    Skip: {e}")
    print(f"  → {len(records)} SO questions")
    save(records, "stackoverflow_rejections")
    return records

# ── Apple Official Sources ───────────────────────────────
def scrape_official():
    print("\n[3/3] Apple Official Sources...")
    sources = [
        {"name":"app_store_review_guidelines",
         "url":"https://developer.apple.com/app-store/review/guidelines/",
         "importance":"CRITICAL — primary rule source"},
        {"name":"human_interface_guidelines",
         "url":"https://developer.apple.com/design/human-interface-guidelines/",
         "importance":"HIGH — design rejection rules"},
        {"name":"app_store_connect_submissions",
         "url":"https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/overview-of-submitting-for-review/",
         "importance":"HIGH — metadata submission requirements"},
        {"name":"developer_news",
         "url":"https://developer.apple.com/news/",
         "importance":"MONITOR — catches guideline changes"},
        {"name":"privacy_manifest_required_apis",
         "url":"https://developer.apple.com/documentation/bundleresources/privacy-manifest-files/describing-use-of-required-reason-api",
         "importance":"CRITICAL — 2024 privacy manifest requirement"},
        {"name":"screenshot_specifications",
         "url":"https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications",
         "importance":"HIGH — exact screenshot size requirements"},
    ]
    changed = []
    for s in sources:
        try:
            r = requests.get(s["url"], headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r.text,"html.parser")
            for tag in soup.select("nav,footer,header,script,style"):
                tag.decompose()
            main = soup.select_one("main,article,.content,#content") or soup.body
            text = main.get_text(separator="\n",strip=True) if main else ""
            content_hash = hashlib.md5(r.text.encode()).hexdigest()
            result = {"name":s["name"],"url":s["url"],"importance":s["importance"],
                      "content":text[:15000],"content_hash":content_hash,
                      "scraped_at":datetime.utcnow().isoformat()}
            prev_path = os.path.join(OFFICIAL_DIR, f"{s['name']}.json")
            if os.path.exists(prev_path):
                with open(prev_path) as f:
                    prev = json.load(f)
                if prev.get("content_hash") != content_hash:
                    result["changed"] = True
                    changed.append(s["name"])
                    print(f"  ⚠️  CHANGED: {s['name']}")
                else:
                    result["changed"] = False
            with open(prev_path,"w") as f:
                json.dump(result, f, indent=2)
            print(f"  ✓ {s['name']} ({len(text):,} chars)")
            time.sleep(1)
        except Exception as e:
            print(f"  ✗ {s['name']}: {e}")
    if changed:
        print(f"\n  ⚠️  {len(changed)} Apple sources changed — update your rules engine!")
    return changed

# ── Merge everything into master ─────────────────────────
def merge_all():
    print("\n[Merging into master...]")
    import pandas as pd
    all_records = []
    files = ["master_rejections.json","hn_rejections.json","stackoverflow_rejections.json"]
    for fname in files:
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
    with open(os.path.join(OUTPUT_DIR,"master_rejections.json"),"w") as f:
        json.dump(deduped, f, indent=2)
    pd.DataFrame(deduped).to_csv(os.path.join(OUTPUT_DIR,"master_rejections.csv"),index=False)
    print(f"\n✅ New master total: {len(deduped)} unique records")

if __name__ == "__main__":
    print("🔍 Scraping extra sources + Apple official docs")
    print("=" * 50)
    scrape_hn()
    scrape_stackoverflow()
    scrape_official()
    merge_all()
    print("\nDone! Check rejection_data/ for all files")
    print("Check rejection_data/official_sources/ for Apple docs")
