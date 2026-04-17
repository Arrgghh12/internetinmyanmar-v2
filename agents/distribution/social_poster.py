"""
agents/distribution/social_poster.py

Post digest articles to Twitter and Facebook.
One Haiku call generates copy for both platforms in a single JSON response.
Called from telegram_bot.py after Anna approves a digest.

Usage (manual test):
  python agents/distribution/social_poster.py --test
"""

import json
import os
import sys

import httpx
import tweepy
from dotenv import load_dotenv

# Add agents/ to path so utils is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from utils.model_router import call

COPY_PROMPT = """Write social media copy for this digest.
Audience: journalists, researchers, NGO staff following Myanmar internet freedom.

Digest title: {TITLE}
Excerpt: {EXCERPT}
Category: {CATEGORY}
URL: {URL}
Source: {SOURCE}

Write TWO versions. Return JSON only, no markdown fences:
{{
  "twitter": "max 220 chars, punchy, 2-3 hashtags at end, do NOT include the URL",
  "facebook": "2-3 sentences of context, source attribution on its own line, URL on its own line, hashtags at end"
}}

Rules: sentence case, never start with Breaking:, always include #Myanmar"""


def generate_copy(title: str, excerpt: str, category: str,
                  source: str, url: str) -> dict:
    """
    One LLM call → copy for both platforms.
    Returns {"twitter": str, "facebook": str}.
    """
    raw = call(
        "copy",
        COPY_PROMPT.format(
            TITLE=title,
            EXCERPT=excerpt[:300],
            CATEGORY=category,
            SOURCE=source,
            URL=url,
        ),
        max_tokens=300,
    )

    clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        fallback = f"{title[:200]} #Myanmar"
        return {
            "twitter": fallback,
            "facebook": f"{title}\n\n{excerpt[:300]}\n\n{url}",
        }


def post_twitter(text: str, url: str) -> dict:
    """Post to Twitter via OAuth 1.0a."""
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_CONSUMER_KEY"],
        consumer_secret=os.environ["TWITTER_CONSUMER_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    full = f"{text}\n{url}"
    if len(full) > 280:
        max_text = 280 - len(url) - 2
        full = f"{text[:max_text].rstrip()}\n{url}"

    response = client.create_tweet(text=full)
    return {"platform": "twitter", "id": str(response.data["id"])}


def post_facebook(text: str) -> dict:
    """Post to Facebook Page via Graph API."""
    page_id = os.environ["FACEBOOK_PAGE_ID"]
    token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

    resp = httpx.post(
        f"https://graph.facebook.com/v19.0/{page_id}/feed",
        params={"access_token": token},
        json={"message": text},
        timeout=15,
    )
    resp.raise_for_status()
    return {"platform": "facebook", "id": resp.json()["id"]}


def post_all(digest_meta: dict) -> dict:
    """
    Generate copy and post to Twitter + Facebook.
    digest_meta: dict with title, excerpt, category, source, slug, url
    Returns {"posted": {platform: result}, "errors": {platform: msg}}
    """
    url = digest_meta.get("url") or \
        f"https://internetinmyanmar.com/digest/{digest_meta['slug']}"

    copy = generate_copy(
        title=digest_meta["title"],
        excerpt=digest_meta.get("excerpt", ""),
        category=digest_meta.get("category", ""),
        source=digest_meta.get("source", ""),
        url=url,
    )

    posted = {}
    errors = {}

    for platform, fn, arg in [
        ("twitter",  post_twitter,  (copy["twitter"], url)),
        ("facebook", post_facebook, (copy["facebook"],)),
    ]:
        try:
            posted[platform] = fn(*arg)
        except Exception as e:
            errors[platform] = str(e)
            print(f"  ✗ {platform}: {e}", file=sys.stderr)

    return {"posted": posted, "errors": errors}


# ── Manual test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" not in sys.argv:
        print("Run with --test to post a test digest to Twitter + Facebook.")
        sys.exit(0)

    test_meta = {
        "title": "TEST — Myanmar internet monitoring active [delete me]",
        "excerpt": "This is an automated test post from the IIM distribution pipeline. Please ignore.",
        "category": "Observatory",
        "source": "internetinmyanmar.com",
        "slug": "test-distribution",
        "url": "https://internetinmyanmar.com/observatory/",
    }

    print("Generating copy...")
    results = post_all(test_meta)
    print("Posted:", json.dumps(results, indent=2))
    print("\nVerify posts on Twitter and Facebook, then delete them manually.")
