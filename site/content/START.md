# Get started in five minutes

<!-- ste: procedural -->

This page installs the library and shows the smallest useful program. The rule lane needs no model download and no network call, so the first result arrives in seconds.

## What you need

- Python 3.11 or newer
- A terminal

Nothing else. The rule lane depends on two small packages, `phonenumbers` and `pyyaml`, and the installer brings both.

## 1. Create a virtual environment

```bash
python3.11 -m venv .venv
.venv/bin/pip install edgepii
```

If you work from source, install the working copy instead:

```bash
git clone https://github.com/raphaelmansuy/edgepii.git
cd edgepii
python3.11 -m venv .venv
.venv/bin/pip install -e .
```

> [!NOTE]
> The rule lane is enough to start. Model lanes are separate extras, because each one pulls `torch` and a checkpoint. Install one only when you need names.

## 2. Find your first spans

Create a file called `first.py`:

```python
from edgepii import Locator

source = (
    "Customer Ada Lovelace called from +852 5555 0101. "
    "Email ada@example.com. Card 4242424242424242. Order 48291."
)

result = Locator.preset("rules").locate(source)

for span in result.spans:
    same = source[span.start:span.end] == span.text
    print(span.type, span.start, span.end, repr(span.text), same)
```

Run it:

```bash
.venv/bin/python first.py
```

You should see this:

```text
PHONE 34 48 '+852 5555 0101' True
EMAIL 56 71 'ada@example.com' True
PAYMENT 78 94 '4242424242424242' True
```

Read the last column first. That `True` is the whole idea: the span is a slice of **your** string, not a sentence a model rewrote. You can assert it in a test.

## 3. Understand the four columns

| Column | Meaning |
| --- | --- |
| `type` | One of eleven public types. Here `PHONE`, `EMAIL`, `PAYMENT` |
| `start` | The index of the first character, counted from 0 |
| `end` | The index after the last character. This is exclusive |
| `text` | Exactly `source[start:end]` |

An exclusive end means `source[56:71]` is 15 characters long. It also means an empty span has `start == end`, which the library refuses to produce.

## 4. Note what stayed out

`Order 48291` produced no span. That is a result, not a miss. An internal order id is not in the default type list, so the locator never looked for it.

This matters more than it looks. A tool that spans every number is impossible to trust, because a reviewer cannot tell a real hit from a busy guess. Restraint is part of the contract.

## 5. Mask it

```python
from edgepii import Locator, redact

source = "Email ada@example.com. Card 4242424242424242."
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)

print(masked)
print(vault)
```

```text
Email <EMAIL_1>. Card <PAYMENT_1>.
{'<EMAIL_1>': 'ada@example.com', '<PAYMENT_1>': '4242424242424242'}
```

The function keeps nothing. It returns the masked string and a vault, and the caller stores the vault. A secret never enters that vault, on purpose. [Mask and restore](../guide-masking/) explains why.

## 6. Pick the types you want

A caller can narrow the list at call time:

```python
result = Locator.preset("rules").locate(source, types=["EMAIL"])
```

The locator asks each detector only for labels that map to `EMAIL`. A span of another type cannot appear.

## 7. Add a model lane when you need names

The rule lane does not find person names, and it never will. A name has no grammar and no checksum. Install the encoder extra when you need `PERSON` or `ADDRESS`:

```bash
.venv/bin/pip install "edgepii[hf]"
```

```python
from edgepii import Locator

locator = Locator.preset("en-closed", device="cpu")
result = locator.locate("Ada Lovelace met Grace Hopper at the lab.")
print([(span.type, span.text) for span in result.spans])
```

```text
[('PERSON', 'Ada'), ('PERSON', 'Lovelace'), ('PERSON', 'Grace'), ('PERSON', 'Hopper')]
```

The first call downloads about 600 MB of weights. Later calls read the local cache. This lane runs on a CPU, and it needs no API key.

> [!WARNING]
> A model lane is slower and less predictable than the rule lane. Check the [public score](../evaluation/) before you trust one. On finance text, the closed encoder's PERSON score falls from 0.995 to 0.048.

## 8. Where to go next

| I want to | Read |
| --- | --- |
| Understand why spans, and not labels | [How it works](../concepts/) |
| See the library on fifteen kinds of text | [Worked examples](../guide-examples/) |
| Mask text and handle the vault | [Mask and restore](../guide-masking/) |
| Check the accuracy claim myself | [Score it yourself](../guide-evaluate/) |
| Read every call shape and error | [Library API](../doc-api/) |

## Troubleshooting

**`ModuleNotFoundError: edgepii`** means the installer ran in a different environment than the one running your script. Use `.venv/bin/python` explicitly, or activate the environment first.

**`DetectorLoadError: extra=hf repo=…`** means the extra is missing or the weights are absent. The message names the extra and the pinned revision. It never includes your text.

**A phone number was not found.** The rule uses libphonenumber, which needs a plausible region. A local number with no country code can stay out. Add the country code and try again.

**A card number was not found.** The card passed a shape match but failed the Luhn check digit. That is the library working. A made-up number usually fails.
