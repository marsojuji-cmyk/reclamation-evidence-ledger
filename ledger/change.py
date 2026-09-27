"""Change assessment: baseline diffs and claim-tier assignment.

The core interpretive rule, from imagery tradecraft:

    detection    — something changed vs the baseline (a measured delta)
    identified   — the change is consistent with a reclamation signal
                   across multiple observations (a hypothesis)
    attributed   — a named party is responsible (NEVER emitted by code;
                   requires human review and ground truth)

The pipeline's job ends at "identified", and only with caveats attached.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT, Config


@dataclass
class Assessment:
    site_id: str
    period: str            # e.g. "2026 growing season"
    baseline_ndvi: float
    baseline_std: float
    current_ndvi: float
    delta: float
    delta_ci95: list       # [lo, hi]: bootstrap 95% CI on the median
                          # matched-month delta (1000 resamples, fixed seed)
    n_baseline_obs: int
    n_current_obs: int
    matched_months: list  # calendar months compared month-for-month
    tier: str              # "detected" | "identified"
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
    # reproducible. With only a handful of matched months this interval is
    # wide — that width is the honest statement of how much we know.
    rng = np.random.default_rng(20260927)
    d = np.asarray(month_deltas, dtype=float)
    boots = [float(np.median(rng.choice(d, size=d.size, replace=True)))
             for _ in range(1000)]
    ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))

    caveats = [
        "10 m pixels cannot resolve wellheads; this is a vegetation screen, not a compliance verdict.",
        "Drought years depress NDVI independent of reclamation progress.",
        "Baseline and current periods are compared month-for-month "
        f"(matched months: {matched}) to avoid seasonal sampling bias.",
        f"Uncertainty is a bootstrap 95% CI over {len(matched)} matched-month "
        "deltas — few matched months means a wide interval, by design.",
    ]

    ci_txt = f"95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}]"
    if delta >= cfg.ndvi_recover_delta:
        tier, statement = "identified", "vegetation recovering"
        rationale = (f"Month-matched NDVI {current:.2f} exceeds the baseline "
                     f"{base:.2f} by {delta:+.2f} (median of {len(matched)} "
                     f"matched-month deltas; {ci_txt}).")
    elif delta <= cfg.ndvi_stall_delta:
        tier, statement = "identified", "vegetation stalled or regressing"
        rationale = (f"Month-matched NDVI {current:.2f} is below the baseline "
                     f"{base:.2f} by {delta:+.2f} (median of {len(matched)} "
                     f"matched-month deltas; {ci_txt}).")
    else:
        tier, statement = "detected", "no significant change vs baseline"
        rationale = (f"Month-matched delta {delta:+.2f} is within the noise band "
                     f"(±{max(cfg.ndvi_recover_delta, abs(cfg.ndvi_stall_delta)):.2f}; {ci_txt}).")

    # Confidence scales with evidence volume, never with enthusiasm.
    n = n_base + n_cur
    confidence = "high" if n >= 24 else "medium" if n >= 12 else "low"

    return Assessment(
        site_id=site_id, period=period, baseline_ndvi=round(base, 4),
        baseline_std=round(std, 4), current_ndvi=round(current, 4),
        delta=round(delta, 4), delta_ci95=[round(ci_lo, 4), round(ci_hi, 4)],
        n_baseline_obs=n_base,
        n_current_obs=n_cur, matched_months=matched, tier=tier, statement=statement,
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
OWA_INVENTORY_MONTH = "2026-09-01"  # file month of the inventory used; recheck live
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

    from .packet import build_packet, write_packet

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
            chips.append({"date": sc["date"], "path": c["path"],
                          "sha256": c["sha256"], "bands": [c["band"]]})

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
                        "scale": "DN/10000", "mask": "clear pixels only"}},
        {"step": "baseline_assessment", "tool": "ledger.change.assess",
         "parameters": {"baseline_years": baseline_years,
                        "assessment_years": current_years,
                        "seasonal_aggregation": "month-matched median deltas "
                        "(each calendar month compared only to itself)",
                        "recover_delta": DEFAULT.ndvi_recover_delta,
                        "stall_delta": DEFAULT.ndvi_stall_delta}},
        {"step": "packet_build", "tool": "ledger.packet.build_packet",
         "parameters": {"schema_version": "1.1.0"}},
    ]
    sources = [
        {"name": "OWA site-specific inventory (Excel)",
         "url": OWA_INVENTORY_URL, "accessed": date_cls.today().isoformat(),
         "license_note": "public data; inventory file month 2026-09-01, recheck live"},
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
        "Chip download used GDAL_HTTP_UNSAFESSL on a TLS-intercepting egress "
        "proxy; payload integrity rests on S3-hosted COGs, not TLS pinning.",
    ]

    packet = build_packet(
        site={"site_id": str(r["site_id"]), "name": str(r["name"]),
              "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
              "owa_stage": str(r["owa_stage"]),
              "owa_inventory_date": OWA_INVENTORY_MONTH},
        assessment={"tier": a.tier, "statement": a.statement,
                    "rationale": a.rationale, "confidence": a.confidence,
                    "period": period, "caveats": caveats},
        observations=observations, chips=chips,
        transforms=transforms, sources=sources,
    )
    packet["claim"]["caveats"] = caveats
    packet["baseline"] = {"period": f"{baseline_years[0]}-{baseline_years[-1]}",
                          "ndvi_median": a.baseline_ndvi, "ndvi_std": a.baseline_std,
                          "n_observations": a.n_baseline_obs}
    packet["assessment_detail"] = {"period": period, "ndvi_median": a.current_ndvi,
                                   "n_observations": a.n_current_obs,
                                   "delta_vs_baseline": a.delta,
                                   "delta_ci95": a.delta_ci95,
                                   "matched_months": a.matched_months}

    out = write_packet(packet, args.out)
    print(f"{args.site}: {a.tier.upper()} — {a.statement} "
          f"(delta {a.delta:+.3f}, baseline {a.baseline_ndvi:.3f} "
          f"-> current {a.current_ndvi:.3f}, confidence {a.confidence})")
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
