"""Monday 8 AM cron job: curate this week's recipe batch.

Crontab entry:
  0 8 * * 1  /opt/meals/venv/bin/python /opt/meals/scripts/weekly_curation.py >> /opt/meals/logs/curation.log 2>&1
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

# Allow imports from /opt/meals/lib
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests
import lib.db as db
import lib.mealie as mealie
import lib.email_notify as notify

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SPOONACULAR_KEY = os.environ["SPOONACULAR_KEY"]
BATCH_SIZE = 14

# Fallback Spoonacular params when Gemini output is invalid
_FALLBACK_PARAMS = {
    "cuisine": "mediterranean,asian,american",
    "maxReadyTime": 45,
}


def get_spoonacular_params(pantry: list[str], prefs: dict) -> dict:
    """Call Gemini to translate preference signals into Spoonacular query params."""
    prompt = f"""You are helping plan weekly dinners for a couple who love variety and healthy eating.

Pantry items they already have (favor using these):
{', '.join(pantry) if pantry else 'none listed'}

Preference signals:
- Jacob consistently enjoys: {', '.join(prefs['jacob']['strong_likes']) or 'no data yet'}
- Jacob consistently skips: {', '.join(prefs['jacob']['consistent_skips']) or 'none'}
- Wife consistently enjoys: {', '.join(prefs['wife']['strong_likes']) or 'no data yet'}
- Wife consistently skips: {', '.join(prefs['wife']['consistent_skips']) or 'none'}
- Both consistently enjoy: {', '.join(prefs['both_liked']) or 'no data yet'}
- Recently shown (avoid repeating for 2 weeks): {', '.join(prefs['recently_shown']) or 'none'}

If preference history is sparse, optimize for variety across proteins, cuisines, and cook times.

Return ONLY a JSON object — no explanation, no markdown fences:
{{
  "cuisine": "comma,separated,cuisines or empty string",
  "diet": "vegetarian|gluten free|etc or empty string",
  "includeIngredients": "pantry items to use, comma-separated or empty string",
  "excludeIngredients": "disliked ingredients, comma-separated or empty string",
  "maxReadyTime": 45
}}"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 512},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip any accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        params = json.loads(text)
        # Ensure required keys exist
        params.setdefault("maxReadyTime", 45)
        return params
    except Exception as exc:
        print(f"[gemini] Error, using fallback params: {exc}")
        return _FALLBACK_PARAMS


def search_spoonacular(params: dict, count: int) -> list[dict]:
    """Search Spoonacular and return recipe results with sourceUrl."""
    query_params = {
        "number": count,
        "addRecipeInformation": True,
        "apiKey": SPOONACULAR_KEY,
    }
    for key in ("cuisine", "diet", "includeIngredients", "excludeIngredients", "maxReadyTime"):
        val = params.get(key, "")
        if val:
            query_params[key] = val

    r = requests.get(
        "https://api.spoonacular.com/recipes/complexSearch",
        params=query_params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("results", [])


def main():
    today = date.today()
    # Snap to Monday of this week
    monday = today - __import__("datetime").timedelta(days=today.weekday())
    week = monday.isoformat()

    print(f"[curation] Starting weekly curation for week {week}")

    existing = db.get_session(week)
    if existing and existing["status"] != "expired":
        print(f"[curation] Session for {week} already exists ({existing['status']}), skipping.")
        return

    pantry = mealie.get_pantry()
    prefs = db.get_preference_summary()

    params = get_spoonacular_params(pantry, prefs)
    print(f"[curation] Spoonacular params: {params}")

    recipes = search_spoonacular(params, count=BATCH_SIZE + 4)  # fetch extra in case some fail import
    print(f"[curation] Spoonacular returned {len(recipes)} recipes")

    slugs = []
    for recipe in recipes:
        source_url = recipe.get("sourceUrl") or recipe.get("spoonacularSourceUrl", "")
        if not source_url:
            continue
        slug = mealie.import_from_url(source_url)
        if slug:
            slugs.append(slug)
            print(f"[curation] Imported: {recipe.get('title')} → {slug}")
        if len(slugs) >= BATCH_SIZE:
            break

    if not slugs:
        print("[curation] ERROR: No recipes could be imported. Aborting.")
        sys.exit(1)

    print(f"[curation] Imported {len(slugs)} recipes into Mealie")
    db.create_session(week, slugs)
    notify.send_swipe_invites(week)
    print(f"[curation] Done — invites sent for week {week}")


if __name__ == "__main__":
    main()
