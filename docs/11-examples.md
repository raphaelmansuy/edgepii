# Examples

<!-- ste: descriptive -->

Every string in this file is fake. Do not replace the examples with production text. The calls match the [public API](06-library-api.md). The types match [taxonomy 2026.11](10-taxonomy.md).

The snippets are the acceptance examples for the [implementation plan](08-implementation-plan.md). A preset is done when the asserted spans match on the rule lane. The model lane must also find the structured spans the rules already prove. Person-name checks wait until the team pins the weights. The test name then says `model_dependent`.

## 1. Rules find structured spans

Preset `rules` needs no weights. Email, phone, and a Luhn-valid test card are in scope. The person name is not a rule hit.

```python
from edgepii import Locator

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
assert source[by_type["EMAIL"].start:by_type["EMAIL"].end] == "ada@example.com"
```

`4242424242424242` is a common test PAN. It passes Luhn. It is not a live card. `Order 48291` stays unspanned. An internal order id is out of the default type list.

## 2. Closed encoder on English

Preset `en-closed` loads ModernBERT weights [antoniogr7/pii-identifier-v0.1](https://huggingface.co/antoniogr7/pii-identifier-v0.1) and the rule detector. Use this preset when the type list stays frozen.

```python
from edgepii import Locator, redact

source = (
    "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
    "about ticket 77. Do not include the password hunter2 in the note."
)
locator = Locator.preset("en-closed", device="cpu")
result = locator.locate(source)
masked, vault = redact(source, result.spans)

assert "ada@example.com" not in masked
assert "hunter2" not in masked
assert "hunter2" not in vault.values()
assert "<SECRET>" in masked
assert "ticket 77" in masked
```

The password is class `secret`. The vault must not contain it. See [ADR 0004](adr/0004-secrets-irreversible.md). The word `hunter2` is a placeholder secret. Do not use it as a real credential.

Model-dependent check, after the pin:

```python
persons = [span for span in result.spans if span.type == "PERSON"]
assert any(span.text == "Ada Lovelace" for span in persons)
```

If that assertion fails on the sealed freeze, the team reads the miss. The team does not edit the example to fit the model. See [AI engineering](03-ai-engineering.md).

## 3. Open schema when the caller picks types

Preset `multi-open` loads [fastino/gliner2-privacy-filter-PII-multi](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi). The type list is an argument. The argument is the reason Lane G exists.

```python
from edgepii import Locator

source = "Write to ada@example.com or to Ada Lovelace in Lisbon."
result = Locator.preset("multi-open").locate(
    source,
    types=["EMAIL"],
)
assert {span.type for span in result.spans} <= {"EMAIL"}
assert any(span.text == "ada@example.com" for span in result.spans)
```

`Ada Lovelace` can be a person in a wider call. This call asked only for `EMAIL`. The public list must not contain `PERSON`. A closed encoder can still tag a person inside the adapter. The locator filters them after the label map.

## 4. Two people stay distinct

```python
from edgepii import Locator, redact

source = "Ada Lovelace met Grace Hopper at the lab."
result = Locator.preset("en-closed").locate(source, types=["PERSON"])
masked, vault = redact(source, result.spans)
assert "<PERSON_1>" in masked
assert "<PERSON_2>" in masked
assert vault["<PERSON_1>"] != vault["<PERSON_2>"]
```

This example is model-dependent for the names. The rule preset will not find them. The test that locks the placeholder rule can inject spans without a model:

```python
from edgepii import Span, redact

source = "Ada Lovelace met Grace Hopper at the lab."
spans = (
    Span("PERSON", 0, 12, "Ada Lovelace", 0.9, "test", "person"),
    Span("PERSON", 17, 29, "Grace Hopper", 0.9, "test", "person"),
)
masked, vault = redact(source, spans)
assert masked.startswith("<PERSON_1>")
assert vault["<PERSON_1>"] == "Ada Lovelace"
assert vault["<PERSON_2>"] == "Grace Hopper"
```

## 5. Bad offsets die

```python
from edgepii import Locator

class Bad:
    def locate(self, source, types):
        return [{
            "type": "EMAIL",
            "start": 0,
            "end": 3,
            "text": "nope",
            "score": 0.9,
            "raw_label": "email",
        }]

result = Locator.from_detectors([Bad()], taxonomy="2026.11").locate("hello")
assert result.spans == ()
assert result.dropped == 1
```

The library must not search `hello` for a repair. `from_detectors` is the test seam. It is public so eval code can wrap a new adapter. Production call sites use `preset`.

## 6. Chinese schema lane

Optional extra `ms`. The schema names are prompts. The public types stay English codes from the taxonomy.

```python
from edgepii import Locator

source = "联系人张伟，手机13800138000，邮箱wei@example.com。"
result = Locator.preset("zh-schema").locate(
    source,
    types=["PERSON", "PHONE", "EMAIL"],
)
assert any(span.type == "PHONE" and span.text == "13800138000" for span in result.spans)
assert any(span.type == "EMAIL" and span.text == "wei@example.com" for span in result.spans)
```

The phone and the email must succeed on the rule detector even if UIE misses them. The person span is model-dependent. `13800138000` is a reserved-looking example, not a number to dial. Treat the whole string as fake.

## 7. Long text keeps original offsets

```python
from edgepii import Locator

prefix = "Note. " * 2000
source = prefix + "Email ada@example.com for the desk."
result = Locator.preset("rules").locate(source)
email = next(span for span in result.spans if span.type == "EMAIL")
assert source[email.start:email.end] == "ada@example.com"
```

Rules do not need a window. The same assertion is required for `en-closed` when the prefix exceeds the model window. The public start must still index `source`, not the tail window. See windowing in the [architecture](07-architecture.md).

## 8. Empty string

```python
from edgepii import Locator

result = Locator.preset("rules").locate("")
assert result.spans == ()
assert result.taxonomy_version == "2026.11"
```

## 9. Redact order

Spans arrive in any order. `redact` applies them from the right.

```python
from edgepii import Span, redact

source = "ada@example.com and +852 5555 0101"
spans = (
    Span("PHONE", 20, 34, "+852 5555 0101", 1.0, "rules.phone", "phone"),
    Span("EMAIL", 0, 15, "ada@example.com", 1.0, "rules.email", "email"),
)
masked, vault = redact(source, spans)
assert masked == "<EMAIL_1> and <PHONE_1>"
assert vault["<EMAIL_1>"] == "ada@example.com"
```

## What a failure looks like in review

A reviewer who sees a green demo and no span list does not accept the change. The review artifact is the span table: type, start, end, and the equality `source[start:end] == text`. A screenshot of masked prose is not that artifact.
