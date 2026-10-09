"""Tests for the Reclamation Evidence corporate website."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"

EXPECTED_PAGES = [
    "index.html",
    "method.html",
    "evidence.html",
    "services.html",
    "about.html",
    "contact.html",
    "order.html",
    "projects.html",
]


def test_site_pages_and_links():
    assert SITE_DIR.is_dir(), "site/ directory must exist"
    for page in EXPECTED_PAGES:
        page_path = SITE_DIR / page
        assert page_path.exists(), f"Missing page: {page}"

    link_pattern = re.compile(r"href=[\"\x27]([^\":]+)[\"\x27]")
    for p in SITE_DIR.glob("*.html"):
        content = p.read_text(encoding="utf-8")
        links = link_pattern.findall(content)
        for l in links:
            if l.startswith("http") or l.startswith("mailto:") or l.startswith("#"):
                continue
            target = SITE_DIR / l
            assert target.exists(), f"Dead link in {p.name}: {l}"


def test_site_numbers_match_evidence_base():
    evidence_html = (SITE_DIR / "evidence.html").read_text(encoding="utf-8")
    assert "99" in evidence_html  # 99 analysis packets
    assert "13" in evidence_html  # 13 licensees
    assert "71" in evidence_html  # 71 detected
    assert "28" in evidence_html  # 28 identified

    services_html = (SITE_DIR / "services.html").read_text(encoding="utf-8")
    assert "$7,500 CAD" in services_html  # fixed pilot fee


def test_site_boundaries_and_limits_displayed():
    for page in ["index.html", "services.html"]:
        html = (SITE_DIR / page).read_text(encoding="utf-8")
        assert "No compliance or reclamation certification" in html
        assert "No contamination status" in html
