"""API tests for the demo. No browser and no model weights."""

from fastapi.testclient import TestClient

from demo.app import app

client = TestClient(app)


def test_health_and_index():
    assert client.get("/api/health").json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200
    assert "Locate spans" in page.text


def test_presets_mark_ready_and_missing():
    rows = client.get("/api/presets").json()["presets"]
    names = {row["name"] for row in rows}
    assert {"rules", "en-closed", "multi-open"} <= names
    rules = next(row for row in rows if row["name"] == "rules")
    assert rules["ready"] is True


def test_types_exclude_quasi_by_default():
    rows = client.get("/api/types").json()["types"]
    dob = next(row for row in rows if row["name"] == "DATE_OF_BIRTH")
    assert dob["default"] is False
    assert dob["class"] == "quasi"
    assert "threshold" not in dob


def test_min_score_filters_when_the_caller_asks():
    body = client.post(
        "/api/locate",
        json={
            "source": "Email ada@example.com. Card 4242424242424242.",
            "preset": "rules",
            "types": ["EMAIL", "PAYMENT"],
            "min_score": 0.5,
        },
    ).json()
    assert [span["type"] for span in body["spans"]] == ["PAYMENT"]


def test_locate_returns_spans_and_slices():
    response = client.post(
        "/api/locate",
        json={
            "source": "Email ada@example.com. Card 4242424242424242. Order 48291.",
            "preset": "rules",
            "types": ["EMAIL", "PAYMENT"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["slice_ok"] is True
    assert {span["type"] for span in body["spans"]} == {"EMAIL", "PAYMENT"}
    for span in body["spans"]:
        assert body["source_chars"] == len(
            "Email ada@example.com. Card 4242424242424242. Order 48291."
        )
        assert span["end"] > span["start"]
    assert "48291" not in {span["text"] for span in body["spans"]}


def test_secret_never_reaches_the_vault():
    response = client.post(
        "/api/locate",
        json={
            "source": "Call +1 202 555 0147. The password hunter2 is set.",
            "preset": "rules",
            "types": ["PHONE", "SECRET"],
        },
    )
    body = response.json()
    assert "<SECRET>" in body["masked"]
    assert all(row["value"] != "hunter2" for row in body["vault"])


def test_unknown_type_is_a_clean_error():
    response = client.post(
        "/api/locate",
        json={"source": "hello", "preset": "rules", "types": ["NOPE"]},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "unknown_type"


def test_long_source_is_refused():
    response = client.post(
        "/api/locate",
        json={"source": "x" * 20_001, "preset": "rules", "types": []},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "too_long"
