"""Per-site NDVI time-series charts. Pure rendering over packet JSON — no I/O
beyond reading the packet dict and writing one PNG.

The chart is the methodology made visible: baseline scenes vs current scenes,
with the month-matched observations (the ones the delta is actually computed
from) ringed. A reader can see at a glance whether the signal comes from
matched months or from calendar luck.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path


def _period_years(packet: dict) -> tuple[list[int], list[int]]:
    """(baseline_years, current_years) from the baseline_assessment transform."""
    for t in packet.get("transforms", []):
        if t.get("step") == "baseline_assessment":
            p = t.get("parameters", {})
            return (list(p.get("baseline_years", [])), list(p.get("assessment_years", [])))

    # Fallback: parse "2023-2024" / "2025-2026 growing seasons" period strings.
    def yrs(s: str) -> list[int]:
        import re

        m = re.findall(r"\d{4}", s or "")
        if len(m) >= 2:
            return list(range(int(m[0]), int(m[1]) + 1))
        return [int(m[0])] if m else []

    return (
        yrs(packet.get("baseline", {}).get("period", "")),
        yrs(packet.get("assessment_detail", {}).get("period", "")),
    )


def render_site_chart(packet: dict, out_path: str | Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base_years, cur_years = _period_years(packet)
    matched = set(packet.get("assessment_detail", {}).get("matched_months", []))
    obs = [o for o in packet.get("observations", []) if o.get("ndvi_mean") is not None]
    obs.sort(key=lambda o: o["date"])

    fig, ax = plt.subplots(figsize=(9, 4.2))
    if not obs:
        ax.text(0.5, 0.5, "no usable scenes", ha="center", va="center")
    else:
        xs = [date.fromisoformat(o["date"]) for o in obs]
        ys = [o["ndvi_mean"] for o in obs]
        is_base = [int(o["date"][:4]) in base_years for o in obs]
        is_matched = [int(o["date"][5:7]) in matched for o in obs]

        for label, flag, color in (("baseline", True, "#4a6fa5"), ("current", False, "#2e7d32")):
            px = [x for x, f in zip(xs, is_base, strict=True) if f == flag]
            py = [y for y, f in zip(ys, is_base, strict=True) if f == flag]
            ax.scatter(px, py, c=color, s=28, label=label, zorder=3)
        # Ring the month-matched observations: these carry the delta.
        mx = [x for x, m in zip(xs, is_matched, strict=True) if m]
        my = [y for y, m in zip(ys, is_matched, strict=True) if m]
        if mx:
            ax.scatter(
                mx,
                my,
                s=110,
                facecolors="none",
                edgecolors="black",
                linewidths=1.2,
                label="month-matched",
                zorder=4,
            )

        b, d = packet.get("baseline", {}), packet.get("assessment_detail", {})
        if b.get("ndvi_median") is not None:
            ax.axhline(
                b["ndvi_median"],
                color="#4a6fa5",
                ls="--",
                lw=1,
                label=f"baseline median {b['ndvi_median']:.2f}",
            )
        if d.get("ndvi_median") is not None:
            ax.axhline(
                d["ndvi_median"],
                color="#2e7d32",
                ls="--",
                lw=1,
                label=f"current median {d['ndvi_median']:.2f}",
            )
        ax.set_ylim(-0.05, 1.0)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()

    delta = packet.get("assessment_detail", {}).get("delta_vs_baseline")
    d_txt = f"{delta:+.3f}" if delta is not None else "n/a"
    ax.set_title(
        f"{packet['site']['site_id']} — NDVI per scene (month-matched Δ {d_txt})", fontsize=11
    )
    ax.set_xlabel("scene date")
    ax.set_ylabel("NDVI (clear-pixel mean)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path
