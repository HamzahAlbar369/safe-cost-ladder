"""Policy document rendering and rules loading (SPEC §4.1, D1.5)."""

from __future__ import annotations

import pytest
import yaml

from engine.datagen.render_policy import ar_count, output_path, render, render_all
from engine.datagen.rules import RULES_V1, load_raw, load_rules, load_version


def test_committed_policy_documents_match_a_fresh_render():
    # The document the models read must never drift from the rules that produce gold labels.
    for path, text in render_all().items():
        assert path.read_text(encoding="utf-8") == text, f"{path.name} is stale: run `engine policy`"


@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize("lang", ["en", "ar"])
def test_fiction_label_opens_and_closes_every_document(version, lang):
    rules = load_version(version)
    text = render(rules, lang)
    label = rules.fiction.label_ar if lang == "ar" else rules.fiction.label_en
    assert text.count(label) == 2
    assert text.index(label) < text.index("## ")
    assert "FICTIONAL" in text  # the English label is also in the Arabic document


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_every_parameter_value_appears_in_both_documents(version):
    rules = load_version(version)
    values = {**rules.params.model_dump(), **rules.faq_only.model_dump()}
    for lang in ("en", "ar"):
        text = render(rules, lang)
        for name, value in values.items():
            if name in ("currency", "rounding", "fault_shares"):
                continue
            shown = f"{value:,}" if value >= 1000 else str(value)
            assert shown in text, f"{version}/{lang}: {name}={value} not in document"


def test_every_enumeration_label_is_rendered():
    rules = load_rules()
    en, ar = render(rules, "en"), render(rules, "ar")
    for group in (
        rules.out_of_scope_perils,
        rules.violations,
        rules.required_documents,
        rules.late_report_justifications.accepted,
        rules.late_report_justifications.not_accepted,
    ):
        for label in group.values():
            assert label.en in en and label.ar in ar


def test_v2_changes_only_the_declared_values():
    v1, v2 = load_raw(RULES_V1), load_raw(RULES_V1.parent / "rules_v2.yaml")
    changed = {k for k in v1["params"] if v1["params"][k] != v2["params"][k]}
    assert changed == {"deductible_floor_sar", "reporting_window_days", "tpl_cap_sar"}
    for key in v1:
        if key not in ("params", "version"):
            assert v1[key] == v2[key], key
    assert v2["version"] == "v2"


def test_override_of_an_unknown_key_is_rejected(tmp_path):
    (tmp_path / "rules.yaml").write_text(RULES_V1.read_text(encoding="utf-8"), encoding="utf-8")
    bad = {"base": "rules.yaml", "version": "vX", "overrides": {"params": {"deductible_flor_sar": 1}}}
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        load_raw(tmp_path / "bad.yaml")


def test_rules_reject_a_non_standard_fault_share_set():
    raw = load_raw(RULES_V1)
    raw["params"]["fault_shares"] = [0, 50, 100]
    with pytest.raises(ValueError, match="fault_shares"):
        type(load_rules()).model_validate(raw)


@pytest.mark.parametrize(
    ("n", "noun", "expected"),
    [
        (1, "ar_day", "يوم واحد"),
        (2, "ar_day", "يومان"),
        (10, "ar_day", "10 أيام"),
        (15, "ar_day", "15 يومًا"),
        (3, "ar_workday", "3 أيام عمل"),
        (15, "ar_workday", "15 يوم عمل"),
        (24, "ar_hour", "24 ساعة"),
    ],
)
def test_arabic_counted_nouns_agree_with_the_number(n, noun, expected):
    assert ar_count(n, noun) == expected


def test_output_paths():
    assert output_path("v1", "ar").name == "policy_v1.ar.md"
