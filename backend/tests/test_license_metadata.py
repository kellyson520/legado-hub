from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_gpl_and_upstream_notice_are_present():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "GPL-3.0" in notice
    assert "2c340d48bb1b9537690ec31eb9c23a57307f30a3" in notice
