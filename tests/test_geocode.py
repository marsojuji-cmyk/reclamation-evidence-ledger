"""Geocoding verification: grid geometry + the published defect.

`ledger.sites.dls_to_latlon` turns Dominion Land Survey names into
coordinates. NEGATIVE-RESULT-2026-10-09.md publishes the diagnosis: across
20,000 wells the median error is 2,658 m and 0.0% fall inside the function's
formerly documented +/-300 m. Screening work stopped on 2026-10-09 on that
finding.

This module pins what CAN be verified today: the grid arithmetic is
self-consistent (LSD spacing, township/range steps, boustrophedon parity),
so any future fix must preserve the geometry while correcting whatever
convention assumption the diagnosis found. The accuracy claim itself is an
xfail work order: it stays visibly failing until the function is verified
against independent ground truth. Survey math is not fixed by intuition —
that is how the bug got here.
"""

import math

import pytest

from ledger.sites import dls_to_latlon, parse_dls


def _hav_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 2 * 6371000 * math.asin(math.sqrt(h))


def test_parse_dls_components():
    assert parse_dls("01-06-018-26W4 (100)") == (1, 6, 18, 26, "4")
    assert parse_dls("13-17-019-27W4 (100)") == (13, 17, 19, 27, "4")
    assert parse_dls("not a dls name") is None


def test_adjacent_lsds_are_quarter_mile_apart():
    a = dls_to_latlon(1, 1, 1, 1, "4")
    b = dls_to_latlon(2, 1, 1, 1, "4")
    assert _hav_m(a, b) == pytest.approx(402.336, abs=2.0)


def test_township_step_is_six_miles():
    a = dls_to_latlon(1, 1, 1, 1, "4")
    b = dls_to_latlon(1, 1, 2, 1, "4")
    assert _hav_m(a, b) == pytest.approx(9656.06, abs=30.0)


def test_range_step_is_six_miles():
    a = dls_to_latlon(1, 1, 18, 26, "4")
    b = dls_to_latlon(1, 1, 18, 27, "4")
    assert _hav_m(a, b) == pytest.approx(9656.06, abs=60.0)


def test_section_boustrophedon_parity():
    # Row 0 runs east->west: section 1 (SE corner) sits east of section 6.
    s1 = dls_to_latlon(1, 1, 18, 26, "4")
    s6 = dls_to_latlon(1, 6, 18, 26, "4")
    assert s1[1] > s6[1]
    # Row 1 runs west->east: section 7 sits one statute mile north of
    # section 6, in the same column.
    s7 = dls_to_latlon(1, 7, 18, 26, "4")
    assert s7[0] == pytest.approx(s6[0] + 1 / 69.0)
    # Same column: longitudes agree within the function's latitude-dependent
    # scaling approximation (range offsets are statute miles at the site's
    # latitude, so one row north shifts ~75 m here — noted, not asserted
    # exact; the published defect is 2,658 m, two orders up).
    assert abs(s7[1] - s6[1]) < 0.002


@pytest.mark.xfail(
    strict=False,
    reason="NEGATIVE-RESULT-2026-10-09: median error 2,658 m on 20,000 wells, "
    "0.0% inside the documented +/-300 m. Fixing requires independent "
    "ground-truth coordinates — do not adjust the formula by intuition.",
)
def test_geocode_accuracy_against_ground_truth():
    """Work order, not a passing test. Register independently verified
    (DLS name -> lat/lon) pairs in GROUND_TRUTH and remove the xfail marker
    when the function verifies against them."""
    GROUND_TRUTH: list[tuple[str, float, float]] = [
        # ("01-06-018-26W4", <lat>, <lon>),  # TODO: verified coordinates
    ]
    assert GROUND_TRUTH, "no ground-truth pairs registered yet"
    for name, lat, lon in GROUND_TRUTH:
        parsed = parse_dls(name)
        assert parsed is not None, name
        got = dls_to_latlon(*parsed)
        assert _hav_m(got, (lat, lon)) <= 300.0, name
