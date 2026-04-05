"""
Publisher
---------
Commits the approved MDX article to a draft/* branch and opens a GitHub PR.
Called by the Telegram bot after Anna hits [Publish].

Usage:
  python publisher.py --brief-id <uuid>

Output: JSON to stdout → {"pr_url": "https://github.com/..."}
"""

import json
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from github import Github, GithubException
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
log = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent
CONFIG = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = CONFIG["github"]["repo"]
BASE_BRANCH = CONFIG["github"]["base_branch"]
DRAFT_PREFIX = CONFIG["github"]["draft_prefix"]

BRIEFS_DIR = AGENTS_DIR / "briefs"
ARTICLES_DIR = Path(CONFIG["paths"]["articles"]).expanduser()


def find_brief(brief_id: str) -> dict:
    for f in BRIEFS_DIR.rglob("*.json"):
        data = json.loads(f.read_text())
        if data.get("id") == brief_id:
            return data
    raise FileNotFoundError(f"Brief {brief_id} not found")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def open_pr(brief: dict, article_path: Path) -> str:
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    branch_name = f"{DRAFT_PREFIX}{brief['slug']}"
    base = repo.get_branch(BASE_BRANCH)

    try:
        repo.create_git_ref(f"refs/heads/{branch_name}", base.commit.sha)
    except GithubException as e:
        if e.status != 422:
            raise
        log.info(f"Branch {branch_name} already exists, updating")

    content = article_path.read_text(encoding="utf-8")
    remote_path = f"src/content/articles/{brief['slug']}.mdx"

    try:
        existing = repo.get_contents(remote_path, ref=branch_name)
        repo.update_file(
            remote_path,
            f"draft: {brief['title']}",
            content,
            existing.sha,
            branch=branch_name,
        )
    except GithubException:
        repo.create_file(
            remote_path,
            f"draft: {brief['title']}",
            content,
            branch=branch_name,
        )

    pr = repo.create_pull(
        title=f"Draft: {brief['title']}",
        body=(
            f"**Category:** {brief['category']}\n"
            f"**Tags:** {', '.join(brief.get('tags', []))}\n\n"
            f"**Excerpt:** {brief.get('excerpt', '')}\n\n"
            "---\n"
            "Set `draft: false` in Keystatic before merging to publish."
        ),
        head=branch_name,
        base=BASE_BRANCH,
        draft=True,
    )
    return pr.html_url


def run(brief_id: str):
    brief = find_brief(brief_id)
    article_path = ARTICLES_DIR / f"{brief['slug']}.mdx"

    if not article_path.exists():
        log.error(f"Article not found: {article_path}")
        sys.exit(1)

    pr_url = open_pr(brief, article_path)
    print(json.dumps({"pr_url": pr_url}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = sys.argv[1:]
    bid = args[args.index("--brief-id") + 1] if "--brief-id" in args else None
    if not bid:
        print("Usage: publisher.py --brief-id <id>", file=sys.stderr)
        sys.exit(1)
    run(bid)
