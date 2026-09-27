# Provisional footprints — READ BEFORE USE

`pilot5_provisional.geojson` holds hand-digitized disturbance footprints for
5 pilot sites. They are **interpreter estimates, not authoritative boundaries.**

## How they were made (2026-09-27)

For each site, the latest clear Sentinel-2 scene's chip was rendered as a
false-colour composite (NIR→red, red→green, blue→blue) with the DLS LSD
centroid marked — see `interpretation/<site>_<date>_falsecolour.png`.
Polygons were drawn in chip pixel coordinates and converted to WGS84 via
each chip's own EPSG:32612 transform.

Interpreter rule: disturbance = a contiguous low-vegetation (dark) patch
around the centroid, distinct from surrounding fields. Where no such patch
exists, the polygon traces the field parcel containing the centroid and
`disturbance_resolved=false`.

## What the confidence classes mean

- **medium** (1 site): a distinct disturbed patch is visible, but its boundary
  is gradational and the pad itself is not resolved at 10 m.
- **low** (4 sites): no discrete disturbance is visible. The polygon is an
  area of interest, not a footprint. Do not use as ground truth.

## What supersedes these

Any of: an AER reclamation application site plan, an OWA project boundary,
a licensed high-resolution survey, or on-the-ground GPS. When one arrives,
these files are replaced, not refined.

## What they must NOT be used for

- Not inputs to the assessment pipeline (nothing in `ledger/` reads this
  directory; that is deliberate).
- Not evidence of where a wellhead is.
- Not a basis for any claim about any operator.

They exist for one purpose: a bounded, documented starting geometry for the
BACI control-site design work, to be discarded the moment real footprints
arrive.
