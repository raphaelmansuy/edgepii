"""Build the static site into `site/dist`.

The docs in `docs/` are the source of truth. This script renders them, adds the
guide pages, and emits one self-contained page per route. No framework, no
network call, and no runtime dependency: the output is plain HTML, CSS, and one
small script.

Run: `python site/build.py`
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "dist"
DOCS = ROOT / "docs"
STATIC = HERE / "static"
DATA = HERE / "data" / "examples.json"
SHOTS = DOCS / "e2e" / "screenshots"

sys.path.insert(0, str(HERE))
import author  # noqa: E402
import examples_page  # noqa: E402
import links  # noqa: E402
import mdrender  # noqa: E402

SITE_NAME = "edgepii"
# GitHub project pages serve from a subpath. Every asset path is relative so the
# same build works on a user site, a project site, and a local file open.
SITE_URL = "https://raphaelmansuy.github.io/edgepii/"
REPO = "https://github.com/raphaelmansuy/edgepii"
REPO_RAW = "https://github.com/raphaelmansuy/edgepii/raw/main/"

# (route, source doc, nav title, nav group, description)
GUIDE_PAGES: list[tuple[str, str, str, str, str]] = [
    ("start", "START.md", "Get started", "Tutorial", "Install edgepii and locate your first PII span in five minutes."),
    ("concepts", "CONCEPTS.md", "How it works", "Tutorial", "Why the library returns character spans, and how rules and models combine."),
    ("guide-masking", "GUIDE-MASKING.md", "Mask and restore", "Tutorial", "Replace spans with placeholders, keep a vault, and keep secrets out of it."),
    ("guide-evaluate", "GUIDE-EVALUATE.md", "Score it yourself", "Tutorial", "Run the public PII corpus score and read the report."),
    ("doc-index", "docs/README.md", "Reference", "Docs", "The full specification: problem, contract, API, taxonomy, and evaluation."),
]

# Docs that get a page. The order is the reading order.
REFERENCE_DOCS = [
    ("doc-span-contract", "01-span-contract.md", "The span contract"),
    ("doc-first-principles", "02-first-principles.md", "First principles"),
    ("doc-api", "06-library-api.md", "Library API"),
    ("doc-taxonomy", "10-taxonomy.md", "Taxonomy 2026.11"),
    ("doc-evaluation", "09-evaluation.md", "Evaluation"),
    ("doc-corpora", "12-public-corpora.md", "Public corpora"),
    ("doc-score", "13-first-public-score.md", "First public score"),
    ("doc-assessment", "14-assessment-2026-11.md", "Assessment, November 2026"),
    ("doc-architecture", "07-architecture.md", "Architecture"),
    ("doc-ai-engineering", "03-ai-engineering.md", "AI engineering"),
    ("doc-landscape", "04-research-landscape.md", "Research landscape"),
    ("doc-catalog", "05-model-catalog.md", "Model catalog"),
    ("doc-plan", "08-implementation-plan.md", "Implementation plan"),
    ("doc-why", "00-five-whys.md", "Five whys"),
    ("doc-glossary", "glossary.md", "Glossary"),
]


def main() -> int:
    if not DATA.is_file():
        print("error: run `python site/gen_data.py` first", file=sys.stderr)
        return 2
    # Remove the generated pages and assets, but keep `shots/`. That directory
    # holds converted images, which take a few seconds to rebuild and do not
    # depend on the Markdown. Wiping them would break a build that runs the
    # checks after another build, which is what the test suite does.
    for path in OUT.iterdir() if OUT.exists() else []:
        if path.name == "shots":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "shots").mkdir(parents=True, exist_ok=True)

    data = json.loads(DATA.read_text(encoding="utf-8"))
    write_assets()

    pages = build_pages(data)
    for page in pages:
        route = page["route"]
        target = OUT / ("index.html" if route == "" else f"{route}/index.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page["html"], encoding="utf-8")

    (OUT / "404.html").write_text(build_404(data), encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8"
    )
    (OUT / "sitemap.xml").write_text(build_sitemap(pages), encoding="utf-8")
    (OUT / "site.webmanifest").write_text(
        json.dumps(
            {
                "name": "edgepii \u2014 typed character spans",
                "short_name": "edgepii",
                "description": "Locate PII as typed character spans on the exact source string.",
                "start_url": "./",
                "scope": "./",
                "display": "standalone",
                "background_color": "#05070d",
                "theme_color": "#05070d",
                "lang": "en",
                "categories": ["developer", "productivity", "utilities"],
                "icons": [
                    {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {
                        "src": "icons/icon-maskable-192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                    {
                        "src": "icons/icon-maskable-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                    {"src": "favicon.svg", "sizes": "any", "type": "image/svg+xml"},
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    # GitHub Pages runs Jekyll unless this file exists. Without it, `_` paths drop.
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    print(f"built {len(pages)} pages into {OUT}")
    return 0


# ---------------------------------------------------------------- assets


def write_assets() -> None:
    css = read(STATIC / "site.css")
    css += "\n" + mdrender.code_css() + "\n"
    (OUT / "assets" / "site.css").write_text(css, encoding="utf-8")
    (OUT / "assets" / "site.js").write_text(read(STATIC / "site.js"), encoding="utf-8")
    (OUT / "assets" / "examples.json").write_bytes(DATA.read_bytes())

    # The icon set. `site/icons.py` writes these; the build only copies them, so a
    # page never points at a file that does not exist.
    icons = STATIC / "icons"
    if not icons.is_dir() or not any(icons.iterdir()):
        raise SystemExit("error: no icons. Run `python site/icons.py` first.")
    (OUT / "icons").mkdir(parents=True, exist_ok=True)
    for image in sorted(icons.iterdir()):
        if image.is_file():
            shutil.copy2(image, OUT / "icons" / image.name)
    # A legacy browser asks for `/favicon.ico` with no path help, so it sits at the root.
    shutil.copy2(icons / "favicon.ico", OUT / "favicon.ico")
    shutil.copy2(STATIC / "favicon.svg", OUT / "favicon.svg")

    # Author, book, and project artwork. Small, static, and part of the page.
    for folder in ("author", "book", "projects"):
        source_dir = STATIC / folder
        if not source_dir.is_dir():
            raise SystemExit(f"error: missing {source_dir}")
        (OUT / "assets" / folder).mkdir(parents=True, exist_ok=True)
        for image in sorted(source_dir.iterdir()):
            if image.is_file():
                shutil.copy2(image, OUT / "assets" / folder / image.name)

    # The social card. Raster, because most link previews will not draw an SVG.
    social = STATIC / "social.png"
    if not social.is_file():
        raise SystemExit("error: no social card. Run `python site/social.py` first.")
    shutil.copy2(social, OUT / "assets" / "social.png")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- pages


def build_pages(data: dict) -> list[dict]:
    pages: list[dict] = []
    pages.append(
        {
            "route": "",
            "html": page(
                data,
                route="",
                title="edgepii · find PII as character spans",
                description=(
                    "A Python library that finds personally identifiable information as typed "
                    "character spans on the exact string you passed. Local weights, no cloud PII service."
                ),
                body=home_body(data),
                active="",
                jsonld=home_jsonld(data),
                hero=True,
            ),
        }
    )
    pages.append(
        {
            "route": "demo",
            "html": page(
                data,
                route="demo",
                title="Live demo · edgepii",
                description=(
                    "Try edgepii on fake text. Pick a lane, filter the types, and read the "
                    "character spans, the masked string, and the vault."
                ),
                body=demo_body(data),
                active="demo",
                jsonld=None,
                hero=False,
            ),
        }
    )
    pages.append(
        {
            "route": "guide-examples",
            "html": page(
                data,
                route="guide-examples",
                title="Fifteen worked examples · edgepii",
                description=(
                    "Fifteen worked examples with real edgepii output: spans, masked text, "
                    "vault, and the offset proof for each one."
                ),
                body=f'<main class="examples-page">{examples_page.build(data)}</main>',
                active="guide-examples",
                jsonld=None,
                hero=False,
            ),
        }
    )
    pages.append(
        {
            "route": "about",
            "html": page(
                data,
                route="about",
                title="About the author \u00b7 edgepii",
                description=(
                    "Raphael Mansuy wrote edgepii: data engineering and AI strategist, "
                    "author of a data integration book, ranked 12 in Favikon Top AI "
                    "Experts in France."
                ),
                body=f'<div class="author-page">{author.section(relative_prefix("about"))}</div>',
                active="about",
                jsonld={"@context": "https://schema.org", "@graph": [author.jsonld()]},
                hero=False,
            ),
        }
    )
    pages.append(
        {
            "route": "tour",
            "html": page(
                data,
                route="tour",
                title="Screenshot tour · edgepii",
                description=(
                    "Every screen of the edgepii demo, with a note on what each screen proves."
                ),
                body=tour_body(),
                active="tour",
                jsonld=None,
                hero=False,
            ),
        }
    )
    pages.append(
        {
            "route": "evaluation",
            "html": page(
                data,
                route="evaluation",
                title="Public score · edgepii",
                description=(
                    "Exact-span F1 for edgepii on two pinned public PII corpora, with the "
                    "label fold and the failure analysis."
                ),
                body=evaluation_body(data),
                active="evaluation",
                jsonld=None,
                hero=False,
            ),
        }
    )

    for route, source, title, _group, description in GUIDE_PAGES:
        path = HERE / "content" / source if not source.startswith("docs/") else ROOT / source
        markdown = read(path)
        body = (
            '<article class="prose">'
            f"{mdrender.render(links.rewrite(markdown))}"
            "</article>"
            f"{page_nav(route)}"
        )
        pages.append(
            {
                "route": route,
                "html": page(
                    data,
                    route=route,
                    title=f"{title} · edgepii",
                    description=description,
                    body=body,
                    active=route,
                    jsonld=None,
                    hero=False,
                    toc=mdrender.headings(markdown),
                ),
            }
        )

    for route, source, title in REFERENCE_DOCS:
        path = DOCS / source
        if not path.is_file():
            print(f"warning: missing {path}", file=sys.stderr)
            continue
        markdown = read(path)
        body = (
            '<article class="prose">'
            f"{mdrender.render(links.rewrite(markdown))}"
            "</article>"
            f"{page_nav(route)}"
        )
        pages.append(
            {
                "route": route,
                "html": page(
                    data,
                    route=route,
                    title=f"{title} · edgepii",
                    description=f"edgepii reference: {title}.",
                    body=body,
                    active=route,
                    jsonld=None,
                    hero=False,
                    toc=mdrender.headings(markdown),
                ),
            }
        )
    return pages


def page(
    data: dict,
    *,
    route: str,
    title: str,
    description: str,
    body: str,
    active: str,
    jsonld: dict | None,
    hero: bool,
    toc: list[tuple[int, str, str]] | None = None,
) -> str:
    prefix = relative_prefix(route)
    taxonomy = data["taxonomy_version"]
    canonical = SITE_URL + ("" if route == "" else f"{route}/")
    nav = nav_html(active, prefix)
    toc_html = toc_sidebar(toc) if toc else ""
    structured = (
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        if jsonld
        else ""
    )
    og_image = f"{SITE_URL}assets/social.png"
    body_class = "page-home" if hero else "page-doc"
    breadcrumb_tag = breadcrumb_jsonld(route, title, canonical)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}" />
<link rel="canonical" href="{canonical}" />
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1" />
<meta name="author" content="Raphael Mansuy" />
<meta name="keywords" content="PII detection, personally identifiable information, Python, character spans, data masking, redaction, NER, privacy, edgepii" />
<meta name="color-scheme" content="dark light" />
<meta name="theme-color" content="#05070d" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="edgepii" />
<meta property="og:locale" content="en_US" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(description)}" />
<meta property="og:url" content="{canonical}" />
<meta property="og:image" content="{og_image}" />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="edgepii: typed character spans on the exact source string, with a span row that proves source[start:end] equals text." />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{esc(title)}" />
<meta name="twitter:description" content="{esc(description)}" />
<meta name="twitter:image" content="{og_image}" />
<meta name="twitter:image:alt" content="edgepii: typed character spans on the exact source string." />
<link rel="icon" href="{prefix}favicon.ico" sizes="32x32" />
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="{prefix}icons/apple-touch-icon.png" sizes="180x180" />
<link rel="manifest" href="{prefix}site.webmanifest" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="{prefix}assets/site.css" />
<link rel="alternate" type="application/json" href="{prefix}assets/examples.json" title="Recorded span output" />
{structured}
{breadcrumb_tag}
<script src="{prefix}assets/site.js" defer></script>
</head>
<body class="{body_class}">
<a class="skip" href="#main">Skip to content</a>
<div class="aurora" aria-hidden="true"></div>
<header class="site-head">
  <a class="brand" href="{prefix}" aria-label="edgepii home">
    <span class="mark" aria-hidden="true">{MARK_INLINE}</span>
    <span class="brand-text"><strong>edgepii</strong><small>typed character spans</small></span>
  </a>
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav" data-nav-toggle>
    <span aria-hidden="true">☰</span><span class="sr">Menu</span>
  </button>
  {nav}
  <div class="head-meta">
    <span class="pill" title="Taxonomy version">taxonomy {taxonomy}</span>
    <a class="pill ghost-pill" href="{REPO}" target="_blank" rel="noopener noreferrer">GitHub</a>
  </div>
</header>
<div class="shell">
  {toc_html}
  <main id="main" class="main">
{body}
  </main>
</div>
<footer class="site-foot">
  <div class="foot-grid">
    <div>
      <strong>edgepii</strong>
      <p>Locate PII as typed character spans on the exact source string. Apache-2.0.</p>
    </div>
    <nav aria-label="Footer">
      <a href="{prefix}start/">Install</a>
      <a href="{prefix}demo/">Live demo</a>
      <a href="{prefix}tour/">Screenshots</a>
      <a href="{prefix}evaluation/">Score</a>
      <a href="{prefix}doc-index/">Reference</a>
      <a href="{prefix}about/">About the author</a>
      <a href="{REPO}" target="_blank" rel="noopener noreferrer">Source</a>
    </nav>
  </div>
  <p class="foot-note">Every example string on this site is fake. Do not paste real personal data into a demo.</p>
</footer>
</body>
</html>
"""


def relative_prefix(route: str) -> str:
    # `404.html` sits at the site root, like `index.html`.
    if route in ("", "404"):
        return ""
    return "../" * (route.count("/") + 1)


def nav_html(active: str, prefix: str) -> str:
    items = [
        ("", "Home", "home"),
        ("start", "Install", "start"),
        ("concepts", "How it works", "concepts"),
        ("guide-examples", "Examples", "guide-examples"),
        ("demo", "Live demo", "demo"),
        ("tour", "Screenshots", "tour"),
        ("evaluation", "Score", "evaluation"),
        ("doc-index", "Reference", "doc-index"),
        ("about", "About", "about"),
    ]
    links = []
    for route, label, key in items:
        current = ' aria-current="page"' if active == key else ""
        href = f"{prefix}{route}/" if route else (prefix or "./")
        links.append(f'<a href="{href}" data-nav="{key}"{current}>{label}</a>')
    return f'<nav id="site-nav" class="site-nav" aria-label="Main">{"".join(links)}</nav>'


def toc_sidebar(toc: list[tuple[int, str, str]]) -> str:
    rows = [row for row in toc if 1 < row[0] <= 3]
    if len(rows) < 3:
        return ""
    items = "".join(
        f'<li class="toc-l{level}"><a href="#{anchor}">{esc(text)}</a></li>'
        for level, anchor, text in rows
    )
    return (
        '<aside class="toc" aria-label="On this page">'
        '<p class="toc-title">On this page</p>'
        f'<ul>{items}</ul>'
        "</aside>"
    )


def page_nav(route: str) -> str:
    order = [row[0] for row in GUIDE_PAGES] + [row[0] for row in REFERENCE_DOCS]
    if route not in order:
        return ""
    index = order.index(route)
    previous = order[index - 1] if index > 0 else None
    following = order[index + 1] if index + 1 < len(order) else None
    titles = {row[0]: row[2] for row in GUIDE_PAGES}
    titles.update({row[0]: row[2] for row in REFERENCE_DOCS})
    parts = ['<nav class="page-nav" aria-label="Page">']
    if previous:
        parts.append(f'<a class="page-nav-link" href="../{previous}/"><span>Previous</span>{esc(titles[previous])}</a>')
    if following:
        parts.append(f'<a class="page-nav-link next" href="../{following}/"><span>Next</span>{esc(titles[following])}</a>')
    parts.append("</nav>")
    return "".join(parts)


def build_sitemap(pages: list[dict]) -> str:
    rows = []
    for page_row in pages:
        route = page_row["route"]
        location = SITE_URL + ("" if route == "" else f"{route}/")
        priority = "1.0" if route == "" else "0.8" if route in ("demo", "start") else "0.6"
        rows.append(
            f"  <url><loc>{location}</loc><changefreq>monthly</changefreq><priority>{priority}</priority></url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )


def build_404(data: dict) -> str:
    body = """<section class="hero short">
  <p class="eyebrow">404</p>
  <h1>That page does not exist</h1>
  <p class="lede">The link may be old, or a type name may have moved. Try one of these.</p>
  <div class="cta-row">
    <a class="button primary" href="./">Home</a>
    <a class="button" href="demo/">Live demo</a>
    <a class="button" href="doc-index/">Reference</a>
  </div>
</section>"""
    return page(
        data,
        route="404",
        title="Page not found · edgepii",
        description="This page does not exist.",
        body=body,
        active="",
        jsonld=None,
        hero=False,
    )


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def score_cell(score: float | None) -> str:
    """A dash is a fact, not a gap. It means no validator covers the form."""

    return "—" if score is None else f"{score:.2f}"


# ---------------------------------------------------------------- bodies


def home_body(data: dict) -> str:
    example = next(row for row in data["examples"] if row["id"] == "support-ticket")
    lane = example["lanes"]["rules"]
    spans = lane["spans"]
    tax = {row["name"]: row for row in data["types"]}

    highlight = render_highlight(example["text"], spans)

    span_rows = "\n".join(
        f"<tr><td>{esc(span['type'])}</td><td>{span['start']}</td><td>{span['end']}</td>"
        f"<td><code>{esc(span['text'])}</code></td><td>{score_cell(span['score'])}</td></tr>"
        for span in spans
    )

    type_chips = "".join(
        f'<li><span class="dot" data-class="{row["class"]}"></span>'
        f'<code>{esc(row["name"])}</code><small>{esc(row["class"])}</small></li>'
        for row in data["types"]
    )

    return f"""<section class="hero">
  <p class="eyebrow">Python library · Apache-2.0 · local weights</p>
  <h1>Know exactly which characters are personal data.</h1>
  <p class="lede">
    <strong>edgepii</strong> finds personally identifiable information as typed character spans on the
    string you passed in. Every result row proves one thing:
    <code>source[start:end] == text</code>. If a detector returns an offset that fails that check,
    the library drops the span and counts it. It never searches the string for a repair.
  </p>
  <div class="cta-row">
    <a class="button primary" href="start/">Install in 5 minutes</a>
    <a class="button" href="demo/">Try the live demo</a>
    <a class="button quiet" href="tour/">See screenshots</a>
  </div>
  <ul class="hero-facts">
    <li><strong>11</strong><span>public types</span></li>
    <li><strong>1</strong><span>model pass per call</span></li>
    <li><strong>0</strong><span>cloud PII services</span></li>
    <li><strong>2</strong><span>pinned public corpora</span></li>
  </ul>
</section>

<section class="panel-block" aria-labelledby="try-title">
  <div class="block-head">
    <h2 id="try-title">What it returns</h2>
    <p class="hint">Real output from the <code>rules</code> lane. No weights, no network.</p>
  </div>
  <div class="split">
    <div>
      <p class="label">Source</p>
      <div class="highlight" aria-label="Source with spans marked">{highlight}</div>
      <p class="label">Masked</p>
      <pre class="masked">{esc(lane["masked"])}</pre>
    </div>
    <div>
      <p class="label">Span table</p>
      <div class="table-wrap">
        <table class="docs-table compact">
          <thead><tr><th>Type</th><th>Start</th><th>End</th><th>Text</th><th>Score</th></tr></thead>
          <tbody>{span_rows}</tbody>
        </table>
      </div>
      <p class="hint">A dash means no checksum covers that form, so the library reports no score.
      It does not invent a probability. <code>Order 48291</code> stays clear because an internal id is
      not in the type list.</p>
    </div>
  </div>
</section>

<section class="value-grid">
  <article class="value-card">
    <h3>Offsets you can check</h3>
    <p>A span is a slice of your string, not a sentence a model rewrote. You can assert it in a test
    and diff it in a review.</p>
  </article>
  <article class="value-card">
    <h3>Rules beside models</h3>
    <p>Email, phone, card, IBAN, and IP follow a published grammar or checksum. Names need a model.
    The preset runs both and merges the results.</p>
  </article>
  <article class="value-card">
    <h3>Secrets stay gone</h3>
    <p>A password is masked irreversibly and never enters the vault. Restoring it would leak the
    credential into the next system.</p>
  </article>
  <article class="value-card">
    <h3>Measured in public</h3>
    <p>Two pinned corpora with a <code>sha256</code> each. Exact-span F1 per type, with the misses
    counted. See the <a href="evaluation/">score</a>.</p>
  </article>
</section>

<section class="panel-block">
  <div class="block-head">
    <h2>The whole API in one example</h2>
    <p class="hint">Three calls: build a locator, locate spans, mask them.</p>
  </div>
  <div class="code-sample">{code_block(QUICKSTART_CODE, "python")}</div>
</section>

<section class="panel-block">
  <div class="block-head">
    <h2>Eleven public types</h2>
    <p class="hint">One YAML file is the only type list. Rank breaks an overlap.</p>
  </div>
  <ul class="type-chips">{type_chips}</ul>
</section>

<section class="author-strip">
  <img src="assets/author/raphael-mansuy.jpg" alt="Headshot of Raphael Mansuy, author of edgepii."
       width="72" height="72" loading="lazy" decoding="async" />
  <div>
    <p class="author-strip-name">Built by <strong>Raphael Mansuy</strong></p>
    <p class="author-strip-meta">Data engineering and AI strategist. Author of
      <em>The Definitive Guide to Data Integration</em>. Ranked 12 in the Favikon
      Top 20 AI Experts in France for 2026.</p>
  </div>
  <div class="author-strip-actions">
    <a class="btn primary" href="about/">About the author</a>
    <a class="btn" href="https://www.linkedin.com/in/raphaelmansuy/" target="_blank" rel="noopener noreferrer">Connect on LinkedIn</a>
  </div>
</section>"""


def demo_body(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lanes = "".join(
        f'<button type="button" class="lane" role="radio" aria-checked="{ "true" if index == 0 else "false"}"'
        f' data-lane="{esc(lane["name"])}" title="{esc(lane["note"])}">'
        f'<strong>{esc(lane["label"])}</strong><small>{esc(lane["name"])}</small></button>'
        for index, lane in enumerate(data["lanes"])
    )
    types = "".join(
        f'<label class="type-toggle"><input type="checkbox" value="{esc(row["name"])}"'
        f'{" checked" if row["default"] else ""} data-class="{row["class"]}" />'
        f'<span class="type-dot" data-class="{row["class"]}"></span>{esc(row["name"])}</label>'
        for row in data["types"]
    )
    examples = "".join(
        f'<button type="button" class="example-chip" data-example="{esc(row["id"])}">'
        f'<strong>{esc(row["title"])}</strong><small>{esc(row["blurb"])}</small></button>'
        for row in data["examples"]
    )
    return f"""<section class="hero short">
  <p class="eyebrow">Live demo · real library output, recorded once</p>
  <h1>Try it on fake text</h1>
  <p class="lede">
    A GitHub Pages site cannot run Python, so this page replays output that the real library
    produced. The type filter and the score floor apply the same two rules the library applies:
    drop a type you did not ask for, and drop a span whose score is below your floor. A span with no
    score cannot meet a floor, so a floor hides it.
  </p>
</section>

<div class="demo" data-demo>
  <aside class="demo-side" aria-label="Demo controls">
    <section class="group">
      <h2>Lane</h2>
      <div class="lane-list" role="radiogroup" aria-label="Lane">{lanes}</div>
      <p class="hint" data-lane-note></p>
    </section>
    <section class="group">
      <h2>Types</h2>
      <div class="type-actions">
        <button type="button" data-types="default">Defaults</button>
        <button type="button" data-types="all">All</button>
        <button type="button" data-types="none">Clear</button>
      </div>
      <div class="type-list">{types}</div>
    </section>
    <section class="group">
      <h2>Score floor</h2>
      <p class="hint">The library ships no floor. This is caller policy.</p>
      <div class="floor-row">
        <input type="range" min="0" max="1" step="0.05" value="0" data-floor aria-label="Minimum score" />
        <output data-floor-value>none</output>
      </div>
    </section>
    <section class="group">
      <h2>Examples</h2>
      <div class="example-list">{examples}</div>
    </section>
  </aside>

  <section class="demo-main" aria-label="Result">
    <div class="workbench-head">
      <h2 data-example-title>Support ticket</h2>
      <span class="counter" data-chars>0 chars</span>
    </div>
    <p class="example-why" data-example-why></p>
    <p class="label">Source</p>
    <div class="highlight" data-highlight></div>
    <p class="label">Masked output</p>
    <pre class="masked" data-masked></pre>
    <div class="stats" data-stats></div>
    <p class="label">Span table</p>
    <div class="table-wrap">
      <table class="docs-table compact" data-span-table>
        <thead><tr><th>#</th><th>Type</th><th>Start</th><th>End</th><th>Text</th><th>Score</th><th>Detector</th><th>Slice</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="label">Vault</p>
    <div class="table-wrap">
      <table class="docs-table compact" data-vault-table>
        <thead><tr><th>Placeholder</th><th>Value</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="empty" data-empty hidden></p>
  </section>
</div>
<script type="application/json" data-examples-source>{payload}</script>"""


def tour_body() -> str:
    shots = [
        ("01-home.png", "The demo opens", "The sidebar lists every lane. The rule lane is active because it needs no download."),
        ("02-rules-ticket.png", "Rules on a ticket", "Phone, email, and a Luhn-valid test card. The order id stays visible."),
        ("03-secret-note.png", "A secret is irreversible", "The password becomes <code>&lt;SECRET&gt;</code>. The vault has no entry for it."),
        ("04-email-only.png", "Only what you asked for", "A request for EMAIL returns one email span and no person, even on a model lane."),
        ("05-chinese.png", "Chinese text", "A Chinese mobile number and an email pass the same slice check."),
        ("06-placeholders.png", "Numbered placeholders", "A repeated slice reuses <code>&lt;EMAIL_1&gt;</code>. A new slice gets <code>&lt;EMAIL_2&gt;</code>."),
        ("07-long-text.png", "Long text keeps offsets", "The email sits far into the string. The start index still refers to the whole source."),
        ("08-empty-state.png", "An empty source", "The page shows a message instead of making a call."),
        ("09-narrow.png", "A narrow screen", "The layout survives a 430 pixel viewport."),
        ("10-model-lane.png", "A model lane finds a name", "The closed encoder finds a person, and the slice check still passes."),
        ("11-copy-json.png", "Copy as JSON", "The span list leaves as JSON, so a reviewer can diff it."),
        ("12-score-floor.png", "Caller policy", "A floor of 0.90 keeps the card and drops the two spans with no score."),
    ]
    cards = []
    for index, (file, title, note) in enumerate(shots, start=1):
        stem = file.removesuffix(".png")
        rep = REPO_RAW + "docs/e2e/screenshots/" + file
        cards.append(
            f"""<figure class="shot" id="shot-{index}">
  <a href="{rep}" target="_blank" rel="noopener" title="Open the full-size capture">
    <img src="../shots/{stem}-1440.jpg"
      srcset="../shots/{stem}-720.jpg 720w, ../shots/{stem}-1440.jpg 1440w"
      sizes="(max-width: 900px) 92vw, 860px"
      loading="lazy" decoding="async" width="1440" height="1000"
      alt="{esc(title)}: the edgepii demo screen showing {esc(remove_html(note))}." />
  </a>
  <figcaption><strong>{index}. {esc(title)}</strong><span>{note}</span></figcaption>
</figure>"""
        )
    return f"""<section class="hero short">
  <p class="eyebrow">Screenshot tour</p>
  <h1>Every screen, and what it proves</h1>
  <p class="lede">
    These images are produced by the browser test run, not by hand. The test fills the page, clicks
    <strong>Locate spans</strong>, waits for the result, and writes the file. A changed image means a
    changed behaviour. Regenerate them with <code>make e2e</code>.
  </p>
</section>
<div class="tour-grid">
  {"".join(cards)}
</div>
<section class="panel-block">
  <h2>How to read a screenshot</h2>
  <ul class="doc-list">
    <li>A green <strong>slice check</strong> card and a green <strong>ok</strong> in each row mean every span
      passed <code>source[start:end] == text</code>.</li>
    <li>A red mark is a contract failure, not a style issue.</li>
    <li>A dash in the <strong>Score</strong> column means no validator covers that form. The library
      does not fill the gap with a number.</li>
    <li>The span table is the review artifact. A masked paragraph alone is not.</li>
  </ul>
</section>"""


def evaluation_body(data: dict) -> str:
    reports = load_reports()
    rows = []
    for report in reports:
        all_row = report["slices"]["all"]
        rows.append(
            f"<tr><td><code>{esc(report['corpus'])}</code></td><td><code>{esc(report['preset'])}</code></td>"
            f"<td>{all_row['documents']:,}</td><td>{all_row['gold_spans']:,}</td>"
            f"<td>{all_row['precision']:.3f}</td><td>{all_row['recall']:.3f}</td>"
            f"<td><strong>{all_row['f1']:.3f}</strong></td><td>{all_row['f2']:.3f}</td>"
            f"<td>{all_row['high_severity_leaks']}</td></tr>"
        )
    per_type = per_type_table(reports)
    return f"""<section class="hero short">
  <p class="eyebrow">Measured, not claimed</p>
  <h1>Public score</h1>
  <p class="lede">
    Exact-span F1 on two pinned public PII corpora. A prediction counts only when the type, the start,
    and the end all match gold. A one-character shift is a miss, because one character is enough to
    break a mask.
  </p>
</section>

<section class="panel-block">
  <h2>The two corpora</h2>
  <div class="table-wrap"><table class="docs-table">
    <thead><tr><th>Key</th><th>Corpus</th><th>License</th><th>Role</th></tr></thead>
    <tbody>
      <tr><td><code>nemotron-pii</code></td><td>NVIDIA Nemotron-PII, test split</td><td>CC-BY-4.0</td>
        <td>In domain. The <code>en-closed</code> checkpoint trains on this distribution</td></tr>
      <tr><td><code>gretel-finance-en</code></td><td>Gretel synthetic PII, finance, English test split</td><td>Apache-2.0</td>
        <td>Out of domain. Finance documents and SWIFT messages</td></tr>
    </tbody>
  </table></div>
  <p class="hint">Each corpus is pinned by commit revision, byte count, and <code>sha256</code>. A download
  that does not match stops the run, because a moved file makes an old score unreadable.</p>
</section>

<section class="panel-block">
  <h2>Results</h2>
  <div class="table-wrap"><table class="docs-table">
    <thead><tr><th>Corpus</th><th>Preset</th><th>Docs</th><th>Gold</th><th>P</th><th>R</th><th>F1</th><th>F2</th><th>Leaks</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
  <p class="hint">The <code>rules</code> lane finds no name, so PERSON and ADDRESS score zero for that lane
  by construction. Those two types need a model lane.</p>
</section>

<section class="panel-block">
  <h2>Per type</h2>
  {per_type}
</section>

<section class="panel-block callout-block">
  <h2>The finding that matters</h2>
  <p>
    The <code>en-closed</code> checkpoint scores <strong>0.995</strong> on PERSON in domain and
    <strong>0.048</strong> out of domain. It learned where a name sits in a synthetic persona note,
    not what a name is. The model card reports F1 0.9628 on its own test split, and that number alone
    would have shipped the lane.
  </p>
  <p>
    This is why the harness exists. Read the full analysis in
    <a href="../doc-score/">the first public score</a>.
  </p>
</section>"""


def per_type_table(reports: list[dict]) -> str:
    names = ["PERSON", "ADDRESS", "EMAIL", "PHONE", "PAYMENT", "GOV_ID", "SECRET", "IP_ADDRESS", "USERNAME"]
    columns = [(row["corpus"], row["preset"], row["slices"]["all"]["per_type"]) for row in reports]
    head = "".join(
        f"<th>{esc(corpus.split('-')[0])}<br /><small>{esc(preset)}</small></th>" for corpus, preset, _ in columns
    )
    body = []
    for name in names:
        cells = []
        for _corpus, _preset, table in columns:
            value = table.get(name, {}).get("f1")
            cells.append("<td>—</td>" if value is None else f"<td>{value:.3f}</td>")
        body.append(f"<tr><td><code>{name}</code></td>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table class="docs-table">'
        f"<thead><tr><th>Type</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def load_reports() -> list[dict]:
    directory = DOCS / "eval"
    wanted = [
        "nemotron-pii__rules-2000.json",
        "nemotron-pii__en-closed-500.json",
        "gretel-finance-en__rules-full.json",
        "gretel-finance-en__en-closed-400.json",
    ]
    reports = []
    for name in wanted:
        path = directory / name
        if path.is_file():
            reports.append(json.loads(path.read_text(encoding="utf-8")))
    return reports


def render_highlight(text: str, spans: list[dict]) -> str:
    parts: list[str] = []
    cursor = 0
    for span in sorted(spans, key=lambda row: row["start"]):
        if span["start"] < cursor:
            continue
        parts.append(esc(text[cursor : span["start"]]))
        score = "—" if span["score"] is None else f"{span['score']:.2f}"
        parts.append(
            f'<mark class="m" data-class="{esc(span["class"])}" '
            f'title="{esc(span["type"])} {span["start"]}:{span["end"]} score {score}">'
            f'{esc(text[span["start"] : span["end"]])}</mark>'
        )
        cursor = span["end"]
    parts.append(esc(text[cursor:]))
    return "".join(parts)


QUICKSTART_CODE = '''from edgepii import Locator, redact

source = (
    "Customer Ada Lovelace called from +852 5555 0101. "
    "Email ada@example.com. Card 4242424242424242. Order 48291."
)

result = Locator.preset("rules").locate(source)

for span in result.spans:
    proof = source[span.start:span.end] == span.text
    print(span.type, span.start, span.end, repr(span.text), proof)

masked, vault = redact(source, result.spans)
print(masked)
# Customer Ada Lovelace called from <PHONE_1>. Email <EMAIL_1>. Card <PAYMENT_1>. Order 48291.'''


def code_block(code: str, language: str) -> str:
    return mdrender._code(code, language)  # noqa: SLF001 - the one code renderer


def remove_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", text)


# ---------------------------------------------------------------- structured data


def home_jsonld(data: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "SoftwareApplication",
                "name": "edgepii",
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": "Linux, macOS, Windows",
                "description": (
                    "A Python library that locates personally identifiable information as typed "
                    "character spans on the exact source string."
                ),
                "programmingLanguage": "Python",
                "license": "https://www.apache.org/licenses/LICENSE-2.0",
                "url": SITE_URL,
                "codeRepository": REPO,
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            },
            {
                "@type": "WebSite",
                "name": "edgepii",
                "url": SITE_URL,
                "inLanguage": "en",
            },
        ],
    }


# The header mark, inlined so it paints with the first byte and costs no request.
# Same geometry as `static/icon.svg`, on a viewBox of 64.
MARK_INLINE = (
    '<svg viewBox="0 0 64 64" width="40" height="40" aria-hidden="true" focusable="false">'
    '<defs><linearGradient id="mg" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#7aa6ff"/><stop offset=".55" stop-color="#4f86ff"/>'
    '<stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>'
    '<rect width="64" height="64" rx="15" fill="url(#mg)"/>'
    '<path d="M24 15 H15 V49 H24" fill="none" stroke="#04070f" stroke-width="9" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M40 15 H49 V49 H40" fill="none" stroke="#04070f" stroke-width="9" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)


def breadcrumb_jsonld(route: str, title: str, canonical: str) -> str:
    """Tell a crawler where this page sits. The home page carries its own graph."""

    if route in ("", "404"):
        return ""
    label = title.split(" · ")[0]
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": label, "item": canonical},
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'


if __name__ == "__main__":
    raise SystemExit(main())
