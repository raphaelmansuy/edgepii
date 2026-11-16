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
      // A pastel palette on a dark canvas. Node fills are light, so every node
      // label is dark ink: 12:1 or better on every pastel below. The page stays
      // dark, which keeps the diagrams reading as part of the app rather than a
      // white box pasted onto it.
      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        themeVariables: {
          darkMode: true,
          background: "#0f1420",
          primaryColor: "#cfe0fb",
          primaryTextColor: "#172033",
          primaryBorderColor: "#7ea3e0",
          secondaryColor: "#cdf0e4",
          secondaryTextColor: "#172033",
          secondaryBorderColor: "#79bfa8",
          tertiaryColor: "#ecdcf8",
          tertiaryTextColor: "#172033",
          tertiaryBorderColor: "#b391d4",
          lineColor: "#9fb3d4",
          textColor: "#dbe3f0",
          mainBkg: "#cfe0fb",
          nodeBorder: "#7ea3e0",
          clusterBkg: "#161d2c",
          clusterBorder: "#3a465c",
          edgeLabelBackground: "#161d2c",
          labelBackground: "#161d2c",
          noteBkgColor: "#f8f0c8",
          noteTextColor: "#172033",
          noteBorderColor: "#d9c98a",
          actorBkg: "#cfe0fb",
          actorBorder: "#7ea3e0",
          actorTextColor: "#172033",
          actorLineColor: "#7a8296",
          signalColor: "#c9d4e6",
          signalTextColor: "#dbe3f0",
          labelBoxBkgColor: "#cdf0e4",
          labelBoxBorderColor: "#79bfa8",
          labelTextColor: "#172033",
          loopTextColor: "#172033",
          activationBkgColor: "#cfe0fb",
          activationBorderColor: "#7ea3e0",
          sequenceNumberColor: "#172033",
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: "14px",
        },
        flowchart: { curve: "basis", padding: 12, htmlLabels: true },
        sequence: { actorMargin: 44, boxMargin: 10, useMaxWidth: true },
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
