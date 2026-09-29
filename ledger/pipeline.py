"""Monthly pipeline: fetch new scenes, assess all pilot sites, render the ledger.

This is the entry point the launchd plist calls:

    python -m ledger.pipeline run-monthly --sites pilots/pilot-02.txt

It chains the three stages that already exist as CLIs:
  1. ledger.imagery fetch   (incremental; skips dates already on disk)
  2. per-site ledger.change assess  (via ops/assess_all.py; skips failures
     honestly instead of crashing the run)
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
        raise SystemExit(f"pipeline step failed ({r.returncode}): {argv[1]} {argv[2]}")


def cmd_run_monthly(args) -> None:
    today = date.today()
    # Growing season only; outside it there is nothing honest to add.
    from .config import DEFAULT
    if today.month not in DEFAULT.growing_months:
        print(f"{today.isoformat()}: outside growing season "
              f"{sorted(DEFAULT.growing_months)} — nothing to do.")
        return

    season_start = date(today.year, 5, 1)
    _run(VENV_PY, "-m", "ledger.imagery", "fetch",
         "--sites", args.sites, "--registry", args.registry,
         "--start", season_start.isoformat(), "--end", today.isoformat(),
         "--out", args.chips, "--max-scenes", str(args.max_scenes))
    _run(VENV_PY, str(ROOT / "ops" / "assess_all.py"))
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
    args = ap.parse_args()
    if args.cmd == "run-monthly":
        cmd_run_monthly(args)


if __name__ == "__main__":
    main()
