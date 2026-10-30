"""Name-collision audit: the driver clash is structural, the held-out audit never exposes ids."""

from engine.datagen.audit_names import audit, format_audit


def test_audit_counts_and_heldout_ids_are_never_exposed():
    counts, ids = audit()
    for split in ("dev", "heldout", "shifted"):
        c = counts[split]
        assert (
            c["driver_shares_caller_name"] == c["driver_line"]
        )  # every driver phrase reuses the caller's name
        assert c["driver_visible_clash"] <= c["driver_line"] <= c["adjudicate"] <= c["n"]
        assert c["gold_unauthorised_driver"] <= c["gold_depends_on_driver"]
        assert c["claimant_visible_clash"] <= c["claimant_same_name"]
    assert ids["heldout"] == []
    assert "dev-0378" in ids["dev"]  # the caller / driver clash that fooled eight of nine configs
    report = format_audit(counts, ids)
    assert "heldout" in report and "heldout-" not in report
