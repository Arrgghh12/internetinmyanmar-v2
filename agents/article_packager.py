"""
Article Packager
----------------
Full production pipeline after a brief is approved. Generates:
  1. MDX article (via writer.py)
  2. Social media campaign (5 posts, 2-week schedule)
  3. Newsletter HTML (MailerLite-ready)
  4. GitHub PR with all assets + review checklist
  5. MailerLite campaign draft → auto-sends to 'test' group for preview

Usage:
  python article_packager.py agents/approved/YYYY-MM-DD/my-slug.md
  python article_packager.py agents/approved/YYYY-MM-DD/my-slug.md --adjustments "focus more on VPN angle"
  python article_packager.py agents/approved/YYYY-MM-DD/my-slug.md --dry-run  # skip MailerLite + GitHub
"""

import json
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

AGENTS_DIR  = Path(__file__).parent
CONFIG_FILE = AGENTS_DIR / "config.yaml"
CONFIG      = yaml.safe_load(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
ARTICLES_DIR = Path(CONFIG.get("paths", {}).get("articles", "~/dev/iimv2/src/content/articles")).expanduser()
SITE_URL     = os.getenv("SITE_URL", "https://www.internetinmyanmar.com")


# ── DeepSeek client ─────────────────────────────────────────────────────────

def _deepseek() -> OpenAI:
    return OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )


def _generate(system: str, user: str, max_tokens: int = 2000) -> str:
    resp = _deepseek().chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


# ── Social campaign ──────────────────────────────────────────────────────────

SOCIAL_SYSTEM = """You write social media campaigns for Internet in Myanmar, an independent digital rights monitor.
Tone: direct, data-forward, never sensationalist. Credible to journalists and researchers.
Write exactly 5 posts as specified. Use real statistics from the article.
Output clean Markdown only — no preamble, no closing remarks."""

SOCIAL_USER_TMPL = """Article title: {title}
Article URL: {url}
Key finding: {finding}
Article excerpt: {excerpt}

Write a 5-post social media campaign spread over 2 weeks:

## Post 1 — Day 1 · X (Main finding, hook)
Platform: X
Image: [chart-1.png]

[tweet text, max 280 chars, include article URL, 2-3 hashtags: #Myanmar #InternetFreedom #OONI or similar]

---

## Post 2 — Day 3 · Facebook/LinkedIn (Context & data deep-dive)
Platform: Facebook / LinkedIn
Image: [chart-2.png]

[longer post, 2-3 paragraphs, focus on one specific data point from the article]

---

## Post 3 — Day 7 · X (Chart highlight)
Platform: X
Image: [chart-3.png]

[tweet thread 2-3 tweets, focus on what the chart reveals, include URL]

---

## Post 4 — Day 10 · LinkedIn (Implications for researchers/journalists)
Platform: LinkedIn
Image: [chart-1.png]

[professional angle, what this means for press freedom researchers, include URL]

---

## Post 5 — Day 14 · X + Facebook (Dataset / open data angle)
Platform: X + Facebook
Image: [none]

[focus on the open datasets available for download, include /observatory/data/ URL]"""


def generate_social_campaign(title: str, url: str, excerpt: str, body: str) -> str:
    finding = body[:400].replace("\n", " ").strip()
    user = SOCIAL_USER_TMPL.format(title=title, url=url, finding=finding, excerpt=excerpt)
    return _generate(SOCIAL_SYSTEM, user, max_tokens=1800)


# ── Newsletter HTML ──────────────────────────────────────────────────────────

NEWSLETTER_SYSTEM = """You write newsletter emails for Internet in Myanmar, an independent digital rights monitor.
The email is sent via MailerLite as HTML. Write the FULL HTML email (complete, valid HTML).
Brand colors: background header #0A1628, accent #00D4C8, dark text #0A1628, light text #e2e8f0.
Keep the body background WHITE for email client compatibility.
MailerLite will automatically add the unsubscribe footer — do NOT add one.
Output ONLY the HTML — no explanation, no markdown fences."""

NEWSLETTER_USER_TMPL = """Article title: {title}
Article URL: {url}
Category: {category}
Excerpt: {excerpt}
Key finding (first 400 chars of body): {finding}

Write a complete responsive HTML newsletter email. Include:
1. Dark header (#0A1628) with "INTERNET IN MYANMAR" monospace label in #00D4C8
2. White body section with:
   - Category label in #00D4C8 monospace uppercase
   - Article title as H1
   - One-sentence key finding in a teal left-border callout box
   - 2 paragraph teaser (don't reproduce the whole article — create curiosity)
   - "Read the full analysis →" CTA button in #00D4C8 linking to {url}
   - "Download open datasets →" secondary CTA linking to {data_url}
3. Dark footer (#0A1628) with "Internet in Myanmar · independent digital rights monitor"

Also provide, at the very top as HTML comments:
<!-- SUBJECT: [subject line max 60 chars] -->
<!-- PREVIEW: [preview text max 90 chars] -->"""


def generate_newsletter_html(title: str, url: str, category: str, excerpt: str, body: str) -> tuple[str, str, str]:
    """Returns (html, subject, preview_text)."""
    finding = body[:400].replace("\n", " ").strip()
    data_url = f"{SITE_URL}/observatory/data/"
    user = NEWSLETTER_USER_TMPL.format(
        title=title, url=url, category=category,
        excerpt=excerpt, finding=finding, data_url=data_url,
    )
    html = _generate(NEWSLETTER_SYSTEM, user, max_tokens=2500)

    # Extract subject + preview from HTML comments
    import re
    subject_m = re.search(r'<!-- SUBJECT: (.+?) -->', html)
    preview_m = re.search(r'<!-- PREVIEW: (.+?) -->', html)
    subject  = subject_m.group(1).strip() if subject_m else f"New analysis: {title[:50]}"
    preview  = preview_m.group(1).strip() if preview_m else excerpt[:90]

    # Clean the HTML comments from the deliverable
    html_clean = re.sub(r'<!--\s*(?:SUBJECT|PREVIEW):.*?-->\s*\n?', '', html)
    return html_clean, subject, preview


# ── GitHub PR ────────────────────────────────────────────────────────────────

def create_review_pr(
    brief: dict,
    article_path: Path,
    media_kit_files: dict[str, str],   # relative_path → content
    preview_url: str,
    ml_campaign_url: str,
    ml_test_sent: bool,
) -> str:
    """Open GitHub PR with article + all review assets. Returns PR URL."""
    from github import Github, GithubException

    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
    REPO_NAME    = CONFIG["github"]["repo"]
    BASE_BRANCH  = CONFIG["github"]["base_branch"]
    DRAFT_PREFIX = CONFIG["github"]["draft_prefix"]

    g    = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    slug = brief["slug"]

    branch_name = f"{DRAFT_PREFIX}{slug}"
    base = repo.get_branch(BASE_BRANCH)
    try:
        repo.create_git_ref(f"refs/heads/{branch_name}", base.commit.sha)
    except GithubException as e:
        if e.status != 422:
            raise

    def _commit(path: str, msg: str, content: str):
        try:
            existing = repo.get_contents(path, ref=branch_name)
            repo.update_file(path, msg, content, existing.sha, branch=branch_name)
        except GithubException:
            repo.create_file(path, msg, content, branch=branch_name)

    # 1. Article MDX
    _commit(
        f"src/content/articles/{slug}.mdx",
        f"draft: {brief['title']}",
        article_path.read_text(encoding="utf-8"),
    )

    # 2. Media kit assets (social campaign, newsletter, etc.)
    for rel_path, content in media_kit_files.items():
        _commit(
            rel_path,
            f"media kit: {rel_path.split('/')[-1]}",
            content,
        )

    # Build PR checklist
    test_line = (
        f"Newsletter preview **sent to test group** — check your inbox."
        if ml_test_sent
        else "Newsletter draft created (test send skipped)."
    )

    pr_body = f"""## Review Checklist

- [ ] Read the article preview and approve text
- [ ] Review social media campaign (see file below)
- [ ] Check newsletter email in your inbox (test group send)
- [ ] Approve newsletter subject line and preview text
- [ ] Set `draft: false` in Keystatic before merging

---

### Article Preview
{preview_url}

### MailerLite Campaign Draft
{ml_campaign_url}
{test_line}

### Assets in this PR
| File | Purpose |
|---|---|
| `src/content/articles/{slug}.mdx` | Article draft |
| `src/content/articles/{slug}/social-campaign.md` | 5-post social campaign (2 weeks) |
| `src/content/articles/{slug}/newsletter.html` | Newsletter email HTML |
| `src/content/articles/{slug}/newsletter-meta.txt` | Subject line + preview text |

---

**Category:** {brief.get("category", "")}
**Tags:** {", ".join(brief.get("tags", []))}

> To publish: set `draft: false` in the MDX frontmatter, then merge this PR."""

    pr = repo.create_pull(
        title=f"Draft: {brief['title']}",
        body=pr_body,
        head=branch_name,
        base=BASE_BRANCH,
        draft=True,
    )
    return pr.html_url


# ── MailerLite integration ───────────────────────────────────────────────────

def create_and_send_test(
    title: str,
    subject: str,
    preview_text: str,
    html: str,
    test_group_name: str = "test",
) -> tuple[str, bool]:
    """Create MailerLite campaign draft + send to test group. Returns (campaign_url, sent_ok)."""
    from mailerlite_client import (
        create_campaign_draft, find_group_id, schedule_instant, campaign_dashboard_url
    )

    test_group_id = find_group_id(test_group_name)
    if not test_group_id:
        log.warning(f"MailerLite group '{test_group_name}' not found — creating draft without group")
        group_ids = []
    else:
        group_ids = [test_group_id]

    campaign = create_campaign_draft(
        name=f"[REVIEW] {title[:80]}",
        subject=subject,
        preview_text=preview_text,
        html_content=html,
        group_ids=group_ids,
    )
    cid = str(campaign.get("id", ""))
    dashboard_url = campaign_dashboard_url(cid) if cid else "https://dashboard.mailerlite.com/campaigns"

    sent_ok = False
    if cid and group_ids:
        try:
            schedule_instant(cid)
            sent_ok = True
            log.info(f"Test newsletter sent to group '{test_group_name}'")
        except Exception as e:
            log.warning(f"Could not auto-send test newsletter: {e}")

    return dashboard_url, sent_ok


# ── Main ─────────────────────────────────────────────────────────────────────

def run(brief_path: str, adjustments: str = "", dry_run: bool = False) -> None:
    # Import writer internals
    sys.path.insert(0, str(AGENTS_DIR))
    import writer as w

    brief, raw_text = w._read_brief(brief_path)
    slug  = brief["slug"]
    title = brief.get("title", slug)
    category = brief.get("category", "News - Policy")
    excerpt  = brief.get("excerpt", brief.get("angle", ""))[:280]
    article_url = f"{SITE_URL}/{slug}/"

    log.info(f"=== Article Packager: {title} ===")

    # 1. Generate MDX article
    log.info("Step 1/4: Writing article...")
    body = w.write_article(raw_text, adjustments)
    frontmatter = w.build_frontmatter(brief)
    mdx_content = frontmatter + body

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    article_path = ARTICLES_DIR / f"{slug}.mdx"
    article_path.write_text(mdx_content, encoding="utf-8")
    log.info(f"  → {article_path}")

    # 2. Generate social campaign
    log.info("Step 2/4: Generating social campaign...")
    social_md = generate_social_campaign(title, article_url, excerpt, body)

    # 3. Generate newsletter
    log.info("Step 3/4: Generating newsletter...")
    newsletter_html, subject, preview_text = generate_newsletter_html(title, article_url, category, excerpt, body)
    newsletter_meta = f"Subject: {subject}\nPreview: {preview_text}\nFrom: {os.getenv('MAILERLITE_FROM_NAME', '')} <{os.getenv('MAILERLITE_FROM_EMAIL', '')}>"

    # Save assets locally alongside the article
    media_dir = ARTICLES_DIR / slug
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "social-campaign.md").write_text(social_md, encoding="utf-8")
    (media_dir / "newsletter.html").write_text(newsletter_html, encoding="utf-8")
    (media_dir / "newsletter-meta.txt").write_text(newsletter_meta, encoding="utf-8")
    log.info(f"  → {media_dir}/")

    # Media kit files for GitHub commit (repo-relative paths)
    media_kit_files = {
        f"src/content/articles/{slug}/social-campaign.md": social_md,
        f"src/content/articles/{slug}/newsletter.html":    newsletter_html,
        f"src/content/articles/{slug}/newsletter-meta.txt": newsletter_meta,
    }

    if dry_run:
        log.info("DRY RUN — skipping GitHub PR and MailerLite")
        _print_review_summary(title, slug, article_url, "DRY_RUN", False, social_md, subject, preview_text)
        return

    # 4. MailerLite: create draft + send to test group
    log.info("Step 4/4: Creating MailerLite draft and sending to test group...")
    ml_url = "https://dashboard.mailerlite.com/campaigns"
    ml_sent = False
    try:
        ml_url, ml_sent = create_and_send_test(title, subject, preview_text, newsletter_html)
    except Exception as e:
        log.warning(f"MailerLite step failed (continuing): {e}")

    # 5. GitHub PR
    log.info("Step 5/5: Creating GitHub PR...")
    try:
        pr_url = create_review_pr(
            brief=brief,
            article_path=article_path,
            media_kit_files=media_kit_files,
            preview_url=f"{SITE_URL}/articles/{slug}/",
            ml_campaign_url=ml_url,
            ml_test_sent=ml_sent,
        )
    except Exception as e:
        log.error(f"GitHub PR failed: {e}")
        pr_url = "ERROR — check logs"

    _print_review_summary(title, slug, article_url, pr_url, ml_sent, social_md, subject, preview_text)


def _print_review_summary(title, slug, url, pr_url, ml_sent, social_md, subject, preview_text):
    print("\n" + "="*60)
    print(f"REVIEW PACKAGE READY: {title}")
    print("="*60)
    print(f"\n  Article preview:  {url}")
    print(f"  GitHub PR:        {pr_url}")
    print(f"  Newsletter (MailerLite): {'sent to test group ✓' if ml_sent else 'draft created (not sent)'}")
    print(f"\n  Subject:   {subject}")
    print(f"  Preview:   {preview_text}")
    print(f"\n  Social campaign preview (Day 1 post):")
    first_post = social_md.split("---")[0].strip().split("\n")
    for line in first_post[:8]:
        if line.strip():
            print(f"    {line}")
    print("\n  → All files saved to src/content/articles/{slug}/")
    print("="*60 + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Article packager — full production pipeline")
    parser.add_argument("brief_path", help="Path to approved brief (.md or .json)")
    parser.add_argument("--adjustments", default="", help="Editor notes for the writer")
    parser.add_argument("--dry-run", action="store_true", help="Generate assets locally only, skip GitHub + MailerLite")
    args = parser.parse_args()
    run(args.brief_path, args.adjustments, args.dry_run)
