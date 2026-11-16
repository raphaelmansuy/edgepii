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
| `app.py` | FastAPI routes: `/`, `/tutorial`, `/architecture`, `/api/*` |
| `pipeline.py` | The four stages and the lane selection |
| `ml_lane.py` | Client for the served GLiNER classifier, with the offset and type guards |
| `tutorial.py` | The six tutorial steps, with output produced by the real library |
| `architecture_page.py` | Renders `ARCHITECTURE.md` into the app |
| `app.yaml` | Start command, models, and the ML lane settings |
| `requirements.txt` | `edgepii==0.5.0` from PyPI, plus FastAPI, uvicorn, the SDK |
| `static/` | The demo, tutorial, and architecture pages. No build step |
| `ARCHITECTURE.md` | The document the `/architecture` page renders |

`tests/test_app_pipeline.py` covers the pipeline with the model call stubbed.
`tests/test_app_ml_lane.py` covers the served classifier's contract with the
endpoint stubbed. `tests/test_app_tutorial.py` re-derives every tutorial example
from the library. `tests/test_app_architecture.py` asserts every diagram reaches
the browser byte-identical to the Markdown. None of them needs the network.

## The four lanes

| Lane | Where detection runs | Finds a person name |
| --- | --- | --- |
| `rules` | in the app process | no |
| `ml` | `edgepii-pii-ml` serving endpoint | yes |
| `hybrid` | both, merged through the library policy | yes |

`rules` needs no weights and no network. `ml` calls a pretrained GLiNER
classifier served by this workspace, so the app holds no torch and no checkpoint.
`hybrid` unions the two and lets the library decide overlaps, so the rule lane
keeps precedence on the types the taxonomy marks `prefer: rule`.

The lane is independent of the model choice: detecting PII and writing a reply
are different jobs, and the UI selects them separately.

### Why pretrained GLiNER

A classifier trained here reached 0.763 macro F1 and could not see a name it had
not memorised a prefix of. The repo's own measurement of the pretrained lane is
0.821 exact recall with zero high-severity misses on the finance slice. The
trained comparison stays in `ml/train_pii_classifier.py`; it is not what ships.

### Reproducing it

```bash
# 1. Log and register the model in Unity Catalog.
python ml/serve_gliner.py --register          # needs gliner>=0.2.30

# 2. Serve it, then set EDGEPII_ML_ENDPOINT in app.yaml.
databricks serving-endpoints create --json '{
  "name": "edgepii-pii-ml",
  "config": {"served_entities": [{
    "entity_name": "workspace.default.edgepii_pii_gliner",
    "entity_version": "2",
    "workload_size": "Small",
    "scale_to_zero_enabled": true
  }]}
}'

# 3. Deploy. Attach the endpoint as an app resource with CAN_QUERY.
```

Unsetting `EDGEPII_ML_ENDPOINT` drops the app back to the rules lane alone, so the
demo never depends on the endpoint being reachable to start.


## The three pages

| Page | Question it answers |
| --- | --- |
| `/` | What does the loop do against a real model? |
| `/tutorial` | What does each call return, and why? |
| `/architecture` | How is it built, and why this way? |

Each links to the other two, so a reader can move from seeing it run, to
understanding a call, to understanding the design.

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
on the branch being deployed. One script does the whole procedure:

```bash
# Deploy the current branch and verify it.
./scripts/deploy_databricks_app.sh --profile opengenie-dev --verify

# See every command without running it.
./scripts/deploy_databricks_app.sh --profile opengenie-dev --dry-run
```

The script checks credentials, refuses to run when the branch is ahead of
`origin` (a Git deploy reads the remote, not your working tree), builds the
endpoint resources, starts compute, deploys, and then proves the result: the four
routes, the lanes the app advertises, and one end-to-end call through the ML lane.

`--verify` is the part worth having. A deploy reports `SUCCEEDED` before the app
can actually answer, so a green deploy is not evidence. The verification step
calls `/api/run` and fails if the gate does not pass.

### What the script does, step by step

| Step | Why it exists |
| --- | --- |
| Check the profile | An expired token fails later, after compute minutes are spent |
| Check `origin` is at HEAD | A Git deploy ships the remote commit, so an unpushed change is invisible |
| Create or find the app | Creation is idempotent, so a re-run is safe |
| Attach resources | A missing `CAN_QUERY` fails at runtime with a 403 that does not name the cause |
| Start compute | `apps deploy` refuses to run unless compute is `ACTIVE` |
| Deploy | Pins the resolved commit in the response, so the deployed code is known |
| Verify | Proves the app answers, and that the configured lanes are real |

### Deploying by hand

The script is the recommendation, but the underlying calls are short enough to
run directly. Note that `apps update` requires the git repository in the same
payload as the resources in this workspace:

```bash
databricks apps create --json '{
  "name": "edgepii-demo",
  "git_repository": {"provider": "gitHub",
                     "url": "https://github.com/raphaelmansuy/edgepii",
                     "branch": "main"},
  "path": "apps/edgepii-databricks"
}' --profile opengenie-dev

databricks apps update edgepii-demo --json '{
  "name": "edgepii-demo",
  "git_repository": {"provider": "gitHub",
                     "url": "https://github.com/raphaelmansuy/edgepii"},
  "resources": [
    {"name": "edgepii-model", "serving_endpoint":
      {"name": "databricks-gpt-oss-20b", "permission": "CAN_QUERY"}},
    {"name": "edgepii-ml-detector", "serving_endpoint":
      {"name": "edgepii-pii-ml", "permission": "CAN_QUERY"}}
  ]
}' --profile opengenie-dev

databricks apps deploy edgepii-demo --json '{
  "git_source": {"branch": "main",
                 "source_code_path": "apps/edgepii-databricks"}
}' --profile opengenie-dev
```

Deploying from Git means a push to `main` is required before `apps deploy` can
see this directory. See [ARCHITECTURE.md](ARCHITECTURE.md#12-deployment) for the
diagram and the failure modes.

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
| GET | `/architecture` | The architecture page, rendered from `ARCHITECTURE.md` |
| GET | `/api/health` | Liveness, version, allowed models |
| GET | `/api/config` | Models, lanes, samples, workspace host. No credentials |
| GET | `/api/tutorial` | Every tutorial step, with output the library produced |
| GET | `/api/architecture` | The architecture document as HTML, one block per diagram |
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
