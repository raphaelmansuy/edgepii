"""FastAPI demo for edgepii. Run with: make demo"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from edgepii import __version__
from demo.samples import SAMPLES
from demo.service import (
    DemoError,
    locate,
    presets_payload,
    types_payload,
)

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"

app = FastAPI(
    title="edgepii demo",
    description="Locate PII as typed character spans on the source string.",
    version=__version__,
)


class LocateRequest(BaseModel):
    source: str = Field(default="", description="The exact string to inspect.")
    preset: str = Field(default="rules")
    types: list[str] = Field(default_factory=list)
    min_score: float | None = Field(default=None, description="Caller policy. No library default.")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "edgepii-demo"}


@app.get("/api/presets")
def presets() -> dict:
    return {"presets": presets_payload()}


@app.get("/api/types")
def types() -> dict:
    return {"types": types_payload()}


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES}


@app.post("/api/locate")
def locate_endpoint(request: LocateRequest) -> JSONResponse:
    try:
        payload = locate(request.source, request.preset, request.types, request.min_score)
    except DemoError as exc:
        body = {"ok": False, "error": exc.kind, "message": exc.message}
        if exc.hint:
            body["hint"] = exc.hint
        return JSONResponse(status_code=422, content=body)
    return JSONResponse(content=payload)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
