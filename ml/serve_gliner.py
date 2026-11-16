"""Package a pretrained GLiNER PII model as an MLflow pyfunc and serve it.

Why GLiNER rather than a model trained here: the repo already measured it. On
`gretel-finance-en` (50 docs), `multi-open` — the GLiNER2 lane — scored 0.821
exact recall and 0.901 containment with zero high-severity misses. A
character-n-gram classifier trained from scratch on the same corpus reached
0.763 macro F1 and cannot see a name it was not shown a prefix of. Pretrained
wins on both quality and effort, so this is the lane that ships.

The serving contract is deliberately narrow:

    input   {"inputs": ["<text>", ...]}
    output  {"predictions": [[{label, start, end, text, score}, ...], ...]}

One text in, one list of spans out, with offsets indexed into that text. All the
translation into `edgepii`'s taxonomy and all the slice checks happen in the app,
where a span can be compared against the source it came from.

Run:
    python ml/serve_gliner.py --register          # log + register the model
    python ml/serve_gliner.py --register --endpoint edgepii-pii-ml
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# The labels GLiNER is asked for, and the taxonomy type each maps to. This is
# the boundary between an open-label model and a closed taxonomy: the model
# answers in words, and this table decides which words the library accepts.
# A label missing here is dropped rather than guessed.
GLINER_LABELS: dict[str, str] = {
    "person": "PERSON",
    "email": "EMAIL",
    "phone number": "PHONE",
    "credit card number": "PAYMENT",
    "iban": "PAYMENT",
    "bank account number": "PAYMENT",
    "social security number": "GOV_ID",
    "government id": "GOV_ID",
    "passport number": "GOV_ID",
    "ip address": "IP_ADDRESS",
    "username": "USERNAME",
    "password": "SECRET",
    "api key": "SECRET",
    "street address": "ADDRESS",
    "date of birth": "DATE_OF_BIRTH",
}

MODEL_ID = "nvidia/gliner-PII"
# Pinned. A moving revision would change what an old score means.
MODEL_REVISION = "bd23e8ef4425fd04e34c5204ab49ffaa706eae79"
# The checkpoint's own default is 0.5. 0.4 trades a little precision for recall,
# which is the right direction when a miss means a value leaves unmasked.
DEFAULT_THRESHOLD = 0.4


def _load():
    from gliner import GLiNER

    return GLiNER.from_pretrained(MODEL_ID, revision=MODEL_REVISION)


def _entities(model, text: str, threshold: float) -> list[dict]:
    """Run one text and return spans the app can trust.

    Two guards here, both cheap and both load-bearing:

    1. The slice check. The model returns offsets; if `text[start:end]` is not
       what it claims, the span is dropped rather than repaired. The library
       enforces the same rule, so a bad offset must not survive this far.
    2. The label fold. A label outside `GLINER_LABELS` is dropped, so the model
       cannot invent a type the taxonomy has no policy for.
    """

    labels = list(GLINER_LABELS)
    out: list[dict] = []
    for entity in model.predict_entities(text, labels, threshold=threshold):
        start, end = int(entity["start"]), int(entity["end"])
        piece = text[start:end]
        if not piece or piece != entity.get("text", piece):
            continue
        folded = GLINER_LABELS.get(str(entity["label"]).strip().lower())
        if folded is None:
            continue
        out.append(
            {
                "label": folded,
                "raw_label": str(entity["label"]),
                "start": start,
                "end": end,
                "text": piece,
                "score": round(float(entity["score"]), 6),
            }
        )
    # Longest first, then earliest, so a client can drop overlaps predictably.
    out.sort(key=lambda row: (row["start"], -row["end"]))
    return out


def _pyfunc_class():
    import mlflow.pyfunc

    class GlinerPII(mlflow.pyfunc.PythonModel):
        """A thin pyfunc around GLiNER. No library import at module scope."""

        def __init__(self, threshold: float = DEFAULT_THRESHOLD):
            self._threshold = threshold
            self._model = None

        def load_context(self, context) -> None:
            # Load at serving start, not at import, so logging the model does not
            # pull 200 MB into the training process.
            self._model = _load()

        def predict(self, context, model_input, params=None):
            import pandas as pd

            column = model_input.columns[0]
            threshold = self._threshold
            if params and "threshold" in params:
                threshold = float(params["threshold"])
            texts = list(model_input[column])
            predictions = [_entities(self._model, str(t), threshold) for t in texts]
            return pd.DataFrame({"predictions": predictions})

    return GlinerPII


def _log_model(model_name: str, experiment: str, threshold: float) -> str:
    import mlflow
    from mlflow.models import infer_signature

    os.environ.setdefault("MLFLOW_TRACKING_URI", "databricks")
    os.environ.setdefault("MLFLOW_REGISTRY_URI", "databricks-uc")

    import pandas as pd

    GlinerPII = _pyfunc_class()
    mlflow.set_experiment(experiment)

    sample = pd.DataFrame({"text": ["Ada Lovelace emailed ada@example.com."]})
    signature = infer_signature(
        sample, pd.DataFrame({"predictions": [["placeholder"]]})
    )

    with mlflow.start_run(run_name="gliner-pii-pretrained") as run:
        mlflow.log_params(
            {
                "base_model": MODEL_ID,
                "revision": MODEL_REVISION,
                "threshold": threshold,
                "labels": ";".join(sorted(GLINER_LABELS)),
                "source": "pretrained",
            }
        )
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=GlinerPII(threshold=threshold),
            signature=signature,
            pip_requirements=[
                "mlflow",
                "gliner>=0.2.30",
                "torch",
                "transformers",
                "pandas",
                "numpy",
            ],
            registered_model_name=model_name,
        )
        print(f"run: {run.info.run_id}")
        print(f"model_uri: {info.model_uri}")
        return info.model_uri


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--local-check", action="store_true", help="run once here")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--model-name", default="workspace.default.edgepii_pii_gliner"
    )
    parser.add_argument(
        "--experiment", default="/Users/raphael.mansuy@gmail.com/edgepii-pii-ml"
    )
    args = parser.parse_args()

    if args.local_check:
        model = _load()
        text = "Ada Lovelace called from +852 5555 0101. Email ada@example.com."
        print(json.dumps(_entities(model, text, args.threshold), indent=2))
        return 0

    if not args.register:
        print("nothing to do: pass --register or --local-check", file=sys.stderr)
        return 2

    uri = _log_model(args.model_name, args.experiment, args.threshold)
    print(json.dumps({"model_uri": uri, "model_name": args.model_name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
