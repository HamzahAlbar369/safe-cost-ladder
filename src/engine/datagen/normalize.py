"""Text normalisation (SPEC §3.1): Arabic-Indic digits → ASCII, thousands separators stripped, dates → ISO,
case/whitespace folded. Used by the fact-preservation check and, in Phase 2, by the graders.

Dates are read day-first (DD/MM/YYYY), the Saudi convention; YYYY-first forms are read as Y/M/D.
"""

from __future__ import annotations

import re
from datetime import date

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
EN_MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
AR_MONTHS = [
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
]
_MONTH = {m: i + 1 for i, m in enumerate(EN_MONTHS)} | {m[:3]: i + 1 for i, m in enumerate(EN_MONTHS)}
_MONTH |= {m: i + 1 for i, m in enumerate(AR_MONTHS)}
_MONTH_RE = "|".join(sorted(_MONTH, key=len, reverse=True))


def _iso(y: str, m: str, d: str) -> str | None:
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def _sub_date(match: re.Match[str]) -> str:
    g = match.groupdict()
    month = g["m"] if g["m"].isdigit() else str(_MONTH[g["m"].lower()])
    iso = _iso(g["y"], month, g["d"])
    return iso if iso else match.group(0)


_YMD = re.compile(r"(?<!\d)(?P<y>\d{4})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})(?!\d)")
_DMY = re.compile(r"(?<!\d)(?P<d>\d{1,2})[-/.](?P<m>\d{1,2})[-/.](?P<y>\d{4})(?!\d)")
_DMONY = re.compile(
    rf"(?<!\d)(?P<d>\d{{1,2}})\s+(?P<m>{_MONTH_RE})\.?,?\s+(?P<y>\d{{4}})(?!\d)", re.IGNORECASE
)


def ascii_digits(text: str) -> str:
    return text.translate(_DIGITS)


def normalise(text: str) -> str:
    t = ascii_digits(text).replace("٬", ",").replace("٫", ".").replace("٪", "%")
    t = _YMD.sub(_sub_date, t)
    t = _DMY.sub(_sub_date, t)
    t = _DMONY.sub(_sub_date, t)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)  # thousands separators
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)  # second pass for millions
    return re.sub(r"\s+", " ", t).strip().casefold()


def fact_present(fact: str, text_normalised: str) -> bool:
    return normalise(fact) in text_normalised
