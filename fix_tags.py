"""
Re-processes records where subjective_or_objective is unknown
and app_category is Unknown, with better prompts
"""
import json, time
import anthropic

API_KEY = import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")
FILE = "./rejection_data/structured_rejections.json"

client = anthropic.Anthropic(api_key=API_KEY)

def fix_record(record):
    text = f"Title: {record.get('title','')}\nBody: {record.get('body','')[:800]}"
    
    prompt = f"""Analyze this App Store rejection post. Respond ONLY with valid JSON.

Post:
{text}

Rules for subjective_or_objective:
- "objective" = clear rule violation anyone can verify (missing privacy string, crash, broken URL, wrong screenshot size, missing IAP, placeholder text)
- "subjective" = judgment call by reviewer (not enough functionality, design looks bad, app too simple, copycat concern, content decision)
- If genuinely unclear, still pick the most likely one

Rules for app_category - pick the closest match even if not explicitly stated:
Games, Productivity, Health & Fitness, Social, Finance, Education, Utilities, Entertainment, Business, Other

Return ONLY this JSON:
{{
  "app_category": "best guess category",
  "subjective_or_objective": "objective or subjective",
  "confidence": "high or low"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        return None

def main():
    with open(FILE) as f:
        records = json.load(f)

    needs_fix = [r for r in records 
                 if r.get("subjective_or_objective","unknown") == "unknown"
                 or r.get("app_category","Unknown") == "Unknown"]
    
    print(f"Records needing fix: {len(needs_fix)}/{len(records)}")
    fixed = 0

    for i, record in enumerate(records):
        if (record.get("subjective_or_objective","unknown") == "unknown" 
            or record.get("app_category","Unknown") == "Unknown"):
            
            print(f"  [{i+1}/{len(records)}] {record.get('title','')[:50]}...")
            result = fix_record(record)
            if result:
                if record.get("subjective_or_objective","unknown") == "unknown":
                    record["subjective_or_objective"] = result.get("subjective_or_objective","unknown")
                if record.get("app_category","Unknown") == "Unknown":
                    record["app_category"] = result.get("app_category","Unknown")
                record["category_confidence"] = result.get("confidence","low")
                fixed += 1
            time.sleep(0.2)

    with open(FILE, "w") as f:
        json.dump(records, f, indent=2)

    from collections import Counter
    cats = Counter(r.get("app_category","Unknown") for r in records)
    subj = Counter(r.get("subjective_or_objective","unknown") for r in records)
    
    print(f"\n✅ Fixed {fixed} records")
    print("\nApp categories:")
    for k,v in cats.most_common(): print(f"  {k}: {v}")
    print("\nSubjective vs Objective:")
    for k,v in subj.most_common(): print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
