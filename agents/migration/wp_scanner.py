"""
WP Scanner — rule-based, outputs CSV for editorial review.
Columns: Title, Date, URL, Author, Word Count, Recommendation, Decision
"""

import csv
import sys
from pathlib import Path
from datetime import datetime
import mysql.connector

import os as _os
from dotenv import load_dotenv as _load
_load()
DB = dict(
    host="127.0.0.1", port=3307,
    database=_os.getenv("WP_DB_NAME", "internetinmyanmar"),
    user=_os.getenv("WP_DB_USER", "claudagent"),
    password=_os.getenv("WP_DB_PASSWORD_READONLY", ""),
)

# Keywords that strongly suggest MIGRATE
MIGRATE_KEYWORDS = [
    "censorship", "shutdown", "blocked", "blocking", "internet freedom",
    "digital rights", "vpn", "firewall", "ooni", "surveillance",
    "coup", "junta", "military", "ban", "outage", "throttling",
    "circumvention", "tor", "proxy", "privacy", "cybersecurity",
    "cyber security", "digital security", "encryption", "internet cut",
    "internet disruption", "network disruption", "spectrum", "telecom policy",
    "telecom regulation", "internet penetration", "digital economy",
    "internet access", "online freedom", "press freedom", "media freedom",
    "disinformation", "misinformation", "content moderation",
    "facebook ban", "twitter ban", "social media ban",
]

# Keywords that suggest SKIP
SKIP_KEYWORDS = [
    "bitcoin", "binance", "crypto", "ethereum", "nft", "defi",
    "kucoin", "blockchain remittance", "passive income", "computesharing",
    "kryptex", "salad.io", "referral code", "cashback",
    "hotel", "inle lake", "bagan tour", "day trip from yangon",
    "restaurant", "travel guide", "tourist",
    "xiaomi mi ", "redmi note", "huawei p40", "honor play",
    "iflix", "joox", "spotify", "netflix", "pyone play",
    "miui", "apn settings", "ussd", "wavepay", "kbzpay",
    "mobile banking app", "contactless payment", "yoma bank",
    "sim card registration", "topping up", "data roaming promotion",
    "myanflix", "esports", "mobile game",
]

# Categories that map cleanly
MIGRATE_CATEGORIES = {
    "Analysis", "Toolbox", "Broadband", "Mobile", "News",
    "Business", "OTT", "Stories", "English",
}
SKIP_CATEGORIES = {
    "Crypto", "Travel", "ခရစ်တိုငွေကြေး", "Promotions",
}


def score(post: dict) -> tuple[str, str]:
    """Returns (recommendation, reason)"""
    title = post["title"].lower()
    cats = set(post["categories"].split(", ")) if post["categories"] else set()
    word_count = post["word_count"]

    # Hard skips
    if cats & SKIP_CATEGORIES:
        return "SKIP", f"category: {', '.join(cats & SKIP_CATEGORIES)}"
    for kw in SKIP_KEYWORDS:
        if kw in title:
            return "SKIP", f"keyword: {kw}"
    if word_count < 300:
        return "SKIP", f"too short ({word_count} words)"

    # Strong migrate signals
    for kw in MIGRATE_KEYWORDS:
        if kw in title:
            return "MIGRATE", f"keyword: {kw}"

    # Category-based
    if cats & MIGRATE_CATEGORIES and word_count >= 600:
        return "MIGRATE", f"category: {', '.join(cats & MIGRATE_CATEGORIES)}, {word_count} words"

    # Burmese-language posts — flag for review
    if any(ord(c) > 0x1000 for c in post["title"]):
        return "REVIEW", "Burmese language — check relevance"

    return "REVIEW", f"no clear signal — {word_count} words, cats: {post['categories']}"


def run():
    conn = mysql.connector.connect(**DB)
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.ID, p.post_title as title, p.post_date, p.post_name as slug,
               ROUND(LENGTH(p.post_content) / 5) as word_count,
               u.display_name as author,
               GROUP_CONCAT(t.name ORDER BY t.name SEPARATOR ', ') as categories
        FROM wp_posts p
        LEFT JOIN wp_users u ON u.ID = p.post_author
        LEFT JOIN wp_term_relationships tr ON p.ID = tr.object_id
        LEFT JOIN wp_term_taxonomy tt ON tr.term_taxonomy_id = tt.term_taxonomy_id AND tt.taxonomy = 'category'
        LEFT JOIN wp_terms t ON tt.term_id = t.term_id
        WHERE p.post_status = 'publish' AND p.post_type = 'post'
        GROUP BY p.ID
        ORDER BY p.post_date DESC
    """)
    posts = cur.fetchall()
    conn.close()

    writer = csv.writer(sys.stdout)
    writer.writerow(["Title", "Date", "Author", "Words", "Categories", "Recommendation", "Reason", "Decision"])

    counts = {"MIGRATE": 0, "REVIEW": 0, "SKIP": 0}
    for p in posts:
        p["categories"] = p["categories"] or ""
        p["word_count"] = p["word_count"] or 0
        p["post_date"] = p["post_date"].strftime("%Y-%m-%d") if p["post_date"] else ""
        rec, reason = score(p)
        counts[rec] += 1
        writer.writerow([
            p["title"],
            p["post_date"],
            p["author"],
            p["word_count"],
            p["categories"],
            rec,
            reason,
            "",  # Decision — you fill this: OK or NOK
        ])

    print(f"\n# Summary: MIGRATE={counts['MIGRATE']} | REVIEW={counts['REVIEW']} | SKIP={counts['SKIP']}", file=sys.stderr)


if __name__ == "__main__":
    run()
