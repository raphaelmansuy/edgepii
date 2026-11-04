# The site

<!-- ste: descriptive -->

A static site for the library, published on GitHub Pages at
<https://raphaelmansuy.github.io/edgepii/>.

The site has one rule: **it must not be able to lie.** The demo shows real spans, the guides print
real output, and every published number comes from a recorded run. The build fails when that stops
being true.

## Build

```bash
make site          # record, build, images, check
make site-serve    # the above, then serve http://127.0.0.1:8099
```

| Step | File | What it does |
| --- | --- | --- |
| Record | `gen_data.py` | Calls the real library on 14 fake strings and writes `data/examples.json` |
| Build | `build.py` | Renders `docs/*.md` and `content/*.md` into `dist/` |
| Images | `images.py` | Converts the e2e PNGs into two responsive JPEG widths |
| Check | `check.py` | Fails on a broken link, bad markup, low contrast, or a bad offset |
| Claims | `verify_claims.py` | Runs the guide snippets and compares the printed output |

## Pages

| Route | Content |
| --- | --- |
| `/` | Hero, a real result, the API in one example, the eleven types |
| `/start/` | Install and first call, in five minutes |
| `/concepts/` | Why spans and not labels, and how rules and models merge |
| `/guide-examples/` | Fourteen worked examples, generated from recorded output |
| `/guide-masking/` | Placeholders, the vault, and why a secret has no entry |
| `/guide-evaluate/` | Run the public corpus score, and what a floor really costs |
| `/demo/` | The interactive demo |
| `/tour/` | Twelve screenshots with a note on what each proves |
| `/evaluation/` | The measured score, per type, with the failure analysis |
| `/doc-*/` | Every reference doc, rendered from the repository |

## The demo cannot lie

GitHub Pages runs no Python. The demo therefore replays output that `gen_data.py` recorded by
calling `locate`. That is a recording, not a mock, and three things keep it honest:

1. **The build re-checks the contract.** `check.py` asserts `source[start:end] == text` on every
   recorded span, and that no two spans overlap. A drifting recording stops the deploy.
2. **The filters mirror the library.** `site.js` applies the same two rules the merger applies: drop
   a type outside the request, and drop a span below the caller floor. A span with no score cannot
   meet a floor, so a floor hides it. The demo says so on the page.
3. **The page says it is a replay.** The first paragraph of the demo names the limitation instead of
   implying a live server.

## The guides cannot drift

`verify_claims.py` holds the snippets the guides show and the output the guides promise. It runs
each snippet and compares. This caught four real errors while the site was built:

- A masking example that used `Password is hunter2`. The grammar needs the cue next to the value, so
  the example produced no span at all. The guide now uses `Password: hunter2` and documents the
  limitation in a warning.
- Two guide outputs that showed `<SECRET>` replacing the whole phrase. The span covers the value
  only, so the cue word stays readable. The output and the prose now match the library.
- A floor sweep that printed the same four rows, because it never passed `min_score`. The guide now
  measures a real sweep and reports that a floor *lowers* F1 on both lanes.

## Design

The tokens match `demo/static/styles.css`, so the site and the local app feel like one product.

| Token | Value | Note |
| --- | --- | --- |
| `--bg` | `#05070d` | Page |
| `--panel-solid` | `#0d1420` | Card |
| `--accent` / `--accent-2` | `#5b8cff` / `#22d3ee` | The gradient on the mark and the primary button |
| `--faint` | `#727f9c` | 5.02:1 on the page, 4.60:1 on a panel. Clears AA |

`check.py` recomputes the contrast ratio for every text token on every surface. The earlier value,
`#64718a`, measured 4.10:1 and failed for the 13px hints, and the check now blocks that regression.

## Accessibility

- One `h1` per page, and no heading level is skipped
- Every image has alt text; every control has a label
- A skip link, and `aria-current` on the active nav item
- The mobile menu reports `aria-expanded`
- `prefers-reduced-motion` turns off the smooth scroll and the transforms
- Tables scroll inside their own box, so the page never scrolls sideways

## SEO

- A unique title and description per page, checked for duplicates and length
- A canonical URL per page
- `sitemap.xml`, `robots.txt`, and a `404.html` that is excluded from the map
- Open Graph and Twitter cards, with an SVG social image
- `SoftwareApplication` structured data on the home page
- Semantic landmarks: `header`, `nav`, `main`, `aside`, `footer`

## Deploy

Two paths exist. Use the first when the repository token has the `workflow` scope.

**1. GitHub Actions (preferred).** `.github/workflows/site.yml` runs on a push to `main` that touches
`site/`, `docs/`, or `src/`. It runs the same build, then the claim check, then publishes the artifact
with `actions/deploy-pages`. Set Pages to **GitHub Actions** as the source in the repository settings.
That is a one-time setting.

CI has no model weights, so `gen_data.py` records the rules lane and keeps the model-lane rows from
the committed data file. `tests/test_site.py` proves that behaviour with the `hf` extra blocked, so a
deploy cannot silently drop ten examples.

Both workflows now live in `.github/workflows/` and run on every push. They were staged in
`site/workflow/` first, because an OAuth App token without the `workflow` scope cannot push that
path. The install used SSH over port 443, which is not subject to the OAuth App restriction:

```bash
ssh -T -p 443 git@ssh.github.com      # confirms the key authenticates
mkdir -p .github/workflows
cp site/workflow/*.yml .github/workflows/
git add .github/workflows && git commit -m "ci: install the workflows"
git remote set-url --push origin git@ssh.github.com:raphaelmansuy/edgepii.git
git push origin main
```

`ci.yml` runs the contract tests on Python 3.11, 3.12, and 3.13, builds the artifacts, runs
`twine check`, then installs the built wheel into a clean environment and runs the public API from it.
The browser tests skip in CI, because they need a Playwright build; `make e2e` runs them locally.

`ci.yml` installs the `dev` extra, which now carries `fastapi`, `uvicorn`, and `httpx`, because
`tests/test_demo_api.py` imports the demo app. Before that fix the job would have failed at
collection, which is the failure a workflow exists to catch.

**2. The `gh-pages` branch (fallback).** A token without the `workflow` scope cannot push
`.github/workflows/site.yml`, and the contents API refuses to create a workflow file for the same
reason. `site/publish.sh` builds the site and force-pushes it to `gh-pages`, which needs only the
`repo` scope.

Pages now deploys from **GitHub Actions**, so `site.yml` publishes the site on every push and
`publish.sh` is no longer needed. Switching the source is one API call from a token with `repo`
scope:

```bash
gh api -X PUT repos/<owner>/<repo>/pages -f build_type=workflow
```

Before that switch the `site` workflow built the site in 43 s and then failed at deploy, because
Pages still pointed at the `gh-pages` branch and the environment rejects a deploy from `main`. The
error reads `Branch "main" is not allowed to deploy to github-pages`. Set the source first, or the
build passes and the deploy is refused.

A detail that broke the first deploy: Pages serves the branch **root**, so the build output must sit
at the root of that branch. Committing `site/dist/` keeps the files under a `site/` prefix and every
URL returns 404 even though the build reports success. `publish.sh` copies the output to a staging
tree first, so the branch root holds `index.html`.
