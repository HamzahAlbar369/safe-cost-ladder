"""The ONE render helper: every number on the page is `m(key, fmt)` -> <span data-metric="key" data-fmt="fmt">.

`fmt_value` is shared with the figures (titles, labels) so a number reads the same in a chart and in the text.
tests/test_report.py re-formats every span's value from metrics.json and compares it with the span's text.
"""

from __future__ import annotations

from html import escape

from markupsafe import Markup

from engine.report.collect import lookup

FORMATS = ("raw", "usd5", "usd4", "usd2", "pct0", "pct1", "spct1", "f3", "f2", "s2", "s1", "int", "x1", "x2")


def fmt_value(v: float | int | str, fmt: str) -> str:
    if fmt == "raw":
        return str(v)
    if fmt == "usd5":
        return f"${v:.5f}"
    if fmt == "usd4":
        return f"${v:.4f}"
    if fmt == "usd2":
        return f"${v:,.2f}"
    if fmt == "pct0":
        return f"{v:.0%}"
    if fmt == "pct1":
        return f"{v:.1%}"
    if fmt == "spct1":
        return f"{v:+.1%}"
    if fmt == "f3":
        return f"{v:.3f}"
    if fmt == "f2":
        return f"{v:.2f}"
    if fmt == "s2":
        return f"{v:.2f} s"
    if fmt == "s1":
        return f"{v:.1f} s"
    if fmt == "int":
        return f"{int(v):,}"
    if fmt == "x1":
        return f"{v:.1f}×"
    if fmt == "x2":
        return f"{v:.2f}×"
    raise ValueError(f"unknown format {fmt}")


class Renderer:
    def __init__(self, metrics: dict):
        self.metrics = metrics

    def m(self, key: str, fmt: str) -> Markup:
        text = fmt_value(lookup(self.metrics, key), fmt)
        return Markup(f'<span class="num" data-metric="{escape(key)}" data-fmt="{fmt}">{escape(text)}</span>')

    def ci(self, key: str, fmt: str) -> Markup:
        """'[lo, hi]' for a metric whose bounds are stored as key_lo / key_hi."""
        return Markup(f'<span class="ci">[{self.m(key + "_lo", fmt)}, {self.m(key + "_hi", fmt)}]</span>')

    def title(self, segments: list) -> Markup:
        """A generated figure title: plain text segments escaped, (key, fmt) segments as metric spans."""
        return Markup("").join(escape(s) if isinstance(s, str) else self.m(*s) for s in segments)

    def v(self, key: str):
        """Raw value for template CONDITIONS only (never printed: printing must go through m())."""
        return lookup(self.metrics, key)

    @staticmethod
    def prov(text: str) -> Markup:
        """Provenance strings (run ids, SHAs, config hashes) are identifiers, not metrics."""
        return Markup(f'<span class="prov" data-prov>{escape(text)}</span>')
