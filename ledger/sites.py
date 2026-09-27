"""Site registry: OWA inventory -> DLS-geocoded site table.

The OWA monthly inventory (public .xlsx, no login) carries NO coordinates.
Site Names are Dominion Land Survey locations, e.g. "01-01-002-19W4 (100)"
= LSD 01, Section 01, Township 002, Range 19 West of the 4th meridian.
We geocode the LSD centroid directly — no AER join needed for the pilot.

Accuracy: LSD centroid, road allowances ignored => ~+/-300 m. Honest enough
for 500 m-buffer screening; NOT a legal survey position. Documented per site.

Usage:
    python -m ledger.sites --out data/sites.parquet
    python -m ledger.sites --owa data/owa_inventory.xlsx --out data/sites.parquet
"""
from __future__ import annotations

import argparse
import math
import re
import urllib.request
from pathlib import Path

import pandas as pd

# The OWA inventory file rotates monthly (date-stamped filename on a CDN),
# so never hardcode the download URL — scrape the inventory page for it.
OWA_INVENTORY_PAGE = "https://www.orphanwell.ca/inventory/site-specific-inventory"

DLS_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{1,3})-(\d{1,2})W([456])\b")

# Meridian base longitudes (degrees)
MERIDIAN_LON = {"4": -110.0, "5": -114.0, "6": -118.0}
MI_PER_DEG_LAT = 69.0


def fetch_current_owa_url(page_url: str = OWA_INVENTORY_PAGE) -> str:
    """Scrape the OWA inventory page for the current monthly .xlsx link."""
    req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
    html_text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    candidates = re.findall(r'href="([^"]+\.xlsx?)"', html_text, re.IGNORECASE)
    if not candidates:
        raise RuntimeError(f"no .xlsx inventory link found on {page_url}")
    for c in candidates:
        if "inventory" in c.lower():
            return c
    return candidates[0]


def download_owa(dest: str | Path, url: str | None = None) -> Path:
    """Download the current OWA monthly inventory to dest. Returns the path."""
    url = url or fetch_current_owa_url()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())
    print(f"downloaded OWA inventory ({dest.stat().st_size / 1e6:.1f} MB) from {url}")
    return dest


def parse_dls(name: str) -> tuple[int, int, int, int, str] | None:
    """'01-01-002-19W4 (100)' -> (lsd, section, township, range, meridian)."""
    m = DLS_RE.match(str(name).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), m.group(5))


def dls_to_latlon(lsd: int, sec: int, twp: int, rng: int, mer: str) -> tuple[float, float]:
    """Centroid of the LSD. Boustrophedon section/LSD numbering; road
    allowances ignored (~+/-300 m). Returns (lat, lon)."""
    # Section position within township (1-36, boustrophedon from SE corner)
    row_s = (sec - 1) // 6
    if row_s % 2 == 0:
        east_col_s = (row_s * 6 + 6) - sec
    else:
        east_col_s = sec - (row_s * 6 + 1)
    # LSD position within section (1-16, boustrophedon from SE corner)
    row_l = (lsd - 1) // 4
    if row_l % 2 == 0:
        east_col_l = (row_l * 4 + 4) - lsd
    else:
        east_col_l = lsd - (row_l * 4 + 1)

    lat_south = 49.0 + (twp - 1) * 6.0 / MI_PER_DEG_LAT
    lat = lat_south + (row_s + (row_l + 0.5) / 4.0) / MI_PER_DEG_LAT

    mi_per_deg_lon = 69.172 * math.cos(math.radians(lat))
    lon_west = MERIDIAN_LON[mer] - rng * 6.0 / mi_per_deg_lon
    lon = lon_west + (east_col_s + (east_col_l + 0.5) / 4.0) / mi_per_deg_lon
    return (round(lat, 5), round(lon, 5))


def normalize_stage(dept: object, ptype: object) -> str:
    """Map OWA (Responsible Department, Current Project Type) to ledger stage."""
    d = str(dept or "").strip().lower()
    p = str(ptype or "").strip().lower()
    if "rec cert" in p or d == "closed":
        return "closed"
    if d.startswith("intake"):
        return "unassigned"
    if d == "decommissioning" or "decommissioning" in p or p in ("downhole",):
        return "decommissioning"
    if d == "environment" or p == "environment":
        return "reclamation"
    return "unknown"


def read_owa_raw(path: str | Path) -> pd.DataFrame:
    """Read the OWA workbook, locating the header row dynamically."""
    xls = pd.ExcelFile(path)
    sheet = "Full Inventory" if "Full Inventory" in xls.sheet_names else xls.sheet_names[0]
    probe = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=15)
    header_row = None
    for i, row in probe.iterrows():
        vals = [str(v).strip() for v in row.values]
        if "Site Name" in vals:
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"could not find 'Site Name' header in sheet {sheet}")
    return pd.read_excel(xls, sheet_name=sheet, header=header_row)


def load_owa(path: str | Path) -> pd.DataFrame:
    """Build the normalized site registry: one row per site name."""
    df = read_owa_raw(path)
    df = df.dropna(subset=["Site Name"]).copy()

    parsed = df["Site Name"].map(parse_dls)
    df["dls"] = parsed
    geo = parsed.dropna().map(lambda t: dls_to_latlon(*t))
    df.loc[geo.index, "latitude"] = geo.map(lambda t: t[0])
    df.loc[geo.index, "longitude"] = geo.map(lambda t: t[1])
    df["owa_stage"] = [normalize_stage(d, p) for d, p in
                       zip(df.get("Responsible Department"), df.get("Current Project Type"))]

    # One row per site: keep the first component row, count components.
    df["n_components"] = df.groupby("Site Name")["Site Name"].transform("size")
    sites = df.drop_duplicates(subset=["Site Name"], keep="first")

    out = pd.DataFrame({
        "site_id": sites["Site Name"].astype(str),
        "name": sites["Site Name"].astype(str),
        "licensee": sites["Licensee"].astype(str) if "Licensee" in sites else "",
        "license_number": sites["License Number"].astype(str) if "License Number" in sites else "",
        "component_type": sites["Component Type"].astype(str) if "Component Type" in sites else "",
        "n_components": sites["n_components"].astype(int),
        "dls_parsed": sites["dls"].notna(),
        "latitude": pd.to_numeric(sites["latitude"], errors="coerce"),
        "longitude": pd.to_numeric(sites["longitude"], errors="coerce"),
        "owa_stage": sites["owa_stage"],
        "geo_method": "DLS LSD centroid (~+/-300 m; road allowances ignored)",
    })
    # Keep only geocoded rows inside Alberta bounds.
    out = out.dropna(subset=["latitude", "longitude"])
    out = out[(out.latitude.between(49, 60)) & (out.longitude.between(-121, -109))]
    return out.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the normalized site registry.")
    ap.add_argument("--owa", required=False, default=None,
                    help="path to OWA monthly inventory file "
                         "(omit to download the current one automatically)")
    ap.add_argument("--out", required=True, help="output parquet path")
    args = ap.parse_args()

    owa_path = args.owa or download_owa(Path("data") / "owa_inventory_latest.xlsx")
    sites = load_owa(owa_path)
    print(f"registry: {len(sites)} geocoded sites")
    print(sites.owa_stage.value_counts().to_string())
    print(f"DLS parse coverage: {sites.dls_parsed.mean():.1%}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sites.to_parquet(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
