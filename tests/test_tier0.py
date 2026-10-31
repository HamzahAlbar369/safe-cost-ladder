"""Tier 0: language detection, empty reject, duplicate reuse, FAQ table (empty by default)."""

from engine.tier0 import Tier0, detect_language


def test_language_detection():
    assert detect_language("My car was hit at a red light.") == "en"
    assert detect_language("سيارتي تضررت في حادث، رقم الوثيقة OMI-1234567") == "ar"
    assert detect_language("12345 !!!") == "unknown"


def test_empty_duplicate_and_pass():
    t0 = Tier0()
    assert t0.check("a", "intent", "   \n").action == "reject_empty"
    assert t0.check("b", "intent", "Where is my payout?").action == "pass"
    dup = t0.check("c", "intent", "  where IS my   payout? ")
    assert dup.action == "duplicate" and dup.duplicate_of == "b"
    assert (
        t0.check("d", "faq", "Where is my payout?").action == "pass"
    )  # same text, other task: not a duplicate


def test_faq_table_is_empty_by_default_and_matches_whole_ticket_only():
    assert Tier0().check("a", "faq", "Is towing covered?").action == "pass"
    t0 = Tier0({"Is towing covered?": "yes"})
    hit = t0.check("a", "faq", "is towing  covered?")
    assert hit.action == "faq" and hit.faq_answer == "yes"
    assert t0.check("b", "faq", "Hi, is towing covered?").action == "pass"  # steps aside unless exact
