"""Regression checks for the verified Oracle 26B Business Benefit reference."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "benefit_reference_26b.json"
GENERIC = (
    "makes the relevant operational records easier to review and monitor",
    "gives users a clearer view of the specific process covered by the feature",
    "gives the responsible users more relevant information for evaluating the documented process",
    "gives the relevant team more direct access to the feature's reporting data",
    "within the process it was designed to support",
    "tied to the documented",
    "keeps using",
    "removes routine manual handling from the documented process",
    "reduces routine intervention in the documented process",
)
BANNED_OPENINGS = (
    "provides ", "supports ", "enables ", "allows ", "improves ",
    "enhances ", "optimizes ", "streamlines ", "this feature",
    "this capability", "this enhancement", "you can ",
)


def test_reference_has_62_features_and_two_specific_bullets_each():
    data = json.loads(REF.read_text(encoding="utf-8"))
    assert len(data) == 62
    for title, bullets in data.items():
        assert len(bullets) == 2, title
        for bullet in bullets:
            words = bullet.split()
            assert 14 <= len(words) <= 48, (title, len(words), bullet)
            low = bullet.lower()
            assert not any(p in low for p in GENERIC), (title, bullet)
            assert not low.startswith(BANNED_OPENINGS), (title, bullet)
            assert re.search(r"[.!?]$", bullet), (title, bullet)


def test_known_generic_website_templates_are_absent():
    data = json.loads(REF.read_text(encoding="utf-8"))
    joined = "\n".join("\n".join(v) for v in data.values()).lower()
    assert "makes the relevant operational records easier to review and monitor" not in joined
    assert "tied to the documented" not in joined
    assert "keeps using" not in joined


if __name__ == "__main__":
    test_reference_has_62_features_and_two_specific_bullets_each()
    test_known_generic_website_templates_are_absent()
    print("ALL VERIFIED 26B BENEFIT REFERENCE TESTS PASSED")
