"""
Uses Claude API to turn raw rejection posts into structured rubric data.
Get your API key at: console.anthropic.com
"""

import json, os, time
import anthropic

API_KEY = import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")
INPUT_FILE = "./rejection_data/master_rejections.json"
OUTPUT_FILE = "./rejection_data/structured_rejections.json"

client = anthropic.Anthropic(api_key=API_KEY)

def tag_record(record):
    text = f"Title: {record.get('title','')}\nBody: {record.get('body','')[:1000]}"
    
    prompt = f"""You are analyzing an App Store rejection post from a developer forum.
Extract structured data from this post. Respond ONLY with valid JSON, no other text.

Post:
{text}

Return exactly this JSON structure:
{{
  "app_category": "one of: Games, Productivity, Health & Fitness, Social, Finance, Education, Utilities, Entertainment, Business, Other, Unknown",
  "rejection_type": "one of: Technical, Privacy, Metadata, Payments/IAP, Minimum Functionality, Design, Spam/Duplicate, Content, Other",
  "guideline_codes": ["list of Apple guideline codes mentioned e.g. 4.2, 2.1, 5.1"],
  "is_first_submission": "true/false/unknown",
  "was_resubmitted_successfully": "true/false/unknown",
  "root_cause_summary": "one sentence describing the core rejection reason",
  "fixable_before_resubmit": "true/false/unknown",
  "subjective_or_objective": "subjective or objective",
  "key_signals": ["2-4 specific things in this post that indicate rejection risk"]
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"    Error: {e}")
        return None

def main():
    with open(INPUT_FILE) as f:
        records = json.load(f)
    
    print(f"Processing {len(records)} records...")
    results = []
    
    for i, record in enumerate(records):
        print(f"  [{i+1}/{len(records)}] {record.get('title','')[:60]}...")
        
        tags = tag_record(record)
        if tags:
            merged = {**record, **tags}
            results.append(merged)
        else:
            results.append(record)
        
        if (i + 1) % 25 == 0:
            with open(OUTPUT_FILE, "w") as f:
                json.dump(results, f, indent=2)
            print(f"  💾 Progress saved ({i+1} records)")
        
        time.sleep(0.3)
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Done! {len(results)} structured records → {OUTPUT_FILE}")
    
    from collections import Counter
    cats = Counter(r.get("app_category","Unknown") for r in results)
    types = Counter(r.get("rejection_type","Other") for r in results)
    subj = Counter(r.get("subjective_or_objective","unknown") for r in results)
    
    print("\nApp categories found:")
    for k,v in cats.most_common(): print(f"  {k}: {v}")
    print("\nRejection types:")
    for k,v in types.most_common(): print(f"  {k}: {v}")
    print("\nSubjective vs Objective:")
    for k,v in subj.most_common(): print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
