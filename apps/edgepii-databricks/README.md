# edgepii as a Databricks App

A working demo of the problem the library exists for: a ticket contains PII, a
model served by Databricks should answer it, and the values must never reach the
endpoint.

```
browser ──▶ Databricks App (this code) ──▶ serving endpoint
              │ 1 detect    edgepii finds typed spans on the source
              │ 2 mask      values become placeholders, vault stays in the app
              │ 3 send      only the masked string crosses the network
              │ 4 restore   placeholders in the answer become the values again
```

The app holds no credential of its own. It runs as the app's service principal,
and the serving endpoint is attached as an app resource, so the token comes from
the runtime.

**[ARCHITECTURE.md](ARCHITECTURE.md)** has the diagrams: context, the four
stages, what the vault holds, how the gate decides, and how one code path serves
a laptop and the app.

## What is deployed

| Path | Role |
| --- | --- |
| `app.py` | FastAPI routes: `/`, `/tutorial`, `/api/config`, `/api/health`, `/api/run`, `/api/tutorial` |
| `pipeline.py` | The four stages. No FastAPI import, so it is testable alone |
| `tutorial.py` | The six tutorial steps, with output produced by the real library |
| `app.yaml` | Start command and `EDGEPII_MODELS` |
| `requirements.txt` | `edgepii==0.5.0` from PyPI, plus FastAPI, uvicorn, the SDK |
| `static/` | The demo page and the tutorial page. Plain HTML, CSS, and JS |
| `ARCHITECTURE.md` | Diagrams and the reasoning behind each boundary |

`tests/test_app_pipeline.py` covers the pipeline with the model call stubbed, so
the suite runs with no network and no serving endpoint.
`tests/test_app_tutorial.py` asserts every tutorial example still matches what
the library returns.

## The tutorial

`/tutorial` is a six-step walkthrough: locate, mask, seal a secret, number
repeated values, restore, and gate the answer. It is a separate page from the
demo because the two answer different questions. The demo shows *the loop
running*; the tutorial shows *what each call returns and why*.

The design constraint is that **no tutorial output is typed by hand.** Every
output string is produced by calling `edgepii` when the page's payload is built,
and `tests/test_app_tutorial.py` re-derives each one from the library. A
tutorial that shows stale output is worse than no tutorial, because a reader
trusts it and then finds the library disagrees.

The tutorial needs no credentials, because the rule lane needs no weights.
A reader with no Databricks profile can read the whole page.


## Deploy

The workspace requires apps to deploy from Git, so the app directory must exist
on the branch being deployed.

```bash
# 1. Create the app, pointed at the repo and this directory.
databricks apps create edgepii-demo \
  --json '{
    "name": "edgepii-demo",
    "description": "edgepii: mask PII before a Databricks model, then restore the answer",
    "git_repository": {
      "provider": "gitHub",
      "url": "https://github.com/raphaelmansuy/edgepii",
      "branch": "main"
    },
    "path": "apps/edgepii-databricks"
  }' \
  --profile opengenie-dev

# 2. Grant the app's service principal permission to query the endpoint.
databricks apps update edgepii-demo \
  --json '{
    "name": "edgepii-demo",
    "resources": [
      {
        "name": "edgepii-model",
        "serving_endpoint": {
          "name": "databricks-gpt-oss-20b",
          "permission": "CAN_QUERY"
        }
      }
    ]
  }' \
  --profile opengenie-dev

# 3. Deploy. The app must be running first.
databricks apps deploy edgepii-demo \
  --json '{"git_source": {"branch": "main", "source_code_path": "apps/edgepii-databricks"}}' \
  --profile opengenie-dev
```

Deploying from Git means a push to `main` is required before step 3 can see this
directory.

## Run locally

The app works on a laptop against the same endpoint. Set a profile and the app
uses the SDK's CLI credentials instead of an app service principal.

```bash
# One command. Uses PROFILE and PORT, defaults shown.
make app PROFILE=opengenie-dev PORT=8000
```

`make app` runs `uvicorn app:app --reload` from the app directory, with
`PYTHONPATH` set to this repo's `src`, so a working copy of the library wins over
the PyPI wheel. That is what you want while changing `src/edgepii`. To test the
**published** version instead, drop the `PYTHONPATH`:

```bash
cd apps/edgepii-databricks
pip install -r requirements.txt
DATABRICKS_PROFILE=opengenie-dev uvicorn app:app --port 8000
```

Either way, the profile needs `CAN_QUERY` on the endpoint. The first failure you
are likely to hit is `auth`; the app tells you to run
`databricks auth login --profile <name>`. The second is `forbidden`; the app
tells you the endpoint grant is missing.

Without a Databricks profile at all, the app still starts and `/api/config`
still answers, so you can read the UI. Only `/api/run` needs credentials.

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/` | The demo page |
| GET | `/tutorial` | The six-step tutorial page |
| GET | `/api/health` | Liveness, version, allowed models |
| GET | `/api/config` | Models, lanes, samples, workspace host. No credentials |
| GET | `/api/tutorial` | Every tutorial step, with output the library produced |
| POST | `/api/run` | All four stages, plus timings and the gate result |

`POST /api/run` takes `{source, model, preset, max_tokens, scan_response}` and
returns `spans`, `masked`, `vault`, `raw_answer`, `answer`, `segments`,
`resolved`, `sealed`, `unresolved`, `unknown`, and `timing`.

`vault` is returned to the browser on purpose: the demo's whole point is to show
which values came back. A production caller keeps the vault server-side and
returns only `answer`.

## The gate

`restore` reports three outcomes, and the app treats them differently:

- **resolved**: a placeholder the vault knew, swapped back. Good.
- **sealed**: `<SECRET>` survived because a secret type is irreversible. The
  value was never in the vault, so this is the intended result, not a failure.
- **unresolved or unknown**: a placeholder we cannot explain, or PII in the raw
  answer that the vault never held. Either one fails the gate.

Turn the response check off in the sidebar to see the difference: `restore` then
runs without a locator and cannot report `unknown`.

## Why the rules lane

The default lane is `rules`, which needs no model weights. The model lanes in
`edgepii.presets` pull torch and a Hugging Face checkpoint at first use, which
turns a one-minute app start into a multi-minute download of uncertain size. The
demo ships the lane that always works. To add a model lane, add the extra to
`requirements.txt`, add the name to `PRESET_ORDER` in `app.py`, and expect a slow
first request while the weights land.

The trade is visible in the **The name gap** sample: rules cannot see a person
name, so `Ada Lovelace` stays in the clear while the phone and email are masked.
That is the documented limit of the rule lane, and the demo shows it rather than
hides it.

## Models

`EDGEPII_MODELS` in `app.yaml` lists what the picker offers:

```
databricks-gpt-oss-20b,databricks-qwen3-next-80b-a3b-instruct,
databricks-meta-llama-3-3-70b-instruct,databricks-gemma-3-12b
```

`gpt-oss-20b` is a reasoning model. It writes hidden reasoning before the answer,
so a small `max_tokens` can return empty `content`. The pipeline asks for
`reasoning_effort: low` on that family and retries once with a 1200-token floor
if the answer still comes back empty.
