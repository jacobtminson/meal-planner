"""FastAPI service — swipe webhook and batch endpoint.

Run with:  uvicorn api.main:app --host 127.0.0.1 --port 8765
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import lib.db as db
import lib.mealie as mealie
from api.meal_plan import generate_meal_plan

app = FastAPI(title="Meals API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your domain in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _current_week() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/batch")
def get_batch(week: Optional[str] = None):
    """Return recipe card data for the week's swipe batch."""
    week = week or _current_week()
    session = db.get_session(week)
    if session is None:
        raise HTTPException(404, f"No session found for week {week}")

    cards = []
    for item in session["batch_slugs"]:
        slug = item["slug"]
        override_image = item.get("image") or None
        try:
            cards.append(mealie.get_recipe_card(slug, override_image=override_image))
        except Exception as exc:
            print(f"[api] Could not fetch card for {slug}: {exc}")

    return {
        "week": week,
        "status": session["status"],
        "recipes": cards,
    }


@app.get("/session-status")
def session_status(week: Optional[str] = None):
    """Let the swipe UI poll for whether both users have submitted."""
    week = week or _current_week()
    session = db.get_session(week)
    if session is None:
        raise HTTPException(404, f"No session for week {week}")
    return {
        "week": week,
        "status": session["status"],
        "jacob_submitted": bool(session["jacob_submitted"]),
        "wife_submitted": bool(session["wife_submitted"]),
    }


class SwipeResults(BaseModel):
    user: str           # 'jacob' or 'wife'
    week: str
    liked: list[str]
    skipped: list[str]
    meal_count: int = 5


@app.post("/swipe-results")
def swipe_results(body: SwipeResults):
    """Record a user's swipe votes. Triggers meal plan generation when both are done."""
    if body.user not in ("jacob", "wife"):
        raise HTTPException(400, "user must be 'jacob' or 'wife'")

    session = db.get_session(body.week)
    if session is None:
        raise HTTPException(404, f"No session for week {body.week}")
    if session["status"] != "pending":
        return {"status": session["status"], "message": "Session already complete"}

    session = db.write_votes(
        user=body.user,
        week=body.week,
        liked=body.liked,
        skipped=body.skipped,
        meal_count=body.meal_count,
    )

    both_done = bool(session["jacob_submitted"]) and bool(session["wife_submitted"])
    if both_done:
        generate_meal_plan(session)

    return {
        "status": "ok",
        "both_done": both_done,
        "jacob_submitted": bool(session["jacob_submitted"]),
        "wife_submitted": bool(session["wife_submitted"]),
    }
