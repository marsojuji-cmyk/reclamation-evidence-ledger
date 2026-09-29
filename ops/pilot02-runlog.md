# Pilot-02 expansion run log (2026-09-27)

## Objective
Expand the ledger pilot from 27 to ~100 sites, fixing the known Lexin-only
limitation (no licensee diversity). Same month-matched methodology, same claim
tiers {detected, identified}, no compliance verdicts ever.

## Selection design (recorded in pilots/pilot-02.txt + ops/select_pilot02.py)
- Carry over: 27 pilot-01 sites (LEXIN RESOURCES LTD, 3 townships SW Calgary).
- New: 72 sites, up to 6 per licensee across 12 new licensees:
  Houston Oil & Gas, Trident Exploration (Alberta), Sanling Energy,
  Canadian Oil & Gas International, Manitok Energy, Verity Energy,
  Terra Energy, Tuscany Energy, Anterra Energy, Neo Exploration,
  Wolf Coulee Resources, LGX Oil + Gas.
- Pool filter: OWA stage=reclamation, component=Well & Access Road,
  within 150 km of Calgary (51.05,-114.07), DLS LSD centroid coords.
- Within-licensee: round-robin across distinct townships, median sorted
  site_id per township (deterministic, avoids pad clustering).
- Total: 99 sites, 13 licensees.
- Notes: LR PROCESSING had 0 qualifying sites -> replaced by TERRA ENERGY CORP.
  CAMBERLY ENERGY skipped (all 6 sites in a single township).

## Execution
- [ ] Imagery fetch: 72 new sites, 2023-05-01..2026-08-31, max-scenes 20
      (matches pilot-01 backfill density). Incremental/safe to rerun.
- [ ] assess_all.py --sites pilots/pilot-02.txt (parametrized from pilot-01-only;
      skips the 27 existing packets unless --force)
- [ ] render -> out/ledger/; snapshot HTML + assets -> docs/
- [ ] validate packets against schemas/evidence-packet.schema.json
- [ ] commit locally; push via github skill (gh_api_push.py) to
      marsojuji-cmyk/reclamation-evidence-ledger main

## Caveats carried forward (unchanged)
- DLS LSD centroid ±300 m on every packet; 500 m buffer absorbs it.
- Drought-year (2023) weather confound — month-matching removes seasonal
  bias, not interannual weather.
- trust_egress_proxy_tls=True is VM-only.
- Honest refusals where <2 matched months.

## Events
- 2026-09-27: selection committed; fetch smoke test passed on
  06-35-011-22W4 (102) (3 scenes, all clear).
- 2026-09-27: single-worker fetch too slow (~2.5-3 min/site -> ~3h).
  Killed and relaunched 4 parallel workers over deterministic partitions
  (sites[w::4], 18 sites each); per-site manifests only, no shared state,
  incremental so nothing lost. Logs: /tmp/pilot02-fetch-w{0..3}.log.
- 2026-09-28 ~01:07 UTC: runtime restart drain killed the coordinating
  agent mid-fetch (NOT a fault in the work). Work left uncommitted:
  modified ledger/pipeline.py + ops/assess_all.py (both sane, kept);
  untracked ops/select_pilot02.py, ops/summarize_pilot02.py,
  ops/pilot02-runlog.md, pilots/pilot-02-new.txt. Fetch logs lost from
  /tmp, but per-site manifests were intact: 26/72 new sites fetched.
- 2026-09-28 ~01:10 UTC: resuming coordinator re-partitioned the 46
  missing sites into 4 workers (/tmp/pilot02parts/p{0..3}.txt) and
  relaunched fetches. All 4 workers completed exit 0. Fetch coverage:
  99/99 manifests; 3 pilot-01 sites thin at 8 scenes (pre-existing).
  A few individual scene downloads failed RasterioIOError (e.g.
  2026-08-25 S2C_12UUB for 16-08-023-23W4); all honestly rejected and
  logged in per-site manifests — the month-matched guardrail absorbs them.
- 2026-09-28 ~02:00 UTC: assessment complete: 99 ok, 0 failed (1.4 min).
  ops/assess_all.py --sites pilots/pilot-02.txt; 27 pilot-01 packets
  skipped as already present. 0 honest refusals.
- 2026-09-28 ~02:05 UTC: render complete (99 pages + index + 99 charts),
  docs/ Pages snapshot rebuilt (rsync out/ledger -> docs/).
- 2026-09-28 ~02:10 UTC: PUSH REFUSED (correctly). Remote main moved out of
  band while pilot-02 was building: remote holds 66ff974 (as 12cacb0f) +
  3 new commits — 4a4cfc62 chore(deps) xarray (#5), a4a22bd6 chore(deps)
  jsonschema (#4), a4fe2941 docs: CHANGELOG entry for v0.1.0 (all
  2026-09-27 ~07:24 MDT, ~12h before this session). gh_api_push.py refused
  because its recorded remote_head (12cacb0f) != current ref (a4fe2941) —
  the script's divergence safeguard working as designed.
  No force-push, no state-file edit: destruction or safeguard bypass is
  not this coordinator's call. Instead, remote's file changes were mirrored
  byte-identical into local (requirements.txt dep bumps, CHANGELOG.md) as
  commit c2f9ae0, so the working tree is content-complete with remote main.
  Local HEAD c2f9ae0 is unpushed; parent decides the push (safe path: update
  .git/interlock-api-sync remote_head to a4fe2941, then gh_api_push.py —
  it will append local commits as children of remote HEAD; trees already
  carry the dep bumps + CHANGELOG, so nothing is reverted).
