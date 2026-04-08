"""
agents/bgp_classifier.py

Classifies each Myanmar ASN as MNO / IGW / IXP / ISP using
RIPEstat asn-neighbours topology data. Run once; refresh weekly.

Usage:
  python agents/bgp_classifier.py
  python agents/bgp_classifier.py --dry-run   # print results, don't write file

Output: src/data/asn-metadata.json
Crontab: 0 2 * * 0  ~/agents/venv/bin/python ~/agents/bgp_classifier.py >> ~/logs/classifier.log 2>&1
"""

import argparse
import json
import time
from pathlib import Path

import requests

ROOT      = Path(__file__).parent.parent
DATA_FILE = ROOT / "src" / "data" / "asn-metadata.json"
STATUS_FILE = ROOT / "src" / "data" / "asn-status.json"

# ── Curated lists (BGP cannot derive these) ───────────────────────────────────

KNOWN_MNOS = {
    "9988",   # Myanma Posts and Telecommunications (MPT)
    "132167", # Ooredoo Myanmar / Nine Communications (U9)
    "136480", # Mytel / Myanmar National Telecom (MNTC)
    "133385", # Atom Myanmar (formerly Telenor Myanmar)
}

KNOWN_IXPS = {
    "137955", # Myanmar Internet Exchange (MMIX)
    "45558",  # MPT IXP / international gateway function
}

MIN_PATH_COUNT = 10  # ignore upstreams seen in fewer than this many paths


# ── RIPEstat helpers ──────────────────────────────────────────────────────────

def get_myanmar_asns_from_status() -> set[str]:
    """Use our own monitored ASN list as the Myanmar ASN set."""
    with open(STATUS_FILE) as f:
        status = json.load(f)
    # Strip "AS" prefix, return bare numbers
    return {k.replace("AS", "") for k in status.keys()}


def get_neighbours(asn_num: str) -> list[dict]:
    """Return asn-neighbours list for one ASN.
    API fields: type ('left'|'right'|'uncertain'), power, v4_peers, v6_peers
    """
    url = f"https://stat.ripe.net/data/asn-neighbours/data.json?resource=AS{asn_num}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["neighbours"]


# ── Classification ────────────────────────────────────────────────────────────

def classify_asn(asn_num: str, myanmar_asns: set[str]) -> dict:
    """
    Returns classification dict.
    type: MNO | IGW | IXP | ISP
    """
    clean = asn_num.replace("AS", "")

    if clean in KNOWN_MNOS:
        return {
            "type": "MNO",
            "is_mno": True,
            "is_igw": False,
            "foreign_upstreams": [],
            "note": "Licensed mobile network operator",
        }

    if clean in KNOWN_IXPS:
        return {
            "type": "IXP",
            "is_mno": False,
            "is_igw": True,
            "foreign_upstreams": [],
            "note": "Internet exchange point",
        }

    # IGW detection via asn-neighbours
    try:
        neighbours = get_neighbours(clean)
        foreign_upstreams = []
        for n in neighbours:
            # API uses "type" field: left | right | uncertain
            if n.get("type") not in ("left", "uncertain"):
                continue
            # Use v4_peers as significance metric (equivalent to path_count)
            peers = n.get("v4_peers", 0) + n.get("v6_peers", 0)
            if peers < MIN_PATH_COUNT:
                continue
            n_asn = str(n["asn"])
            if n_asn not in myanmar_asns:
                foreign_upstreams.append({
                    "asn": f"AS{n_asn}",
                    "path_count": peers,
                })

        if foreign_upstreams:
            top = ", ".join(f["asn"] for f in foreign_upstreams[:3])
            return {
                "type": "IGW",
                "is_mno": False,
                "is_igw": True,
                "foreign_upstreams": foreign_upstreams,
                "note": f"Peers internationally via {top}",
            }

    except Exception as e:
        print(f"  Warning: neighbour lookup failed for AS{clean}: {e}")

    return {
        "type": "ISP",
        "is_mno": False,
        "is_igw": False,
        "foreign_upstreams": [],
        "note": "Domestic ISP — all significant upstreams are Myanmar ASNs",
    }


def run(dry_run: bool = False):
    # Load ASN list from existing asn-status.json
    with open(STATUS_FILE) as f:
        status = json.load(f)
    asn_list = list(status.keys())
    print(f"Classifying {len(asn_list)} ASNs...")

    myanmar_asns = get_myanmar_asns_from_status()
    print(f"  {len(myanmar_asns)} Myanmar ASNs in monitored set")

    db: dict[str, dict] = {}
    for asn in asn_list:
        clean = asn.replace("AS", "")
        result = classify_asn(clean, myanmar_asns)
        db[asn] = result
        badge = {"MNO": "📱", "IGW": "🌐", "IXP": "🔀", "ISP": "🏠"}[result["type"]]
        print(f"  {badge} {asn:12s} {result['type']:4s}  {result['note'][:60]}")
        time.sleep(0.3)  # be polite to RIPEstat

    # Summary
    counts = {t: sum(1 for v in db.values() if v["type"] == t) for t in ("MNO", "IGW", "IXP", "ISP")}
    print(f"\nResults: {counts}")

    igws = [asn for asn, v in db.items() if v["type"] == "IGW"]
    if igws:
        print("\nIGWs detected:")
        for asn in igws:
            print(f"  {asn}: {db[asn]['note']}")

    if dry_run:
        print("\n[dry-run] Not writing file.")
        return

    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Written to {DATA_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
