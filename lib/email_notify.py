"""Email notification helpers."""
import os
import smtplib
from email.message import EmailMessage

_SMTP_HOST = os.environ["SMTP_HOST"]
_SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
_SMTP_USER = os.environ["SMTP_USER"]
_SMTP_PASS = os.environ["SMTP_PASS"]
_JACOB_EMAIL = os.environ["JACOB_EMAIL"]
_WIFE_EMAIL  = os.environ["WIFE_EMAIL"]
_BASE_URL    = os.environ.get("APP_BASE_URL", "https://meals.yourdomain.com")
_MEALIE_URL  = os.environ["MEALIE_URL"]

_USER_EMAILS = {"jacob": _JACOB_EMAIL, "wife": _WIFE_EMAIL}


def _send(to: str | list[str], subject: str, body: str) -> None:
    recipients = [to] if isinstance(to, str) else to
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as s:
        s.starttls()
        s.login(_SMTP_USER, _SMTP_PASS)
        s.send_message(msg)


def send_swipe_invites(week: str) -> None:
    for user, email in _USER_EMAILS.items():
        url = f"{_BASE_URL}?user={user}&week={week}"
        _send(
            to=email,
            subject="🍽️ This week's dinner picks are ready!",
            body=(
                f"Hey! Your weekly meal selections are ready.\n\n"
                f"Swipe through this week's options here:\n{url}\n\n"
                f"You have until Wednesday evening before the plan is locked in.\n"
            ),
        )


def send_plan_confirmation(
    week: str,
    plan_slugs: list[str],
    recipe_names: dict[str, str],
    jointly_loved: set[str],
    shopping_list_id: str | None,
) -> None:
    lines = ["Your meal plan for the week is set!\n"]

    if jointly_loved:
        lines.append("★ You BOTH loved these:")
        for slug in jointly_loved:
            lines.append(f"  • {recipe_names.get(slug, slug)}")
        lines.append("")

    lines.append("This week's dinners:")
    for slug in plan_slugs:
        marker = "★ " if slug in jointly_loved else "  "
        lines.append(f"{marker}• {recipe_names.get(slug, slug)}")

    if shopping_list_id:
        lines.append(f"\nShopping list ready in Mealie:\n{_MEALIE_URL}/shopping-lists/{shopping_list_id}")

    _send(
        to=[_JACOB_EMAIL, _WIFE_EMAIL],
        subject="✅ Meal plan locked in!",
        body="\n".join(lines),
    )


def send_reminder(missing_users: list[str]) -> None:
    for user in missing_users:
        # We don't know the week here easily, so just send a nudge
        _send(
            to=_USER_EMAILS[user],
            subject="⏰ Don't forget to pick your meals!",
            body=(
                "Hey! The weekly meal deadline is tonight.\n"
                "Open your swipe link from Monday's email to make your picks.\n"
            ),
        )
