"""
Source-grounding tests for Business Benefit generation.

Reported regression: benefits were accurate-sounding but introduced claims
Oracle never made, e.g. for the delivery-cart feature —

    "Optimizes warehouse logistics by streamlining deliveries to multiple
     locations using robotic equipment, reducing labor costs and increasing
     throughput."

Oracle's documented outcome for that feature is fewer trips across the floor.
Labour cost and throughput are inventions.

Runs offline, no API keys required:

    python backend/tests/test_benefit_grounding.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from services import ai_enricher as ae  # noqa: E402

CART_SOURCE = (
    "Healthcare providers often have multiple PAR locations in close proximity to "
    "each other, and delivering replenishment orders to all of these locations at "
    "the same time helps optimize the replenishment process. This approach reduces "
    "foot traffic and minimizes the number of trips required to restock supplies, "
    "improving overall efficiency. Now, the robotic material handling integration "
    "can support this optimized workflow by delivering to multiple destinations in "
    "a single run using one cart. This feature boosts operational efficiency and "
    "reduces time to restock critical patient care items by reducing the amount of "
    "trips your material handling robots need to complete."
).lower()

LPN_SOURCE = (
    "License Plate Number (LPN) is a unique identifier assigned to a pallet, bin, or "
    "container of goods to track inventory. Using License Plate Number Real Time "
    "Subject Area in OTBI, you can now create personalized reports on your LPNs and "
    "analyze data pertaining to your documents and transactions. LPN-related measures "
    "and dimensions are now available in OTBI for reporting and analysis across "
    "inventory, receiving and shipping processes."
).lower()

TASK_SOURCE = (
    "Tasking helps warehouse managers ensure operators complete activities. "
    "Currently, task assignment depends on manual allocation by managers or "
    "self-assignment by operators. Manual assignment is often time-consuming and "
    "inefficient. The assistant automatically assigns open inventory tasks to "
    "qualified workers and helps balance workload across the warehouse by "
    "considering shift availability, worker capacity and task priorities."
).lower()

CART_TITLE = ("Redwood: Deliver to Multiple Locations with Robotic Material "
              "Handling Equipment Using a Single Cart")


def test_reported_regression_is_rejected():
    """The exact benefit from the report must not survive validation."""
    reported = ("Optimizes warehouse logistics by streamlining deliveries to multiple "
                "locations using robotic equipment, reducing labor costs and "
                "increasing throughput.")

    invented = ae.unsupported_claims(reported, CART_SOURCE)
    assert "labor cost" in " ".join(invented).lower()
    assert "throughput" in " ".join(invented).lower()

    accepted, reasons = ae.validate_benefit_lines(
        [reported], "", title=CART_TITLE, evidence_blob=CART_SOURCE
    )
    assert not accepted, "unsupported claims were accepted"
    assert "not supported" in reasons[0]
    print("[PASS] grounding: the reported labour-cost/throughput benefit is rejected")


def test_gold_standard_style_is_accepted():
    """The previous deck's wording must pass the stricter gate unchanged."""
    gold = ("Supports fewer trips and less material movement on the warehouse floor "
            "for the users and processes that depend on transfer order processing "
            "and manufacturing operations.")
    assert ae.unsupported_claims(gold, CART_SOURCE) == []
    print("[PASS] grounding: gold-standard wording passes the stricter gate")


def test_allowed_outcomes_are_feature_specific():
    """Each feature's allow-list reflects its own documented outcomes."""
    cart = ae.supported_outcomes({"benefit_source": CART_SOURCE}, CART_SOURCE, "")
    lpn = ae.supported_outcomes({"benefit_source": LPN_SOURCE}, LPN_SOURCE, "")
    task = ae.supported_outcomes({"benefit_source": TASK_SOURCE}, TASK_SOURCE, "")

    assert "fewer trips and less material movement" in cart
    assert "faster reporting and analysis" in lpn
    assert "more balanced workloads across the team" in task
    assert "less manual effort and intervention" in task

    # And each list excludes the others' outcomes.
    assert "faster reporting and analysis" not in cart
    assert "fewer trips and less material movement" not in lpn
    assert cart != lpn != task
    print("[PASS] grounding: allow-lists differ per feature and match the source")


def test_evidence_matching_is_word_bounded():
    """
    "rest" must not match inside "restock". Substring matching once qualified
    the delivery-cart feature for a B2B data-exchange outcome.
    """
    assert not ae._evidence_hit("rest", "trips required to restock supplies")
    assert ae._evidence_hit("restock*", "trips required to restock supplies")
    assert ae._evidence_hit("analyz*", "you can analyze the data")
    assert not ae._evidence_hit("cart", "cartons were received")

    cart = ae.supported_outcomes({"benefit_source": CART_SOURCE}, CART_SOURCE, "")
    assert "more reliable data exchange with partners and systems" not in cart
    print("[PASS] grounding: evidence matching is word-bounded, no false positives")


def test_title_restatement_is_rejected():
    """A benefit that just replays the title explains nothing."""
    restated = ("Delivers to multiple locations with robotic material handling "
                "equipment using a single cart, delivering material to multiple "
                "locations in one run.")
    assert ae._title_restatement_ratio(restated, CART_TITLE) >= 0.65
    accepted, reasons = ae.validate_benefit_lines(
        [restated], "", title=CART_TITLE, evidence_blob=CART_SOURCE
    )
    assert not accepted and "restates the feature title" in " ".join(reasons)
    print("[PASS] grounding: title restatement is rejected")


def test_supported_claims_still_pass():
    """Grounded claims must NOT be stripped — the gate is precise, not blunt."""
    grounded = ("Cuts the number of trips warehouse staff make across the floor by "
                "consolidating replenishment deliveries onto a single cart run.")
    assert ae.unsupported_claims(grounded, CART_SOURCE) == []

    # Compliance wording is only accepted when the source states the same
    # outcome; merely mentioning compliance is not evidence of reduced risk.
    tax_source = "this feature reduces compliance risk for fiscal document reporting."
    assert ae.unsupported_claims("Reduces compliance risk for tax reporting.",
                                 tax_source) == []
    # ...and is rejected when the source does not state that outcome.
    assert ae.unsupported_claims("Reduces compliance risk for tax reporting.",
                                 CART_SOURCE)
    print("[PASS] grounding: supported claims pass, unsupported ones are caught")


def test_fallback_outcome_is_grounded():
    """The deterministic fallback picks an outcome the source supports."""
    benefit = ae.generate_benefit_fallback(CART_TITLE, CART_SOURCE, CART_SOURCE)
    assert benefit.strip(), "fallback must never be empty"
    assert "trips" in benefit.lower() or "material movement" in benefit.lower()
    print("[PASS] grounding: deterministic fallback stays grounded and non-empty")


def test_benefit_repetition_guard():
    first = "Reduces repeated replenishment trips by consolidating deliveries to nearby locations into a single robotic cart run across the warehouse floor."
    second = "Reduces repeated replenishment trips by consolidating deliveries to nearby locations into a single robotic cart run across the warehouse floor."
    assert ae._benefit_similarity(first, second) >= 0.72
    assert ae._benefit_is_too_similar(second, [first]) == first
    print("[PASS] repetition guard: near-duplicate benefits are detected")


if __name__ == "__main__":
    test_reported_regression_is_rejected()
    test_gold_standard_style_is_accepted()
    test_allowed_outcomes_are_feature_specific()
    test_evidence_matching_is_word_bounded()
    test_title_restatement_is_rejected()
    test_supported_claims_still_pass()
    test_fallback_outcome_is_grounded()
    test_benefit_repetition_guard()
    print("\nALL BUSINESS BENEFIT GROUNDING TESTS PASSED")
