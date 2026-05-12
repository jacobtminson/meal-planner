"""Wednesday 8 PM cron job: generate meal plan if deadline has passed.

Crontab entry:
  0 20 * * 3  /opt/meals/venv/bin/python /opt/meals/scripts/deadline_check.py >> /opt/meals/logs/deadline.log 2>&1
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import lib.db as db
import lib.email_notify as notify
from api.meal_plan import generate_meal_plan


def this_week() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def main():
    week = this_week()
    print(f"[deadline] Checking week {week}")

    session = db.get_session(week)
    if session is None:
        print("[deadline] No session found for this week.")
        return

    if session["status"] != "pending":
        print(f"[deadline] Session status is '{session['status']}', nothing to do.")
        return

    jacob_done = bool(session["jacob_submitted"])
    wife_done  = bool(session["wife_submitted"])

    if not jacob_done and not wife_done:
        print("[deadline] Neither user has submitted — sending reminders.")
        notify.send_reminder(["jacob", "wife"])
        return

    missing = []
    if not jacob_done:
        missing.append("jacob")
    if not wife_done:
        missing.append("wife")

    if missing:
        print(f"[deadline] {missing} has not submitted — generating plan with available votes.")
        notify.send_reminder(missing)

    generate_meal_plan(session)
    print("[deadline] Meal plan generated.")


if __name__ == "__main__":
    main()
