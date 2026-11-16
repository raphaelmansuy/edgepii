/* edgepii · architecture page. Renders /api/architecture, then upgrades diagrams. */

const el = (id) => document.getElementById(id);

const nodes = {
  body: el("architecture-body"),
  count: el("diagram-count"),
  toggle: el("toggle-source"),
  version: el("version-pill"),
};

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

/* Mermaid is an optional enhancement. The source is already on the page, so a
   reader with no CDN access still sees the structure. Only load the module when
   a diagram exists, and only upgrade a block that draws. */
function upgradeDiagrams() {
  const diagrams = Array.from(document.querySelectorAll("[data-mermaid]"));
  if (!diagrams.length) {
    nodes.count.textContent = "no diagrams";
    return;
  }

  nodes.count.textContent = `${diagrams.length} diagrams`;

  import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")
    .then((module) => {
      const mermaid = module.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        themeVariables: {
          background: "#05070d",
          primaryColor: "#111a2c",
          primaryTextColor: "#e8edf7",
          primaryBorderColor: "#5b8cff",
          lineColor: "#5b8cff",
          secondaryColor: "#0d1420",
          tertiaryColor: "#0a0f1a",
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: "14px",
        },
      });

      let drawn = 0;
      diagrams.forEach((host, index) => {
        const source = host.querySelector(".diagram-source code");
        if (!source) return;
        mermaid
          .render(`arch-diagram-${index}`, source.textContent)
          .then((result) => {
            const figure = document.createElement("div");
            figure.className = "diagram-drawn";
            figure.innerHTML = result.svg;
            host.append(figure);
            host.classList.add("drawn");
            drawn += 1;
            nodes.count.textContent = `${drawn}/${diagrams.length} diagrams drawn`;
          })
          .catch(() => {
            /* Keep the source. A bad diagram must not break the page. */
            host.classList.add("failed");
          });
      });

      nodes.count.classList.add("live");
    })
    .catch(() => {
      /* Offline, or the CDN is blocked. The source stays readable. */
      nodes.count.textContent = `${diagrams.length} diagrams · source only`;
      nodes.count.classList.add("warn");
    });
}

function wireCopyButtons() {
  document.querySelectorAll("[data-copy-diagram]").forEach((button) => {
    button.addEventListener("click", async () => {
      const host = button.closest("[data-mermaid]");
      const source = host?.querySelector(".diagram-source code");
      if (!source) return;
      try {
        await navigator.clipboard.writeText(source.textContent);
        button.textContent = "Copied";
        setTimeout(() => (button.textContent = "Copy source"), 1400);
      } catch (error) {
        button.textContent = "Copy blocked";
      }
    });
  });
}

async function boot() {
  try {
    const payload = await getJson("/api/architecture");
    nodes.body.innerHTML = payload.html;
    wireCopyButtons();
    upgradeDiagrams();

    nodes.toggle.addEventListener("click", () => {
      const showing = nodes.body.classList.toggle("show-source");
      nodes.toggle.textContent = showing ? "Hide diagram source" : "Show diagram source";
    });
  } catch (error) {
    nodes.body.replaceChildren();
    const p = document.createElement("p");
    p.className = "error";
    p.textContent = `Could not load the architecture document: ${error.message}`;
    nodes.body.append(p);
    nodes.count.textContent = "unavailable";
  }

  try {
    const config = await getJson("/api/config");
    nodes.version.textContent = `v${config.version}`;
  } catch (error) {
    /* the version pill is decoration; a failure here is not worth a message */
  }
}

boot();
