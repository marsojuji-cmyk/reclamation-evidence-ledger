## v0.3.0 (2026-09-29)

- feat: interactive evidence dashboard generated from packets
- fix: bump CI to Python 3.12 for rasterio 1.5 support (#8)

## v0.2.0 (2026-09-28)

- feat: pilot-02 evidence — 72 new packets, tier/identified results, Pages snapshot
- feat: pilot-02 expansion selection + tooling (99 sites, 13 licensees)

## Unreleased

- feat: interactive evidence dashboard (`ops/render_dashboard.py` → `docs/index.html`) — single-file, dependency-free, generated from `packets/*.json`: the self-audit story (v1 seasonal-bias catch → month-matched rebuild → synthetic verification), 99-site findings register with delta histogram and filters, per-site dossiers (NDVI time series with month-matched observations ringed, delta + bootstrap CI, claim, caveats, provenance), method plate, BACI self-audit plate, colophon. Replaces the static snapshot index; per-site packet pages retained as the deep-dive layer.
- docs: README now reflects the 99-site / 13-licensee pilot and the dashboard.

# Changelog

## v0.1.0 (2026-09-27)

- feat: provisional hand-digitized footprints for 5 pilot sites
- feat: radiometric lineage audit recorded as evidence
- fix: degenerate bootstrap CI refused; claim labels made exact; determinism tripwires
- fix: actually ignore data/ (trailing comments broke gitignore patterns)
