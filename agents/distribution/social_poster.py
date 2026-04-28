"""
agents/distribution/social_poster.py

Post digest articles to Twitter and Facebook.
One Haiku call generates copy for both platforms in a single JSON response.
Called from telegram_bot.py after Anna approves a digest.

Usage (manual test):
  python agents/distribution/social_poster.py --test
"""

import json
import mimetypes
import os
import re
import sys
import tempfile
from pathlib import Path

import httpx
import requests
import tweepy
from dotenv import load_dotenv

# Add agents/ to path so utils is importable when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from utils.model_router import call

COPY_PROMPT = """Write social media copy for this digest article.
Audience: journalists, researchers, NGO staff following Myanmar internet freedom.

Digest title: {TITLE}
Excerpt: {EXCERPT}
Category: {CATEGORY}
Site URL: {URL}
Original source: {SOURCE}

Write TWO versions. Return JSON only, no markdown fences:
{{
  "twitter": "max 240 chars including URL. Lead with the key fact. Max 2 hashtags at the very end (#Myanmar is mandatory, add one more only if highly relevant). Do NOT use 'Breaking:'. Sentence case. The URL will be appended automatically so do NOT include it in this field.",
  "facebook": "Hook sentence (the most striking fact). Then 1-2 sentences of context. Then on its own line: 'Via {SOURCE}'. End with 1-2 hashtags. No emojis. Keep under 300 chars total. Do NOT include the URL — it is added automatically as the post link."
}}

Rules:
- Sentence case throughout
- Never start with 'Breaking:', 'BREAKING', or emojis
- Be factual and precise — this audience is expert, not general public
- #Myanmar always included"""


def fetch_og_image(url: str) -> str | None:
    """Extract og:image URL from a page. Returns None on any failure."""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            resp.text,
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                resp.text,
            )
        return m.group(1) if m else None
    except Exception:
        return None


def download_image(url: str) -> str | None:
    """Download image to a temp file. Returns local path or None on failure."""
    try:
        resp = requests.get(url, timeout=15, stream=True)
        resp.raise_for_status()
        ct  = resp.headers.get("content-type", "image/jpeg")
        ext = (mimetypes.guess_extension(ct.split(";")[0].strip()) or ".jpg").replace(".jpe", ".jpg")
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        for chunk in resp.iter_content(8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception:
        return None


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


def post_twitter(text: str, url: str, image_path: str | None = None) -> dict:
    """Post to Twitter via OAuth 1.0a. Attaches image if image_path is provided."""
    media_id = None
    if image_path:
        try:
            auth = tweepy.OAuth1UserHandler(
                os.environ["TWITTER_CONSUMER_KEY"],
                os.environ["TWITTER_CONSUMER_SECRET"],
                os.environ["TWITTER_ACCESS_TOKEN"],
                os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
            )
            media = tweepy.API(auth).media_upload(filename=image_path)
            media_id = str(media.media_id)
        except Exception as e:
            print(f"  ⚠ Twitter media upload failed, posting without image: {e}", file=sys.stderr)

    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_CONSUMER_KEY"],
        consumer_secret=os.environ["TWITTER_CONSUMER_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    full = f"{text}\n{url}"
    if len(full) > 280:
        full = f"{text[:280 - len(url) - 2].rstrip()}\n{url}"

    kwargs: dict = {"text": full}
    if media_id:
        kwargs["media_ids"] = [media_id]
    response = client.create_tweet(**kwargs)
    return {"platform": "twitter", "id": str(response.data["id"])}


def post_facebook(text: str, url: str, image_url: str | None = None) -> dict:
    """Post to Facebook Page via Graph API. Passes explicit image if available."""
    page_id = os.environ["FACEBOOK_PAGE_ID"]
    token   = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

    body: dict = {"message": text, "link": url}
    if image_url:
        body["picture"] = image_url

    resp = httpx.post(
        f"https://graph.facebook.com/v19.0/{page_id}/feed",
        params={"access_token": token},
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return {"platform": "facebook", "id": resp.json()["id"]}


def post_all(digest_meta: dict) -> dict:
    """
    Generate copy and post to Twitter + Facebook.
    digest_meta: dict with title, excerpt, category, source, slug, and optionally
                 og_image (pre-fetched image URL) or source_url (to fetch from).
    Returns {"posted": {platform: result}, "errors": {platform: msg}}
    """
    url = f"https://internetinmyanmar.com/digest/{digest_meta['slug']}"

    # Resolve OG image: use stored value first, fall back to fetching from source URL
    og_image_url = digest_meta.get("og_image")
    if not og_image_url and digest_meta.get("source_url"):
        og_image_url = fetch_og_image(digest_meta["source_url"])

    image_path = download_image(og_image_url) if og_image_url else None

    copy = generate_copy(
        title=digest_meta["title"],
        excerpt=digest_meta.get("excerpt", ""),
        category=digest_meta.get("category", ""),
        source=digest_meta.get("source", ""),
        url=url,
    )

    posted: dict = {}
    errors: dict = {}

    try:
        for platform, fn, args, kw in [
            ("twitter",  post_twitter,  (copy["twitter"],  url), {"image_path": image_path}),
            ("facebook", post_facebook, (copy["facebook"], url), {"image_url":  og_image_url}),
        ]:
            try:
                posted[platform] = fn(*args, **kw)
            except Exception as e:
                errors[platform] = str(e)
                print(f"  ✗ {platform}: {e}", file=sys.stderr)
    finally:
        if image_path:
            Path(image_path).unlink(missing_ok=True)

    return {"posted": posted, "errors": errors}


# ── Manual test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" not in sys.argv:
        print("Run with --test to post a test digest to Twitter + Facebook.")
        sys.exit(0)

    test_meta = {
        "title":      "TEST — Myanmar internet monitoring active [delete me]",
        "excerpt":    "This is an automated test post from the IIM distribution pipeline. Please ignore.",
        "category":   "Observatory",
        "source":     "internetinmyanmar.com",
        "slug":       "test-distribution",
        "source_url": "https://ooni.org/post/2024-myanmar-elections/",  # real page with og:image
    }

    print("Generating copy and fetching OG image…")
    results = post_all(test_meta)
    print("Posted:", json.dumps(results, indent=2))
    print("\nVerify posts on Twitter and Facebook, then delete them manually.")
