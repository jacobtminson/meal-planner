"""SQLite helpers for preferences and weekly sessions."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "meals.db"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# ── sessions ──────────────────────────────────────────────────────────────────

def create_session(week: str, batch_slugs: list[str]) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO weekly_sessions (week, batch_slugs, status)"
            " VALUES (?, ?, 'pending')",
            (week, json.dumps(batch_slugs)),
        )


def get_session(week: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM weekly_sessions WHERE week = ?", (week,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["batch_slugs"] = json.loads(d["batch_slugs"] or "[]")
    d["jacob_liked"] = json.loads(d["jacob_liked"] or "[]")
    d["wife_liked"] = json.loads(d["wife_liked"] or "[]")
    return d


def write_votes(user: str, week: str, liked: list[str], skipped: list[str]) -> dict:
    """Record one user's votes. Returns the updated session."""
    col_submitted = f"{user}_submitted"
    col_liked = f"{user}_liked"
    with _conn() as con:
        con.execute(
            f"UPDATE weekly_sessions SET {col_submitted}=1, {col_liked}=?"
            "  WHERE week=? AND status='pending'",
            (json.dumps(liked), week),
        )
    return get_session(week)


def mark_complete(week: str) -> bool:
    """Atomically transition pending → complete. Returns True if this caller won."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE weekly_sessions SET status='complete'"
            " WHERE week=? AND status='pending'",
            (week,),
        )
        return cur.rowcount == 1


def mark_expired(week: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE weekly_sessions SET status='expired' WHERE week=? AND status='pending'",
            (week,),
        )


# ── preferences ───────────────────────────────────────────────────────────────

def update_preferences(session: dict) -> None:
    today = date.today().isoformat()
    jacob_liked = set(session["jacob_liked"])
    wife_liked = set(session["wife_liked"])
    all_shown = set(session["batch_slugs"])

    with _conn() as con:
        for slug in all_shown:
            for user, liked_set in [("jacob", jacob_liked), ("wife", wife_liked)]:
                liked = slug in liked_set
                con.execute("""
                    INSERT INTO preferences (recipe_slug, user, likes, skips, last_shown)
                      VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(recipe_slug, user) DO UPDATE SET
                      likes      = likes + excluded.likes,
                      skips      = skips + excluded.skips,
                      last_shown = excluded.last_shown,
                      last_liked = CASE WHEN excluded.likes > 0 THEN excluded.last_shown
                                        ELSE last_liked END
                """, (slug, user, int(liked), int(not liked), today))


def get_preference_summary() -> dict:
    """Return structured preference data for the Gemini prompt."""
    cutoff = (date.today() - timedelta(weeks=2)).isoformat()
    with _conn() as con:
        rows = con.execute("SELECT * FROM preferences").fetchall()
        recent = con.execute(
            "SELECT DISTINCT recipe_slug FROM preferences WHERE last_shown >= ?", (cutoff,)
        ).fetchall()

    summary: dict = {
        "jacob": {"strong_likes": [], "consistent_skips": []},
        "wife":  {"strong_likes": [], "consistent_skips": []},
        "both_liked": [],
        "recently_shown": [r["recipe_slug"] for r in recent],
    }

    jacob_likes, wife_likes = set(), set()
    for row in rows:
        user = row["user"]
        slug = row["recipe_slug"]
        if row["likes"] >= 3:
            summary[user]["strong_likes"].append(slug)
            if user == "jacob":
                jacob_likes.add(slug)
            else:
                wife_likes.add(slug)
        if row["skips"] >= 3 and row["likes"] == 0:
            summary[user]["consistent_skips"].append(slug)

    summary["both_liked"] = list(jacob_likes & wife_likes)
    return summary
