# ADR 0004. Secrets stay irreversible

<!-- ste: descriptive -->

Status: accepted. Date: 4 November 2026.

## Context

The mask-and-restore pattern puts a slice into a vault so a later step can put it back. That pattern is right for a name or a phone. It is wrong for a password, an API key, or a recovery code. A restore would write the secret into a ticket, a log, or a second prompt. The parent note says not to stand-in and restore secrets ([Hide names and phones](https://app.notion.com/p/407887c3416481daa9a7e3ce8b346775)).

The locator still needs to find secrets. Otherwise they leave in the clear.

## Decision

Class `secret` is in taxonomy `2026.11`. The locator returns the span. `redact` replaces the slice with `<SECRET>` and does not add a vault entry. Every secret in the call uses that same placeholder. The vault cannot tell the secrets apart. The output has no index that invites a restore.

There is no `unredact` for `<SECRET>`.

## Options rejected

| Option | Why the team rejected it |
| --- | --- |
| Omit secret detection | The secret stays in the outbound string |
| Vault the secret like an email | Restore and logs can bring it back |
| Encrypt the secret into the placeholder | The ciphertext is still a secret-shaped payload in the prompt |

## Consequences

Tests in phase 3 assert that a known fake secret is absent from the vault and absent from the masked string. High-severity leakage includes class `secret`. See [evaluation](../09-evaluation.md).

**WARNING:** Do not add a debug path that puts the secret in the vault for tests. Use a span assertion on the locator output. Then assert that the vault lacks the value.
