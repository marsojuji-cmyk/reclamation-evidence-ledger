# Changelog

## Unreleased

- 360° engineering audit (AUDIT-2026-10-10.md, Ternus lens): P0/P1 findings fixed, P2 parked with reasons
- fix: withdraw the published-false ±300 m geocoding accuracy claim everywhere it appeared (sites.py docstrings, registry `geo_method`, packet caveats, rendered HTML, README); all now reference NEGATIVE-RESULT-2026-10-09.md
- feat: `tests/test_geocode.py` — grid-geometry pins (LSD/township/range steps, boustrophedon parity) + xfail work-order test for ground-truth verification of `dls_to_latlon`
- feat: `pyproject.toml` — `reclamation-ledger` is now pip-installable with console entry points for all 7 CLIs; removed every `sys.path` import hack
- fix: `ops/assess_all.py` uses `sys.executable` instead of a hardcoded `.venv` python; packet period is a `--period` flag instead of a hardcoded string
- fix: deduplicate `sha256_file` (single home: `ledger.packet`)
- ci: ruff lint + format check on every push; fixed 43 findings, formatted 19 files
- fix: `test_observation_count_definitions` reads period years from each packet's own transform instead of hardcoding 2023-2026
- docs: README test count 11 → 17; Evidence section carries the 2026-10-09 negative-result status inline

## v0.4.0 (2026-10-09)

- feat: enhance community standards, automated testing, and client portal (#28)

## v0.3.1 (2026-10-05)

- fix: grant lint-title job pull-requests read permission (#14)

## v0.3.0 (2026-09-29)

- feat: interactive evidence dashboard generated from packets
- feat: dashboard is single-file, dependency-free (`ops/render_dashboard.py` → `docs/index.html`): self-audit story, 99-site findings register with delta histogram and filters, per-site dossiers (NDVI time series with month-matched observations ringed, delta + bootstrap CI, claim, caveats, provenance), method plate, BACI self-audit plate, colophon. Replaces the static snapshot index; per-site packet pages retained as the deep-dive layer.
- docs: README now reflects the 99-site / 13-licensee pilot and the dashboard.
- fix: bump CI to Python 3.12 for rasterio 1.5 support (#8)

## v0.2.0 (2026-09-28)

- feat: pilot-02 evidence — 72 new packets, tier/identified results, Pages snapshot
- feat: pilot-02 expansion selection + tooling (99 sites, 13 licensees)

## v0.1.0 (2026-09-27)

- feat: provisional hand-digitized footprints for 5 pilot sites
- feat: radiometric lineage audit recorded as evidence
- fix: degenerate bootstrap CI refused; claim labels made exact; determinism tripwires
- fix: actually ignore data/ (trailing comments broke gitignore patterns)
