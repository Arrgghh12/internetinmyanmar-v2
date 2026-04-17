"""
Unit tests for agents/distribution/social_poster.py
Run: pytest agents/tests/test_social_poster.py -v
"""

import json
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MOCK_COPY = {
    "twitter": "MPT and Ooredoo withdrew from BGP routing. Third outage this month. #Myanmar #BGP #InternetShutdown",
    "facebook": "Myanmar's two largest ISPs simultaneously withdrew from BGP routing.\n\nSource: RIPEstat\nhttps://internetinmyanmar.com/digest/test\n\n#Myanmar #BGP",
}

DIGEST_META = {
    "title": "MPT and Ooredoo BGP withdrawal — April 2026",
    "excerpt": "Both ISPs withdrew simultaneously at 09:12 UTC. Third major disruption in 30 days.",
    "category": "Censorship & Shutdowns",
    "source": "RIPEstat",
    "slug": "mpt-ooredoo-bgp-april-2026",
    "url": "https://internetinmyanmar.com/digest/mpt-ooredoo-bgp-april-2026",
}


def test_copy_json_structure():
    """One LLM call must return both twitter and facebook keys."""
    from distribution.social_poster import generate_copy

    with patch("distribution.social_poster.call") as mock_call:
        mock_call.return_value = json.dumps(MOCK_COPY)
        result = generate_copy(
            title=DIGEST_META["title"],
            excerpt=DIGEST_META["excerpt"],
            category=DIGEST_META["category"],
            source=DIGEST_META["source"],
            url=DIGEST_META["url"],
        )

    assert "twitter" in result
    assert "facebook" in result
    mock_call.assert_called_once()  # exactly one LLM call


def test_twitter_length():
    """Twitter copy must be ≤ 220 chars before URL is appended."""
    from distribution.social_poster import generate_copy

    with patch("distribution.social_poster.call") as mock_call:
        mock_call.return_value = json.dumps(MOCK_COPY)
        result = generate_copy("t", "e", "c", "s", "https://internetinmyanmar.com/digest/x")

    assert len(result["twitter"]) <= 220


def test_fallback_on_bad_json():
    """If LLM returns malformed JSON, fallback must not crash."""
    from distribution.social_poster import generate_copy

    with patch("distribution.social_poster.call") as mock_call:
        mock_call.return_value = "not valid json at all"
        result = generate_copy("Title", "Excerpt", "Cat", "Source", "https://example.com")

    assert "twitter" in result
    assert "facebook" in result
    assert "#Myanmar" in result["twitter"]


def test_sensitive_content_still_uses_copy_task():
    """All content uses 'copy' task — DeepSeek handles sensitive content via model_router."""
    from distribution.social_poster import generate_copy

    with patch("distribution.social_poster.call") as mock_call:
        mock_call.return_value = json.dumps(MOCK_COPY)
        generate_copy("journalist arrested in Yangon", "e", "c", "s", "https://x.com")

    task_used = mock_call.call_args[0][0]
    assert task_used == "copy"


def test_post_all_partial_failure():
    """Facebook failure must not prevent Twitter result from being returned."""
    from distribution.social_poster import post_all

    with patch("distribution.social_poster.generate_copy", return_value=MOCK_COPY), \
         patch("distribution.social_poster.post_twitter",
               return_value={"platform": "twitter", "id": "123"}), \
         patch("distribution.social_poster.post_facebook",
               side_effect=Exception("FB API down")):

        results = post_all(DIGEST_META)

    assert "twitter" in results["posted"]
    assert "facebook" in results["errors"]
    assert results["errors"]["facebook"] == "FB API down"


def test_post_all_builds_url_from_slug():
    """If no url key, must build it from slug."""
    from distribution.social_poster import post_all

    meta_no_url = {k: v for k, v in DIGEST_META.items() if k != "url"}

    with patch("distribution.social_poster.generate_copy", return_value=MOCK_COPY) as mock_gen, \
         patch("distribution.social_poster.post_twitter", return_value={"platform": "twitter", "id": "1"}), \
         patch("distribution.social_poster.post_facebook", return_value={"platform": "facebook", "id": "2"}):

        post_all(meta_no_url)

    url_used = mock_gen.call_args[1]["url"]
    assert "mpt-ooredoo-bgp-april-2026" in url_used
    assert url_used.startswith("https://internetinmyanmar.com")
