#!/usr/bin/env python3
"""Re-tier committed evidence packets offline under the current tier rule.

No imagery is fetched. Each packet's own observations are re-run through
ledger.change.assess(); the script first checks that the recomputed delta,
CI, medians and observation counts reproduce the stored values exactly, and
aborts if any packet does not reproduce. It then rewrites only the claim and
provenance fields that the rule and provenance fixes touch, and appends a
revision entry (previous tier/statement -> new tier/statement, reason).

Provenance added per packet:
  - chips[].scene_id and chips[].source_url, from the scene asset HREFs in
    ledger/data/radiometric_lineage.json (run ops/audit_lineage.py first)
  - provenance.lineage_audit: how many of the packet's scenes are covered
  - provenance.owa_inventory_file: the file used at assessment time. The
    pre-M1 pipeline did not record its URL or checksum; that is stated, not
    back-filled.
  - provenance.owa_recheck: the current OWA file (URL, date, SHA-256) the
    site was re-checked against, from <registry>.owa_provenance.json

Writes packets/*.json in place, plus docs/retier-<tag>.md and .csv: the
public before/after diff.

Usage:
    python -m ledger.sites --out data/sites.parquet   # current OWA + provenance
    python ops/audit_lineage.py
    python ops/retier_packets.py --tag 2026-10 --date 2026-10-08
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ledger.change import (MIN_MATCHED_MONTHS_FOR_CI, TIER_RULE,  # noqa: E402
                           TIER_RULE_TEXT, _monthly_medians, assess)
from ledger.imagery import BAND_ASSETS  # noqa: E402
from ledger.packet import (GENERATED_BY, SCHEMA, SCHEMA_VERSION,  # noqa: E402
                           empty_review)

LINEAGE = ROOT / "ledger" / "data" / "radiometric_lineage.json"
UNSAFESSL_V1 = "Chip download used GDAL_HTTP_UNSAFESSL"
UNSAFESSL_HISTORIC = (
    "Chips for this packet were downloaded with GDAL_HTTP_UNSAFESSL (TLS "
    "verification off) on a TLS-intercepting egress proxy; integrity rests on "
    "the recorded per-chip SHA-256 and the cited source_url, not TLS.")


def _years(packet: dict) -> tuple[list[int], list[int]]:
    for t in packet["transforms"]:
        if t["step"] == "baseline_assessment":
            p = t["parameters"]
            return list(p["baseline_years"]), list(p["assessment_years"])
    raise ValueError(f"{packet['packet_id']}: no baseline_assessment transform")


def _reason(a) -> str:
    d = f"{a.delta:+.3f}"
    ci = (f"[{a.delta_ci95[0]:+.3f}, {a.delta_ci95[1]:+.3f}]"
          if a.delta_ci95 is not None else None)
    if a.direction == "none":
        return f"|delta| {d} below ±0.08"
    if ci is None:
        return (f"delta {d} beyond ±0.08 but no CI "
                f"({len(a.matched_months)} matched months < {MIN_MATCHED_MONTHS_FOR_CI})")
    if a.tier == "detected":
        return f"delta {d} beyond ±0.08 but 95% CI {ci} includes zero"
    return f"delta {d} beyond ±0.08 and 95% CI {ci} excludes zero"


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def retier(packet: dict, lineage: dict, owa_recheck: dict | None,
           registry, run_date: str, head: str | None) -> tuple[dict, dict]:
    pid = packet["packet_id"]
    base_years, cur_years = _years(packet)
    scenes = packet["observations"]
    a = assess(packet["site"]["site_id"], _monthly_medians(scenes, base_years),
               _monthly_medians(scenes, cur_years),
               packet["assessment_detail"]["period"])

    # --- reproduce before touching anything ---------------------------------
    det, base = packet["assessment_detail"], packet["baseline"]
    checks = {
        "delta": (det["delta_vs_baseline"], a.delta),
        "ci": (det.get("delta_ci95"), a.delta_ci95),
        "matched_months": (det["matched_months"], a.matched_months),
        "current_median": (det["ndvi_median"], a.current_ndvi),
        "baseline_median": (base["ndvi_median"], a.baseline_ndvi),
        "n_current": (det["n_scene_observations"], a.n_current_obs),
        "n_baseline": (base["n_scene_observations"], a.n_baseline_obs),
        "confidence": (packet["claim"]["confidence"], a.confidence),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        raise SystemExit(f"{pid}: stored values do not reproduce: {bad}")

    old = packet["claim"]
    before = {"tier": old["tier"], "statement": old["statement"]}

    # --- claim ----------------------------------------------------------------
    site_caveats = [c for c in old["caveats"]
                    if c.startswith("Site coordinates are DLS")
                    or c.startswith("Sentinel-2's 10 m pixels")]
    caveats = list(a.caveats) + site_caveats
    if any(c.startswith(UNSAFESSL_V1) or c == UNSAFESSL_HISTORIC
           for c in old["caveats"]):
        caveats.append(UNSAFESSL_HISTORIC)
    packet["claim"] = {
        "tier": a.tier, "direction": a.direction, "statement": a.statement,
        "rationale": a.rationale, "confidence": a.confidence,
        "tier_rule": TIER_RULE, "caveats": caveats,
    }
    packet["schema_version"] = SCHEMA_VERSION
    for t in packet["transforms"]:
        if t["step"] == "baseline_assessment":
            t["parameters"].update({
                "min_matched_months_for_ci": MIN_MATCHED_MONTHS_FOR_CI,
                "tier_rule": TIER_RULE, "tier_rule_text": TIER_RULE_TEXT})
        if t["step"] == "packet_build":
            t["parameters"]["schema_version"] = SCHEMA_VERSION

    # --- chips: scene_id + source_url ----------------------------------------
    scene_by_date = {o["date"]: o["scene_id"] for o in scenes}
    asset_for_band = dict(BAND_ASSETS)
    for c in packet["chips"]:
        sid = scene_by_date.get(c["date"])
        if sid is None:
            raise SystemExit(f"{pid}: chip dated {c['date']} has no observation")
        c["scene_id"] = sid
        rec = lineage.get(sid)
        if rec and rec.get("assets"):
            c["source_url"] = rec["assets"][asset_for_band[c["bands"][0]]]

    # --- provenance -------------------------------------------------------------
    prov = packet["provenance"]
    prov["generated_by"] = GENERATED_BY
    prov.setdefault("review", empty_review())
    used = sorted({o["scene_id"] for o in scenes})
    prov["lineage_audit"] = {
        "record": "ledger/data/radiometric_lineage.json",
        "audit_date": lineage["_audit_date"],
        "scenes_in_packet": len(used),
        "scenes_audited": sum(1 for s in used if s in lineage),
    }
    prov.setdefault("owa_inventory_file", {
        "url": None, "file_name": None,
        "file_date": packet["site"].get("owa_inventory_date"),
        "sha256": None, "retrieved_at": None,
        "note": ("Not recorded at assessment time: the pre-M1 pipeline used a "
                 "hardcoded file month and kept no URL or checksum, so the "
                 "exact file cannot be verified. See owa_recheck."),
    })
    if owa_recheck is not None:
        sid = packet["site"]["site_id"]
        row = registry[registry.site_id == sid]
        found = len(row) > 0
        prov["owa_recheck"] = {
            **{k: owa_recheck.get(k) for k in ("url", "file_name", "file_date", "sha256")},
            "checked_on": run_date,
            "site_found": found,
            "owa_stage": str(row.iloc[0].owa_stage) if found else None,
            "coordinates_match": bool(
                found
                and abs(float(row.iloc[0].latitude) - packet["site"]["latitude"]) < 1e-5
                and abs(float(row.iloc[0].longitude) - packet["site"]["longitude"]) < 1e-5),
        }
    after = {"tier": a.tier, "statement": a.statement}
    change = {
        "packet_id": pid, "site_id": packet["site"]["site_id"],
        "old_tier": before["tier"], "old_statement": before["statement"],
        "new_tier": after["tier"], "new_statement": after["statement"],
        "direction": a.direction, "delta": a.delta,
        "ci95": a.delta_ci95, "matched_months": len(a.matched_months),
        "confidence": a.confidence, "reason": _reason(a),
    }
    already = old.get("tier_rule") == TIER_RULE  # idempotent re-runs
    if not already:
      prov.setdefault("revisions", []).append({
        "date": run_date, "tool": "ops/retier_packets.py", "code_commit": head,
        "change": f"re-tiered under {TIER_RULE}; provenance fields added; "
                  "unrecorded 'human-reviewed' stamp removed",
        "previous_tier": before["tier"], "previous_statement": before["statement"],
        "new_tier": after["tier"], "new_statement": after["statement"],
        "reason": change["reason"],
      })
    return packet, change


def write_diff(changes: list[dict], tag: str, run_date: str, head: str | None,
               owa_recheck: dict | None, lineage_meta: dict) -> None:
    out_csv = ROOT / "docs" / f"retier-{tag}.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "old_tier", "old_statement", "new_tier",
                    "new_statement", "delta", "ci95_lo", "ci95_hi",
                    "matched_months", "reason"])
        for c in changes:
            ci = c["ci95"] or [None, None]
            w.writerow([c["site_id"], c["old_tier"], c["old_statement"],
                        c["new_tier"], c["new_statement"], c["delta"],
                        ci[0], ci[1], c["matched_months"], c["reason"]])

    def count(key, val):
        return sum(1 for c in changes if c[key] == val)
    old_id = [c for c in changes if c["old_tier"] == "identified"]
    kept = [c for c in old_id if c["new_tier"] == "identified"]
    demoted = [c for c in old_id if c["new_tier"] != "identified"]
    promoted = [c for c in changes
                if c["old_tier"] != "identified" and c["new_tier"] == "identified"]
    n_noci = sum(1 for c in demoted if c["ci95"] is None)
    n_zero = len(demoted) - n_noci
    by_dir = {d: sum(1 for c in kept if c["direction"] == d)
              for d in ("increase", "decrease")}

    lines = [
        f"# Re-tier diff, {tag}: tier rule `{TIER_RULE}`",
        "",
        f"Run {run_date} (MT) with `ops/retier_packets.py`"
        + (f" at commit `{head[:7]}`" if head else "") + ". "
        "No imagery was re-fetched: every packet's delta, CI, medians and "
        "observation counts were recomputed from the observations stored in "
        "the packet and matched the stored values exactly before any tier "
        "changed.",
        "",
        "## Why",
        "",
        "The v1 rule tiered a site `identified` whenever |median NDVI delta| "
        "≥ 0.08 and ignored the 95% CI. The new rule is: "
        f"{TIER_RULE_TEXT}. Increases and decreases are now worded separately "
        "and neutrally (\"NDVI higher/lower than baseline in the analysis "
        "square\"); the old labels \"vegetation recovering\" and \"vegetation "
        "stalled or regressing\" are retired.",
        "",
        "## Result",
        "",
        "| | before | after |",
        "|---|---|---|",
        f"| identified | {count('old_tier', 'identified')} | {count('new_tier', 'identified')} |",
        f"| detected | {count('old_tier', 'detected')} | {count('new_tier', 'detected')} |",
        f"| total | {len(changes)} | {len(changes)} |",
        "",
        f"- {len(kept)} of {len(old_id)} previously identified packets stay "
        f"identified ({by_dir['increase']} NDVI higher, {by_dir['decrease']} "
        "NDVI lower).",
        f"- {len(demoted)} move to detected: {n_noci} have no CI (fewer than "
        f"{MIN_MATCHED_MONTHS_FOR_CI} matched months) and {n_zero} have a CI "
        "that includes zero.",
        f"- {len(promoted)} packets move up to identified.",
        "",
        "## What \"identified\" still does not mean",
        "",
        "- It describes NDVI in the ~1 km² analysis square around a DLS "
        "centroid (±300 m), which is mostly land around the pad. It is not a "
        "finding about the pad, its cause, or its reclamation status.",
        "- The CI resamples matched months from the same two baseline and two "
        "current years, so it measures within-season consistency, not "
        "year-to-year variability. The baseline years include the 2023 "
        f"drought, and {sum(1 for c in changes if c['delta'] > 0)} of "
        f"{len(changes)} deltas are positive, which points to a "
        "regional signal. A pad-vs-ring correction is planned (milestone M3) "
        "and is expected to change these results again.",
        "- Screening only. Not legal proof, not a certification, not a "
        "methane, soil, contamination or subsurface measurement. Nothing here "
        "names or judges any licensee.",
        "",
        "## Provenance changes in the same pass",
        "",
        f"- Radiometric lineage audit re-run {lineage_meta['audit_date']}: "
        f"{lineage_meta['n_audited']} of {lineage_meta['n_unique_scenes']} "
        "scenes the packets cite (previously 62), "
        f"{len(lineage_meta['anomalies'])} anomalies.",
        "- Every chip now carries its scene_id and source_url (the Earth "
        "Search COG asset it was read from) so its SHA-256 can be checked "
        "against the source window.",
        "- The \"human-reviewed before publish\" stamp is removed; no review "
        "record exists. Each packet has an empty `provenance.review` log.",
        "- The OWA file used at assessment time (dated 2026-09-01) was never "
        "recorded by URL or checksum; packets now say so. Each site was "
        "re-checked against the current OWA file"
        + (f" dated {owa_recheck['file_date']} (sha256 `{owa_recheck['sha256']}`)"
           if owa_recheck else "") + ".",
        "",
        "## Per-site changes (tier changed)",
        "",
        "| site | old tier / statement | new tier / statement | reason |",
        "|---|---|---|---|",
    ]
    for c in sorted(changes, key=lambda c: c["site_id"]):
        if c["old_tier"] != c["new_tier"]:
            lines.append(f"| {c['site_id']} | {c['old_tier']} / {c['old_statement']} "
                         f"| {c['new_tier']} / {c['new_statement']} | {c['reason']} |")
    lines += [
        "",
        "## Still identified",
        "",
        "| site | direction | delta | 95% CI | matched months |",
        "|---|---|---|---|---|",
    ]
    for c in sorted(kept, key=lambda c: c["site_id"]):
        lines.append(f"| {c['site_id']} | {c['direction']} | {c['delta']:+.4f} | "
                     f"[{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}] | {c['matched_months']} |")
    lines += ["", f"All {len(changes)} rows, including unchanged ones and the "
              f"new wording for each, are in [`retier-{tag}.csv`](retier-{tag}.csv).", ""]
    (ROOT / "docs" / f"retier-{tag}.md").write_text("\n".join(lines))
    print(f"wrote docs/retier-{tag}.md and .csv")


def main() -> None:
    import jsonschema
    import pandas as pd

    from ledger.sites import provenance_path

    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="diff file tag, e.g. 2026-10")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--registry", default="data/sites.parquet",
                    help="current registry for the OWA re-check (optional)")
    args = ap.parse_args()

    lin = json.loads(LINEAGE.read_text())
    lineage = {s["scene_id"]: s for s in lin["scenes"]}
    lineage["_audit_date"] = lin["audit_date"]
    reg_path = ROOT / args.registry
    owa_recheck = registry = None
    if reg_path.exists() and provenance_path(reg_path).exists():
        owa_recheck = json.loads(provenance_path(reg_path).read_text())
        registry = pd.read_parquet(reg_path)
    else:
        print(f"no registry/provenance at {reg_path}: skipping OWA re-check")
    head = _git_head()

    changes = []
    for p in sorted((ROOT / "packets").glob("*.json")):
        packet, change = retier(json.loads(p.read_text()), lineage, owa_recheck,
                                registry, args.date, head)
        jsonschema.validate(packet, SCHEMA)
        p.write_text(json.dumps(packet, indent=2))
        changes.append(change)
    write_diff(changes, args.tag, args.date, head, owa_recheck, lin)
    n_id = sum(1 for c in changes if c["new_tier"] == "identified")
    print(f"re-tiered {len(changes)} packets: identified {n_id}, "
          f"detected {len(changes) - n_id}")


if __name__ == "__main__":
    main()
