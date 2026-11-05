"""Browser checks for the rendered research, plan, and shipped evidence."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def static_site():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    process=subprocess.Popen([sys.executable,"-m","http.server",str(port),"--bind","127.0.0.1", "--directory",str(ROOT/"site/dist")],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base,timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.parametrize("width",[1440,390])
def test_research_plan_and_evidence_in_browser(static_site,width,tmp_path):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":width,"height":1000})
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        response=page.goto(static_site+"/doc-research-2026/")
        assert response.status == 200
        assert "5 November 2026" in page.locator("h1").inner_text()
        assert "RIPE" in page.locator("main").inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.goto(static_site+"/doc-improvement-plan/")
        assert "Grounded improvement plan" in page.locator("h1").inner_text()
        assert "IMP-01" in page.locator("main").inner_text()
        assert "204 passed" in page.locator("main").inner_text()
        report_link = page.locator("a[href$='/2026-11-05-final/validation.json']").first
        report = page.request.get(static_site + "/doc-improvement-plan/" + report_link.get_attribute("href"))
        assert report.status == 200 and report.json()["passed"] is True
        assert report.json()["mode"] == "full"
        assert report.json()["pytest"]["tests"] == "205"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        evidence=page.request.get(static_site+"/evidence/research/model-manifest-2026-11-05.json")
        assert evidence.status == 200
        assert len(evidence.json()["models"]) >= 14
        response=page.goto(static_site+"/doc-next-stage/")
        assert response.status == 200
        assert "Next-stage AI engineering" in page.locator("h1").inner_text()
        assert "PII-Tracer" in page.locator("main").inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        next_models=page.request.get(static_site+"/evidence/research/model-manifest-phase2-2026-11-05.json")
        assert next_models.status == 200
        tracer=next(m for m in next_models.json()["models"] if m["repo_id"] == "perplexity-ai/PII-Tracer")
        assert tracer["revision"] == "d25c16f2e57e321f6d2527715c01df9112f956f5"
        assert tracer["gated"] is False
        assert not errors
        destination=Path(os.environ.get("EDGEPII_TEST_ARTIFACTS",str(tmp_path)))
        destination.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(destination/f"site-{width}.png"),full_page=False)
        browser.close()
