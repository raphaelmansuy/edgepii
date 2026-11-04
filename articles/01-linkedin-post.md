# Your prompt is your data leak.

> LinkedIn post — `edgepii` 0.1.0 announcement.
> Body is plain text, no Markdown, no code fences. Copy from the line after `---` to the hashtags.
> Post body: 2,792 characters, under the 3,000 limit. Recount after any edit.

---

Your prompt is your data leak.

Every ticket you summarise with a model carries a name, a phone number, a card. You send all of it. The model does not need it. And you cannot take it back.

That is why I built edgepii.

WHY

Most PII tools answer one question: "does this document contain PII?"

That does not help you. You still have to send the text. And you still do not know which characters are the problem.

I wanted the small answer. Not "this file is sensitive", but "these characters, of this type, on my string".

THE MOVE

Find the PII. Swap it for a placeholder. Send the placeholder. Put the real value back when the answer returns.

That is the whole idea.

from edgepii import Locator, redact

prompt = "My card 4242424242424242 was charged twice. I am Ada Lovelace, call me on +852 5555 0101."

spans = Locator.preset("rules").locate(prompt).spans
masked, vault = redact(prompt, spans)

print(masked)
# My card <PAYMENT_1> was charged twice. I am Ada Lovelace, call me on <PHONE_1>.

# send masked to any model, then restore its answer on your host
answer = "Refund for <PAYMENT_1> is sent. We will call <PHONE_1>."
for placeholder, real in vault.items():
    answer = answer.replace(placeholder, real)

# Refund for 4242424242424242 is sent. We will call +852 5555 0101.

The card never leaves your host. The ticket still makes sense to the model. And you get the real answer back.

ONE CHECK

Every span obeys one rule:

prompt[span.start:span.end] == span.text

If an offset fails that check, the library drops the span and counts it. It does not guess a repair, because a repair can grab the wrong characters.

That is the difference between a mask and a promise.

THE HONEST LIMIT

The rules lane finds cards, phones, emails, IBANs, IPs and passwords. It does not find names.

Look again at the output. "Ada Lovelace" stayed in the text. A name has no checksum and no grammar.

For names, add the model lane:

pip install "edgepii[hf]"
Locator.preset("en-closed")

It runs on your CPU. No API key. That lane does find Ada.

I scored it on public data instead of trusting the model card:

PERSON, in domain: 0.995
PERSON, on finance documents: 0.048

Same model. It learned where a name sits in a synthetic note, not what a name is. So the library publishes the failure next to the score, per type, never averaged.

WHAT YOU GET

- Weights run on your host. Your text never goes to a PII vendor.
- A password never enters the vault. It is destroyed, not restored. A restore would write it into a log.
- Apache 2.0. Python 3.11 and up.

TRY IT

pip install edgepii

Docs and demo: https://raphaelmansuy.github.io/edgepii
Code: https://pypi.org/project/edgepii

What do you send to a model today that you would rather keep?

#PII #LLM #PrivacyEngineering #Python #OpenSource

---

## Notes for the operator (do not paste this section)

### What changed from the first draft

The first version was an argument about document flags. This one starts at the LLM call,
because that is where the reader's pain is. The flag argument is now one short paragraph.

| Block | Job |
|---|---|
| Line 1 | Names the reader's own prompt. |
| The three sentences | Concrete loss: name, phone, card. Then "you cannot take it back". |
| WHY | The pivot. Flag versus character. |
| THE MOVE | The product as three sentences and one code block. |
| The code | Intercept, mask, restore. The whole loop, copyable. |
| ONE CHECK | The proof, in one line. |
| HONEST LIMIT | The name stays visible. This is the section that earns trust. |
| The two scores | Proof that a model card is not a measurement. |
| Close | A question the reader can answer from their own pipeline. |

### Why the name leak is in the post

The rules lane does not find `Ada Lovelace`, and the output shows it. I kept that
instead of hiding it, for three reasons. It is true. A reader who runs the code will
see it anyway. And a tool that admits one gap is easier to believe about the other ten
types.

It also does the selling. The reader now knows the rule lane is fast and free, and the
model lane is the one that finds names.

### Verified claims

| Claim in the body | Where it is true |
|---|---|
| The masked string, verbatim | Ran on this host, 4 November 2026 |
| The restore loop returns the real card and phone | Same run, output copied |
| `Ada Lovelace` stays unspanned on the rules lane | Same run: 2 spans, 0 dropped |
| `en-closed` finds `PERSON`, on CPU, no key | Ran it: 5 spans, name replaced |
| `source[start:end] == text` is enforced | `docs/01-span-contract.md`, `tests/test_acceptance.py` |
| A bad offset is dropped and counted | `LocateResult.dropped` |
| PERSON 0.995 in domain, 0.048 on finance | `docs/13-first-public-score.md`, `docs/eval/*.json` |
| A secret never enters the vault | `docs/adr/0004-secrets-irreversible.md`, ran it |
| Apache-2.0, Python 3.11+ | `pyproject.toml`, wheel metadata |
| `pip install edgepii` works | Installed from PyPI into a clean 3.11 venv |
| Both URLs return 200 | Checked 4 November 2026 |

### Things I fixed while checking

1. **`pip install edgepii` is live.** Published to PyPI as 0.1.0 on 4 November 2026.
   Installed from the public index into a clean Python 3.11 venv and ran the post's code.
2. **The code block was executed, not written.** Every printed line in the post is copied
   from a real run.
3. **The restore loop is written out, not described.** The library has no `restore()`
   call; it returns the vault and the caller applies it. The post shows the loop so a
   reader does not go looking for a function that does not exist.
4. **The two F1 numbers stay separate.** Averaging the two corpora is the mistake the
   eval docs warn against.
5. **The repo link points at PyPI**, where the install line already lives.

### Before posting

1. Attach `docs/e2e/screenshots/02-rules-ticket.png`. It shows the real span table beside
   the masked string, which is the claim in one image.
2. Optional second image: `docs/e2e/screenshots/06-placeholders.png`, for the numbering.
3. The first 210 characters are the feed preview. The hook and the three losses fit.
4. Post Tuesday to Thursday, 08:00 to 10:00 in your audience's timezone.
5. Answer every comment in the first 90 minutes. Ask for the failure they hit, not a like.
