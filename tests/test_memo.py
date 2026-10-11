"""Tests for automated validation memo and triage register generation."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKETS = sorted((ROOT / "packets").glob("*.json"))


def test_memo_generation_unit():
    from ledger.memo import build_validation_memo

    # Load 5 sample packets
    sample_packets = [json.loads(p.read_text()) for p in PACKETS[:5]]
    memo = build_validation_memo(sample_packets, title="Pilot Validation Memo")

    assert "Reclamation Evidence" in memo
    assert "Pilot Validation Memo" in memo
    assert "Ranked Screening Register" in memo
    assert "Methodology & Provenance" in memo
    assert "Limits & Caveats" in memo
    assert "Walk First" in memo or "Monitor" in memo


def test_memo_cli_execution(tmp_path):
    out_file = tmp_path / "validation_memo.md"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "ledger.memo",
            "--packets",
            str(ROOT / "packets"),
            "--out",
            str(out_file),
            "--title",
            "99-Site Pilot Validation Memo",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )

    assert r.returncode == 0, r.stderr
    assert out_file.exists()
    content = out_file.read_text()
    assert "99-Site Pilot Validation Memo" in content
    assert "Total Sites Screened" in content
    assert "99" in content
