"""Tripwire tests for the Reclamation Evidence Ledger.

Each test guards a hard-won correction. If one fails, something regressed
toward a previously fixed bug — read the test name, read the linked rule,
fix the cause, not the test.

Run: .venv/bin/python -m pytest tests/ -q
"""
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ledger.change import MIN_MATCHED_MONTHS_FOR_CI, assess  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "evidence-packet.schema.json").read_text())
PACKETS = sorted((ROOT / "packets").glob("*.json"))


def _synth(months, base_vals, cur_vals):
    """Synthetic month -> [scene means] inputs for assess()."""
    b = {m: [v] * 3 for m, v in zip(months, base_vals)}
    c = {m: [v] * 3 for m, v in zip(months, cur_vals)}
    return b, c


# --- Item 1: the degenerate-CI guard ---------------------------------------

def test_ci_omitted_below_threshold_unit():
    """assess() must not emit delta_ci95 with <4 matched months."""
    b, c = _synth([5, 6], [0.30, 0.32], [0.40, 0.42])
    a = assess("TEST", b, c, "test period")
    assert a.delta_ci95 is None
    assert a.matched_months == [5, 6]
    assert "not estimated" in a.rationale


def test_ci_present_at_threshold_unit():
    b, c = _synth([5, 6, 7, 8], [0.30] * 4, [0.40] * 4)
    a = assess("TEST", b, c, "test period")
    assert a.delta_ci95 is not None and len(a.delta_ci95) == 2
    assert "95% CI" in a.rationale


def test_no_packet_carries_ci_below_threshold():
    """No packet on disk may carry delta_ci95 with <4 matched months."""
    bad = []
    for p in PACKETS:
        d = json.loads(p.read_text())
        det = d["assessment_detail"]
        if len(det["matched_months"]) < MIN_MATCHED_MONTHS_FOR_CI and "delta_ci95" in det:
            bad.append(p.name)
    assert not bad, f"packets with degenerate CI: {bad}"


def test_caveat_does_not_claim_wide_interval():
    """The old lie ('few matched months means a wide interval') must be gone."""
    for p in PACKETS:
        d = json.loads(p.read_text())
        for cav in d["claim"]["caveats"]:
            assert "wide interval" not in cav.lower(), f"{p.name}: {cav}"


# --- Item 3: observation-count labels mean one thing -------------------------

def test_observation_count_definitions():
    """n_scene_observations == recomputed count of scene means in matched
    months with usable NDVI — separately for each period. One label, one
    definition, everywhere."""
    base_years, cur_years = {2023, 2024}, {2025, 2026}
    for p in PACKETS:
        d = json.loads(p.read_text())
        matched = set(d["assessment_detail"]["matched_months"])
        obs = d["observations"]
        n_base = sum(1 for o in obs
                     if int(o["date"][:4]) in base_years
                     and int(o["date"][5:7]) in matched
                     and o["ndvi_mean"] is not None)
        n_cur = sum(1 for o in obs
                    if int(o["date"][:4]) in cur_years
                    and int(o["date"][5:7]) in matched
                    and o["ndvi_mean"] is not None)
        assert d["baseline"]["n_scene_observations"] == n_base, p.name
        assert d["assessment_detail"]["n_scene_observations"] == n_cur, p.name


def test_delta_is_median_of_deltas():
    """delta_vs_baseline is the median of per-month deltas, and must NOT
    equal the difference of the displayed medians in the asymmetric case."""
    # asymmetric monthly deltas: median of deltas (0.075) != diff of medians (0.10)
    b, c = _synth([5, 6, 7, 8], [0.20, 0.30, 0.40, 0.50], [0.25, 0.35, 0.55, 0.60])
    a = assess("TEST", b, c, "test period")
    assert a.delta == pytest.approx(0.075)
    assert (a.current_ndvi - a.baseline_ndvi) == pytest.approx(0.10)
    assert (a.current_ndvi - a.baseline_ndvi) != pytest.approx(a.delta)
    assert "median matched-month" in a.rationale.lower()


def test_delta_std_is_spread_of_deltas():
    """delta_std must be the std of matched-month deltas (not baseline var)."""
    import numpy as np
    b, c = _synth([5, 6, 7, 8], [0.20, 0.30, 0.40, 0.50], [0.30, 0.42, 0.48, 0.55])
    a = assess("TEST", b, c, "test period")
    deltas = [0.10, 0.12, 0.08, 0.05]
    assert a.delta_std == pytest.approx(float(np.std(deltas)), abs=1e-3)


# --- Tier rule ci-gated-v2: identified needs |delta| >= 0.08 AND a CI that
# excludes zero. v1 ignored the CI and called 28/99 sites "identified".

from ledger.change import STATEMENTS, assign_tier  # noqa: E402


def test_identified_requires_ci_excluding_zero():
    assert assign_tier(0.12, [0.05, 0.20])[0] == "identified"
    assert assign_tier(-0.12, [-0.20, -0.05])[0] == "identified"


def test_large_delta_without_ci_is_detected():
    tier, direction, key = assign_tier(0.20, None)
    assert (tier, direction, key) == ("detected", "increase", "no_ci")


def test_large_delta_with_ci_straddling_zero_is_detected():
    assert assign_tier(0.10, [-0.01, 0.20])[:2] == ("detected", "increase")
    assert assign_tier(-0.10, [-0.20, 0.0])[:2] == ("detected", "decrease")


def test_small_delta_is_detected_even_with_tight_ci():
    assert assign_tier(0.05, [0.04, 0.06]) == ("detected", "none", "none")


def test_unit_assess_two_months_never_identified():
    b, c = _synth([5, 6], [0.30, 0.30], [0.50, 0.50])
    a = assess("TEST", b, c, "test period")
    assert a.tier == "detected" and a.direction == "increase"


def test_statements_do_not_overclaim():
    """No tier wording may say reclamation, recovery, healing or stalling:
    the screen describes NDVI in an analysis square, nothing more."""
    banned = ("reclam", "recover", "heal", "stalled", "regress", "certif")
    for text in STATEMENTS.values():
        assert not any(w in text.lower() for w in banned), text


# --- Item 5: determinism ------------------------------------------------------

def test_assess_deterministic_unit():
    b, c = _synth([5, 6, 7, 8], [0.30, 0.31, 0.29, 0.33], [0.40, 0.41, 0.39, 0.43])
    a1 = asdict(assess("TEST", b, c, "test period"))
    a2 = asdict(assess("TEST", b, c, "test period"))
    assert a1 == a2


def _normalize(packet: dict) -> dict:
    """Strip run timestamps so two runs of identical inputs compare equal."""
    p = json.loads(json.dumps(packet))
    p["assessment_date"] = "STAMP"
    p["provenance"]["generated_at"] = "STAMP"
    for t in p["transforms"]:
        t["at"] = "STAMP"
    for s in p["provenance"]["sources"]:
        s["accessed"] = "STAMP"
    return p


_DET_SITE = "07-30-018-26W4 (100)"


def _det_inputs_present() -> bool:
    from ledger.imagery import safe_site_id
    from ledger.sites import provenance_path
    reg = ROOT / "data" / "sites.parquet"
    return ((ROOT / "data" / "chips" / safe_site_id(_DET_SITE) / "manifest.json").exists()
            and reg.exists() and provenance_path(reg).exists())


@pytest.mark.skipif(not _det_inputs_present(),
                    reason="needs gitignored data/chips + data/sites.parquet "
                           "(+ .owa_provenance.json); fetch them to run")
def test_pipeline_rerun_deterministic(tmp_path):
    """Two CLI runs on the same chips must produce byte-identical packets
    apart from run timestamps."""
    site = _DET_SITE
    from ledger.imagery import safe_site_id
    outs = []
    for i in (1, 2):
        out = tmp_path / f"run{i}"
        r = subprocess.run(
            [sys.executable, "-m", "ledger.change", "assess",
             "--site", site,
             "--chips", str(ROOT / "data" / "chips" / safe_site_id(site)),
             "--registry", str(ROOT / "data" / "sites.parquet"),
             "--baseline-start", "2023", "--baseline-end", "2024",
             "--assessment", "2025-2026", "--out", str(out)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=600)
        assert r.returncode == 0, r.stderr[-500:]
        outs.append(next(out.glob("*.json")))
    p1 = _normalize(json.loads(outs[0].read_text()))
    p2 = _normalize(json.loads(outs[1].read_text()))
    assert p1 == p2


# --- schema contract ----------------------------------------------------------

def test_packets_validate_against_schema():
    import jsonschema
    bad = []
    for p in PACKETS:
        try:
            jsonschema.validate(json.loads(p.read_text()), SCHEMA)
        except Exception as e:  # noqa: BLE001
            bad.append((p.name, str(e)[:150]))
    assert not bad, bad


def test_schema_version_pinned():
    want = SCHEMA["properties"]["schema_version"]["const"]
    assert want == "1.2.0"
    for p in PACKETS:
        d = json.loads(p.read_text())
        assert d["schema_version"] == want, p.name


# --- M1 Honest Ledger invariants over the committed packets -------------------

def test_every_identified_packet_meets_ci_rule():
    for p in PACKETS:
        d = json.loads(p.read_text())
        det, claim = d["assessment_detail"], d["claim"]
        tier, _, _ = assign_tier(det["delta_vs_baseline"], det.get("delta_ci95"))
        assert claim["tier"] == tier, p.name
        if tier == "identified":
            lo, hi = det["delta_ci95"]
            assert abs(det["delta_vs_baseline"]) >= 0.08 and not (lo <= 0 <= hi)


def test_no_packet_claims_unrecorded_human_review():
    for p in PACKETS:
        d = json.loads(p.read_text())
        assert "review" not in d["provenance"]["generated_by"].replace(
            "no human review recorded", ""), p.name
        assert "human-reviewed" not in json.dumps(d["claim"]), p.name
        rv = d["provenance"]["review"]
        assert rv["status"] == ("reviewed" if rv["log"] else "not_reviewed"), p.name


def test_every_chip_cites_its_source():
    for p in PACKETS:
        d = json.loads(p.read_text())
        for c in d["chips"]:
            assert c.get("source_url", "").startswith("https://"), (p.name, c["path"])
            assert c.get("scene_id"), (p.name, c["path"])


def test_lineage_audit_covers_every_cited_scene():
    lin = json.loads((ROOT / "ledger" / "data" / "radiometric_lineage.json").read_text())
    audited = {s["scene_id"] for s in lin["scenes"]}
    assert not lin["anomalies"]
    for p in PACKETS:
        d = json.loads(p.read_text())
        missing = {o["scene_id"] for o in d["observations"]} - audited
        assert not missing, (p.name, sorted(missing))


def test_owa_provenance_recorded():
    for p in PACKETS:
        prov = json.loads(p.read_text())["provenance"]
        f = prov["owa_inventory_file"]
        assert f["sha256"] or f.get("note"), p.name  # recorded, or says why not
        if "owa_recheck" in prov:
            assert len(prov["owa_recheck"]["sha256"]) == 64, p.name


def test_tls_verification_on_by_default(monkeypatch):
    from ledger.config import Config
    monkeypatch.delenv("LEDGER_TRUST_EGRESS_PROXY_TLS", raising=False)
    assert Config().trust_egress_proxy_tls is False
    monkeypatch.setenv("LEDGER_TRUST_EGRESS_PROXY_TLS", "1")
    assert Config().trust_egress_proxy_tls is True


def test_owa_file_date_parsed_from_filename():
    from ledger.sites import owa_file_date
    url = ("https://cdn.example/x_Reporting%20-%20Full%20Inventory%20-%20"
           "2026-10-01%2013.41.42.xlsx")
    assert owa_file_date(url) == "2026-10-01"
    assert owa_file_date("owa_inventory_latest.xlsx") is None


def test_footprints_sit_at_their_sites():
    """Guards the UTM-zone bug: two polygons were once 6 degrees east."""
    import math
    g = json.loads((ROOT / "ledger" / "data" / "footprints"
                    / "pilot5_provisional.geojson").read_text())
    sites = {}
    for p in PACKETS:
        s = json.loads(p.read_text())["site"]
        sites[s["site_id"]] = (s["latitude"], s["longitude"])
    for f in g["features"]:
        lat0, lon0 = sites[f["properties"]["site_id"]]
        ring = f["geometry"]["coordinates"][0][:-1]
        lon = sum(c[0] for c in ring) / len(ring)
        lat = sum(c[1] for c in ring) / len(ring)
        dx = (lon - lon0) * 111_320 * math.cos(math.radians(lat0))
        dy = (lat - lat0) * 110_574
        assert math.hypot(dx, dy) < 1000, f["properties"]["site_id"]
