# End-to-end evidence

<!-- ste: descriptive -->

Every image in `screenshots/` comes from `tests/test_demo_e2e.py`. The test fills the page, clicks **Locate spans**, waits for the result, and writes the file. A new run replaces the files, so a changed image is a changed behaviour.

Regenerate:

```bash
make e2e
```

## What the run proves

| File | Source | Check |
| --- | --- | --- |
| `01-home.png` | none | The page loads, the sidebar lists lanes, and the rule lane is active |
| `02-rules-ticket.png` | Support ticket | The rule lane finds phone, email, and card. `Order 48291` stays out |
| `03-secret-note.png` | Secret note | `<SECRET>` replaces the password. The vault has no secret |
| `04-email-only.png` | Email filter | A request for `EMAIL` returns one email span and no person |
| `05-chinese.png` | Chinese line | A Chinese mobile number and email pass the slice check |
| `06-placeholders.png` | Numbered placeholders | A repeated slice reuses `<EMAIL_1>`. A new slice gets `<EMAIL_2>` |
| `07-long-text.png` | Long text | The start index stays on the full source string |
| `08-empty-state.png` | none | An empty source gives a message, not a call |
| `09-narrow.png` | Support ticket | The layout holds at a 430 pixel width |
| `10-model-lane.png` | Person request | `en-closed` finds a name and the slice check passes |
| `11-copy-json.png` | Support ticket | The copy button writes the span list as JSON |
| `12-score-floor.png` | Support ticket | A caller floor of 0.90 keeps the card and drops the two spans with no score |

The viewport is 1440 by 1000 at a device scale of 2, so the files are 2880 pixels wide. The narrow run uses 430 by 900.

## Reading an image

A green **slice check** card and a green **ok** in each table row mean every span passed `source[start:end] == text`. A red mark is a contract failure, not a style issue. The span table is the review artifact. A masked paragraph alone is not.

A dash in the **Score** column means no validator covers that form. The cell title says so. The library does not fill that gap with a number.
