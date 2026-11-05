"""Acceptance checks from docs/11-examples.md, plus merge, score, and window rules."""

from pathlib import Path

from edgepii import DetectorLoadError, Locator, OverlapError, Span, UnknownType, redact
from edgepii.bridges.presidio import to_presidio
from edgepii.detectors.uie import UieDetector
from edgepii.eval.score import exact_span_f1, leakage_count
from edgepii.protocol import Hit
from edgepii.span import LocateResult


def test_rules_find_structured_spans():
    source = (
        "Customer Ada Lovelace called from +852 5555 0101. "
        "Email ada@example.com. Card 4242424242424242. Order 48291."
    )
    result = Locator.preset("rules").locate(source)
    by_type = {span.type: span for span in result.spans}
    assert by_type["PHONE"].text == "+852 5555 0101"
    assert by_type["EMAIL"].text == "ada@example.com"
    assert by_type["PAYMENT"].text == "4242424242424242"
    assert "PERSON" not in by_type
    assert source[by_type["EMAIL"].start : by_type["EMAIL"].end] == "ada@example.com"
    assert "48291" not in {span.text for span in result.spans}


def test_secret_is_not_in_the_vault():
    source = (
        "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
        "about ticket 77. Do not include the password hunter2 in the note."
    )
    result = Locator.preset("rules").locate(source)
    masked, vault = redact(source, result.spans)
    assert "ada@example.com" not in masked
    assert "hunter2" not in masked
    assert "hunter2" not in vault.values()
    assert "<SECRET>" in masked
    assert "ticket 77" in masked


def test_type_filter_drops_other_spans():
    source = "Write to ada@example.com or to Ada Lovelace in Lisbon."

    class Both:
        max_chars = 1000
        overlap_chars = 0

        def locate(self, text, labels):
            hits = []
            if "person" in labels:
                hits.append(Hit("person", 31, 43, 0.9, "model.person"))
            if "email" in labels:
                hits.append(Hit("email", 9, 24, 0.9, "model.email"))
            return hits

    result = Locator.from_detectors([Both()]).locate(source, types=["EMAIL"])
    assert {span.type for span in result.spans} <= {"EMAIL"}
    assert any(span.text == "ada@example.com" for span in result.spans)


def test_two_people_get_distinct_placeholders():
    source = "Ada Lovelace met Grace Hopper at the lab."
    spans = (
        Span("PERSON", 0, 12, "Ada Lovelace", 0.9, "test", "person"),
        Span("PERSON", 17, 29, "Grace Hopper", 0.9, "test", "person"),
    )
    masked, vault = redact(source, spans)
    assert masked.startswith("<PERSON_1>")
    assert vault["<PERSON_1>"] == "Ada Lovelace"
    assert vault["<PERSON_2>"] == "Grace Hopper"
    assert vault["<PERSON_1>"] != vault["<PERSON_2>"]


def test_bad_offsets_are_dropped():
    class Bad:
        def locate(self, source, types):
            return [
                {
                    "type": "EMAIL",
                    "start": 0,
                    "end": 3,
                    "text": "nope",
                    "score": 0.9,
                    "raw_label": "email",
                }
            ]

    result = Locator.from_detectors([Bad()], taxonomy="2026.11").locate("hello")
    assert result.spans == ()
    assert result.dropped == 1


def test_chinese_phone_and_email_on_the_rule_lane():
    source = "联系人张伟，手机13800138000，邮箱wei@example.com。"
    result = Locator.preset("rules").locate(source, types=["PERSON", "PHONE", "EMAIL"])
    assert any(span.type == "PHONE" and span.text == "13800138000" for span in result.spans)
    assert any(span.type == "EMAIL" and span.text == "wei@example.com" for span in result.spans)


def test_long_text_keeps_original_offsets():
    prefix = "Note. " * 2000
    source = prefix + "Email ada@example.com for the desk."
    result = Locator.preset("rules").locate(source)
    email = next(span for span in result.spans if span.type == "EMAIL")
    assert source[email.start : email.end] == "ada@example.com"


def test_empty_string():
    result = Locator.preset("rules").locate("")
    assert result.spans == ()
    assert result.taxonomy_version == "2026.11"


def test_redact_from_the_right():
    source = "ada@example.com and +852 5555 0101"
    spans = (
        Span("PHONE", 20, 34, "+852 5555 0101", 1.0, "rules.phone", "phone"),
        Span("EMAIL", 0, 15, "ada@example.com", 1.0, "rules.email", "email"),
    )
    masked, vault = redact(source, spans)
    assert masked == "<EMAIL_1> and <PHONE_1>"
    assert vault["<EMAIL_1>"] == "ada@example.com"


def test_failed_luhn_and_bad_iban_are_absent():
    source = "Card 4242424242424243 and IBAN GB00TEST00000000000000."
    result = Locator.preset("rules").locate(source)
    assert result.spans == ()


def test_valid_iban_and_ip():
    source = "Pay GB82WEST12345698765432 from 203.0.113.10."
    result = Locator.preset("rules").locate(source)
    kinds = {span.type: span.text for span in result.spans}
    assert kinds["PAYMENT"] == "GB82WEST12345698765432"
    assert kinds["IP_ADDRESS"] == "203.0.113.10"


def test_unknown_type_and_non_string():
    locator = Locator.preset("rules")
    try:
        locator.locate("hello", types=["NOT_A_TYPE"])
        raise AssertionError("expected UnknownType")
    except UnknownType as exc:
        assert exc.name == "NOT_A_TYPE"
    try:
        locator.locate(None)  # type: ignore[arg-type]
        raise AssertionError("expected TypeError")
    except TypeError as exc:
        assert str(exc) == "NoneType"


def test_missing_model_extra():
    try:
        Locator.preset("en-closed")
    except DetectorLoadError as exc:
        assert "extra=hf" in str(exc)
        assert "antoniogr7/pii-identifier-v0.1" in str(exc)
    else:
        # The extra is installed in this environment. The preset must still name the pin.
        locator = Locator.preset("en-closed")
        assert locator.revision == "3d0f39eceaf0c95fc07943064c58fba3fff60243"


def test_overlap_guard_hides_text():
    source = "ada@example.com"
    spans = (
        Span("EMAIL", 0, 15, "ada@example.com", 1.0, "rules.email", "email"),
        Span("PERSON", 0, 3, "ada", 0.9, "test", "person"),
    )
    try:
        redact(source, spans)
        raise AssertionError("expected OverlapError")
    except OverlapError as exc:
        assert "ada" not in str(exc)
        assert str(exc) in {"0:3", "0:15"}


def test_merge_rank_prefer_length_and_score():
    locator = Locator.preset("rules")
    source = "x" * 20

    class Rows:
        def __init__(self, hits):
            self._hits = hits

        def locate(self, text, labels):
            return self._hits

    payment = Hit("card_number", 0, 4, 0.5, "rules.card")
    person = Hit("person", 0, 6, 0.99, "model.person")
    result = Locator.from_detectors([Rows([payment, person])]).locate(source)
    assert [span.type for span in result.spans] == ["PAYMENT"]

    rule_email = Hit("email", 0, 4, 0.5, "rules.email")
    model_email = Hit("email", 0, 4, 0.99, "model.email")
    result = Locator.from_detectors([Rows([rule_email, model_email])]).locate(source, types=["EMAIL"])
    assert result.spans[0].detector_id == "rules.email"

    short = Hit("person", 0, 2, 0.9, "model.a")
    long = Hit("person", 0, 5, 0.4, "model.b")
    result = Locator.from_detectors([Rows([short, long])]).locate(source, types=["PERSON"])
    assert result.spans[0].end == 5

    low = Hit("person", 2, 4, 0.2, "model.low")
    result = Locator.from_detectors([Rows([low])]).locate(source, types=["PERSON"])
    assert len(result.spans) == 1
    # The library ships no floor. A caller passes one that the caller measured.
    filtered = Locator.from_detectors([Rows([low])]).locate(
        source, types=["PERSON"], min_score=0.5
    )
    assert filtered.spans == ()


def test_tokenizer_edge_space_is_trimmed():
    source = "Ask Ada Lovelace"

    class Spaced:
        def locate(self, text, labels):
            return [Hit("first_name", 3, 7, 0.9, "hf.example"), Hit("last_name", 7, 16, 0.9, "hf.example")]

    result = Locator.from_detectors([Spaced()]).locate(source, types=["PERSON"])
    assert [span.text for span in result.spans] == ["Ada", "Lovelace"]
    assert source[result.spans[0].start : result.spans[0].end] == "Ada"
    assert source[result.spans[1].start : result.spans[1].end] == "Lovelace"


def test_window_shifts_offsets():
    source = ("aaaa " * 10) + "ada@example.com"

    class Tiny:
        max_chars = 24
        overlap_chars = 4

        def locate(self, text, labels):
            needle = "ada@example.com"
            index = text.find(needle)
            if index < 0:
                return []
            return [Hit("email", index, index + len(needle), 0.9, "model.email")]

    result = Locator.from_detectors([Tiny()]).locate(source, types=["EMAIL"])
    assert result.spans[0].text == "ada@example.com"
    assert source[result.spans[0].start : result.spans[0].end] == "ada@example.com"


def test_score_exact_shift_and_leak():
    gold = [("EMAIL", 0, 4), ("PERSON", 5, 8)]
    exact = exact_span_f1(gold, gold)
    assert exact.f1 == 1.0
    assert exact.per_type["EMAIL"].f1 == 1.0
    shifted = exact_span_f1(gold, [("EMAIL", 0, 3), ("ORG", 5, 8)])
    assert shifted.shift == 1
    assert shifted.wrong_type == 1
    assert shifted.tp == 0
    extra = exact_span_f1([], [("EMAIL", 0, 2)])
    assert extra.extra == 1
    assert leakage_count([("PAYMENT", 0, 4)], [("PAYMENT", 0, 4)], {"PAYMENT"}) == 0
    assert leakage_count([("PAYMENT", 0, 4)], [], {"PAYMENT"}) == 1


def test_uie_accepts_only_a_matching_slice():
    source = "联系人张伟，手机13800138000。"

    def runner(text, schema):
        assert "手机号" in schema
        return {
            "手机号": [{"text": "13800138000", "offset": [8, 18], "prob": 0.91}],
            "姓名": [{"text": "不存在", "offset": [0, 2], "prob": 0.5}],
        }

    detector = UieDetector(
        "iic/nlp_structbert_siamese-uie_chinese-base",
        "master",
        {"PHONE": "手机号", "PERSON": "姓名"},
        runner=runner,
    )
    result = Locator.from_detectors([detector]).locate(source, types=["PHONE", "PERSON"])
    assert [span.text for span in result.spans] == ["13800138000"]
    assert result.spans[0].type == "PHONE"


def test_presidio_bridge_and_batch_and_no_framework_import():
    source = "ada@example.com"
    locator = Locator.preset("rules")
    results = locator.locate_many([source, ""])
    assert isinstance(results[0], LocateResult)
    assert results[1].spans == ()
    rows = to_presidio(results[0].spans)
    assert rows[0]["entity_type"] == "EMAIL"
    text = Path("src/edgepii/locator.py").read_text(encoding="utf-8")
    assert "import transformers" not in text
    assert "import modelscope" not in text
    assert "import gliner" not in text


def test_closed_encoder_labels_fold_and_health_labels_do_not():
    from edgepii.labelmap import load_taxonomy

    taxonomy = load_taxonomy("2026.11")
    assert taxonomy.public_type("B-credit_debit_card") == "PAYMENT"
    assert taxonomy.public_type("I-ipv4") == "IP_ADDRESS"
    assert taxonomy.public_type("national_id") == "GOV_ID"
    assert taxonomy.public_type("postcode") == "ADDRESS"
    assert taxonomy.public_type("blood_type") is None


def test_same_slice_reuses_placeholder():
    source = "ada@example.com then ada@example.com"
    result = Locator.preset("rules").locate(source, types=["EMAIL"])
    masked, vault = redact(source, result.spans)
    assert masked.count("<EMAIL_1>") == 2
    assert "<EMAIL_2>" not in masked
    assert vault == {"<EMAIL_1>": "ada@example.com"}


def test_version_is_single_sourced():
    """The package, the wheel metadata, and the docs must not drift apart."""

    import tomllib

    import edgepii

    assert edgepii.__version__
    assert "__version__" in edgepii.__all__

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text())
    # The version lives in the module, so the build cannot carry a stale copy.
    assert "version" in config["project"]["dynamic"]
    assert "version" not in config["project"]
    assert config["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "edgepii._version.__version__"
    )
    # The demo must not hard-code a second copy.
    demo = (Path(__file__).resolve().parent.parent / "demo" / "app.py").read_text()
    assert "version=__version__" in demo


def test_merge_stays_linear_in_span_count():
    """A pairwise compare was 16x slower per doubling. The sweep is not."""

    import time

    from edgepii.labelmap import load_taxonomy
    from edgepii.merge import merge_spans

    taxonomy = load_taxonomy("2026.11")
    allowed = set(taxonomy.default_types())

    def timed(count: int) -> float:
        spans = [
            Span("EMAIL", index * 10, index * 10 + 5, "a@b.c", None, "rules.email", "email")
            for index in range(count)
        ]
        start = time.perf_counter()
        merged = merge_spans(spans, taxonomy, allowed)
        assert len(merged) == count
        return time.perf_counter() - start

    timed(200)  # warm up, so import and cache cost stay out of the ratio
    small = max(min(timed(500) for _ in range(5)), 1e-6)
    large = max(min(timed(4000) for _ in range(5)), 1e-6)
    # 8x the spans. A quadratic merge costs about 64x; the sweep costs about 8x.
    assert large / small < 20, f"merge looks super-linear: {small:.4f}s -> {large:.4f}s"
