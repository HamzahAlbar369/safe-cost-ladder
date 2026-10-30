"""Policy document rendering and rules loading (SPEC §4.1, D1.5)."""

from __future__ import annotations

import pytest
import yaml

from engine.datagen.render_policy import ar_count, output_path, render, render_all, render_sources
from engine.datagen.rules import INSURER_SPECIFIC, RULES_V1, SOURCE_RE, load_raw, load_rules, load_version


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
    values = {**rules.values().model_dump(), **rules.faq_values()}
    for lang in ("en", "ar"):
        text = render(rules, lang)
        for name, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or name.endswith("_faq"):
                continue
            shown = f"{value:,}" if value >= 1000 else str(value)
            assert shown in text, f"{version}/{lang}: {name}={value} not in document"


def test_every_enumeration_label_is_rendered():
    rules = load_rules()
    en, ar = render(rules, "en"), render(rules, "ar")
    for group in (
        rules.out_of_scope_perils,
        rules.exclusions.third_party_deny,
        rules.exclusions.third_party_recovery,
        rules.exclusions.own_damage_deny,
        rules.authorised_drivers,
        rules.required_documents,
        rules.late_report_justifications.accepted,
        rules.late_report_justifications.not_accepted,
    ):
        for label in group.values():
            assert label.en in en and label.ar in ar


def test_v2_changes_only_insurer_specific_values():
    v1, v2 = load_raw(RULES_V1), load_raw(RULES_V1.parent / "rules_v2.yaml")
    changed = {k for k in v1["params"] if v1["params"][k] != v2["params"][k]}
    assert changed == {"fixed_deductible_sar", "etl_pct", "reporting_window_days"}
    for k in changed:  # D1.8: regulatory values never change in the policy-change scenario
        assert v1["params"][k]["source"] == INSURER_SPECIFIC
        assert v2["params"][k]["source"] == INSURER_SPECIFIC
    for key in v1:
        if key not in ("params", "version"):
            assert v1[key] == v2[key], key
    assert v2["version"] == "v2"


def _sources(node, path=""):
    if isinstance(node, dict):
        if "source" in node and isinstance(node["source"], str):
            yield path, node["source"]
        for k, v in node.items():
            yield from _sources(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _sources(v, f"{path}[{i}]")


def test_every_rule_parameter_and_item_has_a_well_formed_source():
    raw = load_raw(RULES_V1)
    exempt = {"version", "instruments", "fiction", "reason_codes", "intents", "adversarial", "intents_source"}
    for section, node in raw.items():
        if section in exempt:
            continue
        if section == "document":
            items = [c for s in node["sections"] for c in s["clauses"]]
        elif section == "exclusions" or section == "late_report_justifications":
            items = [i for group in node.values() for i in group.values()]
        elif section in ("precedence",):
            items = node
        elif section == "formats":
            items = [node]
        else:
            items = list(node.values())
        assert items, section
        for item in items:
            assert SOURCE_RE.match(item.get("source", "")), f"{section}: {item}"
    assert sum(1 for _ in _sources(raw)) > 100


def test_sources_table_lists_every_engine_parameter():
    text = render_sources(load_version("v1"), load_version("v2"))
    rules = load_rules()
    for name in rules.params:
        assert f"`{name}`" in text
    assert "CMIR Art. 7.16" in text and "UP Art. 5" in text


@pytest.mark.parametrize(
    "source",
    [
        "UP Art. 5",
        "CMIR Art. 5.4.1, 5.4.7",
        "interpretation of CMIR Art. 5.4.2",
        "CSI (article TBC)",
        "insurer-specific (illustrative)",
        "reported, unverified",
    ],
)
def test_source_forms_accepted(source):
    assert SOURCE_RE.match(source)


@pytest.mark.parametrize("source", ["UP", "Art. 5", "CMIR Article 7", "made up", "interpretation of UP"])
def test_malformed_sources_rejected(source):
    assert not SOURCE_RE.match(source)


def test_override_of_an_unknown_key_is_rejected(tmp_path):
    (tmp_path / "rules.yaml").write_text(RULES_V1.read_text(encoding="utf-8"), encoding="utf-8")
    bad = {
        "base": "rules.yaml",
        "version": "vX",
        "overrides": {"params": {"deductible_flor_sar": {"value": 1}}},
    }
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        load_raw(tmp_path / "bad.yaml")


def test_rules_reject_a_non_standard_fault_share_set():
    raw = load_raw(RULES_V1)
    raw["params"]["fault_shares"]["value"] = [0, 50, 100]
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
