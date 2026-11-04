"use strict";

const state = {
  presets: [],
  types: [],
  samples: [],
  selectedPreset: "rules",
  selectedTypes: new Set(),
  typesTouched: false,
  running: false,
  lastResult: null,
};

const el = (id) => document.getElementById(id);

const nodes = {
  presetList: el("preset-list"),
  typeList: el("type-list"),
  sampleList: el("sample-list"),
  source: el("source"),
  charCount: el("char-count"),
  run: el("run"),
  status: el("status"),
  error: el("error"),
  errorTitle: el("error-title"),
  errorMessage: el("error-message"),
  errorHint: el("error-hint"),
  results: el("results"),
  stats: el("stats"),
  highlight: el("highlight"),
  masked: el("masked"),
  quasiBlock: el("quasi-block"),
  quasiList: el("quasi-list"),
  spanBody: el("span-body"),
  vaultBody: el("vault-body"),
  vaultBlock: el("vault-block"),
  footerRun: el("footer-run"),
  taxonomyPill: el("taxonomy-pill"),
  copyMasked: el("copy-masked"),
  clear: el("clear"),
  intro: el("intro"),
  trySample: el("try-sample"),
  copyJson: el("copy-json"),
  minScore: el("min-score"),
  minScoreValue: el("min-score-value"),
  dropUnscored: el("drop-unscored"),
};

const CLASS_LABEL = {
  secret: "Secret",
  gov_id: "Government id",
  payment: "Payment",
  contact: "Contact",
  person: "Person",
  quasi: "Quasi",
};

function classOf(type) {
  const row = state.types.find((item) => item.name === type);
  return row ? row.class : "contact";
}

function setStatus(text, tone = "") {
  nodes.status.textContent = text;
  nodes.status.className = "status" + (tone ? " " + tone : "");
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.message || "Request failed");
    error.payload = body;
    throw error;
  }
  return body;
}

function renderPresets() {
  nodes.presetList.innerHTML = "";
  for (const preset of state.presets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset" + (preset.ready ? "" : " disabled");
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(preset.name === state.selectedPreset));
    button.dataset.preset = preset.name;
    button.disabled = !preset.ready;

    const dot = document.createElement("span");
    dot.className = "dot";

    const body = document.createElement("span");
    const name = document.createElement("span");
    name.className = "preset-name";
    name.textContent = preset.name;
    const badge = document.createElement("span");
    badge.className = "badge " + (preset.ready ? (preset.gated ? "need" : "ready") : "need");
    badge.textContent = preset.ready
      ? preset.gated
        ? "gated repo"
        : preset.extra || "local"
      : "needs extra";
    name.appendChild(badge);

    const note = document.createElement("span");
    note.className = "preset-note";
    note.textContent = preset.ready
      ? preset.repo_id
        ? preset.repo_id
        : "regex and checksums only"
      : preset.hint || "install an extra";

    body.append(name, note);
    button.append(dot, body);
    button.addEventListener("click", () => selectPreset(preset.name));
    nodes.presetList.appendChild(button);
  }
}

function selectPreset(name) {
  state.selectedPreset = name;
  state.typesTouched = false;
  renderPresets();
  renderTypes();
  setStatus("");
}

function renderTypes() {
  nodes.typeList.innerHTML = "";
  for (const type of state.types) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "type";
    button.dataset.type = type.name;
    button.setAttribute("aria-pressed", String(state.selectedTypes.has(type.name)));
    button.title = `${type.class} · rank ${type.rank} · prefer ${type.prefer}`;

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = `var(--${type.class === "gov_id" ? "gov" : type.class})`;

    const label = document.createElement("span");
    label.textContent = type.name;

    button.append(swatch, label);
    button.addEventListener("click", () => toggleType(type.name));
    nodes.typeList.appendChild(button);
  }
}

function toggleType(name) {
  state.typesTouched = true;
  if (state.selectedTypes.has(name)) {
    state.selectedTypes.delete(name);
  } else {
    state.selectedTypes.add(name);
  }
  renderTypes();
}

function setTypeSelection(names) {
  state.typesTouched = true;
  state.selectedTypes = new Set(names);
  renderTypes();
}

function defaultTypeNames() {
  return state.types.filter((type) => type.default).map((type) => type.name);
}

function loadSample(sample) {
  nodes.source.value = sample.source;
  setTypeSelection(sample.types);
  updateCount();
  clearResult();
  nodes.intro.hidden = false;
  setStatus("Sample loaded. Press Locate spans.", "");
  nodes.source.focus();
}

function renderSamples() {
  nodes.sampleList.innerHTML = "";
  for (const sample of state.samples) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sample";
    button.dataset.sample = sample.id;

    const title = document.createElement("strong");
    title.textContent = sample.label;
    const note = document.createElement("span");
    note.textContent = sample.note;

    button.append(title, note);
    button.addEventListener("click", () => loadSample(sample));
    nodes.sampleList.appendChild(button);
  }
}

function updateCount() {
  const count = nodes.source.value.length;
  nodes.charCount.textContent = `${count.toLocaleString()} chars`;
}

function clearResult() {
  state.lastResult = null;
  nodes.results.hidden = true;
  nodes.error.hidden = true;
  nodes.intro.hidden = false;
  nodes.highlight.innerHTML = "";
  nodes.masked.textContent = "";
  nodes.spanBody.innerHTML = "";
  nodes.vaultBody.innerHTML = "";
  nodes.stats.innerHTML = "";
  nodes.footerRun.textContent = "";
  nodes.copyJson.hidden = true;
}

function showError(error) {
  const payload = error.payload || {};
  nodes.error.hidden = false;
  nodes.errorTitle.textContent = payload.error ? payload.error.replace(/_/g, " ") : "Request failed";
  nodes.errorMessage.textContent = payload.message || error.message;
  if (payload.hint) {
    nodes.errorHint.hidden = false;
    nodes.errorHint.textContent = payload.hint;
  } else {
    nodes.errorHint.hidden = true;
    nodes.errorHint.textContent = "";
  }
  nodes.results.hidden = true;
}

function stat(label, value, tone = "") {
  const box = document.createElement("div");
  box.className = "stat";
  const name = document.createElement("span");
  name.className = "stat-label";
  name.textContent = label;
  const amount = document.createElement("span");
  amount.className = "stat-value" + (tone ? " " + tone : "");
  amount.textContent = value;
  box.append(name, amount);
  return box;
}

function renderStats(result) {
  nodes.stats.innerHTML = "";
  nodes.stats.append(
    stat("Spans", String(result.spans.length)),
    stat("Lane", result.preset),
    stat("Dropped", String(result.dropped), result.dropped ? "bad" : "ok"),
    stat("Slice check", result.slice_ok ? "pass" : "fail", result.slice_ok ? "ok" : "bad"),
    stat("Latency", `${result.elapsed_ms} ms`),
    stat("Chars", result.source_chars.toLocaleString()),
  );
}

function renderHighlight(result) {
  const source = nodes.source.value;
  nodes.highlight.innerHTML = "";
  if (result.spans.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No span found for this lane and type list.";
    nodes.highlight.appendChild(empty);
    return;
  }

  const ordered = [...result.spans].sort((left, right) => left.start - right.start);
  let cursor = 0;
  for (const span of ordered) {
    if (span.start > cursor) {
      nodes.highlight.appendChild(document.createTextNode(source.slice(cursor, span.start)));
    }
    const mark = document.createElement("mark");
    mark.className = "mark-span";
    mark.dataset.class = span.class;
    mark.dataset.type = span.type;
    mark.title = `${span.type} · ${span.start}:${span.end} · score ${span.score ?? "null"}`;
    mark.textContent = source.slice(span.start, span.end);
    nodes.highlight.appendChild(mark);
    cursor = span.end;
  }
  if (cursor < source.length) {
    nodes.highlight.appendChild(document.createTextNode(source.slice(cursor)));
  }
}

function renderQuasi(result) {
  const rows = result.quasi || [];
  nodes.quasiList.textContent = "";
  nodes.quasiBlock.hidden = rows.length === 0;
  for (const row of rows) {
    const item = document.createElement("li");
    item.className = `quasi-item risk-${row.risk}`;
    const name = document.createElement("strong");
    name.textContent = row.name;
    const fields = document.createElement("span");
    fields.className = "quasi-fields";
    fields.textContent = ` ${row.risk} risk: ${row.fields.join(" + ")}`;
    const why = document.createElement("p");
    why.className = "quasi-source";
    why.textContent = row.source;
    item.append(name, fields, why);
    nodes.quasiList.appendChild(item);
  }
}

function renderMasked(result) {
  nodes.masked.textContent = "";
  if (result.redact_error) {
    const line = document.createElement("span");
    line.className = "marked-secret";
    line.textContent = result.redact_error;
    nodes.masked.appendChild(line);
    return;
  }
  const parts = result.masked.split(/(<[A-Z_]+>)/g);
  for (const part of parts) {
    if (/^<[A-Z_]+>$/.test(part)) {
      const token = document.createElement("span");
      const secret = part === "<SECRET>";
      token.className = secret ? "marked-secret" : "mark-span";
      if (!secret) {
        token.dataset.class = "contact";
      }
      token.textContent = part;
      nodes.masked.appendChild(token);
    } else if (part) {
      nodes.masked.appendChild(document.createTextNode(part));
    }
  }
}

function cell(text, className = "", title = "") {
  const td = document.createElement("td");
  if (className) {
    td.className = className;
  }
  if (title) {
    td.title = title;
  }
  td.textContent = text;
  return td;
}

function scoreCell(score) {
  if (score === null) {
    return cell("—", "score-none", "A shape match with no checksum. No invented probability.");
  }
  return cell(score.toFixed(3), "score-value");
}

function renderTable(result) {
  nodes.spanBody.innerHTML = "";
  if (result.spans.length === 0) {
    const row = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.className = "empty";
    td.textContent = "No span found.";
    row.appendChild(td);
    nodes.spanBody.appendChild(row);
  }
  for (const span of result.spans) {
    const row = document.createElement("tr");
    row.dataset.spanType = span.type;

    const chipCell = document.createElement("td");
    const chip = document.createElement("span");
    chip.className = "type-chip";
    chip.dataset.class = span.class;
    chip.textContent = span.type;
    chipCell.appendChild(chip);

    row.append(
      cell(String(span.index)),
      chipCell,
      cell(String(span.start)),
      cell(String(span.end)),
      cell(span.text),
      scoreCell(span.score),
      cell(span.detector_id),
      cell(span.slice_ok ? "ok" : "bad", span.slice_ok ? "slice-ok" : "slice-bad"),
    );
    nodes.spanBody.appendChild(row);
  }
}

function renderVault(result) {
  nodes.vaultBody.innerHTML = "";
  if (result.vault.length === 0) {
    nodes.vaultBlock.hidden = true;
    return;
  }
  nodes.vaultBlock.hidden = false;
  for (const entry of result.vault) {
    const row = document.createElement("tr");
    const placeholder = cell(entry.placeholder);
    const typeCell = document.createElement("td");
    const chip = document.createElement("span");
    chip.className = "type-chip";
    chip.dataset.class = classOf(entry.type);
    chip.textContent = entry.type;
    typeCell.appendChild(chip);
    row.append(placeholder, typeCell, cell(entry.value));
    nodes.vaultBody.appendChild(row);
  }
}

function renderResult(result) {
  state.lastResult = result;
  nodes.error.hidden = true;
  nodes.intro.hidden = true;
  nodes.results.hidden = false;
  renderStats(result);
  renderHighlight(result);
  renderMasked(result);
  renderQuasi(result);
  renderTable(result);
  renderVault(result);
  nodes.footerRun.textContent = `preset=${result.preset} revision=${result.revision} taxonomy=${result.taxonomy_version}`;
  nodes.copyJson.hidden = false;
  const tone = result.slice_ok ? "good" : "bad";
  setStatus(
    `${result.spans.length} span(s) in ${result.elapsed_ms} ms` +
      (result.dropped ? ` · ${result.dropped} dropped` : ""),
    tone,
  );
}

async function run() {
  if (state.running) {
    return;
  }
  const source = nodes.source.value;
  if (!source.trim()) {
    clearResult();
    setStatus("Add some text first.", "bad");
    return;
  }

  state.running = true;
  nodes.run.disabled = true;
  setStatus("Locating…");
  try {
    const payload = await getJson("/api/locate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source,
        preset: state.selectedPreset,
        types: [...state.selectedTypes],
        min_score: currentFloor(),
        drop_unscored: Boolean(nodes.dropUnscored && nodes.dropUnscored.checked),
      }),
    });
    if (nodes.source.value !== source) {
      return;
    }
    renderResult(payload);
  } catch (error) {
    showError(error);
    setStatus("Failed.", "bad");
  } finally {
    state.running = false;
    nodes.run.disabled = false;
  }
}

async function boot() {
  try {
    const [presets, types, samples] = await Promise.all([
      getJson("/api/presets"),
      getJson("/api/types"),
      getJson("/api/samples"),
    ]);
    state.presets = presets.presets;
    state.types = types.types;
    state.samples = samples.samples;
    state.selectedTypes = new Set(defaultTypeNames());
    const ready = state.presets.filter((preset) => preset.ready);
    if (ready.length > 0 && !ready.some((preset) => preset.name === state.selectedPreset)) {
      state.selectedPreset = ready[0].name;
    }
    renderPresets();
    renderTypes();
    renderSamples();
    renderFloor();
    updateCount();
    setStatus("Ready.");
  } catch (error) {
    setStatus("Cannot reach the API.", "bad");
    showError(error);
  }
}

function currentFloor() {
  const value = Number(nodes.minScore.value);
  return value > 0 ? value : null;
}

function renderFloor() {
  const value = currentFloor();
  nodes.minScoreValue.textContent = value === null ? "none" : value.toFixed(2);
}

nodes.run.addEventListener("click", run);
nodes.source.addEventListener("input", () => {
  updateCount();
  if (!state.typesTouched) {
    return;
  }
});
nodes.source.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    run();
  }
});
nodes.clear.addEventListener("click", () => {
  nodes.source.value = "";
  updateCount();
  clearResult();
  setStatus("");
  nodes.source.focus();
});
el("types-default").addEventListener("click", () => setTypeSelection(defaultTypeNames()));
el("types-all").addEventListener("click", () =>
  setTypeSelection(state.types.map((type) => type.name)),
);
el("types-none").addEventListener("click", () => setTypeSelection([]));
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {
    // Fall through to the selection-based copy.
  }
  const helper = document.createElement("textarea");
  helper.value = text;
  helper.setAttribute("readonly", "");
  helper.style.position = "fixed";
  helper.style.opacity = "0";
  document.body.appendChild(helper);
  helper.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(helper);
  return copied;
}

async function flash(node, label, original) {
  node.textContent = label;
  setTimeout(() => {
    node.textContent = original;
  }, 1200);
}

nodes.copyMasked.addEventListener("click", async () => {  if (!state.lastResult) {
    return;
  }
  const done = await copyText(state.lastResult.masked);
  await flash(nodes.copyMasked, done ? "Copied" : "Press ⌘C", "Copy");
});
nodes.minScore.addEventListener("input", renderFloor);
if (nodes.dropUnscored) {
  nodes.dropUnscored.addEventListener("change", run);
}
nodes.trySample.addEventListener("click", () => {
  if (state.samples.length > 0) {
    loadSample(state.samples[0]);
  }
});
nodes.copyJson.addEventListener("click", async () => {
  if (!state.lastResult) {
    return;
  }
  const rows = state.lastResult.spans.map((span) => ({
    type: span.type,
    start: span.start,
    end: span.end,
    text: span.text,
    score: span.score,
  }));
  const done = await copyText(JSON.stringify(rows, null, 2));
  await flash(nodes.copyJson, done ? "Copied" : "Press ⌘C", "Copy JSON");
});

boot();
