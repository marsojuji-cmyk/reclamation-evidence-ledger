#!/usr/bin/env python3
"""Assess all pilot sites in a pilot manifest, skipping and recording failures.

Usage: .venv/bin/python ops/assess_all.py [--sites pilots/pilot-02.txt]
Writes packets/*.json and ops/assess_results.json + failures list.
Safe to rerun: skips sites whose packet already exists (unless --force).
"""
import argparse, csv, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `ledger` importable when run as a script
VENV_PY = str(ROOT / ".venv" / "bin" / "python")


def safe_dir(site_id: str) -> str:
    from ledger.imagery import safe_site_id
    return safe_site_id(site_id)


def packet_name(site_id: str) -> str:
    from ledger.packet import packet_filename
    return packet_filename(f"{site_id}_2025-2026_growing_seasons")


def load_sites(manifest: str) -> list[str]:
    sites = []
    for line in (ROOT / manifest).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            sites.append(line)
    return sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-assess even if packet exists")
    ap.add_argument("--sites", default="pilots/pilot-02.txt",
                    help="pilot manifest (one site_id per line)")
    args = ap.parse_args()

    sites = load_sites(args.sites)
    results, failures = [], []
    t0 = time.time()
    for i, site in enumerate(sites, 1):
        safe = safe_dir(site)
        chips = ROOT / "data" / "chips" / safe
        tifs = list(chips.glob("*.tif")) if chips.is_dir() else []
        packet = ROOT / "packets" / packet_name(site)
        print(f"[{i}/{len(sites)}] {site}  (chips dir: {chips.name}, tifs={len(tifs)})", flush=True)
        if packet.exists() and not args.force:
            results.append({"site": site, "status": "already_present", "packet": packet.name})
            continue
        if not tifs:
            failures.append({"site": site, "reason": "no chips downloaded"})
            continue
        try:
            r = subprocess.run(
                [VENV_PY, "-m", "ledger.change", "assess",
                 "--site", site, "--chips", str(chips),
                 "--baseline-start", "2023", "--baseline-end", "2024",
                 "--assessment", "2025-2026",
                 "--out", str(ROOT / "packets")],
                capture_output=True, text=True, timeout=1800, cwd=str(ROOT))
            if r.returncode != 0:
                failures.append({"site": site, "reason": f"assess exit {r.returncode}: {r.stderr[-400:]}"})
                print(f"  FAILED: {r.stderr[-200:]}", flush=True)
                continue
            # extract summary from the packet (exact sanitized filename)
            new_packets = [packet] if packet.exists() else []
            if not new_packets:
                failures.append({"site": site, "reason": "assess exited 0 but no packet written"})
                continue
            p = json.loads(new_packets[0].read_text())
            results.append({
                "site": site,
                "status": "assessed",
                "packet": new_packets[0].name,
                "tier": p.get("claim", {}).get("tier"),
                "classification": p.get("claim", {}).get("statement"),
                "n_current_scene_observations": p.get("assessment_detail", {}).get("n_scene_observations"),
                "baseline_ndvi": p.get("baseline", {}).get("ndvi_median"),
                "current_ndvi": p.get("assessment_detail", {}).get("ndvi_median"),
                "delta": p.get("assessment_detail", {}).get("delta_vs_baseline"),
                "confidence": p.get("claim", {}).get("confidence"),
            })
            print(f"  OK: {p.get('claim', {}).get('statement')} delta={p.get('assessment_detail', {}).get('delta_vs_baseline')}", flush=True)
        except subprocess.TimeoutExpired:
            failures.append({"site": site, "reason": "assess timed out after 30 min"})
        except Exception as e:  # noqa: BLE001
            failures.append({"site": site, "reason": f"exception: {e}"})

    elapsed = time.time() - t0
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
        "failures": failures,
    }
    (ROOT / "ops" / "assess_results.json").write_text(json.dumps(out, indent=2))
    with open(ROOT / "ops" / "assess_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "status", "packet", "tier", "classification",
                                         "n_current_scene_observations", "baseline_ndvi", "current_ndvi",
                                         "delta", "confidence"])
        w.writeheader()
        for r_ in results:
            w.writerow({k: r_.get(k, "") for k in w.fieldnames})
    print(f"\nDone: {len(results)} ok, {len(failures)} failed, {elapsed/60:.1f} min")
    for fl in failures:
        print("  FAIL:", fl["site"], "-", fl["reason"][:120])


if __name__ == "__main__":
    main()
