/* edgepii · Databricks App demo. No framework, no build step. */

const el = (id) => document.getElementById(id);

const nodes = {
  source: el("source"),
  charCount: el("char-count"),
  samples: el("samples"),
  run: el("run"),
  clear: el("clear"),
  status: el("status"),
  error: el("error"),
  errorTitle: el("error-title"),
  errorMessage: el("error-message"),
  intro: el("intro"),
  trySample: el("try-sample"),
  results: el("results"),
  stats: el("stats"),
  highlight: el("highlight"),
  masked: el("masked"),
  copyMasked: el("copy-masked"),
  vaultBody: el("vault-body"),
  spanBody: el("span-body"),
  answer: el("answer-restored"),
  answerRaw: el("answer-raw"),
  answerModel: el("answer-model"),
  tabRestored: el("tab-restored"),
  tabRaw: el("tab-raw"),
  gate: el("gate"),
  modelList: el("model-list"),
  laneList: el("lane-list"),
  scanResponse: el("scan-response"),
  timing: el("timing"),
  modelPill: el("model-pill"),
  versionPill: el("version-pill"),
  footerHost: el("footer-host"),
};

const state = {
  models: [],
  model: "",
  lanes: [],
  lane: "rules",
  samples: [],
  last: null,
};

function setStatus(text, tone = "") {
  nodes.status.textContent = text;
  nodes.status.dataset.tone = tone;
}

function showError(kind, message) {
  nodes.error.hidden = false;
  nodes.errorTitle.textContent = `Request failed (${kind})`;
  nodes.errorMessage.textContent = message;
}

function clearError() {
  nodes.error.hidden = true;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }
  if (!response.ok) {
    const message = payload?.message || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return payload;
}

function classOf(type) {
  const map = {
    SECRET: "secret",
    GOV_ID: "gov_id",
    PAYMENT: "payment",
    EMAIL: "contact",
    PHONE: "contact",
    IP_ADDRESS: "contact",
    URL: "contact",
    PERSON: "person",
  };
  return map[type] || "quasi";
}

function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

/* --- model and lane pickers ------------------------------------------- */

function renderModels() {
  nodes.modelList.replaceChildren();
  for (const name of state.models) {
    const button = make("button", "preset");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(name === state.model));
    if (name === state.model) button.classList.add("active");
    const dot = make("span", "dot");
    const label = make("span", "preset-name", name.replace("databricks-", ""));
    button.append(dot, label);
    button.addEventListener("click", () => {
      state.model = name;
      renderModels();
      nodes.modelPill.textContent = name;
    });
    nodes.modelList.append(button);
  }
}

function renderLanes() {
  nodes.laneList.replaceChildren();
  for (const lane of state.lanes) {
    const button = make("button", "preset");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(lane.name === state.lane));
    if (lane.name === state.lane) button.classList.add("active");
    const dot = make("span", "dot");
    const wrap = make("span", "preset-name");
    wrap.textContent = lane.label || lane.name;
    wrap.append(make("span", "preset-note", lane.note || ""));
    button.append(dot, wrap);
    button.addEventListener("click", () => {
      state.lane = lane.name;
      renderLanes();
    });
    nodes.laneList.append(button);
  }
}

function renderSamples() {
  nodes.samples.replaceChildren();
  for (const sample of state.samples) {
    const chip = make("button", "sample-chip", sample.label);
    chip.type = "button";
    chip.title = sample.note || "";
    chip.addEventListener("click", () => {
      nodes.source.value = sample.source;
      updateCount();
      nodes.source.focus();
    });
    nodes.samples.append(chip);
  }
}

/* --- results ----------------------------------------------------------- */

function updateCount() {
  const n = nodes.source.value.length;
  nodes.charCount.textContent = `${n} chars`;
}

function stat(label, value, tone = "") {
  const box = make("div", "stat");
  box.append(make("div", "stat-label", label));
  const v = make("div", "stat-value", value);
  if (tone) v.dataset.tone = tone;
  box.append(v);
  return box;
}

function renderStats(result) {
  nodes.stats.replaceChildren();
  nodes.stats.append(
    stat("Spans", String(result.span_count), result.span_count ? "ok" : ""),
    stat("Masked chars", String(result.masked.length)),
    stat("Model", `${Math.round(result.timing.model_ms)} ms`),
    stat("Total", `${Math.round(result.timing.total_ms)} ms`),
    stat(
      "Slice check",
      result.slice_ok ? "pass" : "fail",
      result.slice_ok ? "ok" : "bad",
    ),
    stat(
      "Response gate",
      result.restore_ok ? "clean" : "flagged",
      result.restore_ok ? "ok" : "warn",
    ),
  );
}

function renderHighlight(result) {
  const source = result.source;
  const nodesOut = [];
  let cursor = 0;
  for (const span of result.spans) {
    if (span.start > cursor) {
      nodesOut.push(document.createTextNode(source.slice(cursor, span.start)));
    }
    const mark = make("mark", classOf(span.type), source.slice(span.start, span.end));
    mark.title = `${span.type} · ${span.start}:${span.end}`;
    nodesOut.push(mark);
    cursor = span.end;
  }
  if (cursor < source.length) {
    nodesOut.push(document.createTextNode(source.slice(cursor)));
  }
  if (!nodesOut.length) {
    nodesOut.push(document.createTextNode(source));
  }
  nodes.highlight.replaceChildren(...nodesOut);
}

function renderMasked(result) {
  nodes.masked.textContent = result.masked;
}

function renderVault(result) {
  nodes.vaultBody.replaceChildren();
  if (!result.vault.length) {
    const row = document.createElement("tr");
    const cell = make("td", "mono-wrap", "Nothing reversible. Secrets are dropped.");
    cell.colSpan = 2;
    row.append(cell);
    nodes.vaultBody.append(row);
    return;
  }
  for (const item of result.vault) {
    const row = document.createElement("tr");
    const key = make("td", "", item.placeholder);
    const value = make("td", "mono-wrap", item.value);
    row.append(key, value);
    nodes.vaultBody.append(row);
  }
}

function renderSpans(result) {
  nodes.spanBody.replaceChildren();
  for (const span of result.spans) {
    const row = document.createElement("tr");
    row.append(make("td", "", String(span.index)));
    const typeCell = document.createElement("td");
    typeCell.append(make("span", `tag ${classOf(span.type)}`, span.type));
    row.append(typeCell);
    row.append(make("td", "", String(span.start)));
    row.append(make("td", "", String(span.end)));
    row.append(make("td", "mono-wrap", span.text));
    row.append(
      make("td", "", span.score === null ? "—" : span.score.toFixed(2)),
    );
    row.append(
      make("td", span.slice_ok ? "ok-mark" : "bad-mark", span.slice_ok ? "ok" : "fail"),
    );
    nodes.spanBody.append(row);
  }
}

function renderAnswer(result) {
  nodes.answer.className = "answer restored";

  const parts = (result.segments || []).map((segment) =>
    segment.kind === "value"
      ? make("span", "value", segment.text)
      : document.createTextNode(segment.text),
  );
  nodes.answer.replaceChildren(
    ...(parts.length ? parts : [document.createTextNode(result.answer || "(empty)")]),
  );

  nodes.answerRaw.textContent = result.raw_answer || "(empty)";
  nodes.answerModel.textContent = result.model;
}

function renderGate(result) {
  const bits = [];
  if (result.restore_ok) {
    bits.push("Every placeholder resolved. No PII outside the vault.");
  }
  if (result.sealed.length) {
    bits.push(
      `${result.sealed.join(", ")} stayed masked on purpose: a secret is irreversible, so it never enters the vault.`,
    );
  }
  if (result.unresolved.length) {
    bits.push(`Unresolved placeholders: ${result.unresolved.join(", ")}.`);
  }
  if (result.unknown.length) {
    bits.push(
      `PII in the raw answer that the vault never held: ${result.unknown
        .map((row) => `${row.type} "${row.text}"`)
        .join(", ")}.`,
    );
  }
  nodes.gate.hidden = false;
  nodes.gate.className = `gate ${result.restore_ok ? "ok" : "warn"}`;
  nodes.gate.textContent = bits.join(" ") || "No response check ran.";
}

function renderTiming(result) {
  const rows = [
    ["detect", result.timing.detect_ms],
    ["mask", result.timing.mask_ms],
    ["model", result.timing.model_ms],
    ["restore", result.timing.restore_ms],
    ["total", result.timing.total_ms],
  ];
  nodes.timing.replaceChildren();
  for (const [label, value] of rows) {
    const li = document.createElement("li");
    li.append(make("span", "", label), make("span", "", `${Math.round(value)} ms`));
    nodes.timing.append(li);
  }
  if (result.tokens.prompt !== null) {
    const li = document.createElement("li");
    li.append(
      make("span", "", "tokens"),
      make(
        "span",
        "",
        `${result.tokens.prompt} → ${result.tokens.completion ?? "?"}`,
      ),
    );
    nodes.timing.append(li);
  }
}

function renderResult(result) {
  nodes.last = result;
  nodes.intro.hidden = true;
  nodes.results.hidden = false;
  renderStats(result);
  renderHighlight(result);
  renderMasked(result);
  renderVault(result);
  renderSpans(result);
  renderAnswer(result);
  renderGate(result);
  renderTiming(result);
  nodes.tabRestored.click();
}

/* --- run --------------------------------------------------------------- */

async function run() {
  const source = nodes.source.value.trim();
  if (!source) {
    showError("empty", "Add some text first.");
    return;
  }
  clearError();
  nodes.run.disabled = true;
  setStatus("running four stages…", "");

  try {
    const payload = await getJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: nodes.source.value,
        model: state.model,
        lane: state.lane,
        scan_response: nodes.scanResponse.checked,
      }),
    });
    renderResult(payload);
    setStatus(
      `${payload.span_count} spans · ${Math.round(payload.timing.total_ms)} ms`,
      payload.restore_ok ? "ok" : "warn",
    );
  } catch (error) {
    showError("run", error.message);
    setStatus("failed", "bad");
  } finally {
    nodes.run.disabled = false;
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    setStatus("copied", "ok");
  } catch (error) {
    setStatus("copy blocked by the browser", "warn");
  }
}

/* --- boot -------------------------------------------------------------- */

async function boot() {
  nodes.tabRestored.addEventListener("click", () => {
    nodes.tabRestored.classList.add("active");
    nodes.tabRaw.classList.remove("active");
    nodes.tabRestored.setAttribute("aria-selected", "true");
    nodes.tabRaw.setAttribute("aria-selected", "false");
    nodes.answer.hidden = false;
    nodes.answerRaw.hidden = true;
  });
  nodes.tabRaw.addEventListener("click", () => {
    nodes.tabRaw.classList.add("active");
    nodes.tabRestored.classList.remove("active");
    nodes.tabRaw.setAttribute("aria-selected", "true");
    nodes.tabRestored.setAttribute("aria-selected", "false");
    nodes.answerRaw.hidden = false;
    nodes.answer.hidden = true;
  });

  nodes.run.addEventListener("click", run);
  nodes.source.addEventListener("input", updateCount);
  nodes.source.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      run();
    }
  });
  nodes.clear.addEventListener("click", () => {
    nodes.source.value = "";
    updateCount();
    nodes.results.hidden = true;
    nodes.intro.hidden = false;
    clearError();
    setStatus("");
    nodes.source.focus();
  });
  nodes.trySample.addEventListener("click", () => {
    const first = state.samples[0];
    if (!first) return;
    nodes.source.value = first.source;
    updateCount();
    run();
  });
  nodes.copyMasked.addEventListener("click", () => copyText(nodes.masked.textContent));

  try {
    const config = await getJson("/api/config");
    state.models = config.models || [];
    state.model = config.default_model || state.models[0] || "";
    state.lanes = config.lanes || [{ name: "rules", label: "Rules" }];
    state.lane = config.default_lane || "rules";
    state.samples = config.samples || [];

    nodes.versionPill.textContent = `v${config.version}`;
    nodes.modelPill.textContent = state.model;
    nodes.modelPill.classList.add("live");
    nodes.footerHost.textContent = config.workspace_host
      ? `serving from ${config.workspace_host}`
      : "";

    renderModels();
    renderLanes();
    renderSamples();
    updateCount();
    if (state.samples.length) {
      nodes.source.value = state.samples[0].source;
      updateCount();
    }
  } catch (error) {
    showError("config", error.message);
    setStatus("config failed", "bad");
  }
}

boot();
