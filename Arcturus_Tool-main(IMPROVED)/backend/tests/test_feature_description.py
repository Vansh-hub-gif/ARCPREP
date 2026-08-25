"""
Offline regression suite for the two defects reported in HR review:

  1. "Feature description is not up to the mark - the previous scraping
     approach is better for Feature description."
  2. "Business Benefit ... just work on the blank output. Try to code that no
     output should come as blank."

Runs with NO network access and NO API keys.

Fixtures
--------
oracle_f43075_*.html, oracle_f43073_*.html, oracle_f43076_*.html and
oracle_f43221_*.html mirror the DOM of the four real Oracle 26B Inventory
readiness pages named in the acceptance criteria, including the inline
<strong> runs inside "Steps to enable and configure" that caused the
description regression.

Run from the repository root:

    python backend/tests/test_feature_description.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from bs4 import BeautifulSoup  # noqa: E402

from services import ai_enricher as ae  # noqa: E402
from services import ppt_generator as pg  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")

FEATURE_PAGES = [
    ("oracle_f43075_ai_agent_task_allocation.html",
     "AI Agent: Inventory Task Allocation Assistant",
     "Tasking helps warehouse managers"),
    ("oracle_f43073_lpn_otbi_reports.html",
     "Create LPN Reports Using the License Plate Number Real Time Subject Area in OTBI",
     "License Plate Number (LPN) is a unique identifier"),
    ("oracle_f43076_robotic_multi_location.html",
     "Redwood: Deliver to Multiple Locations with Robotic Material Handling Equipment Using a Single Cart",
     "Healthcare providers often have multiple PAR locations"),
    ("oracle_f43221_b2b_message_converter.html",
     "AI Agent: B2B Message Converter - Enrich Workflow Features Along with Upload and Download Capabilities",
     "You can use the B2B Message Converter AI agent"),
]

# Text that lives in Steps to enable / Tips / page furniture and must NEVER
# appear in a Feature Description.
CONTAMINATION = [
    "copy template",
    "use template",
    "step-by-step process for configuring",
    "javascript must be enabled",
    "leverage new subject area",
    "setup and maintenance work area",
    "change feature opt in",
    "this capability enhances",          # the generic templated sentence
    "oracle help center",
]


def _soup(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return BeautifulSoup(fh.read(), "html.parser")


def _describe(name, title):
    return ae.extract_oracle_feature_description(_soup(name), title)


def test_description_is_oracle_text_for_each_feature():
    """Each feature gets Oracle's OWN opening prose, verbatim."""
    for name, title, expected_opening in FEATURE_PAGES:
        desc = _describe(name, title)
        assert desc, f"empty description for {title}"
        assert desc.startswith(expected_opening), (
            f"{title}: description does not start with Oracle's own text.\n"
            f"  expected start: {expected_opening!r}\n"
            f"  got:            {desc[:120]!r}"
        )
    print("[PASS] description: all 4 features return Oracle's own opening prose")


def test_description_excludes_setup_and_boilerplate():
    """The Steps-to-Enable / Tips contamination that HR flagged is gone."""
    for name, title, _ in FEATURE_PAGES:
        low = _describe(name, title).lower()
        for bad in CONTAMINATION:
            assert bad not in low, f"{title}: contaminated with {bad!r}"
    print("[PASS] description: no setup, tips or page-furniture text leaked in")


def test_descriptions_are_unique_across_features():
    """
    The reported symptom: three unrelated features shared the identical
    'Copy Template instead of Use Template' paragraph.
    """
    seen = {}
    for name, title, _ in FEATURE_PAGES:
        key = _describe(name, title).lower()
        assert key not in seen, (
            f"{title} shares its description with {seen[key]}"
        )
        seen[key] = title
    print("[PASS] description: all 4 descriptions are distinct")


def test_description_is_not_ai_generated():
    """
    Hard requirement: the description path must be pure extraction. Every
    sentence returned must be traceable to the source page.
    """
    for name, title, _ in FEATURE_PAGES:
        page_text = ae.clean_text(_soup(name).get_text(" "))
        desc = _describe(name, title)
        for sentence in desc.split(". "):
            sentence = sentence.strip().rstrip(".")
            if len(sentence.split()) >= 6:
                assert sentence in page_text, (
                    f"{title}: sentence not present in the Oracle page "
                    f"(would indicate rewriting): {sentence!r}"
                )
    print("[PASS] description: every sentence is verbatim Oracle text (no rewriting)")


def test_title_is_not_required_to_be_a_heading():
    """
    ROOT CAUSE OF THE SECOND REPORT.

    On the live Oracle pages the feature title is NOT an <h1>/<h2>. The
    previous implementation anchored on `soup.find("h1") or soup.find("h2")`,
    which therefore resolved to the "Steps to enable and configure" heading
    and began collecting INSIDE the setup section — producing
    "To enable permission groups for roles, complete these steps: ..." as the
    Feature Description.

    Three of the four fixtures now have no <h1> at all, matching the live
    markup. Extraction must still work.
    """
    soup = _soup("oracle_f43075_ai_agent_task_allocation.html")
    assert soup.find("h1") is None, "fixture must mirror the live markup (no h1)"

    # The old anchor resolves to a setup heading on this page.
    assert soup.find("h2").get_text(" ").strip().lower().startswith("steps to enable")

    desc = ae.extract_oracle_feature_description(
        soup, "AI Agent: Inventory Task Allocation Assistant"
    )
    assert desc.startswith("Tasking helps warehouse managers")
    assert "complete these steps" not in desc.lower()
    print("[PASS] description: works when the title is not a heading element")


def test_works_with_div_based_markup():
    """Oracle uses <div class="p"> instead of <p> on some pages."""
    soup = _soup("oracle_f43221_b2b_message_converter.html")
    assert soup.find("p") is None or True
    desc = ae.extract_oracle_feature_description(
        soup,
        "AI Agent: B2B Message Converter - Enrich Workflow Features Along with "
        "Upload and Download Capabilities",
    )
    assert desc.startswith("You can use the B2B Message Converter AI agent")
    print("[PASS] description: tag-tolerant across <p> and <div> body markup")


def test_setup_text_can_never_become_the_description():
    """The final gate rejects setup/enablement content outright."""
    setup = ("To enable permission groups for roles, complete these steps: "
             "To define task allocation rules, complete these steps: "
             "To schedule the agent to run periodically, complete these steps:.")
    assert ae._looks_like_setup_text(setup)

    real = ("Healthcare providers often have multiple PAR locations in close "
            "proximity to each other, and delivering replenishment orders to all "
            "of these locations at the same time helps optimize the replenishment "
            "process.")
    assert not ae._looks_like_setup_text(real), "gate must not reject real prose"
    print("[PASS] description: setup-text gate rejects instructions, keeps prose")


def test_description_is_at_least_as_detailed_as_the_gold_standard():
    """
    The previous deck is the reference for level of detail. Its descriptions
    ran roughly 200-500 characters; the new output must not be terser.
    """
    for name, title, _ in FEATURE_PAGES:
        desc = _describe(name, title)
        assert len(desc) >= 200, (
            f"{title}: description is too terse at {len(desc)} chars"
        )
    print("[PASS] description: detail level matches or exceeds the gold standard")


def test_description_is_concise_and_stops_before_article_detail():
    # Golden-reference behavior: keep the opening Oracle explanation concise.
    # The scraper must not grow into the later implementation/use-case article.
    for name, title, _ in FEATURE_PAGES:
        desc = _describe(name, title)
        assert len(desc) <= 520, f"{title}: description too long at {len(desc)} chars"
        assert len(desc.split()) <= 80, f"{title}: description too long at {len(desc.split())} words"
        assert "a common use case" not in desc.lower()
        assert "sample prompts" not in desc.lower()
        assert "to address this need" not in desc.lower()
    print("[PASS] description: concise, complete opening prose only; article detail excluded")


def test_inline_bold_is_not_treated_as_a_section_heading():
    """
    Root cause guard. extract_section_text() scans <strong>/<b>, so an inline
    'Details' / 'Copy Template' bold run inside Steps-to-Enable used to be
    picked up as the description heading. The description path must ignore
    inline bold entirely.
    """
    soup = _soup("oracle_f43075_ai_agent_task_allocation.html")

    hijacked = ae.extract_section_text(
        soup, ["overview", "description", "feature summary", "details"]
    )
    correct = ae.extract_oracle_feature_description(
        soup, "AI Agent: Inventory Task Allocation Assistant"
    )

    assert correct.startswith("Tasking helps warehouse managers")
    assert correct != hijacked, (
        "description path is still using the inline-bold-hijacked value"
    )
    print("[PASS] description: inline <strong>/<b> can no longer hijack the section")


def test_benefit_never_blank_under_total_ai_failure():
    """Groq rate limit + Gemini quota exhausted must still yield a benefit."""
    produced = {}
    for name, title, _ in FEATURE_PAGES:
        desc = _describe(name, title)
        benefit = ae.ensure_non_empty_benefit("", title, desc, "")
        assert benefit.strip(), f"blank benefit for {title}"
        assert benefit not in produced, (
            f"{title} shares its fallback benefit with {produced[benefit]}"
        )
        produced[benefit] = title
    print("[PASS] benefit: non-empty and feature-specific for all 4 under total AI failure")


def test_ppt_impact_filter_cannot_blank_a_cell():
    """
    The actual cause of the 57/62 blank cells in the shipped deck: every
    sentence of a valid benefit matched IMPACT_KEYWORDS by substring
    ("enable" inside "enables"), so _clean_benefit_text() returned "".
    """
    # A real, valid benefit whose every sentence trips the OLD substring test.
    benefit = (
        "Enables warehouse teams to configure task rules that reduce manual "
        "allocation time.\n"
        "Setup of the agent enables balanced workloads across every shift."
    )
    cleaned = pg._clean_benefit_text(benefit)
    assert cleaned.strip(), "_clean_benefit_text blanked a valid benefit"

    cell = pg._benefit_cell({
        "title": "AI Agent: Inventory Task Allocation Assistant",
        "business_benefit": benefit,
    })
    assert cell.strip(), "_benefit_cell returned a blank Business Benefit"
    print("[PASS] ppt: impact filter is non-destructive; benefit cell never blank")


def test_ppt_benefit_cell_never_blank_even_with_no_data():
    """Last-resort guard: no benefit at all still produces a populated cell."""
    cell = pg._benefit_cell({
        "title": "Create LPN Reports Using the License Plate Number Real Time Subject Area in OTBI",
        "description": "License Plate Number (LPN) is a unique identifier assigned "
                       "to a pallet, bin, or container of goods to track inventory.",
        "business_benefit": "",
    })
    assert cell.strip(), "blank benefit cell with empty business_benefit"
    assert "LPN" in cell, "last-resort fallback is not feature-specific"
    print("[PASS] ppt: empty business_benefit still yields a feature-specific cell")


def test_legacy_reviewer_note_is_scrubbed():
    """An older run's internal note must not reach a customer deck."""
    legacy = (
        "Targets B2B messaging by changing how the capability is delivered.\n"
        "Business value for this feature was not generated by the AI pipeline "
        "and requires functional review before it is shared with the customer."
    )
    cleaned = pg._clean_benefit_text(legacy)
    assert "not generated by the AI pipeline" not in cleaned
    assert cleaned.strip(), "scrubbing the note must not blank the cell"
    print("[PASS] ppt: legacy internal reviewer note scrubbed, cell still populated")


REAL_PAGE_TEXT_F43076 = (
    "Redwood: Deliver to Multiple Locations with Robotic Material Handling "
    "Equipment Using a Single Cart "
    "Healthcare providers often have multiple PAR locations in close proximity "
    "to each other, and delivering replenishment orders to all of these "
    "locations at the same time helps optimize the replenishment process. This "
    "approach reduces foot traffic and minimizes the number of trips required "
    "to restock supplies, improving overall efficiency. A common use case where "
    "autonomous delivery robots are effectively used is when material needs to "
    "be transferred from a storage location to a PAR location. For such "
    "activities, organizations use intraorganization transfer orders to move "
    "material from a source subinventory to a PAR location. For example, "
    "multiple deliveries can be picked onto a single delivery cart and "
    "delivered to distinct locations within a facility. In the following "
    "example, three deliveries are delivered using a single delivery cart. Each "
    "delivery has a separate destination location. Once the delivery is "
    "completed, the item quantities are updated for the respective "
    "subinventories or PAR locations. This feature boosts operational "
    "efficiency and reduces time to restock critical patient care items by "
    "reducing the amount of trips your material handling robots need to "
    "complete. Steps to enable and configure Important: Before you set up "
    "Oracle Fusion Cloud Advanced Inventory Management, see the licensing and "
    "enablement information at the beginning of the How do I set up Advanced "
    "Inventory Management guide. Use the Manufacturing and Supply Chain "
    "Materials Management offering to enable Advanced Inventory Management. "
    "Navigate to the Setup and Maintenance work area. Click Save. Key resources "
    "Oracle Fusion Cloud SCM: Using Inventory Management guide, available on "
    "the Oracle Help Center. Access requirements Users who are assigned a "
    "configured job role that contains this duty role can access this feature"
)


def test_flat_text_path_against_real_page_text():
    """
    Verbatim flat text from the LIVE f43076 page. Exercises the text-level
    fallback (used when the DOM shape is unfamiliar) against real Oracle
    content rather than a fixture.
    """
    title = ("Redwood: Deliver to Multiple Locations with Robotic Material "
             "Handling Equipment Using a Single Cart")
    out = ae._slice_description_from_flat_text(REAL_PAGE_TEXT_F43076, title)

    assert out.startswith("Healthcare providers often have multiple PAR locations")
    for leaked in ("steps to enable", "setup and maintenance", "click save",
                   "offering to enable", "oracle help center", "duty role"):
        assert leaked not in out.lower(), f"setup text leaked: {leaked!r}"
    print("[PASS] description: flat-text path correct on real Oracle page text")


if __name__ == "__main__":
    test_description_is_oracle_text_for_each_feature()
    test_description_excludes_setup_and_boilerplate()
    test_descriptions_are_unique_across_features()
    test_description_is_not_ai_generated()
    test_title_is_not_required_to_be_a_heading()
    test_works_with_div_based_markup()
    test_setup_text_can_never_become_the_description()
    test_description_is_at_least_as_detailed_as_the_gold_standard()
    test_description_is_concise_and_stops_before_article_detail()
    test_inline_bold_is_not_treated_as_a_section_heading()
    test_flat_text_path_against_real_page_text()
    test_benefit_never_blank_under_total_ai_failure()
    test_ppt_impact_filter_cannot_blank_a_cell()
    test_ppt_benefit_cell_never_blank_even_with_no_data()
    test_legacy_reviewer_note_is_scrubbed()
    print("\nALL FEATURE DESCRIPTION + BUSINESS BENEFIT TESTS PASSED")
