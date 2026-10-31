"""Local router (SPEC §6.4): TF-IDF char 2-5-grams + simple features -> logistic regression, 5-fold out-of-fold.

Where it can act: on faq / intent / extract, O1 already starts at the cheapest config meeting the floor, so a
router has nothing cheaper to choose. On adjudicate, O1 always pays for the haiku-low || haiku-medium pair and
escalates ~6% of tickets to opus-low after waiting for them. The router predicts "O1 will escalate this ticket";
when confident (p >= threshold) the ticket goes straight to opus-low, skipping the pair and its wait. Otherwise
the normal O1 path runs (SPEC §6.1 step 2: unsure -> cascade).

Labels come from replaying O1 on dev; predictions used for evaluation are out-of-fold only.
"""

from __future__ import annotations

import re

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from engine.contracts import Ticket
from engine.tier0 import detect_language

FOLDS = 5
SEED = 20261030
_AMOUNT = re.compile(r"\d[\d,٬]*(?:\.\d+)?")
_DATE = re.compile(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\b\d{1,2}\s+[A-Za-z؀-ۿ]{3,}\s+\d{4}")


def dense_features(t: Ticket) -> list[float]:
    text = t.text
    return [
        np.log1p(len(text)),
        float(detect_language(text) == "ar"),
        np.log1p(sum(ch.isdigit() for ch in text)),
        float(len(_AMOUNT.findall(text))),
        float(len(_DATE.findall(text))),
    ]


def _fit_predict(train: list[Ticket], y: np.ndarray, test: list[Ticket]) -> np.ndarray:
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
    xt = vec.fit_transform([t.text for t in train])
    dense_train = np.array([dense_features(t) for t in train])
    mu, sd = dense_train.mean(0), dense_train.std(0) + 1e-9
    x_train = hstack([xt, csr_matrix((dense_train - mu) / sd)]).tocsr()
    x_test = hstack(
        [
            vec.transform([t.text for t in test]),
            csr_matrix((np.array([dense_features(t) for t in test]) - mu) / sd),
        ]
    ).tocsr()
    clf = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0)
    clf.fit(x_train, y)
    return clf.predict_proba(x_test)[:, 1]


def out_of_fold(tickets: list[Ticket], labels: list[bool]) -> dict[str, float]:
    """P(label) per ticket id, each predicted by a model that never saw that ticket."""
    y = np.array(labels, dtype=int)
    folds = min(FOLDS, int(y.sum()), int(len(y) - y.sum()))
    if folds < 2:
        raise ValueError("too few positive or negative examples for cross-validation")
    probs = np.zeros(len(tickets))
    for train_idx, test_idx in StratifiedKFold(folds, shuffle=True, random_state=SEED).split(
        np.zeros(len(y)), y
    ):
        probs[test_idx] = _fit_predict(
            [tickets[i] for i in train_idx], y[train_idx], [tickets[i] for i in test_idx]
        )
    return {t.id: float(p) for t, p in zip(tickets, probs, strict=True)}
