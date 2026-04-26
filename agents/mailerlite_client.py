"""
MailerLite API v2 client (connect.mailerlite.com)
Simple wrapper used by article_packager.py.
"""

import logging
import os
from typing import Optional

import requests

log = logging.getLogger(__name__)
BASE = "https://connect.mailerlite.com/api"


def _h() -> dict:
    token = os.environ.get("MAILERLITE_API_TOKEN", "")
    if not token:
        raise ValueError("MAILERLITE_API_TOKEN not set in environment")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_groups() -> list[dict]:
    r = requests.get(f"{BASE}/groups", headers=_h(), params={"limit": 100}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def find_group_id(name: str) -> Optional[str]:
    """Find a group ID by name (case-insensitive)."""
    for g in get_groups():
        if g.get("name", "").lower() == name.lower():
            return str(g["id"])
    return None


def get_all_subscriber_groups() -> list[str]:
    """Return IDs of all groups (for production send)."""
    return [str(g["id"]) for g in get_groups()]


def create_campaign_draft(
    name: str,
    subject: str,
    preview_text: str,
    html_content: str,
    group_ids: list[str],
) -> dict:
    """Create a campaign draft targeting specific groups. Returns campaign dict."""
    from_email = os.environ.get("MAILERLITE_FROM_EMAIL", "")
    from_name  = os.environ.get("MAILERLITE_FROM_NAME", "Internet in Myanmar")
    if not from_email:
        raise ValueError("MAILERLITE_FROM_EMAIL not set in environment")

    payload = {
        "name": name,
        "type": "regular",
        "groups": group_ids,
        "emails": [{
            "subject": subject,
            "preview_text": preview_text,
            "from": from_email,
            "from_name": from_name,
            "content": html_content,
        }],
    }
    r = requests.post(f"{BASE}/campaigns", json=payload, headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})


def schedule_instant(campaign_id: str) -> None:
    """Send a campaign immediately."""
    r = requests.post(
        f"{BASE}/campaigns/{campaign_id}/schedule",
        json={"delivery": "instant"},
        headers=_h(),
        timeout=30,
    )
    r.raise_for_status()
    log.info(f"Campaign {campaign_id} scheduled for instant delivery")


def campaign_dashboard_url(campaign_id: str) -> str:
    return f"https://dashboard.mailerlite.com/campaigns/{campaign_id}/review"
