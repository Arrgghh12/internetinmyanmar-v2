"""
Link Validator
--------------
Checks all URLs in article frontmatter `sources` field before publishing.
Returns list of dead/broken links so writer can remove or replace them.

Used by telegram_bot.py after writer.py runs, before sending draft to Anna.
Also usable standalone:
  python utils/link_validator.py /path/to/article.mdx
"""

import asyncio
import logging
import re
import sys
from pathlib import Path

import httpx
import yaml

log = logging.getLogger(__name__)

TIMEOUT = 12
MAX_CONCURRENT = 8
# Treat these HTTP codes as "site exists, just bot-blocking" — NOT dead
TREAT_AS_OK = {301, 302, 303, 307, 308, 401, 403, 405, 429}
# These domains aggressively block bots but are reliable — only skip
# if they return ≥400 but NOT 404. A 404 still means dead page.
BOT_BLOCKING_DOMAINS = {
    "freedomhouse.org", "rsf.org", "hrw.org", "cpj.org",
    "article19.org", "citizenlab.ca", "netblocks.org",
}


async def check_url(client: httpx.AsyncClient, url: str) -> dict:
    """Check a single URL. Returns {url, status, ok, error}."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lstrip("www.")
    is_bot_blocking = any(domain.endswith(d) or domain == d for d in BOT_BLOCKING_DOMAINS)
    try:
        resp = await client.head(url, timeout=TIMEOUT, follow_redirects=True)
        status = resp.status_code
        if status == 405:
            resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
            status = resp.status_code
        # 404 is always dead — even on bot-blocking domains
        if status == 404:
            return {"url": url, "status": status, "ok": False, "error": "404 Not Found"}
        # Bot-blocking domains: 403/429 etc = site exists, just blocking crawlers
        if is_bot_blocking and status in TREAT_AS_OK:
            return {"url": url, "status": status, "ok": True, "error": None}
        ok = status < 400 or status in TREAT_AS_OK
        return {"url": url, "status": status, "ok": ok, "error": None}
    except httpx.TimeoutException:
        return {"url": url, "status": None, "ok": False, "error": "timeout"}
    except httpx.ConnectError:
        return {"url": url, "status": None, "ok": False, "error": "connection_error"}
    except Exception as e:
        return {"url": url, "status": None, "ok": False, "error": str(e)[:60]}


async def validate_urls(urls: list[str]) -> list[dict]:
    """Check all URLs concurrently with rate limiting."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IIMBot/1.0; +https://internetinmyanmar.com)",
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def guarded(client, url):
        async with sem:
            return await check_url(client, url)

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        results = await asyncio.gather(*[guarded(client, u) for u in urls])
    return list(results)


def extract_sources_from_mdx(path: str) -> list[str]:
    """Read MDX file and extract sources URLs from frontmatter."""
    content = Path(path).read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return []
    try:
        fm = yaml.safe_load(match.group(1))
        sources = fm.get("sources", [])
        return [s for s in sources if isinstance(s, str) and s.startswith("http")]
    except Exception:
        return []


def validate_article_sources(mdx_path: str) -> dict:
    """
    Validate all source URLs in an MDX article.
    Returns {valid: [...], broken: [...], skipped: [...]}.
    """
    urls = extract_sources_from_mdx(mdx_path)
    if not urls:
        return {"valid": [], "broken": [], "skipped": [], "urls_checked": 0}

    results = asyncio.run(validate_urls(urls))

    valid, broken = [], []
    for r in results:
        if r["ok"]:
            valid.append(r)
        else:
            broken.append(r)
            log.warning(f"DEAD LINK: {r['url']} — {r.get('status')} {r.get('error','')}")

    return {
        "valid": valid,
        "broken": broken,
        "skipped": [],
        "urls_checked": len(urls),
    }


def remove_broken_sources(mdx_path: str, broken_urls: list[str]) -> int:
    """Remove broken URLs from article frontmatter sources list. Returns count removed."""
    if not broken_urls:
        return 0
    path = Path(mdx_path)
    content = path.read_text(encoding="utf-8")
    broken_set = set(broken_urls)
    removed = 0
    for url in broken_set:
        # Remove the line containing this URL from the sources YAML block
        escaped = re.escape(url)
        new_content, n = re.subn(rf'^\s*-\s*["\']?{escaped}["\']?\s*\n', '', content, flags=re.MULTILINE)
        if n:
            content = new_content
            removed += n
    path.write_text(content, encoding="utf-8")
    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Usage: link_validator.py /path/to/article.mdx [--fix]")
        sys.exit(1)
    mdx_path = sys.argv[1]
    fix = "--fix" in sys.argv

    result = validate_article_sources(mdx_path)
    print(f"\nChecked {result['urls_checked']} URLs:")
    print(f"  ✓ Valid:   {len(result['valid'])}")
    print(f"  ✗ Broken:  {len(result['broken'])}")
    print(f"  ~ Skipped: {len(result['skipped'])} (trusted domains)")

    if result["broken"]:
        print("\nBroken links:")
        for r in result["broken"]:
            print(f"  {r['url']}  [{r.get('status','?')} {r.get('error','')}]")
        if fix:
            broken_urls = [r["url"] for r in result["broken"]]
            removed = remove_broken_sources(mdx_path, broken_urls)
            print(f"\nRemoved {removed} broken link(s) from {mdx_path}")
    else:
        print("\nAll links OK.")
