# Reclamation Evidence Ledger

**An independent satellite watchdog for Alberta's orphan wells.** Free
Sentinel-2 imagery, a fully automated Python pipeline, and one question per
site, answered on a schedule: *is the land healing?* Every claim stamped for
provenance, uncertainty, and limits.

Live ledger · 99-site pilot (13 licensees) · Alberta, Canada

> **Dashboard:** `docs/index.html` is now an interactive evidence dashboard generated from the packets themselves (`python ops/render_dashboard.py`) — the audit story, the 99-site findings register, per-site dossiers with NDVI time series, the method, and the ongoing self-audit. Every number on it is computed at render time; nothing is hand-typed.

---

## The story in 60 seconds

Alberta has tens of thousands of orphan oil and gas wells — sites whose
operators walked away, leaving cleanup to the public purse. Nobody was
watching whether reclaimed land actually recovers. This project watches from
orbit and publishes exactly what it sees, with every claim stamped for
provenance, uncertainty, and limits — including its own caught mistakes: the
first method reported all 27 pilot sites recovering, and a full audit found
it was measuring the calendar, not reclamation.

The most important thing this project produced wasn't a green dashboard — it
was a caught mistake. The first version of the change-detection method
compared seasonal vegetation medians and reported that **all 27 pilot sites
were recovering**. A full audit found the flaw: baseline scenes were sampled
in May/June while current scenes were sampled in July. Summer is greener than
spring — the method was measuring the calendar, not reclamation. The
assessment was rebuilt around **month-matched median-of-deltas** (each
calendar month compared only to itself, ≥2 matched months required, honest
refusal otherwise). Under the corrected method, most sites show no
significant change, and several honestly report insufficient evidence.

That arc — build, audit, catch the bias, fix it, say so publicly — is the
point. A watchdog that can't catch its own errors can't be trusted to watch
anyone else.

## What it does

1. **Registry** — downloads the Orphan Well Association's monthly inventory
   (21,892 geocoded sites) and derives coordinates from Dominion Land Survey
   names to ~±300 m LSD centroids.
2. **Imagery** — queries the Sentinel-2 STAC catalog and downloads windowed
   red/NIR/SWIR/blue/SCL chips (500 m buffers) with per-scene checksums,
   cloud/shadow rejection, and incremental backfill.
3. **Assessment** — per-scene NDVI/NDMI/bare-soil indices, SCL cloud masking,
   month-matched baseline-vs-current comparison, schema-validated evidence
   packet per site with claim tier (`detected` / `identified` only —
   attribution is excluded by design).
4. **Ledger** — renders a static, publish-anywhere website: site map, trend
   per site, methodology, and a limitations page.

## Doctrine

Borrowed from imagery interpretation tradecraft:

- **Detection ≠ identification ≠ attribution.** The pipeline may report that
  vegetation changed (detected) and that the change is consistent with
  reclamation (identified). It never names a responsible party (attributed) —
  attribution requires human review and ground truth.
- **Keep the raw evidence.** Every chip is stored untouched with a checksum.
  Every transform is logged. Nothing is a black box.
- **Change over time beats single frames.** Baselines are built from prior
  growing seasons; each new observation is a diff against the baseline.
- **Screen, don't accuse.** Outputs prioritize sites for ground inspection.
  They are not compliance verdicts.

## Honest limits

- Sentinel-2's 10 m pixels cannot resolve wellheads or prove contamination,
  legal compliance, causation, or methane emissions.
- Compare growing season to growing season only (May–Sep). Alberta snow
  (Nov–Mar) makes winter comparisons meaningless; drought years mimic
  non-recovery.
- Every public claim carries its claim tier and provenance. No exceptions.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Build the site registry — downloads the current OWA monthly inventory automatically.
#    The OWA file carries no coordinates: sites are geocoded from their
#    Dominion Land Survey names to LSD centroids (~+/-300 m; road allowances ignored).
python -m ledger.sites --out data/sites.parquet

# 2. Fetch imagery chips for pilot sites (STAC query + windowed band download,
#    500 m buffer crops, per-site manifest with URLs, checksums, rejections)
python -m ledger.imagery fetch --sites pilots/pilot-01.txt \
    --start 2023-05-01 --end 2026-08-31 --out data/chips --max-scenes 10
# Re-running fetch for a site only downloads dates it doesn't already have
# (incremental backfill — safe to repeat for clouded-out years).

# 3. Assess chips -> schema-validated evidence packet (SCL cloud mask, NDVI/NDMI/
#    bare-soil/SAVI/MSAVI per scene, month-matched baseline diff with bootstrap
#    95% CI on the median delta, claim tier)
python -m ledger.change assess --site "01-06-018-26W4 (100)" \
    --chips data/chips/01-06-018-26W4__100_ \
    --baseline-start 2023 --baseline-end 2024 --assessment 2025-2026 \
    --out packets/

# 4. Render the static ledger site
python -m ledger.render --packets packets/ --out out/ledger/

# 5. Recurring run (the entry point ops/ca.reclamation-ledger.plist calls):
#    fetch new scenes + assess all pilot sites + re-render. No-ops outside
#    the growing season (May-Sep).
python -m ledger.pipeline run-monthly --sites pilots/pilot-01.txt
```

## Layout

```
ledger/          pipeline modules (sites → imagery → indices → change → packet → render)
schemas/         JSON schema for evidence packets (the contract everything honors)
pilots/          pilot site lists (start small: 20–30 sites, one county)
data/            raw inputs (chips/ gitignored; reproducible via fetch, not stored)
packets/         evidence packets (generated; each is self-describing)
docs/            published ledger site snapshot (GitHub Pages serves this)
ops/             launchd plist for the recurring run
```

## Recurring run

`ops/ca.reclamation-ledger.plist` runs the full pipeline monthly during growing
season (May–Sep) and refreshes the OWA inventory each run. Install with:

```bash
cp ops/ca.reclamation-ledger.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/ca.reclamation-ledger.plist
```

## Data sources

| Source | What | Access | Cost |
|---|---|---|---|
| OWA site inventory | orphan site list, closure stage (no coordinates in file) | orphanwell.ca (monthly) | free |
| DLS geocoding | LSD-centroid coords derived from OWA site names (~±300 m) | built-in (`ledger/sites.py`) | free |
| Sentinel-2 L2A | 10 m multispectral imagery, ~5-day revisit | AWS `s3://sentinel-cogs/` / Copernicus Data Space | free |
| Landsat | deep archive back to 1972 (optional baseline) | USGS EarthExplorer | free |

Copernicus data requires attribution — see the site footer.

## License

MIT — see [LICENSE](LICENSE).

## Continuous validation

`.github/workflows/validate.yml` re-validates every `packets/*.json` against
`schemas/evidence-packet.schema.json` on each push to main. A packet that
fails the contract never ships.
