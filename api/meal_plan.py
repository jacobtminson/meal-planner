"""Shared logic: merge votes and write meal plan to Mealie."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import lib.db as db
import lib.mealie as mealie
import lib.email_notify as notify


def generate_meal_plan(session: dict) -> None:
    """Merge both users' votes, create meal plan + shopping list in Mealie, notify."""
    week = session["week"]

    # Atomically claim the transition pending → complete
    if not db.mark_complete(week):
        print(f"[meal_plan] Session {week} already being processed, skipping.")
        return

    jacob_liked = set(session["jacob_liked"] or [])
    wife_liked  = set(session["wife_liked"]  or [])
    both_liked  = jacob_liked & wife_liked
    either_liked = jacob_liked | wife_liked

    # Priority order: jointly loved first, then singly liked
    plan = list(both_liked) + [s for s in either_liked if s not in both_liked]

    print(f"[meal_plan] Plan for {week}: {len(plan)} recipes ({len(both_liked)} jointly loved)")

    meal_count = session.get("meal_count") or 5
    mealie.add_to_meal_plan(week, plan, meal_count=meal_count)
    shopping_list_id = mealie.generate_shopping_list(week, plan[:meal_count])

    db.update_preferences(session)

    # Fetch names for the email
    recipe_names: dict[str, str] = {}
    for slug in plan:
        try:
            r = mealie.get_recipe(slug)
            recipe_names[slug] = r.get("name", slug)
        except Exception:
            recipe_names[slug] = slug

    notify.send_plan_confirmation(
        week=week,
        plan_slugs=plan,
        recipe_names=recipe_names,
        jointly_loved=both_liked,
        shopping_list_id=shopping_list_id,
    )
