"""
Unit tests for process_datasets.py — normalize and join functions.
Run with: cd agents && python -m pytest tests/test_process_datasets.py -v
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from process_datasets import (
    compute_metrics,
    join_unified_events,
    normalize_bgp_outages,
    normalize_cf_radar,
    normalize_keepiton,
    parse_date,
    parse_dt,
    severity_bgp,
    severity_keepiton,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BGP_RAW_SAMPLE = [
    {
        "asn": "AS9988",
        "name": "MPT",
        "status": "DOWN",
        "started_at": "2026-04-10T06:00:00+00:00",
        "ended_at":   "2026-04-10T08:30:00+00:00",
        "duration_minutes": 150,
        "min_visibility_pct": 0.0,
        "ioda_confirmed": True,
        "resolved": True,
    },
    {
        "asn": "AS132167",
        "name": "Ooredoo",
        "status": "DOWN",
        "started_at": "2026-04-15T12:00:00+00:00",
        "ended_at":   "2026-04-15T12:20:00+00:00",
        "duration_minutes": 20,
        "min_visibility_pct": 50.0,
        "ioda_confirmed": False,
        "resolved": True,
    },
]

KIT_RAW_SAMPLE = {
    "lastUpdated": "2026-04-26T00:00:00Z",
    "totalEvents": 2,
    "source": "Access Now",
    "events": [
        {
            "id": "kit-001",
            "startDate": "2026-04-09",
            "endDate": "2026-04-12",
            "ongoing": False,
            "type": "full_network",
            "scope": "Sagaing Region",
            "perpetrator": "Military",
            "services": ["Mobile", "Broadband"],
            "sourceUrl": "https://example.com/1",
        },
        {
            "id": "kit-002",
            "startDate": "2021-02-01",
            "endDate": None,
            "ongoing": True,
            "type": "full_network",
            "scope": "Nationwide",
            "perpetrator": "Military",
            "services": ["Mobile"],
            "sourceUrl": "https://example.com/2",
        },
    ],
}


# ---------------------------------------------------------------------------
# parse_dt / parse_date
# ---------------------------------------------------------------------------

def test_parse_dt_utc():
    dt = parse_dt("2026-04-10T06:00:00+00:00")
    assert dt.tzinfo is not None
    assert dt.hour == 6


def test_parse_dt_z_suffix():
    dt = parse_dt("2026-04-10T06:00:00Z")
    assert dt.hour == 6


def test_parse_dt_offset():
    dt = parse_dt("2026-04-10T08:00:00-04:00")
    assert dt.hour == 12  # converted to UTC


def test_parse_date_valid():
    assert parse_date("2026-04-10") == date(2026, 4, 10)


def test_parse_date_none():
    assert parse_date(None) is None
    assert parse_date("") is None


# ---------------------------------------------------------------------------
# normalize_bgp_outages
# ---------------------------------------------------------------------------

def test_normalize_bgp_outages_count():
    result = normalize_bgp_outages(BGP_RAW_SAMPLE)
    assert len(result) == 2


def test_normalize_bgp_outages_fields():
    result = normalize_bgp_outages(BGP_RAW_SAMPLE)
    r = result[0]
    assert r["asn"] == "AS9988"
    assert r["isp_name"] == "MPT"
    assert r["duration_minutes"] == 150
    assert r["ioda_confirmed"] is True
    assert isinstance(r["_started_dt"], datetime)


def test_normalize_bgp_outages_sorted():
    result = normalize_bgp_outages(BGP_RAW_SAMPLE)
    times = [r["_started_dt"] for r in result]
    assert times == sorted(times)


def test_normalize_bgp_outages_empty():
    assert normalize_bgp_outages([]) == []


def test_normalize_bgp_skips_malformed():
    bad = [{"asn": "AS999"}]  # missing started_at
    result = normalize_bgp_outages(bad)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# normalize_keepiton
# ---------------------------------------------------------------------------

def test_normalize_keepiton_count():
    result = normalize_keepiton(KIT_RAW_SAMPLE)
    assert len(result) == 2


def test_normalize_keepiton_fields():
    result = normalize_keepiton(KIT_RAW_SAMPLE)
    # sorted by start_date: kit-002 (2021-02-01) precedes kit-001 (2026-04-09)
    r = next(x for x in result if x["id"] == "kit-001")
    assert r["start_date"] == "2026-04-09"
    assert r["ongoing"] is False
    assert r["duration_days"] == 3
    assert isinstance(r["_start_date"], date)


def test_normalize_keepiton_ongoing_duration():
    result = normalize_keepiton(KIT_RAW_SAMPLE)
    ongoing = next(r for r in result if r["ongoing"])
    # ongoing since 2021-02-01 — duration should be large
    assert ongoing["duration_days"] > 365 * 5


def test_normalize_keepiton_empty():
    result = normalize_keepiton({})
    assert result == []


def test_normalize_keepiton_skips_no_start():
    raw = {"events": [{"id": "x", "startDate": None, "endDate": None, "ongoing": False,
                        "type": "shutdown", "scope": "", "perpetrator": "",
                        "services": [], "sourceUrl": ""}]}
    result = normalize_keepiton(raw)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# normalize_cf_radar
# ---------------------------------------------------------------------------

def test_normalize_cf_radar_empty():
    assert normalize_cf_radar({}) == []


def test_normalize_cf_radar_active():
    raw = {"activeOutages": [{"start": "2026-04-10T00:00:00Z", "end": None, "scope": "MM"}]}
    result = normalize_cf_radar(raw)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# severity helpers
# ---------------------------------------------------------------------------

def test_severity_bgp_ioda_confirmed_long():
    assert severity_bgp(300, True, 0.0) == 5


def test_severity_bgp_ioda_confirmed_short():
    assert severity_bgp(60, True, 0.0) == 4


def test_severity_bgp_long_unconfirmed():
    assert severity_bgp(300, False, 0.0) == 3


def test_severity_bgp_medium():
    assert severity_bgp(90, False, 50.0) == 2


def test_severity_bgp_blip():
    assert severity_bgp(15, False, 80.0) == 1


def test_severity_keepiton_nationwide_ongoing():
    assert severity_keepiton("full_network", "Nationwide", True) == 5


def test_severity_keepiton_regional():
    assert severity_keepiton("full_network", "Sagaing", False) == 4


def test_severity_keepiton_mobile():
    assert severity_keepiton("mobile", "Kachin", False) == 3


# ---------------------------------------------------------------------------
# join_unified_events
# ---------------------------------------------------------------------------

def test_join_produces_both_types():
    bgp  = normalize_bgp_outages(BGP_RAW_SAMPLE)
    kit  = normalize_keepiton(KIT_RAW_SAMPLE)
    cf   = normalize_cf_radar({})
    result = join_unified_events(bgp, kit, cf)

    types = {e["event_type"] for e in result}
    assert "outage" in types
    assert "shutdown" in types


def test_join_bgp_event_matched_to_keepiton():
    bgp  = normalize_bgp_outages(BGP_RAW_SAMPLE)  # first outage: 2026-04-10
    kit  = normalize_keepiton(KIT_RAW_SAMPLE)      # kit-001: 2026-04-09 → 2026-04-12
    result = join_unified_events(bgp, kit, [])

    bgp_events = [e for e in result if e["event_type"] == "outage" and "bgp" in e["sources"]]
    first = next(e for e in bgp_events if "AS9988" in (e.get("asn") or ""))
    assert first["keepiton_matched"] is True
    assert "kit-001" in first["keepiton_ids"]


def test_join_bgp_event_unmatched():
    # Outage on 2026-04-15, no KIT event covering it (kit-001 ends 2026-04-12)
    bgp  = normalize_bgp_outages([BGP_RAW_SAMPLE[1]])  # AS132167 on 2026-04-15
    kit  = normalize_keepiton({"events": [KIT_RAW_SAMPLE["events"][0]]})
    result = join_unified_events(bgp, kit, [])

    bgp_events = [e for e in result if e["event_type"] == "outage" and "bgp" in e["sources"]]
    # kit-001 ends 2026-04-12, outage is 2026-04-15 — ongoing KIT event absent here
    # (we only included kit-001 which is not ongoing)
    assert bgp_events[0]["keepiton_matched"] is False


def test_join_keepiton_shutdown_is_confirmed():
    bgp  = normalize_bgp_outages([])
    kit  = normalize_keepiton(KIT_RAW_SAMPLE)
    result = join_unified_events(bgp, kit, [])

    kit_events = [e for e in result if e["event_type"] == "shutdown"]
    for e in kit_events:
        assert e["is_confirmed"] is True


def test_join_sorted_chronologically():
    bgp  = normalize_bgp_outages(BGP_RAW_SAMPLE)
    kit  = normalize_keepiton(KIT_RAW_SAMPLE)
    result = join_unified_events(bgp, kit, [])
    times = [e["event_time"] for e in result]
    assert times == sorted(times)


def test_join_no_internal_fields():
    bgp  = normalize_bgp_outages(BGP_RAW_SAMPLE)
    kit  = normalize_keepiton(KIT_RAW_SAMPLE)
    result = join_unified_events(bgp, kit, [])
    for event in result:
        for key in event:
            assert not key.startswith("_"), f"Internal field leaked: {key}"


def test_join_empty_inputs():
    result = join_unified_events([], [], [])
    assert result == []


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------

def test_compute_metrics_active_shutdowns():
    bgp  = normalize_bgp_outages([])
    kit  = normalize_keepiton(KIT_RAW_SAMPLE)  # 1 ongoing
    unified = join_unified_events(bgp, kit, [])
    metrics = compute_metrics(unified, [], {}, {}, {})
    assert metrics["active_shutdowns"] == 1


def test_compute_metrics_ooni_rate():
    ooni_daily = [
        {"period": "2026-04-24", "anomaly_rate": 10.0, "measurement_start_day": "2026-04-24"},
        {"period": "2026-04-25", "anomaly_rate": 12.0, "measurement_start_day": "2026-04-25"},
        {"period": "2026-04-26", "anomaly_rate": 14.0, "measurement_start_day": "2026-04-26"},
    ]
    metrics = compute_metrics([], ooni_daily, {}, {}, {})
    assert metrics["ooni_anomaly_rate_30d"] == 12.0
    assert metrics["censorship_prevalence_pct"] == 14.0


def test_compute_metrics_blocked_sites():
    blocked = {"totalDomains": 42, "sites": []}
    metrics = compute_metrics([], [], blocked, {}, {})
    assert metrics["confirmed_blocked_sites"] == 42


def test_compute_metrics_bgp_down():
    status = {
        "AS9988":  {"status": "RED"},
        "AS12345": {"status": "GREEN"},
        "AS99999": {"status": "YELLOW"},
    }
    metrics = compute_metrics([], [], {}, {}, status)
    assert metrics["bgp_networks_down_now"] == 2


def test_compute_metrics_cf_latest():
    cf = {"daily": [
        {"timestamp": "2026-04-24T00:00:00Z", "cf_traffic": 80.0},
        {"timestamp": "2026-04-25T00:00:00Z", "cf_traffic": 85.5},
    ]}
    metrics = compute_metrics([], [], {}, cf, {})
    assert metrics["cf_traffic_latest_pct"] == 85.5


def test_compute_metrics_partial_failure():
    # All inputs empty/missing — should not raise
    metrics = compute_metrics([], [], {}, {}, {})
    assert metrics["active_shutdowns"] == 0
    assert metrics["confirmed_blocked_sites"] == 0
