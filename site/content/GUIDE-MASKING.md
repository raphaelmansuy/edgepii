# Mask and restore

<!-- ste: procedural -->

`redact` replaces each span with a placeholder and returns a vault. This page explains the shape of
the output, why a secret is different, and how to restore text safely.

## The two return values

```python
from edgepii import Locator, redact

source = "Email ada@example.com and call +852 5555 0101."
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)
```

```text
masked  Email <EMAIL_1> and call <PHONE_1>.
vault   {'<EMAIL_1>': 'ada@example.com', '<PHONE_1>': '+852 5555 0101'}
```

`redact` keeps nothing. It is a pure function: same input, same output, no state. The vault is the
caller's to store, encrypt, or discard.

## Why placeholders are numbered

The number keeps two different values apart. A text with two emails produces two placeholders:

```python
source = "Write to ada@example.com or grace@example.com."
```

```text
Write to <EMAIL_1> or <EMAIL_2>.
{'<EMAIL_1>': 'ada@example.com', '<EMAIL_2>': 'grace@example.com'}
```

A repeat of the **same** value reuses its placeholder, so a model reading the masked text can still
tell that two mentions point at one person:

```text
Write to <EMAIL_1> or grace@example.com. The desk is <EMAIL_1>.
```

The angle brackets matter. They are rare in prose, so a placeholder is unlikely to collide with real
text.

## Applying spans from the right

`redact` walks the span list from the **end** of the string. That is the only way offsets stay valid
while the string changes length:

```python
source = "ada@example.com and +852 5555 0101"
# Replace the phone first, at 20:34. The email offset, 0:15, is still correct.
# Then replace the email. No offset needed to move.
```

Replacing left to right would shift every later offset, and a long text would drift. The test suite
locks this with a fixture that supplies spans out of order.

## Secrets are different

A password becomes `<SECRET>`, and the vault gets **no entry** for it:

```python
source = "Do not include the password hunter2 in the note."
```

```text
Do not include the password <SECRET> in the note.
{}    ← the vault, which holds no secret
```

This is deliberate. A restore would write the credential into the next system, which is exactly the
leak the library exists to prevent. A caller who truly needs the password must read it before
masking. The library will not hold it.

The cue word stays visible and only the value is replaced, so `password` remains in the masked text.
That is a trade, not an oversight: the cue is not itself a secret, and keeping it lets a reader see
why a `<SECRET>` sits in that position.

The decision is recorded as ADR 0004 and enforced by a test that searches the vault values for the
secret. The test fails if a secret ever appears there.

> [!IMPORTANT]
> Do not build a "show the original" feature on top of the vault and expect it to work for secrets.
> It cannot, by design. Show a message instead.

## Overlaps are an error

`redact` raises `OverlapError` when two spans share a character:

```python
from edgepii import OverlapError, Span, redact

spans = (
    Span("EMAIL", 0, 15, "ada@example.com", None, "test", "email"),
    Span("PERSON", 0, 3, "ada", 0.9, "test", "person"),
)
redact("ada@example.com", spans)   # raises OverlapError
```

The locator never produces overlapping spans, so this error is a guard against a hand-built span
list, not a second merge pass. The error message carries the offsets only, never the text.

## A worked example with a restore

```python
from edgepii import Locator, redact

source = (
    "Ada Lovelace called. Email ada@example.com. "
    "Card 4242424242424242. Password: hunter2."
)
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)

print(masked)
print(sorted(vault))
```

```text
Ada Lovelace called. Email <EMAIL_1>. Card <PAYMENT_1>. Password: <SECRET>.
['<EMAIL_1>', '<PAYMENT_1>']
```

The span covers only the value, not the cue word. `Password:` stays readable, and only the
credential is replaced.

> [!WARNING]
> The cue word must sit directly before the value. `Password: hunter2` is found. `Password is hunter2`
> is **not**, because the grammar reads `is` as the value and then rejects it for holding no digit or
> symbol. If your text puts a verb between the cue and the secret, the rule lane will miss it. Test
> your own phrasing, and use a model lane or a policy gate if a miss is unacceptable.

Then restore, if the caller kept the vault:

```python
restored = masked
for placeholder, value in vault.items():
    restored = restored.replace(placeholder, value)
# The email and the card come back. <SECRET> stays, because it has no vault entry.
```

## What to store, and where

| Item | Store it? | Why |
| --- | --- | --- |
| The masked string | Yes, anywhere | It holds no original values |
| The vault | Only somewhere you already protect personal data | It is the sensitive part |
| The span list | Yes, for a review | It holds offsets and types, but `text` copies PII |
| The original string | Wherever it lived before | The library does not keep a copy |

One detail catches people out: a span row has a `text` field, and that field is a copy of your
string. A log of `result.to_dict()` therefore copies PII. The library never logs span text unless
`EDGEPII_LOG_TEXT=1` is set, and the default log line has offsets only.

## Next

- See masking run in the [live demo](../demo/)
- Read the [worked examples](../guide-examples/) for more shapes
- Read the [library API](../doc-api/) for `redact` and the error table
