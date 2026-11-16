"""Databricks App: edgepii protect-send-restore demo.

The browser never holds a credential. The app's own service principal calls the
serving endpoint, and the vault stays in this process.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from edgepii import __version__
from edgepii.presets import PRESETS
from pipeline import DEFAULT_MODEL, PipelineError, models, run

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"

SAMPLES: list[dict] = [
    {
        "id": "ticket",
        "label": "Support ticket",
        "note": "Phone, email, card, and IBAN. The order id stays clear.",
        "source": (
            "Customer called from +852 5555 0101 about order 48291. "
            "Reply to ada@example.com. The card on file is 4242424242424242. "
            "The refund goes to IBAN GB82WEST12345698765432."
        ),
    },
    {
        "id": "secret",
        "label": "Credential in a note",
        "note": "A password is masked for good, so it never enters the vault.",
        "source": (
            "Escalate ticket 77 to the platform team. The staging password: hunter2 "
            "and the box is 203.0.113.10. Reach the on-call at +1 202 555 0147."
        ),
    },
    {
        "id": "gap",
        "label": "The name gap",
        "note": "Rules cannot see a person name. This is the documented limit.",
        "source": (
            "Ada Lovelace opened ticket 48291 from +852 5555 0101 and asked for "
            "a callback. Her email is ada@example.com."
        ),
    },
    {
        "id": "chinese",
        "label": "Chinese line",
        "note": "Chinese phone and email on the same rule lane.",
        "source": "联系人张伟，手机13800138000，邮箱wei@example.com。请在下班前回复订单 48291 的状态。",
    },
    {
        "id": "numbered",
        "label": "Repeat values",
        "note": "A repeated slice reuses its token, so the model sees one person.",
        "source": (
            "Write to ada@example.com or grace@example.com. "
            "The desk address is ada@example.com, and the fallback is grace@example.com."
        ),
    },
]

PRESET_ORDER = ("rules",)

app = FastAPI(
    title="edgepii · Databricks App demo",
    description="Mask PII before a Databricks-hosted model sees the prompt, then restore the answer.",
    version=__version__,
)


class RunRequest(BaseModel):
    source: str = Field(default="", description="The exact string to protect.")
    model: str = Field(default=DEFAULT_MODEL)
    preset: str = Field(default="rules")
    max_tokens: int = Field(default=400, ge=64, le=2048)
    scan_response: bool = Field(
        default=True,
        description="Also scan the raw answer for PII the vault never sent.",
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "edgepii-databricks",
        "version": __version__,
        "models": models(),
    }


@app.get("/api/config")
def config() -> dict:
    """Everything the UI needs to draw itself. No credentials cross this line."""

    return {
        "version": __version__,
        "models": models(),
        "default_model": models()[0],
        "default_preset": "rules",
        "presets": [
            {
                "name": name,
                "ready": True,
                "extra": PRESETS[name].extra,
                "note": _preset_note(name),
            }
            for name in PRESET_ORDER
            if name in PRESETS
        ],
        "samples": SAMPLES,
        "workspace_host": os.environ.get("DATABRICKS_HOST", ""),
    }


@app.post("/api/run")
def run_endpoint(request: RunRequest) -> JSONResponse:
    try:
        payload = run(
            request.source,
            model=request.model,
            preset=request.preset,
            max_tokens=request.max_tokens,
            scan_response=request.scan_response,
        )
    except PipelineError as exc:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": exc.kind, "message": exc.message},
        )
    return JSONResponse(content=payload)


def _preset_note(name: str) -> str:
    return {
        "rules": "Regex and checksums. No weights, no model download.",
    }.get(name, "")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
