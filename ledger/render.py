"""Static ledger renderer: packets -> publishable HTML.

No server, no database, no JavaScript framework. The ledger is a set of
static pages: an index table plus one page per packet. Anything a reader
needs is in the HTML; the JSON packets sit alongside for verification.

Usage:
    python -m ledger.render --packets packets/ --out public/
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

ATTRIBUTION = ("Imagery: Copernicus Sentinel-2 (ESA), via AWS Open Data. "
               "Contains modified Copernicus Sentinel data.")

PAGE_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Reclamation Evidence Ledger</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:70ch;margin:2rem auto;padding:0 1rem;line-height:1.5}}
.tier{{display:inline-block;padding:.2rem .6rem;border-radius:4px;font-weight:600}}
.detected{{background:#fff3cd}} .identified{{background:#d1ecf1}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ccc;padding:.4rem;text-align:left}}
.caveat{{background:#f8f9fa;border-left:4px solid #999;padding:.5rem 1rem;margin:.5rem 0}}
footer{{margin-top:3rem;font-size:.85rem;color:#555;border-top:1px solid #ccc;padding-top:1rem}}
code{{background:#f4f4f4;padding:.1rem .3rem}}
</style></head>
<body>
<h1>Reclamation Evidence Ledger</h1>
{body}
<footer><p>{attribution}</p>
<p>Screening only: these packets prioritize ground inspection. They are not
compliance verdicts and name no responsible party.</p></footer>
</body></html>"""


def _esc(v) -> str:
    return html.escape(str(v))


def render_packet(packet: dict) -> str:
    c = packet["claim"]
    obs_rows = "".join(
        f"<tr><td>{_esc(o['date'])}</td><td><code>{_esc(o['scene_id'])}</code></td>"
        f"<td>{o.get('ndvi_mean') if o.get('ndvi_mean') is not None else '—'}</td>"
        f"<td>{o.get('ndmi_mean') if o.get('ndmi_mean') is not None else '—'}</td>"
        f"<td>{o['clear_pixel_fraction']:.0%}</td></tr>"
        for o in packet["observations"]
    )
    caveats = "".join(f'<div class="caveat">{_esc(x)}</div>' for x in c["caveats"])
    transforms = "".join(
        f"<li><b>{_esc(t['step'])}</b> — {_esc(t['tool'])} "
        f"<code>{_esc(json.dumps(t['parameters']))}</code></li>"
        for t in packet["transforms"]
    )
    srcs = "".join(
        f"<li>{_esc(s['name'])} — <a href='{_esc(s['url'])}'>{_esc(s['url'])}</a> "
        f"(accessed {_esc(s['accessed'])})</li>" for s in packet["provenance"]["sources"]
    )
    s = packet["site"]
    return PAGE_TMPL.format(
        title=_esc(packet["packet_id"]),
        attribution=ATTRIBUTION,
        body=f"""
<h2>Site {_esc(s['site_id'])}</h2>
<p>{_esc(s.get('name',''))} — {_esc(s['latitude'])}, {_esc(s['longitude'])}<br>
OWA stage: <b>{_esc(s['owa_stage'])}</b> (inventory {_esc(s.get('owa_inventory_date',''))})</p>
<h3>Claim <span class="tier {c['tier']}">{_esc(c['tier']).upper()}</span></h3>
<p><b>{_esc(c['statement'])}</b> — {_esc(c['rationale'])}<br>
Confidence: {_esc(c['confidence'])}</p>
{caveats}
<h3>Observations</h3>
<table><tr><th>Date</th><th>Scene</th><th>NDVI</th><th>NDMI</th><th>Clear</th></tr>
{obs_rows}</table>
<h3>Transforms (the argument against the result)</h3>
<ol>{transforms}</ol>
<h3>Sources</h3>
<ul>{srcs}</ul>
<p><a href="index.html">← ledger index</a></p>
""",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Render the static ledger site.")
    ap.add_argument("--packets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    packets = sorted(Path(args.packets).glob("*.json"))

    rows = []
    for p in packets:
        packet = json.loads(p.read_text())
        # packet_ids can contain '/' (site names like "102/10-16"); filenames must not.
        page = re.sub(r"[\\/]", "_", packet["packet_id"]) + ".html"
        (out / page).write_text(render_packet(packet))
        c = packet["claim"]
        rows.append(
            f"<tr><td><a href='{page}'>{_esc(packet['packet_id'])}</a></td>"
            f"<td><span class='tier {c['tier']}'>{_esc(c['tier'])}</span></td>"
            f"<td>{_esc(c['statement'])}</td><td>{_esc(c['confidence'])}</td></tr>"
        )

    index = PAGE_TMPL.format(
        title="Index", attribution=ATTRIBUTION,
        body=f"<h2>{len(packets)} evidence packets</h2>"
             "<table><tr><th>Packet</th><th>Tier</th><th>Finding</th><th>Confidence</th></tr>"
             + "".join(rows) + "</table>",
    )
    (out / "index.html").write_text(index)
    print(f"rendered {len(packets)} packets -> {out}")


if __name__ == "__main__":
    main()
