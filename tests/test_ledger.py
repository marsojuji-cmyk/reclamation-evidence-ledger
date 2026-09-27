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
    assert "Median matched-month" in a.rationale


def test_delta_std_is_spread_of_deltas():
    """delta_std must be the std of matched-month deltas (not baseline var)."""
    import numpy as np
    b, c = _synth([5, 6, 7, 8], [0.20, 0.30, 0.40, 0.50], [0.30, 0.42, 0.48, 0.55])
    a = assess("TEST", b, c, "test period")
    deltas = [0.10, 0.12, 0.08, 0.05]
    assert a.delta_std == pytest.approx(float(np.std(deltas)), abs=1e-3)


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


def test_pipeline_rerun_deterministic(tmp_path):
    """Two CLI runs on the same chips must produce byte-identical packets
    apart from run timestamps."""
    site = "07-30-018-26W4 (100)"
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
    for p in PACKETS:
        d = json.loads(p.read_text())
        assert d["schema_version"] == "1.1.0", p.name
