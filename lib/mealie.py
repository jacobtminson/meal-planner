"""Mealie API client."""
import os
import requests
from typing import Optional

_BASE = os.environ["MEALIE_URL"].rstrip("/")
_HEADERS = {"Authorization": f"Bearer {os.environ['MEALIE_TOKEN']}"}


def _get(path: str, **params) -> dict:
    r = requests.get(f"{_BASE}{path}", headers=_HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> dict:
    r = requests.post(f"{_BASE}{path}", headers=_HEADERS, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


# ── recipe import ──────────────────────────────────────────────────────────────

def import_from_url(url: str) -> Optional[str]:
    """Import a recipe from a URL. Returns the Mealie slug, or None on failure."""
    try:
        result = _post("/api/recipes/create/url", {"url": url})
        return result.get("slug") or result.get("id")
    except Exception as exc:
        print(f"[mealie] Failed to import {url}: {exc}")
        return None


def get_recipe(slug: str) -> dict:
    return _get(f"/api/recipes/{slug}")


def get_recipe_card(slug: str) -> dict:
    """Return just the fields needed for the swipe UI card."""
    r = get_recipe(slug)
    return {
        "slug": slug,
        "name": r.get("name", slug),
        "description": r.get("description", ""),
        "image": f"{_BASE}/api/media/recipes/{slug}/images/original.webp",
        "cook_time": r.get("performTime") or r.get("totalTime") or "",
        "tags": [t["name"] for t in (r.get("tags") or [])],
        "source_url": r.get("orgURL", ""),
    }


# ── meal plan ──────────────────────────────────────────────────────────────────

def add_to_meal_plan(week: str, slugs: list[str]) -> None:
    """Add each recipe to the meal plan for the given week (as dinners Mon–Sun)."""
    from datetime import date, timedelta
    monday = date.fromisoformat(week)
    for i, slug in enumerate(slugs):
        day = (monday + timedelta(days=i % 7)).isoformat()
        recipe = get_recipe(slug)
        try:
            _post("/api/meal-plans/", {
                "date": day,
                "entryType": "dinner",
                "recipeId": recipe["id"],
                "title": recipe["name"],
            })
        except Exception as exc:
            print(f"[mealie] Failed to add {slug} to meal plan: {exc}")


# ── shopping list ──────────────────────────────────────────────────────────────

def generate_shopping_list(week: str, slugs: list[str]) -> Optional[str]:
    """Create a shopping list from the given recipe slugs. Returns list id."""
    from datetime import date
    monday = date.fromisoformat(week)
    try:
        recipe_ids = []
        for slug in slugs:
            r = get_recipe(slug)
            recipe_ids.append(r["id"])

        result = _post("/api/households/shopping/lists", {
            "name": f"Week of {monday.strftime('%B %d')}",
            "recipeReferences": [{"recipeId": rid, "recipeQuantity": 1.0}
                                  for rid in recipe_ids],
        })
        return result.get("id")
    except Exception as exc:
        print(f"[mealie] Failed to create shopping list: {exc}")
        return None


# ── pantry ────────────────────────────────────────────────────────────────────

def get_pantry() -> list[str]:
    """Return a list of ingredient names currently in the pantry."""
    try:
        data = _get("/api/households/ingredient-foods", perPage=200)
        items = data.get("items", data) if isinstance(data, dict) else data
        return [item["name"] for item in items if item.get("name")]
    except Exception as exc:
        print(f"[mealie] Failed to fetch pantry: {exc}")
        return []
