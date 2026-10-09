# Negative result: the Reclamation Evidence Ledger's satellite screen does not work as built

Written 2026-10-09 (America/Edmonton, MT), after Marcus Richards decided on 2026-10-09 at 12:37 MT to stop the Ledger screening work and write up the negative result. Screening work has stopped. The planned visibility re-run (v2b) and any v3 will not be run.

Every number below comes from one of the following files, and the source is named next to each claim. Paths are relative to `/workspace/seedling-ledger/`.
- **[DESIGN]** `experiment-design.md`
- **[README]** `repo/README.md` (the Ledger's own description, code at commit 582d1b2)
- **[V1-PREREG]** `preregistration-2026-10-02.md` and its `.sha256.txt`
- **[V1-RESULTS]** `run/results.md`
- **[V1-DEV]** `run/deviations.md`
- **[DIAG]** `run/pad-diagnosis.md`
- **[V2-PREREG]** `preregistration-v2-2026-10-08.md` and its `.sha256.txt`
- **[V2-RESULTS]** `run-v2/v2a/results.md`
- **[V2-DEV]** `run-v2/deviations.md`

## 1. What the Ledger claimed to do
The Reclamation Evidence Ledger describes itself as "an independent satellite watchdog for Alberta's orphan wells". It uses free Sentinel-2 imagery and an automated pipeline to answer one question per site: "is the land healing?" [README]. It publishes a 99-site pilot as "packets" and a dashboard served from GitHub Pages [README].

It presents itself as a screen, not a judge: "Screen, don't accuse. Outputs prioritize sites for ground inspection. They are not compliance verdicts." [README]. The project's own design rules never allow the words "reclaimed", "recovered" or "certifiable" [DESIGN]. Its strongest label is a claim tier called **"identified"**, meaning that vegetation changed in a way "consistent with reclamation" [README].

What we tested is whether that screen can tell real change at a well from ordinary background change.

## 2. What we tested, and how we kept ourselves honest
Both test plans were written down and sealed before any data was run. Each plan was saved, its SHA-256 hash recorded, and the file made read-only. Changes after that go only into a dated deviations log.
- **v1 plan, sealed 2026-10-02:** sha256 `41e056ffaf494446905890f3362acdb1209d009816b5066c9f7e8f19a90cd37d` [V1-PREREG]. It was re-verified as unchanged before the run on 2026-10-08 [V1-RESULTS].
- **v2 plan, sealed 2026-10-08:** sha256 `8ef3250a7140b417c295628c32c36f0ed91a26c8dde3ac68c4496844e3645282` [V2-PREREG]. It was re-verified, along with every analysis script, after scoring [V2-RESULTS].

The Ledger code itself was never changed. Every test ran on a copy of commit 582d1b2 [V1-RESULTS, V2-RESULTS].

### Stage 0a (v1): the "no-well" test. Verdict: **KILL**
We picked 100 random spots with no known well within 604 m, each matched to one of the pilot sites, and ran the Ledger's own pipeline on them exactly as it runs today [V1-RESULTS].
- **15 of 100** no-well spots came out "identified": all 15 as "vegetation recovering" [V1-RESULTS]. The pre-set line was KILL at 11 or more [V1-RESULTS].
- The screen's ability to tell published well sites from the no-well spots (AUC) was **0.60** (0.6015) [V1-RESULTS]. 0.5 would be pure chance.
- For comparison, the published pilot marks 28 of its 99 sites "identified" [V1-RESULTS]. Against a 15% false-alarm rate on land with no well at all, that 28% can't be read as evidence about the wells.
- The no-well spots also tended to get greener overall: 70 of 100 had positive changes [V1-RESULTS]. That fits a regional effect such as drought in the 2023–24 baseline years, not site recovery [V1-RESULTS].

### Stage 0b (v1): can a person see a well pad at 10 m? Verdict: **INVALID**
- **What was rated:** 50 blinded image chips (30 target pads, 10 active pads as a positive check, and 10 no-well decoys) [V1-RESULTS].
- **What makes a run valid:** at least 8 of 10 active pads seen, and at most 1 of 10 decoys [V1-RESULTS].
- **What happened:** 6 of 10 active pads were seen and 0 of 10 decoys, so the run failed its own check and is INVALID [V1-RESULTS].
- **Target result:** 3 of 30 targets were seen. That number is reported but not acted on [V1-RESULTS].
- **Why the run failed (post-hoc diagnosis):** all 4 missed active pads were real, producing, shallow wells with no clearing that 10 m pixels can resolve [DIAG]. So the positive check itself was badly specified.

### The diagnosis: the Ledger was looking in the wrong place
While checking coordinates, we found that the Ledger's location function (`dls_to_latlon`, which turns a legal land description into latitude/longitude) is systematically wrong [DIAG].
- **Across the province:** in 20,000 random wells, the median error was 2,658 m. 0.0% were within 300 m, the function's documented accuracy [DIAG].
- **At the 99 published pilot sites:** the Ledger's point is 1,165–4,387 m from the actual well (median **2,410 m**) [DIAG]. **0 of 99** analysis squares (±500 m) contain the well [DIAG]. In other words, the published packets measured land about 2.4 km from each well [DIAG].

This was a post-hoc diagnosis and changed no verdict [DIAG, V1-DEV].

### v2a: a fairer, corrected version of the screen. Verdict: **RE-SCOPE**
v2 fixed the location problem by using the regulator's surveyed well coordinates (AER ST37) [DIAG, V2-PREREG]. It also corrected for regional change by subtracting 5 matched control spots per subject, and kept the Ledger's ±500 m square [V2-PREREG].
- **No-well spots (nulls):** **6 of 100** were flagged as changed. 100 of 100 were matched; 95 had a result and 5 were refused for too few usable months [V2-RESULTS]. Under the plan, refusals count as not flagged and the denominator stays 100. 6 falls in the pre-set RE-SCOPE band of 6–10 [V2-PREREG, V2-RESULTS]. 6 of the 95 with a result would be 6.3%, which is also inside the RE-SCOPE band. Three of the six were only just over the 0.08 threshold [V2-RESULTS].
- **Known new pads (the "guard set" of 10 recent southern pads):** **0 of 10** flagged, and all 10 had a result [V2-RESULTS]. The corrected screen did not detect any of the new pads it should most easily have seen.
- **Wells:** **1 of 99** flagged (91 with a result) [V2-RESULTS].
- **Panels:** the northern cropland panel had 1 of 9 flagged and the forest panel 0 of 9. These were reported only and gate nothing [V2-RESULTS].

So even after correction, the square-level screen false-alarms more than the plan allowed, and it misses real new pads [V2-RESULTS].

### Report-only pad-scale arm (v2a-PS): **exploratory, not a validated result**
The plan included a secondary measure that compares a 40 m pad circle against a 100–250 m ring around the same point. It was declared in advance as report-only: it gates nothing and cannot change any verdict [V2-PREREG].
- **No-well spots:** 0 of 100 flagged (98 with a result) [V2-RESULTS].
- **Guard pads:** 7 of 10 flagged [V2-RESULTS].
- **P-001:** a pad replaced in the guard set because it had no controls. It was also flagged [V2-RESULTS].
- **Pre-set "readiness line":** no more than 5 of 100 nulls flagged AND at least 8 of 10 guard pads flagged. It was **not met** [V2-RESULTS].

This arm is **exploratory**. It was never tested as a primary outcome, its 0.10 bar was set from pad contrasts seen in the post-hoc diagnosis rather than at a tested decision threshold [V2-PREREG §2], and 7 of 10 is below its own readiness line. It suggests that something may be measurable at pad scale. It does not show that it is.

## 3. What this means
- **The published packets** measured land a median of about 2.4 km from each well, and 0 of 99 analysis squares contain their well [DIAG]. They are not evidence of recovery, or of non-recovery, at any well.
- **The area-mean screen** ("identified") labels 15% of random no-well spots as recovering in its original form [V1-RESULTS]. In corrected form it still flags 6 of 100 nulls and 0 of 10 known new pads [V2-RESULTS]. It should not be read as evidence of recovery at any well.

## 4. Limits and deviations
All deviations are logged with timestamps in [V1-DEV] and [V2-DEV]. The ones that matter most:
- **Box restart during v2a:** the machine restarted at about 20:14 MT on 2026-10-08, which killed the imagery fetch at 626 of 1,358 sites [V2-DEV].
  - The 732 unfinished sites were fetched again with the unchanged script. Sites already complete were not re-fetched [V2-DEV].
  - All 1,358 sites finished, and 1,358 of 1,358 assessments succeeded [V2-RESULTS, V2-DEV].
  - Imagery was queried in two time windows, which could in principle differ slightly [V2-DEV].
- **Software environment:** the Python environment had to be rebuilt after the restart, before v1 Stage 0a on 2026-10-08 (after a ~Oct 5 restore) [V1-DEV] and again during v2a [V2-DEV].
  - Exact earlier package versions were not recorded, so they can't be compared [V1-DEV, V2-DEV].
  - In v2a, the scipy package is missing from the rebuilt environment. It is not used by fetching, assessment or scoring [V2-DEV].
  - The Ledger code and every analysis script matched their sealed hashes [V2-RESULTS].
- **Late v1 delivery:** the v1 plan was sealed on 2026-10-02, but Stage 0a was only run and scored on 2026-10-08, after a box restore [V1-PREREG, V1-RESULTS, V1-DEV].
  - Stage 0a also needed two operational fixes. The `--site` argument was missing from the pre-registered command, and a metadata field value failed schema validation (`owa_stage`), which was changed to "unknown" [V1-DEV].
  - Neither fix affects the measured change [V1-DEV].
- **AI raters in Stage 0b:** the two "raters" were two passes by the same AI agent in the same session, not humans [V1-RESULTS].
  - They were sealed 38 s and 29 s apart and agreed on every yes/not-yes call (κ = 1.0), so their independence is weak [V1-RESULTS, V1-DEV].
  - IDs were misread while typing (4 of 50 in pass A, 7 of 50 in pass B) and re-keyed by position. No answer was changed [V1-DEV].
- **Other limits:** the 0b diagnosis was post-hoc, used no sub-metre imagery, rested on 10 active pads, and was done knowing which chips were actives [DIAG].
- **v2a regional gaps:** more than 20% of subjects had no result in Central Parkland (7 of 31), Dry Mixedwood (2 of 7) and Lower Boreal Highlands (1 of 1) [V2-RESULTS].

## 5. What we are NOT claiming
- We are **not** claiming that any well site has or has not recovered. These tests say nothing about the land at any particular well.
- We are **not** claiming that satellite monitoring of well sites cannot work. We tested this pipeline, at this scale (10 m pixels, ±500 m area means), with these settings.
- We are **not** claiming that the pad-scale measure works. It is exploratory and did not meet its own readiness line.
- We are **not** claiming that anything was deliberate. The location error looks like a systematic bug [DIAG].
- We are **not** making any statement about soil, contamination, methane, legal compliance or reclamation certificates. None was ever in scope [README, DESIGN].
- We are **not** saying the human-rater visibility question is settled. Stage 0b was INVALID, and the planned re-run with human raters (v2b) was not carried out.

## 6. Suggested follow-ups for Marcus (suggestions only, for you to decide)
- **Published site and packets:** consider taking down the GitHub Pages site and the published packets, or adding a clear caveat that they measured land about 2.4 km from each well and should not be read as evidence at any well.
- **Converter bug:** consider fixing `dls_to_latlon`, or at least flagging it publicly (for example in the README or an issue). [DIAG] also notes a related, earlier-reported bug where 2 of 5 hand-drawn pad outlines were exactly 6° of longitude off.
- **HFI licence:** before publishing anything derived from the ABMI Human Footprint Inventory 2023 (used in the diagnosis), consider confirming its licence terms [DIAG].
- **This write-up:** decide whether to publish it in the repo. It has not been added there.
