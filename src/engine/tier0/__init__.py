"""Tier 0 (SPEC §6.1 step 1): no model, no cost. Steps aside on any ambiguity.

- language detection (share of Arabic letters among letters);
- empty ticket -> rejected without a model call (a failed task, cost 0);
- exact duplicate (same normalised text already answered in this stream) -> the earlier answer is reused;
- FAQ lookup: the whole normalised ticket equals a key of an operator-curated FAQ table. The table is empty by
  default: none exists for the fictional insurer, and filling it from the data generator's phrase bank would
  leak the templates into the policy.

The regex policy-number shortcut from SPEC §6.1 is not built: no task's output is a policy number alone
(extract needs every field), so it could never answer a ticket by itself.
"""

from __future__ import annotations

import re
import unicodedata

from engine.contracts import Frozen

_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
_LETTER = re.compile(r"[^\W\d_]")


def detect_language(text: str) -> str:
    letters = _LETTER.findall(text)
    if not letters:
        return "unknown"
    return "ar" if sum(bool(_ARABIC.match(c)) for c in letters) / len(letters) >= 0.5 else "en"


def normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class Tier0Result(Frozen):
    language: str
    action: str  # "pass" | "reject_empty" | "duplicate" | "faq"
    duplicate_of: str | None = None
    faq_answer: str | int | None = None


class Tier0:
    def __init__(self, faq_table: dict[str, str | int] | None = None):
        self.faq_table = {normalise(k): v for k, v in (faq_table or {}).items()}
        self._seen: dict[tuple[str, str], str] = {}  # (task, normalised text) -> first ticket id

    def check(self, ticket_id: str, task: str, text: str) -> Tier0Result:
        lang = detect_language(text)
        key = normalise(text)
        if not key:
            return Tier0Result(language=lang, action="reject_empty")
        if (task, key) in self._seen:
            return Tier0Result(language=lang, action="duplicate", duplicate_of=self._seen[(task, key)])
        self._seen[(task, key)] = ticket_id
        if task == "faq" and key in self.faq_table:
            return Tier0Result(language=lang, action="faq", faq_answer=self.faq_table[key])
        return Tier0Result(language=lang, action="pass")
