"""Unsplash API client — returns photo suggestions for article images."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

UNSPLASH_API = "https://api.unsplash.com"
ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")


def search_photos(query: str, count: int = 3) -> list[dict]:
    """
    Search Unsplash for photos matching query.
    Returns list of dicts with: url, thumb, credit, alt, download_location.
    """
    if not ACCESS_KEY:
        return []

    resp = requests.get(
        f"{UNSPLASH_API}/search/photos",
        headers={"Authorization": f"Client-ID {ACCESS_KEY}"},
        params={"query": query, "per_page": count, "orientation": "landscape"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    return [
        {
            "url": photo["urls"]["regular"],
            "thumb": photo["urls"]["thumb"],
            "credit": f'{photo["user"]["name"]} on Unsplash',
            "alt": photo.get("alt_description") or query,
            "download_location": photo["links"]["download_location"],
        }
        for photo in results
    ]


def trigger_download(download_location: str) -> None:
    """Unsplash API requires triggering a download event when using a photo."""
    if not ACCESS_KEY:
        return
    requests.get(
        download_location,
        headers={"Authorization": f"Client-ID {ACCESS_KEY}"},
        timeout=5,
    )
