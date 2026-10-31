"""Report integrity (Phase 5 brief): every number on report.html is a data-metric span matching metrics.json,
no raw digits appear outside those spans, and the held-out numbers trace to the frozen run's own report."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from engine.llm.pricing import ROOT
from engine.report import collect as C
from engine.report.build import metrics_keys_on_page, render_html
from engine.report.render import fmt_value

METRICS = ROOT / "reports" / "metrics.json"
pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="reports/metrics.json not built")

# identifiers that contain digits but are not metrics: policy / check / decision names, SPEC refs, dates,
# version strings, figure-free tags
ALLOWED = [
    r"\b[BO][1-5]\b",  # policy names B1..B5, O1..O4
    r"\bV[0-3]\b",  # verifier names
    r"\bD\d+\.\d+\b",  # decision log refs
    r"§\s?\d+(\.\d+)*",  # SPEC section refs
    r"\b\d{4}-\d{2}-\d{2}\b",  # dates
    r"\b(floors|freeze)-v\d+\b",  # tags
    r"\bv\d+(\.\d+)*\b",  # version strings
    r"\b95% CIs?\b",  # the interval's name (the level is the method, not a result)
    r"\bp(50|95)\b",  # percentile names
    r"\bTier 0\b",  # layer name
]


class _Text(HTMLParser):
    """Visible text outside <script>/<style> and outside data-metric / data-prov spans."""

    def __init__(self):
        super().__init__()
        self.skip, self.depth, self.chunks = 0, [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        hide = tag in ("script", "style") or "data-metric" in a or "data-prov" in a
        self.depth.append(hide)
        self.skip += hide

    def handle_endtag(self, tag):
        if self.depth:
            self.skip -= self.depth.pop()

    def handle_data(self, data):
        if not self.skip:
            self.chunks.append(data)


@pytest.fixture(scope="module")
def page() -> tuple[dict, str]:
    m = C.load()
    return m, render_html(m)


def test_every_metric_span_matches_metrics_json(page):
    m, html = page
    spans = metrics_keys_on_page(html)
    assert len(spans) > 200
    for key, fmt, text in spans:
        expected = fmt_value(C.lookup(m, key), fmt)
        assert text.replace("&amp;", "&").replace("&#39;", "'") == expected, key


def test_no_raw_digits_outside_metric_spans(page):
    _, html = page
    p = _Text()
    p.feed(html)
    text = " ".join(p.chunks)
    for pat in ALLOWED:
        text = re.sub(pat, " ", text)
    offenders = re.findall(r".{0,30}\d.{0,30}", text)
    assert not offenders, offenders[:12]


def test_spec_labels_verbatim(page):
    _, html = page
    for label in ("Cost without caching (headline)", "Cost with caching (actual)", "simulated", "live"):
        assert label in html
    assert "FICTIONAL" in html
    assert "analysis added after observing shifted; it selects nothing from shifted" in html


def test_report_is_self_contained(page):
    _, html = page
    assert not re.search(r'<script[^>]+src=|<link[^>]+href="http', html)


def test_heldout_export_reproduces_the_frozen_report():
    """The export (D5.2) must give exactly the policy table of reports/final/heldout.txt."""
    m = C.load()
    txt = (ROOT / "reports" / "final" / "heldout.txt").read_text("utf-8")
    pols = m["splits"]["heldout"]["policies"]
    rows = {
        "B1": "B1:",
        "B2": "B2:",
        "B3": "B3:",
        "B4": "B4:",
        "B5": "B5:",
        "O1": "O1 (frozen)",
        "Oracle": "Oracle:",
    }
    for k, prefix in rows.items():
        line = next(x for x in txt.splitlines() if x.strip().startswith(prefix))
        acc, succ, p95, cn, cc = re.findall(r"\d+\.\d+", line.split(")")[-1] if "(" in line else line)[:5]
        e = pols[k]
        assert (f"{e['acc']:.3f}", f"{e['success']:.3f}", f"{e['p95_s']:.2f}") == (acc, succ, p95), k
        assert (f"{e['cpst_nocache']:.5f}", f"{e['cpst_cached']:.5f}") == (cn, cc), k
