"""The tutorial, with every example output produced by the real library.

A tutorial that shows stale output is worse than no tutorial, because a reader
trusts it and then finds the library disagrees. So nothing here is typed by
hand: each step runs an `edgepii` call and formats the value it got back.

`STEPS` is built once at import. The rule lane needs no weights and no network,
so the whole page costs a few milliseconds. The one step that needs a model
shows the prompt it would send and says the rest happens in the app, rather
than inventing an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from edgepii import Locator, redact, restore

TICKET = (
    "Ada Lovelace called from +852 5555 0101 about order 48291. "
    "Email ada@example.com. The card on file is 4242424242424242."
)


@dataclass(frozen=True, slots=True)
class Step:
    """One tutorial step: what to say, what to run, what actually happened."""

    title: str
    body: str
    code: str
    output: str = ""
    output_kind: str = "text"  # text | json | nothing
    note: str = ""
    terms: list[str] = field(default_factory=list)


def _locate_output() -> tuple[str, str]:
    """Step 1: the span list, and the slice check that makes it trustworthy."""

    result = Locator.preset("rules").locate(TICKET)
    rows = [f"{span.type:12s} {span.start:>3}:{span.end:<3} {span.text}" for span in result.spans]
    ok = all(TICKET[span.start : span.end] == span.text for span in result.spans)
    header = f"{'type':12s} {'start:end':>9}  text"
    output = "\n".join([header, *rows, "", f"every slice matches the source: {ok}"])
    return output, "text"


def _mask_output() -> tuple[str, str]:
    """Step 2: the masked string, and the vault that holds the values."""

    result = Locator.preset("rules").locate(TICKET)
    masked, vault = redact(TICKET, result.spans)
    rows = "\n".join(f"  {token:16s} -> {value}" for token, value in vault.items())
    output = f"masked:\n  {masked}\n\nvault ({len(vault)} entries):\n{rows}"
    return output, "text"


def _secret_output() -> tuple[str, str]:
    """Step 3: a secret is masked and never vaulted, so it cannot come back.

    The output must not name the secret. A tutorial that prints the password to
    prove the password is gone defeats its own lesson, so it reports a boolean
    computed against the vault instead.
    """

    source = "Escalate ticket 77. The staging password: hunter2 and the box is 203.0.113.10."
    secret = "hunter2"
    result = Locator.preset("rules").locate(source)
    masked, vault = redact(source, result.spans)
    output = (
        f"masked:\n  {masked}\n\n"
        f"vault keys: {sorted(vault)}\n"
        f"secret found in masked:  {secret in masked}\n"
        f"secret found in vault:   {secret in vault.values()}"
    )
    return output, "text"


def _repeat_output() -> tuple[str, str]:
    """Step 4: the same value twice reuses one token, a new value gets a new one."""

    source = "Write to ada@example.com or grace@example.com. The desk is ada@example.com."
    result = Locator.preset("rules").locate(source)
    masked, vault = redact(source, result.spans)
    output = f"masked:\n  {masked}\n\nvault keys: {sorted(vault)}"
    return output, "text"


def _restore_output() -> tuple[str, str]:
    """Step 5: the model echoes the tokens, and restore swaps the values back."""

    source = "Call +852 5555 0101, email ada@example.com."
    result = Locator.preset("rules").locate(source)
    masked, vault = redact(source, result.spans)
    # A stand-in for a model answer: it echoes the tokens it was given. The live
    # app asks a real endpoint here; this step must stay offline and honest.
    answer = "Understood, I will call <PHONE_1> and write to <EMAIL_1>."
    outcome = restore(answer, vault, locator=Locator.preset("rules"))
    output = (
        f"model said:\n  {answer}\n\n"
        f"restored:\n  {outcome.text}\n\n"
        f"ok: {outcome.ok}   unresolved: {list(outcome.unresolved)}"
    )
    return output, "text"


def _invented_output() -> tuple[str, str]:
    """Step 6: the gate catches PII the vault never held."""

    vault = {"<EMAIL_1>": "ada@example.com"}
    answer = "I emailed <EMAIL_1> and also copied bob@elsewhere.test and rung 555-666-7777."
    outcome = restore(answer, vault, locator=Locator.preset("rules"))
    unknown = ", ".join(f"{span.type} {span.text!r}" for span in outcome.unknown)
    output = (
        f"model said:\n  {answer}\n\n"
        f"ok: {outcome.ok}\n"
        f"unknown: {unknown}"
    )
    return output, "text"


def _build() -> list[Step]:
    locate_out, _ = _locate_output()
    mask_out, _ = _mask_output()
    secret_out, _ = _secret_output()
    repeat_out, _ = _repeat_output()
    restore_out, _ = _restore_output()
    invented_out, _ = _invented_output()

    return [
        Step(
            title="Locate spans, not documents",
            body=(
                "The library answers one question: which characters, of which type, on this "
                "string? It returns rows, and each row proves `source[start:end] == text`. "
                "That check is the contract. The rule lane finds email, phone, card, IBAN, "
                "IP address, and secrets without downloading anything."
            ),
            code=(
                "from edgepii import Locator\n\n"
                "result = Locator.preset(\"rules\").locate(source)\n"
                "for span in result.spans:\n"
                "    print(span.type, span.start, span.end, span.text)"
            ),
            output=locate_out,
            note="This is the exact output for the ticket at the top of the page.",
        ),
        Step(
            title="Mask into a vault",
            body=(
                "`redact` replaces each span with a placeholder and hands back the mapping. "
                "It keeps nothing: no state, no file, no cache. The vault is yours to store "
                "or discard. Only the masked string is safe to send anywhere."
            ),
            code=(
                "from edgepii import redact\n\n"
                "masked, vault = redact(source, result.spans)\n"
                "print(masked)\n"
                "print(vault)"
            ),
            output=mask_out,
            note="The order id 48291 stays clear, because an order id is not PII.",
        ),
        Step(
            title="A secret never enters the vault",
            body=(
                "A password is masked with `<SECRET>` and gets no vault entry. A restore would "
                "write the credential into the next system, which is the leak the library exists "
                "to prevent. This is why a `<SECRET>` left in a model answer is correct behaviour, "
                "not a failure."
            ),
            code=(
                "source = \"Escalate ticket 77. The staging password: hunter2 ...\"\n"
                "masked, vault = redact(source, result.spans)\n"
                "print(masked, sorted(vault))"
            ),
            output=secret_out,
            note="Recorded as ADR 0004. There is no unredact for this token.",
        ),
        Step(
            title="Numbering tells values apart",
            body=(
                "Two different values get two tokens, so the model can still see that two mentions "
                "are two people. The same value reuses its token, so the model sees one person "
                "mentioned twice."
            ),
            code=(
                "source = \"Write to ada@example.com or grace@example.com. \"\n"
                "         \"The desk is ada@example.com.\"\n"
                "masked, vault = redact(source, result.spans)"
            ),
            output=repeat_out,
            note="The third mention reuses <EMAIL_1> rather than becoming <EMAIL_3>.",
        ),
        Step(
            title="Send, then restore",
            body=(
                "Only the masked string crosses the network. The model is asked to copy the tokens "
                "exactly. `restore` then swaps each token back. It tolerates a model that "
                "lower-cases a token or spaces the brackets, because that is the same token."
            ),
            code=(
                "from edgepii import restore\n\n"
                "answer = \"Understood, I will call <PHONE_1> and write to <EMAIL_1>.\"\n"
                "outcome = restore(answer, vault, locator=Locator.preset(\"rules\"))\n"
                "print(outcome.text, outcome.ok)"
            ),
            output=restore_out,
            note=(
                "The live app puts a real endpoint here. This step uses a fixed answer so the "
                "tutorial works with no credentials."
            ),
        ),
        Step(
            title="Gate the answer on what came back",
            body=(
                "The dangerous case is not a token that survives. It is PII in the answer that the "
                "vault never held, because the model invented it or echoed something the mask "
                "missed. Passing a locator makes `restore` report those spans, and the app fails "
                "the gate on them."
            ),
            code=(
                "vault = {\"<EMAIL_1>\": \"ada@example.com\"}\n"
                "answer = \"I emailed <EMAIL_1> and copied bob@elsewhere.test ...\"\n"
                "outcome = restore(answer, vault, locator=Locator.preset(\"rules\"))\n"
                "print(outcome.ok, outcome.unknown)"
            ),
            output=invented_out,
            note="Two spans the vault never held: one email and one phone.",
            terms=["unknown", "gate"],
        ),
    ]


STEPS: list[Step] = _build()


def payload() -> dict:
    """What the tutorial page renders. Outputs are already real."""

    return {
        "source": TICKET,
        "steps": [
            {
                "index": position,
                "title": step.title,
                "body": step.body,
                "code": step.code,
                "output": step.output,
                "output_kind": step.output_kind,
                "note": step.note,
            }
            for position, step in enumerate(STEPS, start=1)
        ],
    }
