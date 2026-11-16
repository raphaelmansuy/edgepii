"""Tests for the in-app architecture page.

The page renders ARCHITECTURE.md from the deployment, so these tests check the
rendering contract rather than the prose: every diagram becomes an upgradeable
block, every diagram's text reaches the browser byte-identical to the Markdown,
and the page needs no credentials.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "apps" / "edgepii-databricks"
sys.path.insert(0, str(APP_DIR))

import architecture_page  # noqa: E402

DOC = APP_DIR / "ARCHITECTURE.md"


def _fences() -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)


def _blocks() -> list[str]:
    body = architecture_page.rendered()
    return re.findall(
        r'<pre class="diagram-source"><code>(.*?)</code></pre>', body, re.S
    )


def test_every_mermaid_fence_becomes_one_block():
    fences = _fences()
    blocks = _blocks()

    assert fences, "the architecture document should have diagrams"
    assert len(fences) == len(blocks)
    assert architecture_page.payload()["diagrams"] == len(fences)


def test_no_raw_mermaid_fence_survives():
    """A leftover <pre><code class="language-mermaid"> would render as code."""

    body = architecture_page.rendered()
    assert 'class="language-mermaid"' not in body
    assert "```" not in body


def test_each_block_text_reaches_the_browser_unchanged():
    """Mermaid receives textContent, so the round-trip must be exact.

    `markdown_it` escapes the fence body. If the page escaped it a second time,
    Mermaid would get `&amp;lt;` and draw that literally instead of a bracket.
    HTML-unescaping the served block must give back the original fence.
    """

    fences = _fences()
    blocks = _blocks()

    for index, (fence, block) in enumerate(zip(fences, blocks), start=1):
        as_browser_sees_it = html.unescape(block)
        assert as_browser_sees_it.strip() == fence.strip(), f"diagram {index} drifted"


def test_the_page_says_how_many_diagrams_to_expect():
    payload = architecture_page.payload()
    assert payload["diagrams"] >= 7
    assert isinstance(payload["title"], str) and payload["title"]


def test_tables_and_headings_render():
    """The document leans on tables and headings for its argument."""

    body = architecture_page.rendered()
    assert body.count("<table>") >= 3
    assert body.count("<h2>") >= 8
    assert "<strong>" in body


def test_the_module_map_lists_every_module_in_the_deployment():
    """A module missing from the map is a documentation bug the page can catch."""

    body = architecture_page.rendered()
    on_disk = {path.name for path in APP_DIR.glob("*.py")}
    for name in ("app.py", "pipeline.py", "tutorial.py", "architecture_page.py"):
        assert name in on_disk, f"{name} should exist"
        assert name in body, f"{name} is missing from the module map"


def test_the_page_needs_no_credentials(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", "/tmp/edgepii-no-such-config")
    monkeypatch.setenv("DATABRICKS_PROFILE", "no-such-profile")
    assert architecture_page.payload()["diagrams"] >= 7


def test_the_architecture_routes_serve_without_credentials(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", "/tmp/edgepii-no-such-config")
    monkeypatch.setenv("DATABRICKS_PROFILE", "no-such-profile")

    import app as app_module

    client = TestClient(app_module.app)

    page = client.get("/architecture")
    assert page.status_code == 200
    assert "architecture.js" in page.text

    payload = client.get("/api/architecture").json()
    assert payload["diagrams"] >= 7
    assert "data-mermaid" in payload["html"]

    script = client.get("/static/architecture.js")
    assert script.status_code == 200


@pytest.mark.parametrize("path", ["/", "/tutorial"])
def test_other_pages_link_to_the_architecture_page(path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", "/tmp/edgepii-no-such-config")
    monkeypatch.setenv("DATABRICKS_PROFILE", "no-such-profile")

    import app as app_module

    page = TestClient(app_module.app).get(path)
    assert 'href="/architecture"' in page.text


def test_the_page_links_back_to_the_demo_and_tutorial():
    from fastapi.testclient import TestClient

    import app as app_module

    text = TestClient(app_module.app).get("/architecture").text
    assert 'href="/"' in text
    assert 'href="/tutorial"' in text
