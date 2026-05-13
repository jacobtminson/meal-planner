"""Run once to create the SQLite database schema."""
import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "meals.db"


def init():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS preferences (
            recipe_slug  TEXT NOT NULL,
            user         TEXT NOT NULL,
            likes        INTEGER DEFAULT 0,
            skips        INTEGER DEFAULT 0,
            after_meal_rating INTEGER,
            last_shown   TEXT,
            last_liked   TEXT,
            PRIMARY KEY (recipe_slug, user)
        );

        CREATE TABLE IF NOT EXISTS weekly_sessions (
            week             TEXT PRIMARY KEY,
            batch_slugs      TEXT NOT NULL,
            jacob_submitted  INTEGER DEFAULT 0,
            wife_submitted   INTEGER DEFAULT 0,
            jacob_liked      TEXT,
            wife_liked       TEXT,
            meal_count       INTEGER DEFAULT 5,
            status           TEXT DEFAULT 'pending'
        );
    """)
    # Migrate existing DBs that predate the meal_count column
    try:
        conn.execute("ALTER TABLE weekly_sessions ADD COLUMN meal_count INTEGER DEFAULT 5")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print(f"Database initialised at {DB_PATH}")


if __name__ == "__main__":
    init()
