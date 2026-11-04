"""Fake sample text for the demo. Do not paste production data here."""

from __future__ import annotations

SAMPLES: list[dict] = [
    {
        "id": "ticket",
        "label": "Support ticket",
        "note": "Phone, email, and a test card. The order id stays clear.",
        "source": (
            "Customer Ada Lovelace called from +852 5555 0101. "
            "Email ada@example.com. Card 4242424242424242. Order 48291."
        ),
        "types": ["EMAIL", "PHONE", "PAYMENT"],
    },
    {
        "id": "secret",
        "label": "Secret note",
        "note": "The password is masked. It never enters the vault.",
        "source": (
            "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
            "about ticket 77. Do not include the password hunter2 in the note."
        ),
        "types": ["EMAIL", "PHONE", "SECRET"],
    },
    {
        "id": "payment",
        "label": "Payments",
        "note": "An IBAN passes MOD-97. A bad card number is ignored.",
        "source": (
            "Wire to IBAN GB82WEST12345698765432 from card 4242424242424243. "
            "Reach ops at ops@example.org or 203.0.113.10."
        ),
        "types": ["EMAIL", "PAYMENT", "IP_ADDRESS"],
    },
    {
        "id": "chinese",
        "label": "Chinese line",
        "note": "Chinese phone and email on the rule lane.",
        "source": "联系人张伟，手机13800138000，邮箱wei@example.com。",
        "types": ["PERSON", "PHONE", "EMAIL"],
    },
    {
        "id": "numbered",
        "label": "Numbered placeholders",
        "note": "A distinct slice gets a new number. A repeat reuses its token.",
        "source": (
            "Write to ada@example.com or grace@example.com. "
            "The desk address is ada@example.com."
        ),
        "types": ["EMAIL"],
    },
    {
        "id": "long",
        "label": "Long text",
        "note": "Offsets stay on the full source string.",
        "source": "Note. " * 400 + "Email ada@example.com for the desk.",
        "types": ["EMAIL"],
    },
]
