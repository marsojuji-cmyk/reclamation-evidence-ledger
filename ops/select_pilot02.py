#!/usr/bin/env python3
"""Select pilot-02: expand the ledger pilot to ~100 sites with licensee diversity.

Design (2026-09-27):
  - Carry over the 27 pilot-01 sites (LEXIN RESOURCES LTD, 3 townships SW Calgary).
  - Add up to 6 sites from each of 12 new licensees, drawn from the OWA
    reclamation-stage pool within 150 km of Calgary (51.05,-114.07), component
    type "Well & Access Road" only (matches pilot-01 criteria).
  - Within a licensee: round-robin across distinct townships (DLS T-R key from
    site_id); within a township take the median of sorted site_ids — spread,
    deterministic, no pad-cluster duplication.
  - Lexin excluded (already covered). LR PROCESSING had 0 qualifying sites and
    was replaced by TERRA ENERGY CORP.

Writes pilots/pilot-02.txt (99 site_ids, full manifest) and
pilots/pilot-02-new.txt (72 new site_ids, for imagery fetch).
"""

import re

import numpy as np
import pandas as pd

LAT0, LON0 = 51.05, -114.07
RADIUS_KM = 150
PER_LICENSEE = 6

LICENSEES = [
    "HOUSTON OIL & GAS LTD",
    "TRIDENT EXPLORATION (ALBERTA) CORP",
    "SANLING ENERGY LTD",
    "CANADIAN OIL & GAS INTERNATIONAL INC",
    "MANITOK ENERGY INC",
    "VERITY ENERGY LTD",
    "TERRA ENERGY CORP",
    "TUSCANY ENERGY LTD",
    "ANTERRA ENERGY INC",
    "NEO EXPLORATION INC",
    "WOLF COULEE RESOURCES INC",
    "LGX OIL + GAS INC",
]


def township(site_id: str) -> str:
    m = re.search(r"(\d{3})-(\d{2}W\d)", site_id)
    return f"{m.group(1)}-{m.group(2)}" if m else "?"


def main() -> None:
    df = pd.read_parquet("data/sites.parquet")
    dlat = (df["latitude"] - LAT0) * 111.0
    dlon = (df["longitude"] - LON0) * 111.0 * np.cos(np.radians(df["latitude"]))
    df["km"] = np.sqrt(dlat**2 + dlon**2)
    pool = df[
        (df["owa_stage"] == "reclamation")
        & (df["component_type"] == "Well & Access Road")
        & (df["km"] <= RADIUS_KM)
        & (df["licensee"] != "LEXIN RESOURCES LTD")
    ].copy()
    pool["township"] = pool["site_id"].map(township)

    new_sites: list[str] = []
    picks_log: list[str] = []
    for lic in LICENSEES:
        sub = pool[pool["licensee"] == lic]
        if sub.empty:
            print(f"WARN: no qualifying sites for {lic}; skipped")
            continue
        by_twp = {t: sorted(g["site_id"].tolist()) for t, g in sub.groupby("township")}
        twps = sorted(by_twp)
        chosen: list[str] = []
        i = 0
        while len(chosen) < PER_LICENSEE:
            twp = twps[i % len(twps)]
            remaining = [s for s in by_twp[twp] if s not in chosen]
            if remaining:
                # deterministic: median of the remaining sorted sites in the township
                chosen.append(remaining[len(remaining) // 2])
            i += 1
            if i > PER_LICENSEE * len(twps) + len(twps):
                break  # every site of this licensee is taken
        new_sites.extend(chosen)
        picks_log.append(
            f"{lic}: {len(chosen)} sites, {len({township(c) for c in chosen})} townships"
        )

    p1 = [ln.strip() for ln in open("pilots/pilot-01.txt") if ln.strip() and not ln.startswith("#")]
    assert not (set(new_sites) & set(p1)), "overlap with pilot-01"
    assert len(new_sites) == len(set(new_sites)), "duplicate new sites"

    header = (
        [
            "# Pilot 02 — 2026-09-27",
            "# Goal: expand to ~100 sites with licensee diversity (pilot-01 was Lexin-only).",
            "# Carry-over: 27 pilot-01 sites (LEXIN RESOURCES LTD; 3 townships SW Calgary).",
            f"# New: {len(new_sites)} sites — up to {PER_LICENSEE} each from 12 new licensees,",
            "# OWA stage=reclamation, component=Well & Access Road, within 150 km of Calgary",
            "# (51.05,-114.07), coords via DLS LSD centroid (accuracy withdrawn 2026-10-09).",
            "# round-robin across distinct townships, median sorted site_id per township —",
            "# deterministic, avoids pad clustering. LR PROCESSING had 0 qualifying sites,",
            "# replaced by TERRA ENERGY CORP.",
            "# Per-licensee picks:",
        ]
        + [f"#   {pick}" for pick in picks_log]
        + [f"# Total: {len(p1) + len(new_sites)} sites"]
    )
    with open("pilots/pilot-02.txt", "w") as f:
        f.write("\n".join(header) + "\n" + "\n".join(p1 + new_sites) + "\n")
    with open("pilots/pilot-02-new.txt", "w") as f:
        f.write("\n".join(new_sites) + "\n")
    print(
        f"wrote pilots/pilot-02.txt ({len(p1) + len(new_sites)} sites), "
        f"pilots/pilot-02-new.txt ({len(new_sites)} new)"
    )
    for pick in picks_log:
        print(" ", pick)


if __name__ == "__main__":
    main()
