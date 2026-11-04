"""The author section: who wrote this, and where to reach him.

The project is one person's work, so the page says so, with a face, a link to
LinkedIn, and a direct request. This follows the same shape as the author block
on the EdgeSQL project: a profile, a verified recognition line, the book, the
other projects, and a call to action.

Every claim here is checkable. The Favikon rank and score were read from the
Favikon article on the day this was written, and `verify_claims.py` is the place
a future drift gets caught.
"""

from __future__ import annotations

import html

LINKEDIN = "https://www.linkedin.com/in/raphaelmansuy/"
GITHUB_PROFILE = "https://github.com/raphaelmansuy"
REPO = "https://github.com/raphaelmansuy/edgepii"


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


PROJECTS = [
    {
        "name": "EdgeQuake",
        "url": "https://edgequake.com/",
        "image": "edgequake.jpg",
        "alt": "EdgeQuake knowledge graph view: 200 nodes and 840 edges over an AI research corpus.",
        "body": (
            "Graph-RAG in Rust: one binary, one Postgres, any LLM. It reads PDFs and text, "
            "builds a knowledge graph in PostgreSQL, and answers questions with sources."
        ),
    },
    {
        "name": "EdgeCrab",
        "url": "https://www.edgecrab.com/",
        "image": "edgecrab.jpg",
        "alt": "EdgeCrab illustration: a comic battle between EdgeCrab and OpenClaw.",
        "body": (
            "A personal and coding SuperAgent in one native Rust binary, with a terminal UI "
            "and a ReAct tool loop. It supports 24 LLM providers and 17 messaging gateways."
        ),
    },
    {
        "name": "EdgeWhisper",
        "url": "https://edgewhisper.com/",
        "image": "edgewhisper.jpg",
        "alt": "EdgeWhisper banner: voice dictation, on-device AI for macOS.",
        "body": (
            "Voice dictation for macOS, powered by Voxtral from Mistral AI. It runs fully on "
            "the device, with no cloud and no data collection."
        ),
    },
]


def section(prefix: str) -> str:
    """Return the author page block. `prefix` is the relative path to the site root."""

    projects = "".join(
        f"""<article class="project">
      <a class="project-media" href="{esc(project['url'])}" target="_blank" rel="noopener noreferrer" tabindex="-1">
        <img src="{prefix}assets/projects/{esc(project['image'])}" alt="{esc(project['alt'])}"
             width="800" height="500" loading="lazy" decoding="async" />
      </a>
      <h3><a href="{esc(project['url'])}" target="_blank" rel="noopener noreferrer">{esc(project['name'])}</a></h3>
      <p>{esc(project['body'])}</p>
    </article>"""
        for project in PROJECTS
    )

    return f"""<section class="author-section" aria-labelledby="author-name">
  <div class="author-card">
    <img class="portrait" src="{prefix}assets/author/raphael-mansuy.jpg"
         alt="Headshot of Raphael Mansuy, author of edgepii."
         width="128" height="128" loading="lazy" decoding="async" />
    <div class="author-body">
      <p class="eyebrow">About the author</p>
      <h1 id="author-name">Raphael Mansuy</h1>
      <p class="author-meta">Author of edgepii &middot; data engineering and AI strategist</p>
      <p>
        Raphael has more than 20 years of global technology leadership experience. He works on
        democratising data management and AI, and helps organisations build scalable data
        platforms. His work covers resilient data infrastructure, machine learning models, and
        coaching teams on practice. He leads a startup studio in Hong Kong and writes about AI
        and data strategy.
      </p>
      <p>
        <strong>Why this library exists.</strong> A PII tool usually answers one question: is this
        document sensitive? That answer is too coarse for a support ticket, a log line, or a
        prompt, and it gives no proof of what left the system. The smallest honest fix is a typed
        range of characters on the caller's own string, with one checkable equation behind every
        row. So he built it, and then measured it on two public corpora rather than trusting a
        model card.
      </p>
      <p class="author-links">
        <a class="btn primary" href="{LINKEDIN}" target="_blank" rel="noopener noreferrer">Connect on LinkedIn</a>
        <a class="btn" href="{GITHUB_PROFILE}" target="_blank" rel="noopener noreferrer">GitHub profile</a>
        <a class="btn" href="{REPO}" target="_blank" rel="noopener noreferrer">Repository</a>
      </p>
    </div>
  </div>

  <div class="author-grid">
    <article class="author-panel">
      <h2 class="panel-title">Recognition</h2>
      <p>
        Favikon ranks Raphael at <strong>12</strong> in
        <a href="https://www.favikon.com/blog/top-ai-experts-france" target="_blank" rel="noopener noreferrer">Top 20 AI Experts in France in 2026</a>,
        with a Favikon Authority Score of 7,012 points. The entry cites his 20 years of data and AI
        leadership, his work on scalable data platforms, and the startup studio he leads in
        Hong Kong.
      </p>
      <p class="source">Source: Favikon, <em>Top 20 AI Experts in France in 2026</em>.</p>
    </article>

    <article class="author-panel book-panel">
      <a href="https://www.oreilly.com/library/view/the-definitive-guide/9781837631919/" target="_blank" rel="noopener noreferrer" tabindex="-1">
        <img src="{prefix}assets/book/definitive-guide-data-integration.jpg"
             alt="Cover of The Definitive Guide to Data Integration, with Raphael Mansuy as a co-author."
             width="120" height="148" loading="lazy" decoding="async" />
      </a>
      <div>
        <h2 class="panel-title">The Definitive Guide to Data Integration</h2>
        <p class="author-meta">Packt, 2024</p>
        <p>
          <em>Unlock the power of data integration to efficiently manage, transform, and analyze
          data.</em> Raphael is a co-author with Pierre-Yves Bonnefoy, Emeric Chaize, Mehdi Tazi,
          and Stephane Heckel.
        </p>
        <p class="author-links">
          <a class="btn" href="https://www.oreilly.com/library/view/the-definitive-guide/9781837631919/" target="_blank" rel="noopener noreferrer">Read it on O&rsquo;Reilly</a>
        </p>
      </div>
    </article>
  </div>

  <h2 class="author-projects-title">Other projects by Raphael</h2>
  <div class="project-grid">
    {projects}
  </div>

  <div class="cta-band">
    <p><strong>Handling PII in a pipeline?</strong> Tell Raphael what you are building.</p>
    <a class="btn primary" href="{LINKEDIN}" target="_blank" rel="noopener noreferrer">Connect on LinkedIn</a>
  </div>
</section>"""


def jsonld() -> dict:
    """The author graph, so a crawler ties the software to a person."""

    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Raphael Mansuy",
        "jobTitle": "Data engineering and AI strategist",
        "url": GITHUB_PROFILE,
        "sameAs": [LINKEDIN, GITHUB_PROFILE, REPO],
        "knowsAbout": [
            "Data engineering",
            "Data integration",
            "Artificial intelligence",
            "Privacy engineering",
            "Personally identifiable information",
        ],
    }
