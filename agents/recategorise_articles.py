"""
agents/recategorise_articles.py

One-time script to migrate articles from single `category:` to `categories:` array
with the new 7-category taxonomy.

Usage:
  python agents/recategorise_articles.py --dry-run   # preview only
  python agents/recategorise_articles.py             # apply changes
"""

import argparse
import re
from pathlib import Path

ROOT         = Path(__file__).parent.parent
ARTICLES_DIR = ROOT / "src" / "content" / "articles"

# ── Explicit per-slug mapping ──────────────────────────────────────────────────
# slug (filename without .mdx) → list of new categories (first = primary)

EXPLICIT: dict[str, list[str]] = {
    # Censorship & Shutdowns (core mission)
    "myanmar-internet-censorship":                          ["Censorship & Shutdowns", "Policy & Regulation"],
    "myanmar-digital-repression-2026":                      ["Censorship & Shutdowns"],
    "myanmars-digital-walls-leaked-files-how-chinas-great-firewall-was-exported": ["Censorship & Shutdowns"],
    "the-economic-cost-of-internet-censorship-in-myanmar-a-call-for-change": ["Censorship & Shutdowns", "Policy & Regulation"],
    "impact-myanmar-smart-city-privacy":                    ["Censorship & Shutdowns", "Policy & Regulation"],
    "myanmar-digital-economy-plan":                         ["Censorship & Shutdowns", "Policy & Regulation"],
    "fiber-broadband-ftth-myanmar":                         ["ISP & Broadband"],
    "fiber-broadband-ftth-myanmar-my":                      ["ISP & Broadband"],

    # VPN & Security
    "vpn-myanmar":                                          ["VPN & Security", "Censorship & Shutdowns"],
    "protonvpn-vpn-privacy":                                ["VPN & Security"],
    "protect-online-privacy-android-myanmar":               ["VPN & Security"],
    "how-to-protect-your-online-privacy-in-2023-myanmar":   ["VPN & Security"],
    "protect-your-online-privacy-android-myanmar":          ["VPN & Security"],
    "mobile-device-security-myanmar":                       ["VPN & Security"],
    "reasons-use-password-manager":                         ["VPN & Security"],
    "public-dns-fastest-myanmar":                           ["VPN & Security"],
    "apn-settings-and-how-to-change-it":                    ["VPN & Security", "Mobile & Data Plans"],
    "bypass-country-google-play-store":                     ["VPN & Security", "Digital Services"],
    "bypass-country-google-play-store-mm":                  ["VPN & Security", "Digital Services"],
    "watch-pyone-play-outside-myanmar":                     ["VPN & Security", "Digital Services"],

    # ISP & Broadband
    "isp-overview-myanmar":                                 ["ISP & Broadband"],
    "choose-business-internet-provider":                    ["ISP & Broadband"],
    "things-consider-choosing-isp-in-myanmar":              ["ISP & Broadband"],
    "top-10-ideas-successful-isp-myanmar":                  ["ISP & Broadband"],
    "service-provider-blacklist-spam-myanmar":              ["ISP & Broadband"],
    "panic-myanmar-broadband-market":                       ["ISP & Broadband"],
    "save-money-internet-bill":                             ["ISP & Broadband"],
    "home-broadband-plans-myanmar-july-19":                 ["ISP & Broadband"],
    "home-internet-myanmar-sept20":                         ["ISP & Broadband"],
    "residential-internet-myanmar":                         ["ISP & Broadband"],
    "residential-internet-myanmar-january-17":              ["ISP & Broadband"],
    "residential-internet-myanmar-july-2017":               ["ISP & Broadband"],
    "residential-internet-plans-myanmar-2018":              ["ISP & Broadband"],
    "residential-internet-plans-myanmar-nov-2018":          ["ISP & Broadband"],
    "residential-unlimited-broadband-myanmar-december-2017":["ISP & Broadband"],
    "residential-broadband-april-2017":                     ["ISP & Broadband"],
    "globalnet-5bb-residential-broadband":                  ["ISP & Broadband"],
    "myanmarnet-broadband-mass":                            ["ISP & Broadband"],
    "myanmarnet-innovation-myanmar":                        ["ISP & Broadband"],
    "netcore-isp-myanmar":                                  ["ISP & Broadband"],
    "netcore-promotion":                                    ["ISP & Broadband"],
    "netcore-slash-prices":                                 ["ISP & Broadband"],
    "netcore-updates-prices":                               ["ISP & Broadband"],
    "redlink-dead-hail-redlink":                            ["ISP & Broadband"],
    "welink-internet-provider-yangon":                      ["ISP & Broadband"],
    "truenet-isp-myanmar":                                  ["ISP & Broadband"],
    "bluewave-promotion-isp":                               ["ISP & Broadband"],
    "agb-wireless-internet-service-provider-in-myanmar":    ["ISP & Broadband"],
    "myanmar-speednet":                                     ["ISP & Broadband"],
    "peerapp-fortune-success-story":                        ["ISP & Broadband"],
    "ooredoo-myanmar-broadband":                            ["ISP & Broadband"],
    "ooredoo-supernet-wireless-ananda-threat":              ["ISP & Broadband"],
    "telenor-home-wireless-internet":                       ["ISP & Broadband"],
    "telenor-home-wireless-plans":                          ["ISP & Broadband"],
    "telenor-launch-ftth":                                  ["ISP & Broadband"],
    "telenor-myanmar-wifi-offload":                         ["ISP & Broadband"],
    "yatanarpon-lte-ftth":                                  ["ISP & Broadband"],
    "mpt-fiber-broadband-price":                            ["ISP & Broadband"],
    "mpt-broadband-ftth-promotion":                         ["ISP & Broadband"],
    "ipv6-deployment-status-in-myanmar":                    ["Telecom & Infrastructure", "ISP & Broadband"],
    "internet-volume-plans-myanmar":                        ["ISP & Broadband"],
    "watch-netflix-myanmar":                                ["Digital Services", "VPN & Security"],

    # Mobile & Data Plans
    "mpt-3g-4g-apn-settings":                              ["Mobile & Data Plans"],
    "mytel-3g-4g-apn-settings":                            ["Mobile & Data Plans"],
    "ooredoo-myanmar-3g-4g-apn-settings":                  ["Mobile & Data Plans"],
    "telenor-myanmar-3g-4g-apn-settings":                  ["Mobile & Data Plans"],
    "mobile-internet-myanmar-nov16":                        ["Mobile & Data Plans"],
    "mobile-internet-plans-in-myanmar-october-2016":        ["Mobile & Data Plans"],
    "mobile-internet-price-war":                            ["Mobile & Data Plans"],
    "mobile-data-calm-storm":                               ["Mobile & Data Plans"],
    "mobile-operator-myanmar-drop-data-price":              ["Mobile & Data Plans"],
    "mobile-wifi-routers":                                  ["Mobile & Data Plans"],
    "state-mobile-internet-myanmar-20":                     ["Mobile & Data Plans"],
    "tourist-phone-myanmar":                                ["Mobile & Data Plans"],
    "registering-your-sim-card-in-myanmar-a-how-to-guide":  ["Mobile & Data Plans", "Policy & Regulation"],
    "mpt-4g-myanmar":                                       ["Mobile & Data Plans"],
    "mpt-4g-review":                                        ["Mobile & Data Plans"],
    "mpt-mobile-ott":                                       ["Mobile & Data Plans"],
    "mpt-myanmar-speedtest-awards":                         ["Mobile & Data Plans"],
    "mytel-million-subs-myanmar":                           ["Mobile & Data Plans"],
    "mytel-esim-myanmar":                                   ["Mobile & Data Plans"],
    "mytel-3g-4g-apn-settings":                            ["Mobile & Data Plans"],
    "ooredoo-4g-review":                                    ["Mobile & Data Plans"],
    "ooredoo-facebook-topup":                               ["Mobile & Data Plans"],
    "ooredoo-launch-4g-pro-myanmar":                        ["Mobile & Data Plans"],
    "ooredoo-launch-facebook-pack":                         ["Mobile & Data Plans"],
    "ooredoo-launched-m-pitesan-going-after-wave-money":    ["Mobile & Data Plans"],
    "ooredoo-myanmar-offers-esims-to-subscribers":          ["Mobile & Data Plans"],
    "ooredoo-myanmar-operator-year-2018":                   ["Mobile & Data Plans"],
    "ooredoo-night-packs":                                  ["Mobile & Data Plans"],
    "ooredoo-partner-iflix":                                ["Mobile & Data Plans"],
    "ooredoo-planning-an-exit-from-myanmar":                ["Mobile & Data Plans"],
    "ooredoo-telenor-mpt-ussd-memo":                        ["Mobile & Data Plans"],
    "telenor-4g-new-data-suboo":                            ["Mobile & Data Plans"],
    "telenor-announces-unlimited-data-roaming-packs-to-thailand": ["Mobile & Data Plans"],
    "telenor-launch-binge-watching-plans":                  ["Mobile & Data Plans"],
    "telenor-launches-suboo":                               ["Mobile & Data Plans"],
    "telenor-myanmar-3g-4g-apn-settings":                  ["Mobile & Data Plans"],
    "telenor-myanmar-4g-six-cities":                        ["Mobile & Data Plans"],
    "telenor-myanmar-data-roaming":                         ["Mobile & Data Plans"],
    "telenor-myanmar-joox":                                 ["Mobile & Data Plans"],
    "telenor-myanmar-rebrands-to-atom-myanmar":             ["Mobile & Data Plans"],
    "telenor-video-youtube":                                ["Mobile & Data Plans"],
    "reading-lines-telenor-ceo-interview":                  ["Mobile & Data Plans"],
    "mobile-myanmar":                                       ["Mobile & Data Plans"],
    "opensignal-myanmar-mobile-coverage":                   ["Mobile & Data Plans"],
    "myanmar-mobile-data-rise":                             ["Mobile & Data Plans"],
    "myanmar-myanmar-4th-telco-launch-2018":                ["Mobile & Data Plans"],
    "myanmar-4th-telco-launch-2018":                        ["Mobile & Data Plans"],

    # Telecom & Infrastructure
    "4g-spectrum-2017":                                     ["Telecom & Infrastructure"],
    "4g-broadband-myanmar":                                 ["Telecom & Infrastructure"],
    "4g-telco-myanmar-market":                              ["Telecom & Infrastructure"],
    "lte-internet-myanmar-auction":                         ["Telecom & Infrastructure"],
    "myanmar-4g-spectrum":                                  ["Telecom & Infrastructure"],
    "myanmar-mobile-spectrum-4g":                           ["Telecom & Infrastructure"],
    "myanmar-bidder-lte-4g":                                ["Telecom & Infrastructure"],
    "myanmar-consultation-900mhz-e-gsm":                    ["Telecom & Infrastructure"],
    "4g-spectrum-bid-results":                              ["Telecom & Infrastructure"],
    "ixp-internet-exchange-myanmar":                        ["Telecom & Infrastructure"],
    "sd-wan-myanmar-opportunity":                           ["Telecom & Infrastructure"],
    "datacenter-cloud-myanmar":                             ["Telecom & Infrastructure"],
    "embracing-multi-cloud-strategy-myanmar":               ["Telecom & Infrastructure"],
    "shared-vps-dedicated-hosting-myanmar":                 ["Telecom & Infrastructure"],
    "virtual-private-servers-in-myanmar":                   ["Telecom & Infrastructure"],
    "5g-myanmar-future":                                    ["Telecom & Infrastructure"],
    "5g-internet-mobile-myanmar":                           ["Telecom & Infrastructure"],
    "internet-users-myanmar-2017":                          ["Telecom & Infrastructure"],
    "internet-penetration-sept-17":                         ["Telecom & Infrastructure"],
    "internet-myanmar-digest":                              ["Telecom & Infrastructure"],
    "myanmar-4g-spectrum":                                  ["Telecom & Infrastructure"],
    "internet-provider-mandalay":                           ["ISP & Broadband"],
    "yangon-internet-ocean-tamwe":                          ["ISP & Broadband"],
    "yangon-internet-people-park":                          ["ISP & Broadband"],
    "yangon-internet-tour-airport":                         ["ISP & Broadband"],
    "yangon-wifi-map":                                      ["ISP & Broadband"],

    # Digital Services
    "spotify-myanmar":                                      ["Digital Services", "VPN & Security"],
    "how-to-use-spotify-myanmar-my":                        ["Digital Services", "VPN & Security"],
    "iflix-available-myanmar":                              ["Digital Services"],
    "joox-myanmar-leading":                                 ["Digital Services"],
    "pyone-play-download-offline":                          ["Digital Services"],
    "pyone-play-phone":                                     ["Digital Services"],
    "myanflix-telenor":                                     ["Digital Services"],
    "digital-wallets-myanmar":                              ["Digital Services"],
    "rise-of-mobile-banking-in-myanmar":                    ["Digital Services", "Policy & Regulation"],
    "the-growth-of-e-commerce-in-myanmar-opportunities-challenges-and-future-trends": ["Digital Services", "Policy & Regulation"],
    "top-digital-services-myanmar":                         ["Digital Services"],
    "cookie-tv-app-myanmar":                                ["Digital Services"],
    "find-job-myanmar":                                     ["Digital Services"],
    "digital-services-travel-myanmar":                      ["Digital Services"],
    "ooredoo-launched-m-pitesan-going-after-wave-money":    ["Digital Services", "Mobile & Data Plans"],

    # Policy & Regulation
    "technology-in-myanmar-telecom-cybersecurity-blockchain": ["Policy & Regulation"],
    "checking-your-internet-speed-in-myanmar-tools-and-tips": ["Policy & Regulation"],
    "ai-journey-d0-b0-journey-in-the-company-of-a-developer": ["Policy & Regulation"],
    "presearch-a-decentralized-private-and-rewarding-search-engine": ["Policy & Regulation"],
    "my-ooredoo-app-guide":                                 ["Mobile & Data Plans"],
    "enabling-international-and-roaming-services-via-the-ooredoo-app": ["Mobile & Data Plans"],
    "social-marketing-isp-myanmar":                         ["ISP & Broadband"],
    "social-media-mobile":                                  ["Mobile & Data Plans"],
    "digital-wallets-myanmar":                              ["Digital Services"],
    "digital-economy-myanmar":                              ["Policy & Regulation", "Digital Services"],
    "e1-80-80-e1-80-bc-e1-80-ba-e1-80-94-e1-80-b9-e1-80-b1-e1-80-90-e1-80-ac-e1-80-b9": ["Digital Services"],
    "e1-80-90-e1-80-85-e1-80-b9-e1-80-85-e1-80-91-e1-80-80-e1-80-b9-e1-80-90-e1-80-85": ["Digital Services"],
    "e1-80-9a-e1-80-b1-e1-80-94-e1-82-94-e1-80-b1-e1-80-81-e1-80-90-e1-80-b9-e1-80-9c": ["Digital Services"],

    # Misc phones/devices → Mobile
    "huawei-honor-4-pro-temperature":                       ["Mobile & Data Plans"],
    "huawei-p40-myanmar":                                   ["Mobile & Data Plans"],
    "mi-note-10-108mp-camera":                              ["Mobile & Data Plans"],
    "redmi-note-8-sales":                                   ["Mobile & Data Plans"],
    "redmi-note-9-pro-soon-myanmar":                        ["Mobile & Data Plans"],
    "xiaomi-mi-11-release-myanmar":                         ["Mobile & Data Plans"],
    "xiaomi-miui-11":                                       ["Mobile & Data Plans"],
    "xiaomi-miui-12-mi10-youth":                            ["Mobile & Data Plans"],
    "find-android-myanmar":                                 ["Mobile & Data Plans"],
    "myanflix-telenor":                                     ["Digital Services"],
    "mobile-myanmar":                                       ["Mobile & Data Plans"],

    # Misc
    "mobile-internet-myanmar-nov16":                        ["Mobile & Data Plans"],
    "phalan-phalan":                                        ["Mobile & Data Plans"],
    "digital-services-travel-myanmar":                      ["Digital Services"],
    "rise-of-mobile-banking-in-myanmar":                    ["Digital Services", "Policy & Regulation"],
    "digital-wallets-myanmar":                              ["Digital Services"],
}

# ── Keyword fallback rules (applied when no explicit mapping) ─────────────────
# Each rule: (list_of_keywords_to_match_in_tags, category)
# Tags are checked case-insensitively. First match wins.

KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["censorship", "shutdown", "surveillance", "firewall", "blocking"],   "Censorship & Shutdowns"),
    (["vpn", "nordvpn", "protonvpn", "privacy", "dns", "duckduckgo"],     "VPN & Security"),
    (["cybersecurity", "password", "encryption", "android security"],      "VPN & Security"),
    (["ftth", "fiber", "wisp", "broadband", "5bb", "frontiir", "myanmarnet", "netcore", "isp"],
                                                                            "ISP & Broadband"),
    (["apn", "3g", "4g", "lte", "sim", "roaming", "mpt", "ooredoo", "mytel", "telenor", "atom"],
                                                                            "Mobile & Data Plans"),
    (["spectrum", "igw", "ixp", "ipv6", "sd-wan", "cloud", "datacenter"],  "Telecom & Infrastructure"),
    (["netflix", "spotify", "iflix", "streaming", "joox", "pyone", "wallet", "fintech", "e-commerce"],
                                                                            "Digital Services"),
    (["policy", "regulation", "digital policy", "telecom", "blockchain"],   "Policy & Regulation"),
]

# Old → new category mapping (for articles not in EXPLICIT)
OLD_TO_NEW: dict[str, str] = {
    "Censorship & Shutdowns":   "Censorship & Shutdowns",
    "Telecom & Infrastructure": "Telecom & Infrastructure",
    "Digital Economy":          "Digital Services",
    "Guides & Tools":           "VPN & Security",
    "News - Mobile":            "Mobile & Data Plans",
    "News - Broadband":         "ISP & Broadband",
    "News - Policy":            "Policy & Regulation",
}


def guess_categories(slug: str, tags: list[str], old_category: str) -> list[str]:
    """Return best-guess categories for an article not in EXPLICIT."""
    # Try keyword rules on tags
    tags_lower = [t.lower() for t in tags]
    for keywords, cat in KEYWORD_RULES:
        if any(kw.lower() in tags_lower for kw in keywords):
            return [cat]
    # Fall back to old→new mapping
    return [OLD_TO_NEW.get(old_category, "Policy & Regulation")]


def process_file(path: Path, dry_run: bool) -> str:
    text = path.read_text(encoding="utf-8")
    slug = path.stem

    # Extract old category
    cat_match = re.search(r'^category:\s+"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    if not cat_match:
        return f"  SKIP (no category): {slug}"

    old_cat = cat_match.group(1).strip()

    # Extract tags for keyword fallback
    tags: list[str] = re.findall(r'"([^"]+)"', re.search(
        r'^tags:\s*\[([^\]]*)\]', text, re.MULTILINE | re.DOTALL
    ).group(1) if re.search(r'^tags:\s*\[', text, re.MULTILINE) else "")

    # Determine new categories
    if slug in EXPLICIT:
        new_cats = EXPLICIT[slug]
    else:
        new_cats = guess_categories(slug, tags, old_cat)

    # Build replacement YAML
    cats_yaml = "\n".join(f'  - "{c}"' for c in new_cats)
    new_block = f"categories:\n{cats_yaml}"

    # Replace `category: "..."` with `categories:\n  - "..."`
    new_text = re.sub(
        r'^category:\s+"?[^"\n]+"?\s*$',
        new_block,
        text,
        flags=re.MULTILINE,
    )

    if new_text == text:
        return f"  UNCHANGED: {slug}"

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")

    action = "DRY" if dry_run else "UPDATED"
    return f"  {action}: {slug}\n    {old_cat} → {', '.join(new_cats)}"


def run(dry_run: bool):
    files = sorted(ARTICLES_DIR.glob("*.mdx"))
    print(f"{'DRY RUN — ' if dry_run else ''}Processing {len(files)} articles…\n")

    results = [process_file(f, dry_run) for f in files]
    for r in results:
        print(r)

    updated = sum(1 for r in results if "UPDATED" in r or "DRY" in r and "→" in r)
    skipped = sum(1 for r in results if "SKIP" in r or "UNCHANGED" in r)
    print(f"\n{'Would update' if dry_run else 'Updated'}: {updated} | Skipped/unchanged: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
