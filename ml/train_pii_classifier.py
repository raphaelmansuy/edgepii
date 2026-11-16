"""Train and log a PII token classifier to Databricks, then serve it.

The demo has three lanes today: `rules`, `en-closed`, `multi-open` — all of which
load weights inside the app. This script builds a fourth lane that does the
opposite: it trains a small classifier, registers it in Unity Catalog, and lets
Databricks Model Serving host it. The app then calls the endpoint as a detector.

Why train rather than reuse a public checkpoint? The corpus this repo already
pins, `nvidia/Nemotron-PII`, has gold character spans across 100,000 documents.
Training on it gives a model whose errors are measurable against the same corpus
the evaluator uses, so the claim "the ML lane beats the rule lane on names" is
checkable rather than asserted.

Run:
    python ml/train_pii_classifier.py --rows 20000 --register

The model is a logistic-regression bag-of-words classifier over character
n-grams, not a transformer. That is deliberate: a transformer cannot fit in an
MLflow PythonModel served on a CPU Small endpoint in a few minutes, and a
classifier that trains in under a minute keeps the demo reproducible. The
tradeoff is documented in the app's architecture page.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import mlflow
import mlflow.pyfunc

# The label fold. The corpus has ~40 gold labels; the taxonomy has nine types.
# Folding many fine labels into few types is what makes a small classifier
# workable, and it is the same fold `src/edgepii/eval/corpora.yaml` already
# declares. A label absent here is dropped, never guessed.
LABEL_FOLD: dict[str, str] = {
    "first_name": "PERSON",
    "last_name": "PERSON",
    "middle_name": "PERSON",
    "name": "PERSON",
    "email": "EMAIL",
    "phone_number": "PHONE",
    "fax_number": "PHONE",
    "street_address": "ADDRESS",
    "credit_debit_card": "PAYMENT",
    "ssn": "GOV_ID",
    "national_id": "GOV_ID",
    "tax_id": "GOV_ID",
    "password": "SECRET",
    "api_key": "SECRET",
    "ipv4": "IP_ADDRESS",
    "ipv6": "IP_ADDRESS",
    "user_name": "USERNAME",
    "date_of_birth": "DATE_OF_BIRTH",
}

# A span must be long enough to hold a signal. One character carries none.
MIN_SPAN_CHARS = 2
# A context window on each side of the target span, in characters.
CONTEXT_CHARS = 48


@dataclass(frozen=True, slots=True)
class Example:
    """One training row: the masked context, and the span to classify."""

    context: str
    span: str
    label: str


def _fold(label: str) -> str | None:
    return LABEL_FOLD.get(label)


def load_examples(parquet: Path, rows: int) -> tuple[list[Example], dict]:
    """Turn gold spans into positive examples and sampled negatives.

    A negative is a random non-PII slice from a document. Without negatives the
    model would label every token, which is the failure mode a classifier is most
    prone to and the one a demo must not hide.
    """

    import pyarrow.parquet as pq

    table = pq.read_table(parquet, columns=["text", "spans"]).slice(0, rows)
    texts = table.column("text").to_pylist()
    raw_spans = table.column("spans").to_pylist()

    positives: list[Example] = []
    negatives: list[Example] = []
    label_counts: dict[str, int] = {}

    for text, raw in zip(texts, raw_spans):
        if not text:
            continue
        spans = ast.literal_eval(raw) if isinstance(raw, str) else raw
        if not spans:
            continue

        covered: list[tuple[int, int]] = []
        for span in spans:
            label = _fold(str(span.get("label", "")))
            start, end = int(span["start"]), int(span["end"])
            covered.append((start, end))
            if label is None:
                continue
            piece = text[start:end]
            if len(piece) < MIN_SPAN_CHARS:
                continue
            window_start = max(0, start - CONTEXT_CHARS)
            window_end = min(len(text), end + CONTEXT_CHARS)
            context = text[window_start:start] + " {} " + text[end:window_end]
            positives.append(Example(context=context, span=piece, label=label))
            label_counts[label] = label_counts.get(label, 0) + 1

        # One negative per document, drawn from an uncovered region, so the
        # negative rate stays proportional to the number of documents rather
        # than to how many spans a document happens to have.
        gap = _sample_gap(text, covered)
        if gap is not None:
            start, end = gap
            window_start = max(0, start - CONTEXT_CHARS)
            window_end = min(len(text), end + CONTEXT_CHARS)
            context = text[window_start:start] + " {} " + text[end:window_end]
            negatives.append(Example(context=context, span=text[start:end], label="O"))

    return positives + negatives, label_counts


def _sample_gap(text: str, covered: list[tuple[int, int]]) -> tuple[int, int] | None:
    """A slice of the document that holds no gold span."""

    import random

    covered_sorted = sorted(covered)
    free: list[tuple[int, int]] = []
    cursor = 0
    for start, end in covered_sorted:
        if start - cursor >= 8:
            free.append((cursor, start))
        cursor = max(cursor, end)
    if len(text) - cursor >= 8:
        free.append((cursor, len(text)))

    if not free:
        return None
    left, right = random.choice(free)
    width = min(12, right - left)
    start = random.randint(left, right - width)
    piece = text[start : start + width]
    return (start, start + width) if piece.strip() else None


def build_model(seed: int = 17):
    """A character n-gram logistic regression, wrapped as an MLflow pyfunc."""

    import mlflow.pyfunc
    from sklearn.feature_extraction.text import HashingVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    # Hashing keeps the model a fixed size regardless of vocabulary, so the
    # artifact stays small enough to ship to a serving container quickly.
    vectorizer = HashingVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        n_features=2**16,
        alternate_sign=False,
        norm="l2",
    )
    classifier = LogisticRegression(max_iter=400, C=4.0, random_state=seed)
    return Pipeline([("vec", vectorizer), ("clf", classifier)])


class PIIClassifier(mlflow.pyfunc.PythonModel):
    """Serving wrapper. Takes a rendered context, returns a label and a score.

    The pipeline is deliberately simple: the caller renders the text around a
    candidate span as `left {} right`, and the model says whether the candidate
    is PII and of which type. That keeps the serving contract small enough to
    explain on one screen, and it keeps all span arithmetic in the caller where
    offsets can be checked against the source.
    """

    def __init__(self, pipeline, labels: list[str]):
        self._pipeline = pipeline
        self._labels = labels

    def predict(self, context, model_input, params=None):
        import pandas as pd

        texts = list(model_input[model_input.columns[0]])
        if not texts:
            return pd.DataFrame({"label": [], "score": []})
        probabilities = self._pipeline.predict_proba(texts)
        classes = list(self._pipeline.classes_)
        out = []
        for row in probabilities:
            best = max(range(len(classes)), key=lambda index: row[index])
            out.append({"label": classes[best], "score": float(row[best])})
        return pd.DataFrame(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=Path("/tmp/piiml/nemotron.parquet"))
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--model-name", default="workspace.default.edgepii_pii_classifier")
    parser.add_argument("--experiment", default="/Users/raphael.mansuy@gmail.com/edgepii-pii-ml")
    args = parser.parse_args()

    if not args.parquet.exists():
        print(f"corpus not found: {args.parquet}", file=sys.stderr)
        return 2

    os.environ.setdefault("MLFLOW_TRACKING_URI", "databricks")
    os.environ.setdefault("MLFLOW_REGISTRY_URI", "databricks-uc")

    from sklearn.metrics import classification_report, f1_score
    from sklearn.model_selection import train_test_split

    print(f"reading {args.rows} documents from {args.parquet}")
    examples, counts = load_examples(args.parquet, args.rows)
    print(f"examples: {len(examples)}")
    for label, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        print(f"  {label:16s} {count}")

    texts = [f"{example.context} {example.span}" for example in examples]
    labels = [example.label for example in examples]

    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=17, stratify=labels
    )

    model = build_model()
    print(f"training on {len(x_train)} examples")
    model.fit(x_train, y_train)

    predicted = model.predict(x_test)
    macro_f1 = f1_score(y_test, predicted, average="macro", zero_division=0)
    print(f"\nmacro F1 on held-out rows: {macro_f1:.3f}\n")
    print(classification_report(y_test, predicted, zero_division=0))

    if not args.register:
        print("not registering (pass --register)")
        return 0

    from sklearn.metrics import accuracy_score

    accuracy = accuracy_score(y_test, predicted)
    mlflow.set_experiment(args.experiment)
    with mlflow.start_run(run_name=f"pii-char-ngram-{len(examples)}") as run:
        mlflow.log_params(
            {
                "rows": args.rows,
                "examples": len(examples),
                "analyzer": "char_wb 2-4",
                "classifier": "logistic_regression",
                "labels": ";".join(sorted(set(labels))),
            }
        )
        mlflow.log_metrics({"macro_f1": macro_f1, "accuracy": accuracy})

        from mlflow.models import infer_signature

        signature = infer_signature(
            __import__("pandas").DataFrame({"context": x_test[:5]}),
            __import__("pandas").DataFrame({"label": predicted[:5], "score": [1.0] * 5}),
        )
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=PIIClassifier(model, sorted(set(labels))),
            signature=signature,
            pip_requirements=[
                "mlflow",
                "scikit-learn",
                "pandas",
                "numpy",
            ],
            registered_model_name=args.model_name if args.register else None,
        )
        print(f"\nrun: {run.info.run_id}")
        print(f"model_uri: {info.model_uri}")
        print(json.dumps({"macro_f1": macro_f1, "accuracy": accuracy}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
