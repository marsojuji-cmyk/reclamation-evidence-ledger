"""Change assessment: baseline diffs and claim-tier assignment.

The core interpretive rule, from imagery tradecraft:

    detected     — a delta was measured vs the baseline. This includes
                   deltas beyond the threshold that are NOT supported by a
                   95% CI (no CI, or a CI that includes zero).
    identified   — |median delta| >= the threshold AND a bootstrap 95% CI
                   exists (>= 4 matched months) AND that CI excludes zero.
                   It says only that the analysis square's NDVI moved in a
                   stated direction, consistently across matched months. It
                   is a screening hypothesis about the ~1 km² square around a
                   DLS centroid, NOT a finding about the pad, its cause, or
                   its reclamation status. Increases and decreases are worded
                   separately and neutrally.
    attributed   — a named party is responsible (NEVER emitted by code;
                   requires human review and ground truth)

The pipeline's job ends at "identified", and only with caveats attached.
It screens; it never certifies. It says nothing about soil, contamination,
subsurface condition or methane.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT, Config


# Bootstrap CIs over matched-month deltas are degenerate below this many
# matched months (with n=2 the resampled-median distribution has only 3
# distinct values: the interval looks precise and means almost nothing).
# Below the threshold we report NO interval rather than a misleading one.
MIN_MATCHED_MONTHS_FOR_CI = 4

# Identifier of the tier rule, recorded in every packet so a re-score is
# traceable. v1 (pilot-01/02) tiered on |delta| alone and ignored the CI.
TIER_RULE = "ci-gated-v2"
TIER_RULE_TEXT = ("identified only if |median matched-month NDVI delta| >= "
                  "threshold AND a bootstrap 95% CI exists (>= 4 matched "
                  "months) AND the CI excludes zero; otherwise detected")

STATEMENTS = {
    "increase": "NDVI higher than baseline in the analysis square (screening signal)",
    "decrease": "NDVI lower than baseline in the analysis square (screening signal)",
    "no_ci": "change beyond threshold, not supported: no 95% CI (fewer than 4 matched months)",
    "ci_includes_zero": "change beyond threshold, not supported: 95% CI includes zero",
    "none": "no change beyond threshold vs baseline",
}

SCREENING_CAVEATS = [
    "Screening only: not legal proof, not a reclamation certification or "
    "compliance verdict, and not a methane, soil, contamination or "
    "subsurface measurement.",
    "The 500 m buffer (~1 km² square) is mostly land around the pad; the NDVI "
    "change describes that square, not the pad itself, and regional weather "
    "(e.g. the 2023 drought in the baseline years) moves it too.",
    "The bootstrap CI resamples matched months drawn from the same two "
    "baseline and two current years: it measures within-season consistency, "
    "not year-to-year variability.",
]


def assign_tier(delta: float, ci: list | None, cfg: Config = DEFAULT
                ) -> tuple[str, str, str]:
    """(tier, direction, statement_key) under TIER_RULE.

    direction is "increase" | "decrease" | "none" and is reported for every
    tier so a reader can see which way a not-supported delta pointed."""
    if delta >= cfg.ndvi_recover_delta:
        direction = "increase"
    elif delta <= cfg.ndvi_stall_delta:
        direction = "decrease"
    else:
        return "detected", "none", "none"
    if ci is None:
        return "detected", direction, "no_ci"
    lo, hi = ci
    if lo <= 0.0 <= hi:
        return "detected", direction, "ci_includes_zero"
    return "identified", direction, direction


@dataclass
class Assessment:
    site_id: str
    period: str            # e.g. "2026 growing season"
    baseline_ndvi: float   # median of per-month baseline medians (context only)
    delta_std: float       # std dev of the matched-month DELTAS — NOT baseline
                          # variation. Named for what it is: spread of the
                          # month-for-month differences the delta summarizes.
    current_ndvi: float    # median of per-month current medians (context only)
    delta: float
    delta_ci95: list | None  # [lo, hi]: bootstrap 95% CI on the median
                             # matched-month delta (1000 resamples, fixed
                             # seed); None when len(matched_months) < 4 —
                             # an interval there would be degenerate, not wide
    n_baseline_obs: int
    n_current_obs: int
    matched_months: list  # calendar months compared month-for-month
    tier: str              # "detected" | "identified"
    direction: str         # "increase" | "decrease" | "none"
    statement: str
    rationale: str
    caveats: list
    confidence: str        # "low" | "medium" | "high" (evidence-volume heuristic)


def assess(site_id: str, baseline_monthly: dict[int, list[float]],
           current_monthly: dict[int, list[float]], period: str,
           cfg: Config = DEFAULT) -> Assessment:
    """Month-matched baseline diff.

    baseline_monthly / current_monthly map calendar month -> list of scene
    NDVI means for that month. Deltas are computed per matched month and the
    median of those deltas is the signal, so a baseline sampled in May/June
    is never compared against a current period sampled in July. This is the
    fix for phenology bias: greenness follows the calendar, not the project.
    """
    import numpy as np

    matched = sorted(set(baseline_monthly) & set(current_monthly))
    if len(matched) < 2:
        raise ValueError(
            f"{site_id}: need >=2 month-matched baseline/current months, "
            f"got {matched}")
    month_deltas = []
    n_base = n_cur = 0
    for m in matched:
        b = float(np.median(baseline_monthly[m]))
        c = float(np.median(current_monthly[m]))
        month_deltas.append(c - b)
        n_base += len(baseline_monthly[m])
        n_cur += len(current_monthly[m])

    base = float(np.median([float(np.median(baseline_monthly[m])) for m in matched]))
    current = float(np.median([float(np.median(current_monthly[m])) for m in matched]))
    delta = float(np.median(month_deltas))
    std = float(np.std(month_deltas)) if len(month_deltas) > 2 else 0.0

    # Real uncertainty: bootstrap 95% CI on the median matched-month delta.
    # 1000 resamples over the matched-month deltas, fixed seed so packets are
    # reproducible. With few matched months this interval is DEGENERATE, not
    # wide: at n=2 the resampled-median distribution has only 3 distinct
    # values, so the interval looks precise and means almost nothing. Below
    # MIN_MATCHED_MONTHS_FOR_CI we refuse to report one — a missing interval
    # is the honest statement of how much we know.
    if len(matched) >= MIN_MATCHED_MONTHS_FOR_CI:
        rng = np.random.default_rng(20260927)
        d = np.asarray(month_deltas, dtype=float)
        boots = [float(np.median(rng.choice(d, size=d.size, replace=True)))
                 for _ in range(1000)]
        ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        ci = [round(ci_lo, 4), round(ci_hi, 4)]
        ci_txt = f"95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}]"
        ci_caveat = (f"Uncertainty is a bootstrap 95% CI over {len(matched)} "
                     "matched-month deltas.")
    else:
        ci = None
        ci_txt = (f"interval not estimated (only {len(matched)} matched months; "
                  f"a bootstrap CI needs >= {MIN_MATCHED_MONTHS_FOR_CI})")
        ci_caveat = (f"No uncertainty interval is reported: {len(matched)} "
                     f"matched months is below the {MIN_MATCHED_MONTHS_FOR_CI} "
                     "needed for a non-degenerate bootstrap CI. The delta "
                     "below is a point estimate only.")

    caveats = [
        "10 m pixels cannot resolve wellheads; this is a vegetation screen, not a compliance verdict.",
        "Drought years depress NDVI independent of reclamation progress.",
        "Baseline and current periods are compared month-for-month "
        f"(matched months: {matched}) to avoid seasonal sampling bias.",
        ci_caveat,
        *SCREENING_CAVEATS,
    ]

    tier, direction, key = assign_tier(delta, ci, cfg)
    statement = STATEMENTS[key]
    band = max(cfg.ndvi_recover_delta, abs(cfg.ndvi_stall_delta))
    numbers = (f"median matched-month NDVI delta {delta:+.2f} (median of "
               f"{len(matched)} matched-month deltas; baseline median "
               f"{base:.2f}, current median {current:.2f}; {ci_txt})")
    if key == "none":
        rationale = f"The {numbers} is within the ±{band:.2f} threshold."
    elif key == "no_ci":
        rationale = (f"The {numbers} is beyond ±{band:.2f}, but with fewer "
                     f"than {MIN_MATCHED_MONTHS_FOR_CI} matched months no CI "
                     "is estimated, so the change is not supported.")
    elif key == "ci_includes_zero":
        rationale = (f"The {numbers} is beyond ±{band:.2f}, but the 95% CI "
                     "includes zero, so the change is not supported.")
    else:
        rationale = (f"The {numbers} is beyond ±{band:.2f} and the 95% CI "
                     "excludes zero. This describes the analysis square, not "
                     "the pad, and is a screening hypothesis only.")
    # The delta is the median of per-month deltas, NOT the difference of the
    # two displayed medians (median of differences != difference of medians).
    # The rationale states all three numbers so the relationship is exact by
    # construction: nothing is implied to subtract.

    # Confidence scales with evidence volume, never with enthusiasm.
    n = n_base + n_cur
    confidence = "high" if n >= 24 else "medium" if n >= 12 else "low"

    return Assessment(
        site_id=site_id, period=period, baseline_ndvi=round(base, 4),
        delta_std=round(std, 4), current_ndvi=round(current, 4),
        delta=round(delta, 4), delta_ci95=ci,
        n_baseline_obs=n_base,
        n_current_obs=n_cur, matched_months=matched, tier=tier,
        direction=direction, statement=statement,
        rationale=rationale, caveats=caveats, confidence=confidence,
    )


# ---------------------------------------------------------------------------
# CLI: assess chips on disk and build a schema-validated evidence packet.
#
#     python -m ledger.change assess --site <site_id> \
#         --chips data/chips/<safe_id> \
#         --baseline-start 2023 --baseline-end 2024 --assessment 2025-2026
# ---------------------------------------------------------------------------

OWA_INVENTORY_URL = "https://www.orphanwell.ca/inventory/site-specific-inventory"
# The inventory file month is no longer a constant: it is read from the
# <registry>.owa_provenance.json record written by `ledger.sites` (file URL,
# file date, SHA-256) so every packet names the exact file it used.
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
COPERNICUS_URL = "https://sentiwiki.copernicus.eu/"


def _parse_years(spec: str) -> list[int]:
    spec = spec.strip()
    if "," in spec:
        return sorted({int(y) for y in spec.split(",") if y.strip()})
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def _scene_means(chips_dir, cfg: Config = DEFAULT):
    """Per-scene index means from chip GeoTIFFs. Returns (scenes, manifest)."""
    import json
    import numpy as np
    import rasterio
    from . import indices

    manifest = json.loads((chips_dir / "manifest.json").read_text())
    scene_by_stamp = {s["date"].replace("-", ""): s for s in manifest["scenes"]}
    out = []
    for f in sorted(chips_dir.glob("*_red.tif")):
        stamp = f.name.split("_")[0]
        sc = scene_by_stamp.get(stamp)
        if sc is None:
            continue
        bands = {}
        for band in ("red", "nir", "swir", "blue", "scl"):
            p = chips_dir / f"{stamp}_{band}.tif"
            with rasterio.open(p) as ds:
                bands[band] = ds.read(1)
        refl = {b: bands[b].astype(float) / 10000.0
                for b in ("red", "nir", "swir", "blue")}
        scl = bands["scl"].astype(np.int16)
        clear = (scl != 0) & ~np.isin(scl, list(cfg.scl_mask_values))
        clear &= (bands["red"] > 0)  # nodata guard
        out.append({
            "date": sc["date"],
            "scene_id": sc["scene_id"],
            "ndvi_mean": indices.mean_or_nan(indices.ndvi(refl["nir"], refl["red"], clear)),
            "ndmi_mean": indices.mean_or_nan(indices.ndmi(refl["nir"], refl["swir"], clear)),
            "bare_soil_mean": indices.mean_or_nan(
                indices.bare_soil_index(refl["swir"], refl["red"],
                                        refl["nir"], refl["blue"], clear)),
            "savi_mean": indices.mean_or_nan(
                indices.savi(refl["nir"], refl["red"], clear)),
            "msavi_mean": indices.mean_or_nan(
                indices.msavi(refl["nir"], refl["red"], clear)),
            "clear_pixel_fraction": round(indices.clear_fraction(clear), 4),
        })
    return out, manifest


def _monthly_medians(scenes: list[dict], years: list[int]) -> dict[int, list[float]]:
    """Scene NDVI means grouped by calendar month (month-matched comparison)."""
    out: dict[int, list[float]] = {}
    for s in scenes:
        y, m = int(s["date"][:4]), int(s["date"][5:7])
        if y in years and s["ndvi_mean"] is not None:
            out.setdefault(m, []).append(s["ndvi_mean"])
    return out


def cmd_assess(args):
    import json
    from datetime import date as date_cls
    from pathlib import Path

    import pandas as pd

    from .packet import SCHEMA_VERSION, build_packet, write_packet

    chips_dir = Path(args.chips)
    scenes, manifest = _scene_means(chips_dir)
    if not scenes:
        raise SystemExit(f"no usable scenes in {chips_dir}")

    baseline_years = list(range(args.baseline_start, args.baseline_end + 1))
    current_years = _parse_years(args.assessment)
    base_monthly = _monthly_medians(scenes, baseline_years)
    cur_monthly = _monthly_medians(scenes, current_years)
    period = (f"{min(current_years)}-{max(current_years)} growing seasons"
              if len(current_years) > 1 else f"{current_years[0]} growing season")

    a = assess(args.site, base_monthly, cur_monthly, period)

    from .sites import provenance_path
    prov_file = provenance_path(args.registry)
    if not prov_file.exists():
        raise SystemExit(
            f"{prov_file} missing: rebuild the registry with `python -m "
            "ledger.sites` so the OWA file URL, date and SHA-256 are recorded.")
    owa_prov = json.loads(prov_file.read_text())

    registry = pd.read_parquet(args.registry)
    row = registry[registry.site_id == args.site]
    if len(row) == 0:
        raise SystemExit(f"site {args.site} not found in {args.registry}")
    r = row.iloc[0]

    observations = [
        {"date": s["date"], "scene_id": s["scene_id"],
         "ndvi_mean": s["ndvi_mean"], "ndmi_mean": s["ndmi_mean"],
         "bare_soil_mean": s["bare_soil_mean"],
         "savi_mean": s["savi_mean"], "msavi_mean": s["msavi_mean"],
         "clear_pixel_fraction": s["clear_pixel_fraction"]}
        for s in scenes
    ]
    chips = []
    for sc in manifest["scenes"]:
        for c in sc["chips"]:
            chip = {"date": sc["date"], "path": c["path"],
                    "sha256": c["sha256"], "bands": [c["band"]],
                    "scene_id": sc["scene_id"]}
            if c.get("source_url"):
                chip["source_url"] = c["source_url"]
            chips.append(chip)

    transforms = [
        {"step": "stac_scene_query", "tool": "pystac-client",
         "parameters": manifest["query"]},
        {"step": "chip_download_windowed",
         "tool": "rasterio windowed read over HTTPS (/vsicurl)",
         "parameters": {"buffer_m": 500.0,
                        "bands": ["B04", "B08", "B11", "B02", "SCL"],
                        "resampling": {"10m": "bilinear", "SCL": "nearest"},
                        "reference_grid": "red band (10 m)",
                        "note": "chips stored as written; DN = reflectance*10000"}},
        {"step": "cloud_mask", "tool": "Sentinel-2 SCL classification",
         "parameters": {"masked_classes": list(DEFAULT.scl_mask_values),
                        "min_clear_fraction": DEFAULT.min_clear_fraction,
                        "rejected_scenes": manifest["rejections"]}},
        {"step": "index_computation", "tool": "ledger.indices (numpy)",
         "parameters": {"ndvi": "(nir-red)/(nir+red)",
                        "ndmi": "(nir-swir)/(nir+swir)",
                        "bare_soil": "((swir+red)-(nir+blue))/((swir+red)+(nir+blue))",
                        "savi": "((nir-red)*(1+L))/(nir+red+L), L=0.5 "
                                "(soil-adjusted; supporting evidence only)",
                        "msavi": "(2*nir+1-sqrt((2*nir+1)^2-8*(nir-red)))/2 "
                                 "(self-adjusting; supporting evidence only)",
                        "primary_signal": "ndvi",
                        "scale": "DN/10000",
                        "scale_justification": "ledger/data/radiometric_lineage.json: "
                        "per-scene STAC audit (processing baseline + "
                        "earthsearch:boa_offset_applied per scene); the data "
                        "provider removed the PB>=04.00 +1000 DN offset when "
                        "generating these COGs, confirmed by chip-level DN "
                        "minima ~1. Not assumed — recorded.",
                        "mask": "clear pixels only"}},
        {"step": "baseline_assessment", "tool": "ledger.change.assess",
         "parameters": {"baseline_years": baseline_years,
                        "assessment_years": current_years,
                        "seasonal_aggregation": "month-matched median deltas "
                        "(each calendar month compared only to itself)",
                        "recover_delta": DEFAULT.ndvi_recover_delta,
                        "stall_delta": DEFAULT.ndvi_stall_delta,
                        "min_matched_months_for_ci": MIN_MATCHED_MONTHS_FOR_CI,
                        "tier_rule": TIER_RULE,
                        "tier_rule_text": TIER_RULE_TEXT}},
        {"step": "packet_build", "tool": "ledger.packet.build_packet",
         "parameters": {"schema_version": SCHEMA_VERSION}},
    ]
    sources = [
        {"name": "OWA site-specific inventory (Excel)",
         "url": owa_prov.get("url") or OWA_INVENTORY_URL,
         "accessed": (owa_prov.get("retrieved_at") or date_cls.today().isoformat())[:10],
         "license_note": f"public data; inventory file dated "
                         f"{owa_prov.get('file_date') or 'unknown'}, "
                         f"sha256 {owa_prov.get('sha256')}"},
        {"name": "Element 84 Earth Search STAC (Sentinel-2 L2A)",
         "url": EARTH_SEARCH_URL, "accessed": date_cls.today().isoformat()},
        {"name": "Copernicus Sentinel-2 (ESA)", "url": COPERNICUS_URL,
         "accessed": date_cls.today().isoformat(),
         "license_note": "Contains modified Copernicus Sentinel data."},
    ]
    caveats = list(a.caveats) + [
        f"Site coordinates are DLS LSD centroids (~±300 m; {r['geo_method']}). "
        "The 500 m analysis buffer absorbs this uncertainty; this is not a "
        "survey of the wellhead.",
        "Sentinel-2's 10 m pixels cannot resolve individual wellheads.",
    ]
    if DEFAULT.trust_egress_proxy_tls:
        caveats.append(
            "Chip download used GDAL_HTTP_UNSAFESSL (TLS verification off) on a "
            "TLS-intercepting egress proxy; payload integrity rests on the "
            "recorded per-chip SHA-256 and S3-hosted COGs, not TLS.")

    packet = build_packet(
        site={"site_id": str(r["site_id"]), "name": str(r["name"]),
              "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
              "owa_stage": str(r["owa_stage"]),
              **({"owa_inventory_date": owa_prov["file_date"]}
                 if owa_prov.get("file_date") else {})},
        assessment={"tier": a.tier, "statement": a.statement,
                    "rationale": a.rationale, "confidence": a.confidence,
                    "period": period, "caveats": caveats},
        observations=observations, chips=chips,
        transforms=transforms, sources=sources,
    )
    packet["claim"]["caveats"] = caveats
    packet["claim"]["direction"] = a.direction
    packet["claim"]["tier_rule"] = TIER_RULE
    packet["provenance"]["owa_inventory_file"] = {
        k: owa_prov.get(k) for k in ("url", "file_name", "file_date", "sha256",
                                     "retrieved_at")}
    packet["baseline"] = {"period": f"{baseline_years[0]}-{baseline_years[-1]}",
                          "ndvi_median": a.baseline_ndvi,
                          "n_scene_observations": a.n_baseline_obs}
    packet["assessment_detail"] = {
        "period": period, "ndvi_median": a.current_ndvi,
        "n_scene_observations": a.n_current_obs,
        "delta_vs_baseline": a.delta,
        "delta_std": a.delta_std,
        # Median of per-month deltas != difference of the displayed medians.
        # Stated here so no reader has to discover it by subtraction.
        "delta_method_note": (
            "delta_vs_baseline is the median of per-month "
            "(current-median minus baseline-median) deltas over matched "
            "months; it is not the difference of baseline.ndvi_median and "
            "assessment_detail.ndvi_median."),
        "matched_months": a.matched_months}
    if a.delta_ci95 is not None:
        # Omitted (not null) below MIN_MATCHED_MONTHS_FOR_CI matched months:
        # the schema keeps the field optional so absence is the honest signal.
        packet["assessment_detail"]["delta_ci95"] = a.delta_ci95

    out = write_packet(packet, args.out)
    print(f"{args.site}: {a.tier.upper()} — {a.statement} "
          f"(delta {a.delta:+.3f} = median of {len(a.matched_months)} matched-month deltas; "
          f"baseline median {a.baseline_ndvi:.3f}, current median {a.current_ndvi:.3f}, "
          f"confidence {a.confidence})")
    print(f"  packet: {out}")
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Change assessment and packet builder.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assess", help="assess chips and build an evidence packet")
    a.add_argument("--site", required=True, help="site_id as in the registry")
    a.add_argument("--chips", required=True, help="data/chips/<safe site dir>")
    a.add_argument("--registry", default="data/sites.parquet")
    a.add_argument("--baseline-start", type=int, default=2023)
    a.add_argument("--baseline-end", type=int, default=2024)
    a.add_argument("--assessment", default="2025-2026",
                   help="'2025-2026' range or '2025,2026' list")
    a.add_argument("--out", default="packets")
    args = ap.parse_args()
    if args.cmd == "assess":
        cmd_assess(args)


if __name__ == "__main__":
    main()
