# Architecture

<!-- ste: descriptive -->

This file explains how the Databricks App demo is built and why each part sits
where it does. The [README](README.md) covers deploy steps and endpoints. The
library's own module map is in [docs/07-architecture.md](../../docs/07-architecture.md).

The app is a thin shell around one promise: **the values in a ticket never reach
the model, and they come back in the answer.**

## 1. Context

Who talks to whom, and what crosses each boundary.

```mermaid
flowchart LR
  subgraph BROWSER["Browser"]
    UI["static/<br/>index.html · app.js · styles.css"]
  end

  subgraph APP["Databricks App · this code"]
    direction TB
    FA["app.py<br/>FastAPI routes"]
    PL["pipeline.py<br/>4 stages"]
    VAULT[("vault<br/>placeholder → value<br/>process memory only")]
  end

  subgraph WS["Databricks workspace"]
    EP["serving endpoint<br/>databricks-gpt-oss-20b"]
    IAM["OAuth<br/>app service principal"]
  end

  UI -- "POST /api/run<br/>source text" --> FA
  FA --> PL
  PL <--> VAULT
  PL -- "masked string only" --> EP
  EP -- "answer with placeholders" --> PL
  PL -- "spans · masked · vault · answer" --> FA
  FA -- "JSON" --> UI
  IAM -. "token for the<br/>service principal" .-> PL

  classDef boundary fill:#1b2436,stroke:#5b8cff,color:#e8edf7
  class APP boundary
  classDef model fill:#2a1f3d,stroke:#b98cff,color:#e8edf7
  class EP model
```

The dashed edge is the reason the browser holds no credential. The app
authenticates as its own service principal, and that identity is what the
endpoint sees.

## 2. The four stages

One request, four stages, in the order that makes the boundary provable.

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant A as app.py
  participant P as pipeline.py
  participant E as edgepii
  participant M as serving endpoint

  B->>A: POST /api/run {source, model, preset}
  A->>P: run(...)
  Note over P: stage 1 · detect
  P->>E: Locator.preset("rules").locate(source)
  E-->>P: spans, each proving source[start:end] == text
  Note over P: stage 2 · mask
  P->>E: redact(source, spans)
  E-->>P: masked string + vault
  Note over P: stage 3 · send
  P->>M: messages with the masked string
  M-->>P: answer, placeholders echoed back
  Note over P: stage 4 · restore
  P->>E: restore(answer, vault, locator)
  E-->>P: restored text, resolved, unresolved, unknown
  P-->>A: payload + timings + gate
  A-->>B: JSON
```

Stage 3 is the only stage that leaves the process. Everything the model can see
is the string `masked`, and stage 2 built it from spans that stage 1 proved.

## 3. Inside stage 2: what the vault holds

The vault is an ordinary dict, and the taxonomy decides what enters it.

```mermaid
flowchart TD
  S["a span on the source"] --> Q{"its class is<br/>irreversible?"}
  Q -- "yes · secret" --> SEAL["placeholder &lt;SECRET&gt;<br/>no vault entry"]
  Q -- "no" --> KEY{"same type and<br/>same text seen?"}
  KEY -- "yes" --> REUSE["reuse the token<br/>&lt;EMAIL_1&gt;"]
  KEY -- "no" --> NEW["new token<br/>&lt;EMAIL_2&gt;"]
  SEAL --> OUT["masked string"]
  REUSE --> OUT
  NEW --> OUT
  NEW --> V[("vault")]
  REUSE --> V

  classDef seal fill:#3d1f2a,stroke:#ff5c8a,color:#ffd0dd
  class SEAL seal
```

Two consequences the demo makes visible:

- A repeated value gets the **same** token, so the model sees one person rather
  than two. The *Repeat values* sample shows this.
- A secret is **sealed**, never vaulted. It cannot be restored, by design. See
  [ADR 0004](../../docs/adr/0004-secrets-irreversible.md).

## 4. The gate

`restore` reports three kinds of leftover, and the app treats them differently.
This is the part that is easy to get wrong.

```mermaid
flowchart TD
  R["placeholder survives<br/>in the answer"] --> K{"was it in the vault?"}
  K -- "no, but we sent it" --> SEALED["sealed<br/>&lt;SECRET&gt; stayed masked<br/>✔ intended"]
  K -- "yes, but it did not resolve" --> UNRES["unresolved<br/>✘ gate fails"]
  R2["PII in the raw answer<br/>the vault never held"] --> UNK["unknown<br/>✘ gate fails"]

  SEALED --> PASS["restore_ok = true"]
  UNRES --> FAIL["restore_ok = false"]
  UNK --> FAIL

  classDef good fill:#12332b,stroke:#35e0b6,color:#c9fff0
  classDef bad fill:#3d1f2a,stroke:#ff5c8a,color:#ffd0dd
  class PASS,SEALED good
  class FAIL,UNRES,UNK bad
```

`outcome.ok` from the library calls `<SECRET>` a failure, because the library
cannot know the caller intended it. The pipeline narrows that: it computes
`sealed` as the tokens it sent that were never in the vault, and fails only on
`unresolved` or `unknown`. Without this, the credential sample reported a false
failure while behaving exactly right.

## 5. Why the server picks the highlighted ranges
The UI marks restored values in the answer. The obvious approach — search the
answer for each vault value — breaks.

```mermaid
flowchart LR
  subgraph BAD["browser string search"]
    A1["answer: 'mail ada@example.com'"] --> A2["indexOf('ada@example.com')"]
    A2 --> A3["wrong range if two<br/>values share a substring"]
  end
  subgraph GOOD["server segments"]
    B1["raw answer"] --> B2["_segments(raw, vault)<br/>mirrors restore's pattern"]
    B2 --> B3["[{kind:text},{kind:value,token}]"]
    B3 --> B4["browser renders spans<br/>no search"]
  end

  classDef bad fill:#3d1f2a,stroke:#ff5c8a,color:#ffd0dd
  classDef good fill:#12332b,stroke:#35e0b6,color:#c9fff0
  class A3 bad
  class B4 good
```

`_segments` runs the same pattern `restore` uses, longest token first, and
records which token produced which range. A test asserts the segments
concatenate to exactly `restore`'s text, so the highlight cannot drift from the
answer.

## 6. Module map

| Module | Owns | Does not own |
| --- | --- | --- |
| `app.py` | Routes, request model, samples, static mount | Detection, masking, model calls |
| `pipeline.py` | The four stages, the gate, timing, segments | HTTP routing, HTML |
| `tutorial.py` | The six tutorial steps, with output from the library | HTTP routing, rendering |
| `architecture_page.py` | Rendering `ARCHITECTURE.md` to HTML | Any second copy of the architecture |
| `static/app.js` | Demo rendering, pickers, copy | Any decision about what is PII |
| `static/tutorial.js` | Tutorial rendering | The examples, which come from `tutorial.py` |
| `static/architecture.js` | Diagram upgrade, source toggle, copy | The document, which comes from `ARCHITECTURE.md` |
| `static/index.html` | Demo structure | Content |
| `static/tutorial.html` | Tutorial structure | Content |
| `static/architecture.html` | Architecture structure | The architecture content |
| `static/styles.css` | One dark surface, per-class colours | Behaviour |
| `app.yaml` | Start command, `EDGEPII_MODELS` | Code |
| `requirements.txt` | Pinned `edgepii`, FastAPI, uvicorn, SDK | Source |

`pipeline.py`, `tutorial.py`, and `architecture_page.py` import no FastAPI, so
`tests/test_app_pipeline.py`, `tests/test_app_tutorial.py`, and
`tests/test_app_architecture.py` exercise all three with no network and no
serving endpoint.

### 6.1 Why the tutorial generates its own examples

The tutorial is the one page where a stale string is actively harmful: a reader
copies the code, runs it, and gets different output than the page promised. So
no output on that page is typed by hand.

```mermaid
flowchart LR
  Q["/api/tutorial"] --> T["tutorial.py<br/>payload()"]
  T --> L["STEPS built at import:<br/>each step calls edgepii"]
  L --> R["output strings are<br/>library return values"]
  R --> P["JSON to the browser"]
  P --> U["static/tutorial.js renders<br/>no transformation"]

  TEST["tests/test_app_tutorial.py"] -. "re-derives every<br/>output from edgepii" .-> R

  classDef gen fill:#12332b,stroke:#35e0b6,color:#c9fff0
  class R,L gen
```

Three properties follow:

- **Offline.** The rule lane needs no weights, so the page builds in
  milliseconds with no credentials. A reader with no Databricks profile still
  gets all six steps.
- **Honest about the one network step.** Step 5 restores a *fixed* model answer
  rather than inventing one, and the page says so. The live endpoint is what the
  demo page is for.
- **Locked by tests.** Each assertion re-derives the value from the library and
  compares it to the page. If a library change alters `redact`, the tutorial test
  fails before the page can go stale.

One step had to be rewritten because of this. Step 3 originally printed
`'hunter2' in the vault: False` to prove the secret was gone, which put the
password on a page explaining that passwords must not be printed. It now prints
two booleans computed against the vault, and a test asserts the secret string is
absent from the output.

## 7. Two runtimes, one code path

The same `pipeline.py` serves a laptop and the app. Only credential discovery
differs.

```mermaid
flowchart TD
  START["pipeline._invoke()"] --> CID{"DATABRICKS_CLIENT_ID<br/>set?"}
  CID -- "yes · Databricks App" --> SP["WorkspaceClient()<br/>app service principal<br/>injected by the runtime"]
  CID -- "no · laptop" --> PROF["WorkspaceClient(profile=...)<br/>from DATABRICKS_PROFILE"]
  SP --> CALL["POST /serving-endpoints/{model}/invocations"]
  PROF --> CALL
  CALL --> RESP{"status"}
  RESP -- "403" --> F["actionable message:<br/>attach the resource / grant CAN_QUERY"]
  RESP -- "200" --> OK["ModelCall"]

  classDef app fill:#1b2436,stroke:#5b8cff,color:#e8edf7
  class SP app
  classDef local fill:#1b2a36,stroke:#22d3ee,color:#e8edf7
  class PROF local
```

This is why the app needs no secret resource. In the app, the runtime provides
the identity. On a laptop, the CLI's cached token does.

A 403 gets its own message because it is the one failure a reader is most likely
to hit, and the generic HTTP error does not say which of the two fixes applies.

## 8. What the app does not do

The demo is honest about its edges, and three of them matter.

| Not done | Why | Where it shows |
| --- | --- | --- |
| Model lanes | They pull torch and a checkpoint at first request, turning a one-minute start into an unbounded download | The sidebar offers `rules` only |
| Person names on the rule lane | `rules` is regex and checksums. A name needs a model | The **The name gap** sample |
| Server-side vault | The demo returns the vault so a reader can see which values came back | `POST /api/run` response |

A production caller keeps the vault server-side and returns only `answer`. That
is a one-line change in `pipeline.run`, and the README says so.

## 9. Local and Databricks side by side

| Concern | Local | Databricks App |
| --- | --- | --- |
| Start | `make app` | `databricks apps deploy` |
| Port | 8000 (override with `PORT`) | 8000, from `app.yaml` |
| Identity | `DATABRICKS_PROFILE` | injected service principal |
| Endpoint grant | the profile needs `CAN_QUERY` | the app resource grants it |
| Source | working tree, `--reload` | a Git commit, resolved and pinned |
| Vault | process memory | process memory |
| Failure to expect | `auth` with a login hint | `forbidden` with a resource hint |

The differences are all in credential discovery and file delivery. The four
stages, the gate, and the payload are identical, which is why the same tests
cover both.

## 10. One Markdown file, three readers
`ARCHITECTURE.md` is read three ways, and none of them restates its content.

```mermaid
flowchart TD
  MD["ARCHITECTURE.md<br/>the only copy"]
  MD --> GH["GitHub renders it<br/>for a reviewer"]
  MD --> PAGE["architecture_page.py<br/>markdown-it-py at import"]
  PAGE --> HTML["/api/architecture<br/>HTML + data-mermaid blocks"]
  HTML --> JS["static/architecture.js<br/>upgrades each block"]
  JS --> CDN{"Mermaid module<br/>loads?"}
  CDN -- "yes" --> SVG["drawn diagram"]
  CDN -- "no" --> SRC["source stays visible<br/>structure still readable"]

  classDef src fill:#1b2436,stroke:#5b8cff,color:#e8edf7
  classDef good fill:#12332b,stroke:#35e0b6,color:#c9fff0
  class MD src
  class SVG,SRC good
```

Two decisions follow from this:

- **The page renders the file, not a copy of it.** A page that restated the
  architecture in its own words would drift from the file the moment either
  changed. `architecture_page.rendered()` reads the deployment's own
  `ARCHITECTURE.md`, so the page cannot disagree with the file.
- **A diagram is an enhancement, not a requirement.** Mermaid loads from a CDN,
  which may be blocked. The source stays on the page underneath, and the page
  says how many diagrams drew. A reader with no CDN access still sees every
  diagram's structure, which is the same rule the repo's docs site follows.

The escaping is the one subtle part. `markdown_it` escapes the fence body, so the
HTML must unescape it before handing the text to Mermaid, or Mermaid receives
`&amp;lt;` and draws it literally. A test asserts each diagram block's text is
byte-identical to the fence in the Markdown file.


## 11. The ML lane

The demo has three detection lanes. They exist because the rule lane has a
documented blind spot: it cannot see a person name.

| Lane | Where it runs | What it costs | Finds a name |
| --- | --- | --- | --- |
| `rules` | in the app process | microseconds | no |
| `ml` | a serving endpoint | one network call | yes |
| `hybrid` | both, merged | one network call | yes, plus proven rule types |

```mermaid
flowchart TD
  S["source text"] --> L{"lane"}
  L -- "rules" --> R["Locator.preset('rules')<br/>regex and checksums"]
  L -- "ml" --> M["/serving-endpoints/edgepii-pii-ml<br/>GLiNER, pretrained"]
  L -- "hybrid" --> BOTH["both, then merge"]
  R --> SPANS["spans that prove<br/>source[start:end] == text"]
  M --> SPANS
  BOTH --> SPANS
  SPANS --> RED["redact → masked + vault"]

  subgraph GUARD["guards on the model answer"]
    G1["slice check:<br/>drop a span whose text<br/>disagrees with its offset"]
    G2["type check:<br/>drop a label the taxonomy<br/>has no policy for"]
  end
  M -.-> GUARD

  classDef ml fill:#2a1f3d,stroke:#b98cff,color:#e8edf7
  class M,BOTH ml
  classDef guard fill:#3d2a1f,stroke:#ffb454,color:#ffe6c7
  class G1,G2 guard
```

### Why a pretrained model, not one trained here

The first attempt trained a character n-gram classifier on the pinned
Nemotron-PII corpus. It reached 0.763 macro F1 and could not see a name built
from parts it had not memorised. The repo already measured the pretrained
alternative: `multi-open`, the GLiNER lane, scored **0.821 exact recall** with
**zero high-severity misses** on the finance slice. Pretrained won on quality,
on effort, and because its errors were already measured rather than newly
produced.

`ml/train_pii_classifier.py` stays in the tree. It is the comparison, and it is
reproducible in under a minute. It is not the lane that ships.

### Why the model is remote

The two earlier model lanes, `en-closed` and `multi-open`, load torch inside the
app process. That turns a one-minute app start into an unbounded checkpoint
download, which is why neither was ever offered in the deployed demo. Serving the
model moves that cost to the endpoint, where it is paid once at deploy time and
then kept warm or scaled to zero.

### The two guards

A remote model is exactly where an unchecked offset would come from, so neither
guard is optional:

1. **Slice check.** `source[start:end]` must equal the span's own text. A span
   that fails is dropped, never repaired. Repair would invent a claim the model
   never made.
2. **Type check.** The label must exist in taxonomy `2026.11`. Without this, an
   unknown label would reach `taxonomy.types[...]` and raise there, far from the
   model that caused it.

Both have tests, and one of them pins the exact two-level JSON envelope the live
endpoint returns, so a future MLflow change fails in the suite rather than in the
deployment.

### What the lane cannot do

The endpoint handles 8,000 characters per call and the app refuses longer input
with a message rather than truncating it. Truncation would silently drop spans,
which is worse than refusing.

### An observed false positive

Honest documentation means naming the errors this lane makes. On the sample

> `Ada Lovelace opened ticket 48291 from +852 5555 0101 …`

the served model labels the ticket number `48291` as `GOV_ID` with score 0.922,
so the masked string becomes `<PERSON_1> opened ticket <GOV_ID_1> …`. That is a
false positive: an order id is not a government id.

Three things follow from it, and none of them is "raise the threshold".

- **A false positive over-masks, which is the safe direction.** The alternative
  error leaves a value in the clear. The demo shows the mask widening rather than
  hiding it.
- **The rule lane would not make this mistake.** It requires an SSN shape and a
  cue. This is the trade the `hybrid` lane cannot resolve by itself: a model can
  over-label what a grammar would reject.
- **`GOV_ID` is `prefer: rule` in the taxonomy.** Merge does not drop the model
  span, because the rule lane found nothing to displace it. Preference decides
  between two spans on the same characters, not whether one exists.

A caller who needs to suppress this has three options, in increasing cost: raise
`EDGEPII_ML_THRESHOLD`, narrow the label list in `ml/serve_gliner.py`, or add a
policy gate that drops a span whose type has no structural validator. The demo
does none of them, because hiding the error would defeat the point of showing a
classifier's real output.

## 12. Deployment

The deploy has one constraint that shapes everything else: **this workspace only
deploys an app from a Git ref.** There is no upload path. A deploy reads the
remote commit, so an unpushed change is not deployed and no error says so.

```mermaid
flowchart TD
  DEV["working tree"] -->|"push"| GH["origin/branch"]
  SCRIPT["scripts/deploy_databricks_app.sh"]

  SCRIPT --> C1{"profile<br/>authenticated?"}
  C1 -- "no" --> STOP1["stop: auth login"]
  C1 -- "yes" --> C2{"origin/branch<br/>== HEAD?"}
  C2 -- "no" --> STOP2["stop: push first"]
  C2 -- "yes" --> C3["create app if absent<br/>Git ref + path"]
  C3 --> C4["attach resources<br/>CAN_QUERY per endpoint"]
  C4 --> C5{"compute<br/>ACTIVE?"}
  C5 -- "no" --> C6["start, poll"]
  C6 --> C5
  C5 -- "yes" --> C7["apps deploy<br/>git_source"]
  GH -.->|"read by"| C7
  C7 --> C8{"--verify?"}
  C8 -- "no" --> DONE["url"]
  C8 -- "yes" --> V1["4 routes 200"]
  V1 --> V2["lanes match<br/>the endpoints"]
  V2 --> V3["one real /api/run<br/>gate must pass"]
  V3 --> DONE

  classDef stop fill:#fbdae4,stroke:#d98a9c,color:#172033
  classDef good fill:#cdf0e4,stroke:#79bfa8,color:#172033
  classDef step fill:#cfe0fb,stroke:#7ea3e0,color:#172033
  class STOP1,STOP2 stop
  class DONE,V3 good
  class C3,C4,C6,C7,V1,V2 step
```

### The five failures worth knowing

Each of these was hit while building the demo, and each produces a message that
does not name its cause on its own.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Git repository is required` | The workspace refuses app creation without one | Pass `git_repository` in the create payload |
| `No command to run` | The app directory is not at the deployed ref | Push, then redeploy; the path is read from the remote |
| `not in RUNNING state` | `apps deploy` needs compute `ACTIVE` | `apps start`, then poll until `ACTIVE` |
| `403` from a run | The service principal lacks `CAN_QUERY` | Attach the endpoint as a resource |
| Deploy `SUCCEEDED`, app broken | Success means the deployment applied, not that the app answers | Run `--verify` |

### Why verification is a separate step

`apps deploy` returns `SUCCEEDED` once the deployment record is written. The app
may still be failing to import, missing an environment variable, or unable to
reach an endpoint. The script therefore makes one real call and asserts the gate
passed, because that is the only check that exercises the whole path: credential
discovery, both endpoints, and the four stages.

### Environment the app reads

| Variable | Effect when unset |
| --- | --- |
| `EDGEPII_MODELS` | Falls back to `databricks-gpt-oss-20b` |
| `EDGEPII_ML_ENDPOINT` | The ML lane disappears; only `rules` is offered |
| `EDGEPII_ML_THRESHOLD` | `0.4` |
| `EDGEPII_ML_WITH_RULES` | `1`, so `hybrid` is offered |

The app starts and serves all three pages with every one of these unset. Only
`/api/run` needs credentials and endpoints, which is what makes the demo readable
before it is deployable.
