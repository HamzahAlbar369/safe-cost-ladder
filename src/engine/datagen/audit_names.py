"""Name-collision audit (Phase 2 sign-off): how many tickets give two different people the same first name?

Two mechanisms exist in the generator (`datagen/templates/render.py`):
  * DRIVER lines: every phrase for a driver other than the policyholder ("my brother {name}", "a colleague
    {name}", "{name} from work", ...) fills `{name}` from the CALLER's own name slot, so the named driver
    always shares the caller's first name.
  * CLAIMANT: the other named person in a third-party claim is drawn independently from the same 20 names
    (`people()`), so it equals the caller's name with probability 1/20.
"Visible" means the caller's name also appears elsewhere in the ticket text (agent header, signature, "my
name is"), so a reader can see the clash. The audit regenerates every split in memory and records, per final
ticket text, what the renderer did; it changes no data. Held-out is audited in-process and reported as
counts only.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from engine.contracts import Ticket
from engine.datagen import gen as G
from engine.datagen.templates import render as R

UNAUTHORISED = "R5_OD_unauthorised_driver"


def _occurrences(name: str, text: str, lang: str) -> int:
    if lang == "ar":
        return text.count(name)
    return len(re.findall(rf"(?<!\w){re.escape(name)}(?!\w)", text))


@contextmanager
def _recording() -> Iterator[dict[str, dict[str, Any]]]:
    """Wrap the renderer so each rendered text is mapped to what happened while rendering it."""
    records: dict[str, dict[str, Any]] = {}
    driver_calls: list[bool] = []
    original_driver, original_render = R._driver_text, G.render_ticket

    def driver_text(fam, driver, slots, rng):
        out = original_driver(fam, driver, slots, rng)
        driver_calls.append(slots["name"] in out)  # the caller's own name inside the driver phrase
        return out

    def render_ticket(slot, content, fam, rng, rules):
        driver_calls.clear()
        text, gold, meta = original_render(slot, content, fam, rng, rules)
        names = R.NAMES_AR if fam.lang == "ar" else R.NAMES_EN
        p = content.people
        records[text] = {
            "caller": names[p["name_i"]],
            "claimant_same_draw": p["name_i"] == p["other_i"],
            "driver_phrase": bool(driver_calls),
            "driver_has_caller_name": any(driver_calls),
        }
        return text, gold, meta

    R._driver_text, G.render_ticket = driver_text, render_ticket
    try:
        yield records
    finally:
        R._driver_text, G.render_ticket = original_driver, original_render


def classify(t: Ticket, rec: dict[str, Any]) -> dict[str, bool]:
    case = t.meta.case
    visible = _occurrences(rec["caller"], t.text, t.language) >= 2
    driver_line = bool(rec["driver_phrase"])
    unauthorised = UNAUTHORISED in getattr(t.gold, "reasons", ())
    return {
        "driver_line": driver_line,
        "driver_shares_caller_name": driver_line and rec["driver_has_caller_name"],
        "driver_visible_clash": driver_line and rec["driver_has_caller_name"] and visible,
        # the gold label hinges on who was driving: denied for an unauthorised driver, or an authorised
        # non-insured driver whose recognition keeps the claim payable
        "gold_depends_on_driver": driver_line and case is not None and case.driver != "insured",
        "gold_unauthorised_driver": driver_line and unauthorised,
        "claimant_same_name": t.task_type == "adjudicate"
        and case is not None
        and case.claim_type == "third_party_claim"
        and rec["claimant_same_draw"],
        "claimant_visible_clash": t.task_type == "adjudicate"
        and case is not None
        and case.claim_type == "third_party_claim"
        and rec["claimant_same_draw"]
        and visible,
    }


def audit(seed: int | None = None) -> tuple[dict[str, Counter[str]], dict[str, list[str]]]:
    """Per-split counters, and the ids of flagged dev / shifted tickets (never held-out ids)."""
    with _recording() as records:
        splits = G.generate() if seed is None else G.generate(seed)
    counts: dict[str, Counter[str]] = {}
    ids: dict[str, list[str]] = {}
    for split, tickets in splits.items():
        c: Counter[str] = Counter(
            n=len(tickets), adjudicate=sum(t.task_type == "adjudicate" for t in tickets)
        )
        flagged: list[str] = []
        for t in tickets:
            flags = classify(t, records[t.text])
            c.update(k for k, v in flags.items() if v)
            c["gold_depends_and_visible_clash"] += (
                flags["gold_depends_on_driver"] and flags["driver_visible_clash"]
            )
            c["unauthorised_and_visible_clash"] += (
                flags["gold_unauthorised_driver"] and flags["driver_visible_clash"]
            )
            if flags["driver_visible_clash"] or flags["claimant_visible_clash"]:
                flagged.append(t.id)
        counts[split] = c
        ids[split] = flagged if split != "heldout" else []  # held-out: counts only
    return counts, ids


ROWS = (
    ("tickets", "n"),
    ("adjudicate tickets", "adjudicate"),
    ("tickets with a non-insured driver named", "driver_line"),
    ("  driver shares the caller's first name (by construction)", "driver_shares_caller_name"),
    ("  ... and the caller's name also appears elsewhere (visible clash)", "driver_visible_clash"),
    ("gold depends on who was driving (driver is not the policyholder)", "gold_depends_on_driver"),
    ("  ... of which gold = deny because the driver is unauthorised", "gold_unauthorised_driver"),
    ("  ... of which the clash is visible", "gold_depends_and_visible_clash"),
    ("  ... unauthorised-driver tickets with a visible clash", "unauthorised_and_visible_clash"),
    ("third-party claims where claimant and caller share a name (independent draw)", "claimant_same_name"),
    ("  ... and the clash is visible", "claimant_visible_clash"),
)


def format_audit(counts: dict[str, Counter[str]], ids: dict[str, list[str]]) -> str:
    splits = list(counts)
    lines = [f"{'':<80}" + "".join(f"{s:>10}" for s in splits)]
    for label, key in ROWS:
        lines.append(f"{label:<80}" + "".join(f"{counts[s][key]:>10}" for s in splits))
    lines += ["", "Held-out is reported as counts only; ticket ids are listed for dev and shifted."]
    for s in splits:
        if ids[s]:
            lines.append(f"{s} tickets with a visible clash ({len(ids[s])}): {', '.join(ids[s])}")
    return "\n".join(lines)
