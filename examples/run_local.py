"""Run the local examples and print a span table. Model presets run on Modal."""

from edgepii import Locator, redact


def show(title: str, source: str, result) -> None:
    print(title)
    print(f"preset={result.preset} revision={result.revision} dropped={result.dropped}")
    for span in result.spans:
        same = source[span.start : span.end] == span.text
        print(
            f"  {span.type} {span.start}:{span.end} score={span.score} "
            f"detector={span.detector_id} slice_ok={same} text={span.text!r}"
        )
    print()


def main() -> None:
    ticket = (
        "Customer Ada Lovelace called from +852 5555 0101. "
        "Email ada@example.com. Card 4242424242424242. Order 48291."
    )
    result = Locator.preset("rules").locate(ticket)
    show("1. rules", ticket, result)
    masked, vault = redact(ticket, result.spans)
    print("masked", masked)
    print("vault keys", sorted(vault))
    print()

    note = (
        "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
        "about ticket 77. Do not include the password hunter2 in the note."
    )
    note_result = Locator.preset("rules").locate(note)
    show("2. secret cue on the rule lane", note, note_result)
    masked, vault = redact(note, note_result.spans)
    print("masked", masked)
    print("secret in vault", "hunter2" in vault.values())
    print()

    zh = "联系人张伟，手机13800138000，邮箱wei@example.com。"
    show("6. rules on a Chinese line", zh, Locator.preset("rules").locate(zh))


if __name__ == "__main__":
    main()
