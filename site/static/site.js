/* edgepii site script. No dependency, no network call.
   The demo replays output recorded by the real library in site/gen_data.py. */

(function () {
  "use strict";

  // ---------------------------------------------------------------- nav

  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        nav.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  // ---------------------------------------------------------------- copy

  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-copy-code]");
    if (!button) return;
    const code = button.closest(".code");
    const body = code && code.querySelector("pre");
    if (!body) return;
    copy(body.innerText).then(function (ok) {
      const before = button.textContent;
      button.textContent = ok ? "Copied" : "Press ⌘C";
      setTimeout(function () {
        button.textContent = before;
      }, 1400);
    });
  });

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(
        function () {
          return true;
        },
        function () {
          return fallbackCopy(text);
        }
      );
    }
    return Promise.resolve(fallbackCopy(text));
  }

  function fallbackCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (error) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  // ---------------------------------------------------------------- diagrams

  // A Mermaid diagram is a nice extra, not a requirement. The source is already
  // on the page, so a reader with no CDN access still sees the structure. Only
  // load the module when a diagram exists, and only upgrade a block that draws.
  const diagrams = Array.prototype.slice.call(document.querySelectorAll("[data-mermaid]"));
  if (diagrams.length) {
    import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")
      .then(function (module) {
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
            fontSize: "14px"
          }
        });
        diagrams.forEach(function (host, index) {
          const source = host.querySelector(".diagram-source code");
          if (!source) return;
          mermaid
            .render("diagram-" + index, source.textContent)
            .then(function (result) {
              const figure = document.createElement("div");
              figure.className = "diagram-drawn";
              figure.innerHTML = result.svg;
              host.appendChild(figure);
              host.classList.add("drawn");
            })
            .catch(function () {
              /* Keep the source. A bad diagram must not break the page. */
            });
        });
      })
      .catch(function () {
        /* Offline, or the CDN is blocked. The source stays readable. */
      });
  }

  // ---------------------------------------------------------------- demo

  const root = document.querySelector("[data-demo]");
  if (!root) return;
  const source = document.querySelector("[data-examples-source]");
  if (!source) return;

  let data;
  try {
    data = JSON.parse(source.textContent);
  } catch (error) {
    return;
  }

  const state = {
    exampleId: data.examples[0].id,
    lane: data.lanes[0].name,
    types: new Set(
      data.types.filter(function (row) {
        return row.default;
      }).map(function (row) {
        return row.name;
      })
    ),
    floor: 0
  };

  const els = {
    title: root.querySelector("[data-example-title]"),
    why: root.querySelector("[data-example-why]"),
    chars: root.querySelector("[data-chars]"),
    highlight: root.querySelector("[data-highlight]"),
    masked: root.querySelector("[data-masked]"),
    stats: root.querySelector("[data-stats]"),
    spanBody: root.querySelector("[data-span-table] tbody"),
    vaultBody: root.querySelector("[data-vault-table] tbody"),
    empty: root.querySelector("[data-empty]"),
    laneNote: root.querySelector("[data-lane-note]"),
    floor: root.querySelector("[data-floor]"),
    floorValue: root.querySelector("[data-floor-value]"),
    typeToggles: Array.prototype.slice.call(root.querySelectorAll(".type-toggle input"))
  };

  function example() {
    return data.examples.find(function (row) {
      return row.id === state.exampleId;
    });
  }

  function laneData() {
    const row = example();
    return row.lanes[state.lane] || { spans: [], masked: row.text, vault: [], dropped: 0 };
  }

  /**
   * The two filters the library applies, in the same order:
   *   1. drop a type the caller did not ask for
   *   2. drop a span whose score is below the caller floor
   * A span with no score cannot meet a floor, so a floor removes it.
   * That rule is in merge_spans, and this mirror keeps the demo honest.
   */
  function visibleSpans() {
    return laneData().spans.filter(function (span) {
      if (!state.types.has(span.type)) return false;
      if (state.floor > 0) {
        if (span.score === null || span.score === undefined) return false;
        if (span.score < state.floor) return false;
      }
      return true;
    });
  }

  function inlineCode(text) {
    // The example notes use `backticks` for code. Render them as code, escaped.
    return esc(text).replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function render() {
    const row = example();
    const lane = laneData();
    const spans = visibleSpans();

    els.title.textContent = row.title;
    els.why.innerHTML = inlineCode(row.why);
    els.chars.textContent = row.chars.toLocaleString() + " chars";
    els.highlight.innerHTML = highlight(row.text, spans);
    els.masked.textContent = spans.length ? mask(row.text, spans, lane) : row.text;
    els.laneNote.textContent = laneNote(state.lane);
    els.floorValue.textContent = state.floor > 0 ? state.floor.toFixed(2) : "none";

    els.spanBody.innerHTML = spans
      .map(function (span, index) {
        const slice = row.text.slice(span.start, span.end) === span.text;
        return (
          "<tr>" +
          "<td>" + (index + 1) + "</td>" +
          '<td><span class="type-dot" data-class="' + esc(span.class) + '"></span> ' + esc(span.type) + "</td>" +
          "<td>" + span.start + "</td>" +
          "<td>" + span.end + "</td>" +
          "<td><code>" + esc(span.text) + "</code></td>" +
          "<td>" + (span.score === null || span.score === undefined ? "—" : span.score.toFixed(2)) + "</td>" +
          '<td><code>' + esc(span.detector_id) + "</code></td>" +
          '<td class="' + (slice ? "ok-cell" : "bad-cell") + '">' + (slice ? "ok" : "fail") + "</td>" +
          "</tr>"
        );
      })
      .join("");

    els.vaultBody.innerHTML = buildVault(spans, lane)
      .map(function (item) {
        return "<tr><td><code>" + esc(item.placeholder) + "</code></td><td><code>" + esc(item.value) + "</code></td></tr>";
      })
      .join("");

    const classes = {};
    spans.forEach(function (span) {
      classes[span.class] = (classes[span.class] || 0) + 1;
    });
    const allOk = spans.every(function (span) {
      return row.text.slice(span.start, span.end) === span.text;
    });
    const chips = [
      stat(spans.length + (spans.length === 1 ? " span" : " spans"), false),
      stat(Object.keys(classes).length + " classes", false),
      stat("dropped " + lane.dropped, false),
      stat(allOk ? "slice check ok" : "slice check failed", true, !allOk)
    ];
    els.stats.innerHTML = chips.join("");

    if (!spans.length) {
      els.empty.hidden = false;
      els.empty.textContent = state.floor > 0
        ? "No span scores at least " + state.floor.toFixed(2) + ". Move the floor down, or pick more types."
        : "No span of the selected types is in this text. That is a result, not an error: nothing here matched a grammar or a model.";
    } else {
      els.empty.hidden = true;
    }

    root.querySelectorAll("[data-example]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.example === state.exampleId ? "true" : "false");
    });
  }

  function buildVault(spans, lane) {
    // Reuse the recorded vault, then hide an entry whose span the filter removed.
    const visible = {};
    spans.forEach(function (span) {
      visible[span.type] = (visible[span.type] || 0) + 1;
    });
    const counted = {};
    const rows = [];
    const seen = new Set();
    spans.forEach(function (span) {
      if (span.class === "secret") return;
      counted[span.type] = (counted[span.type] || 0) + 1;
      const token = "<" + span.type + "_" + counted[span.type] + ">";
      const key = token + "\u0000" + span.text;
      if (seen.has(key)) return;
      seen.add(key);
      rows.push({ placeholder: token, value: span.text });
    });
    void visible;
    void lane;
    return rows;
  }

  function mask(text, spans, lane) {
    if (spans.length === lane.spans.length) return lane.masked;
    const ordered = spans.slice().sort(function (a, b) {
      return a.start - b.start;
    });
    const counts = {};
    const seen = {};
    let out = "";
    let cursor = 0;
    ordered.forEach(function (span) {
      out += text.slice(cursor, span.start);
      if (span.class === "secret") {
        out += "<SECRET>";
      } else {
        const key = span.type + "\u0000" + span.text;
        if (!(key in seen)) {
          counts[span.type] = (counts[span.type] || 0) + 1;
          seen[key] = "<" + span.type + "_" + counts[span.type] + ">";
        }
        out += seen[key];
      }
      cursor = span.end;
    });
    return out + text.slice(cursor);
  }

  function highlight(text, spans) {
    const ordered = spans.slice().sort(function (a, b) {
      return a.start - b.start;
    });
    let out = "";
    let cursor = 0;
    ordered.forEach(function (span) {
      if (span.start < cursor) return;
      out += esc(text.slice(cursor, span.start));
      const score = span.score === null || span.score === undefined ? "no score" : span.score.toFixed(2);
      out +=
        '<mark class="m" data-class="' + esc(span.class) + '" title="' +
        esc(span.type + " " + span.start + ":" + span.end + " · " + score) + '">' +
        esc(text.slice(span.start, span.end)) +
        "</mark>";
      cursor = span.end;
    });
    out += esc(text.slice(cursor));
    return out;
  }

  function stat(label, positive, negative) {
    const kind = negative ? " bad" : positive ? " ok" : "";
    return '<span class="stat' + kind + '"><strong>' + esc(label) + "</strong></span>";
  }

  function laneNote(name) {
    const row = data.lanes.find(function (lane) {
      return lane.name === name;
    });
    return row ? row.note : "";
  }

  function esc(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---------------------------------------------------------------- events

  root.querySelectorAll("[data-lane]").forEach(function (button) {
    button.addEventListener("click", function () {
      state.lane = button.dataset.lane;
      root.querySelectorAll("[data-lane]").forEach(function (other) {
        other.setAttribute("aria-checked", other === button ? "true" : "false");
      });
      render();
    });
  });

  root.querySelectorAll("[data-example]").forEach(function (button) {
    button.addEventListener("click", function () {
      state.exampleId = button.dataset.example;
      render();
    });
  });

  els.typeToggles.forEach(function (input) {
    input.addEventListener("change", function () {
      if (input.checked) state.types.add(input.value);
      else state.types.delete(input.value);
      render();
    });
  });

  root.querySelectorAll("[data-types]").forEach(function (button) {
    button.addEventListener("click", function () {
      const mode = button.dataset.types;
      state.types = new Set(
        mode === "none"
          ? []
          : data.types
              .filter(function (row) {
                return mode === "all" || row.default;
              })
              .map(function (row) {
                return row.name;
              })
      );
      els.typeToggles.forEach(function (input) {
        input.checked = state.types.has(input.value);
      });
      render();
    });
  });

  if (els.floor) {
    els.floor.addEventListener("input", function () {
      state.floor = Number(els.floor.value);
      render();
    });
  }

  render();
})();
