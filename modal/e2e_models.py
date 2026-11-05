"""Model-lane examples. Run with: modal run modal/e2e_models.py"""

import os
import modal

app = modal.App("edgepii-model-e2e")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch>=2.2", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install(
        "phonenumbers>=8.13",
        "pyyaml>=6",
        "transformers>=5.22.1,<6",
        "gliner2[local]==2.1.0",
    )
    .add_local_dir("src/edgepii", remote_path="/root/edgepii", copy=True)
)


@app.function(
    image=image,
    timeout=1800,
    cpu=4,
    memory=16384,
    secrets=[modal.Secret.from_local_environ(["HF_TOKEN"])] if os.getenv("HF_TOKEN") else [],
)
def run_model_examples() -> dict:
    import gc
    import sys

    sys.path.insert(0, "/root")
    from edgepii import Locator, redact

    report: dict = {}

    note = (
        "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
        "about ticket 77. Do not include the password hunter2 in the note."
    )
    report["en-closed"] = _closed(note, Locator, redact)
    gc.collect()

    mail = "Write to ada@example.com or to Ada Lovelace in Lisbon."
    report["multi-open"] = _open(mail, Locator)
    gc.collect()

    control_source = "Email ada@example.com about order 48291."
    report["en-bert"] = _bert(control_source, Locator)
    return report


def _closed(note: str, locator_cls, redact) -> dict:
    try:
        closed = locator_cls.preset("en-closed", device="cpu")
        closed_result = closed.locate(note)
        masked, vault = redact(note, closed_result.spans)
        people = [span.text for span in closed_result.spans if span.type == "PERSON"]
        return {
            "revision": closed.revision,
            "spans": [_row(note, span) for span in closed_result.spans],
            "email_masked": "ada@example.com" not in masked,
            "secret_masked": "hunter2" not in masked,
            "secret_not_in_vault": "hunter2" not in vault.values(),
            "ticket_kept": "ticket 77" in masked,
            "person_ada": "Ada Lovelace" in people,
            "model_spans": _model_count(closed_result.spans, "hf."),
        }
    except Exception as exc:
        return {"error": _err(exc)}


def _open(mail: str, locator_cls) -> dict:
    try:
        opened = locator_cls.preset("multi-open", device="cpu")
        opened_result = opened.locate(mail, types=["EMAIL"])
        from edgepii.labelmap import load_taxonomy

        labels = load_taxonomy().raw_labels_for(["EMAIL"])
        model_hits = opened._detectors[-1].locate(mail, labels)
        model_email = any(mail[hit.start : hit.end] == "ada@example.com" for hit in model_hits)
        return {
            "revision": opened.revision,
            "types": sorted({span.type for span in opened_result.spans}),
            "email": any(span.text == "ada@example.com" for span in opened_result.spans),
            "model_email": model_email,
            "spans": [_row(mail, span) for span in opened_result.spans],
            "model_spans": _model_count(opened_result.spans, "gliner2."),
        }
    except Exception as exc:
        return {"error": _err(exc)}


def _bert(source: str, locator_cls) -> dict:
    try:
        control = locator_cls.preset("en-bert", device="cpu")
        control_result = control.locate(source, types=["EMAIL"])
        return {
            "revision": control.revision,
            "email": any(span.text == "ada@example.com" for span in control_result.spans),
            "spans": [_row(source, span) for span in control_result.spans],
            "model_spans": _model_count(control_result.spans, "hf."),
        }
    except Exception as exc:
        text = _err(exc)
        gated = "gated" in text.casefold() or "403" in text
        return {"error": text, "gated": gated}


def _model_count(spans, prefix: str) -> int:
    return sum(1 for span in spans if span.detector_id.startswith(prefix))


def _err(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    while current is not None and len(parts) < 4:
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__
    return " | ".join(parts)[:800]


def _row(source: str, span) -> dict:
    return {
        "type": span.type,
        "start": span.start,
        "end": span.end,
        "text": span.text,
        "score": span.score,
        "detector_id": span.detector_id,
        "slice_ok": source[span.start : span.end] == span.text,
    }


@app.local_entrypoint()
def main() -> None:
    report = run_model_examples.remote()
    _require(report)


def _require(report: dict) -> None:
    closed = report["en-closed"]
    if closed.get("error") or not closed.get("email_masked") or not closed.get("secret_masked"):
        raise SystemExit(f"en-closed failed: {closed}")
    if not closed["secret_not_in_vault"] or not closed["ticket_kept"]:
        raise SystemExit(f"en-closed vault failed: {closed}")
    if closed.get("model_spans", 0) < 1:
        raise SystemExit(f"en-closed model returned no spans: {closed}")
    opened = report["multi-open"]
    if opened.get("error") or opened.get("types") != ["EMAIL"] or not opened.get("email"):
        raise SystemExit(f"multi-open failed: {opened}")
    if not opened.get("model_email"):
        raise SystemExit(f"multi-open model missed the email: {opened}")
    bert = report["en-bert"]
    if bert.get("gated"):
        print("en-bert skipped: the Hugging Face account cannot read this gated repo")
    elif not bert.get("email"):
        raise SystemExit(f"en-bert failed: {bert}")
    for name, row in report.items():
        bad = [span for span in row.get("spans") or [] if not span["slice_ok"]]
        if bad:
            raise SystemExit(f"{name} slice check failed: {bad}")
    print("model e2e passed")
    for name, row in report.items():
        print(name, row.get("revision"))
        for span in row.get("spans") or []:
            print(
                f"  {span['type']} {span['start']}:{span['end']} "
                f"{span['text']!r} {span['detector_id']}"
            )
