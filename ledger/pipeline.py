"""Monthly pipeline: fetch new scenes, assess all pilot sites, render the ledger.

This is the entry point the launchd plist calls:

    python -m ledger.pipeline run-monthly --sites pilots/pilot-02.txt

It chains the stages that already exist as CLIs:
  0. ledger.sites            (downloads the current OWA inventory and writes
     the registry plus <registry>.owa_provenance.json: file URL, date,
     SHA-256; skip with --skip-owa-refresh)
  1. ledger.imagery fetch   (incremental; skips dates already on disk)
  2. per-site ledger.change assess  (via ops/assess_all.py --force, so sites
     with new scenes are re-assessed; failures are recorded, not fatal)
  3. ledger.render           (rebuilds the static site from packets/)

Growing-season discipline lives in config.growing_months; months outside it
are never fetched or assessed. Nothing is published here — the operator
reviews out/ledger/ before any upload.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = sys.executable


def _run(*argv: str) -> None:
    print(f"$ {' '.join(argv)}", flush=True)
    r = subprocess.run(argv, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"pipeline step failed ({r.returncode}): {' '.join(argv[1:3])}")


def cmd_run_monthly(args) -> None:
    today = date.today()
    # Growing season only; outside it there is nothing honest to add.
    from .config import DEFAULT
    if today.month not in DEFAULT.growing_months:
        print(f"{today.isoformat()}: outside growing season "
              f"{sorted(DEFAULT.growing_months)} — nothing to do.")
        return

    season_start = date(today.year, 5, 1)
    if not args.skip_owa_refresh:
        _run(VENV_PY, "-m", "ledger.sites", "--out", args.registry)
    _run(VENV_PY, "-m", "ledger.imagery", "fetch",
         "--sites", args.sites, "--registry", args.registry,
         "--start", season_start.isoformat(), "--end", today.isoformat(),
         "--out", args.chips, "--max-scenes", str(args.max_scenes))
    assess = [VENV_PY, str(ROOT / "ops" / "assess_all.py"),
              "--sites", args.sites, "--registry", args.registry,
              "--chips", args.chips, "--packets", args.packets,
              "--baseline-start", str(args.baseline_start),
              "--baseline-end", str(args.baseline_end),
              "--assessment", args.assessment]
    if not args.no_force:
        assess.append("--force")
    _run(*assess)
    _run(VENV_PY, "-m", "ledger.render",
         "--packets", args.packets, "--out", args.out)
    print("monthly run complete: review out/ledger/ before publishing.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Reclamation Evidence Ledger pipeline.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-monthly", help="fetch + assess + render for pilot sites")
    r.add_argument("--sites", default="pilots/pilot-02.txt")
    r.add_argument("--registry", default="data/sites.parquet")
    r.add_argument("--chips", default="data/chips")
    r.add_argument("--packets", default="packets")
    r.add_argument("--out", default="out/ledger")
    r.add_argument("--max-scenes", type=int, default=10)
    r.add_argument("--baseline-start", type=int, default=2023)
    r.add_argument("--baseline-end", type=int, default=2024)
    r.add_argument("--assessment", default="2025-2026",
                   help="assessment years; packets are named by this period")
    r.add_argument("--skip-owa-refresh", action="store_true",
                   help="reuse the existing registry instead of downloading "
                        "the current OWA inventory")
    r.add_argument("--no-force", action="store_true",
                   help="skip sites that already have a packet for the period")
    args = ap.parse_args()
    if args.cmd == "run-monthly":
        cmd_run_monthly(args)


if __name__ == "__main__":
    main()
