"""Deterministic variation layer (SPEC §4.2 step 4, D1.2): typos, filler, sentence reordering, code-switching.

Never edits a token that contains a digit or overlaps a gold-relevant fact; the fact-preservation check
(SPEC §4.4) verifies this on every item. Light in dev/held-out, heavy in the shifted split.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from engine.datagen.templates import bank_ar as AR
from engine.datagen.templates import bank_en as EN
from engine.datagen.templates.render import Family, Rendered


@dataclass(frozen=True)
class Intensity:
    typo: float  # per eligible word
    filler: float  # per sentence
    reorder: float  # per item (movable middle sentences)
    codeswitch: float  # per item


LIGHT = Intensity(typo=0.015, filler=0.08, reorder=0.15, codeswitch=0.10)
HEAVY = Intensity(typo=0.05, filler=0.30, reorder=0.50, codeswitch=0.60)

_WORD = re.compile(r"^[^\W\d_]{7,}$")


def _typo(word: str, rng: random.Random) -> str:
    i = rng.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2 :]


def _protected(token: str, facts: list[str]) -> bool:
    return any(ch.isdigit() for ch in token) or any(token.strip(".,;:!?") in f or f in token for f in facts)


def _typos(sentence: str, rng: random.Random, p: float, facts: list[str]) -> str:
    out = []
    for tok in sentence.split(" "):
        core = tok.strip(".,;:!?()،؟")
        if _WORD.match(core) and not _protected(tok, facts) and rng.random() < p:
            tok = tok.replace(core, _typo(core, rng))
        out.append(tok)
    return " ".join(out)


def _codeswitch(sentences: list[str], fam: Family, rng: random.Random, last_only: bool) -> list[str]:
    if fam.lang == "ar":
        swapped = []
        for s in sentences:
            for ar_word, en_word in AR.CODESWITCH.items():
                if ar_word in s and rng.random() < 0.5:
                    s = s.replace(ar_word, en_word, 1)
            swapped.append(s)
        return swapped
    i = len(sentences) - 1 if last_only else rng.randrange(len(sentences))  # never inside a form field
    out = list(sentences)
    stem = out[i].rstrip(".?!")
    end = out[i][len(stem) :] or "."
    out[i] = stem + ", " + rng.choice(EN.CODESWITCH_APPEND) + end
    return out


def _fillers(fam: Family) -> list[str]:
    return EN.FILLER if fam.lang == "en" else AR.FILLER["saudi" if fam.register == "saudi" else "msa"]


def apply(r: Rendered, fam: Family, rng: random.Random, inten: Intensity) -> str:
    body = list(r.sentences)
    if r.movable and len(body) > 3 and rng.random() < inten.reorder:
        middle = body[1:]
        rng.shuffle(middle)
        body = [body[0], *middle]
    if body and rng.random() < inten.codeswitch:
        body = _codeswitch(body, fam, rng, last_only=fam.mode in ("form", "bullets"))
    fillers = _fillers(fam)
    out = []
    for s in body:
        if fam.mode == "prose" and rng.random() < inten.filler:
            f = rng.choice(fillers)
            keep = fam.lang == "ar" or s.startswith(("I ", "I'"))
            s = f"{f} {s if keep else s[0].lower() + s[1:]}"
        out.append(_typos(s, rng, inten.typo, r.facts))
    text = r.joiner.join(out)
    return "\n".join([*r.head, text, *r.tail]).strip()
