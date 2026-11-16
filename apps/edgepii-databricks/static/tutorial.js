/* edgepii · tutorial page. Renders /api/tutorial, which is built from the library. */

const el = (id) => document.getElementById(id);

const nodes = {
  source: el("tutorial-source"),
  steps: el("steps"),
  version: el("version-pill"),
};

function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function renderStep(step) {
  const item = make("li", "step");

  const head = make("div", "step-head");
  head.append(make("span", "step-index", String(step.index)));
  head.append(make("h3", "step-title", step.title));
  item.append(head);

  item.append(make("p", "step-body", step.body));

  const codeWrap = make("div", "code-block");
  const codeHead = make("div", "code-head");
  codeHead.append(make("span", "", "python"));
  const copy = make("button", "ghost tiny", "Copy");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(step.code);
      copy.textContent = "Copied";
      setTimeout(() => (copy.textContent = "Copy"), 1400);
    } catch (error) {
      copy.textContent = "Copy blocked";
    }
  });
  codeHead.append(copy);
  codeWrap.append(codeHead);
  codeWrap.append(make("pre", "code", step.code));
  item.append(codeWrap);

  const outWrap = make("div", "output-block");
  const outHead = make("div", "output-head");
  outHead.append(make("span", "output-label", "output"));
  outHead.append(make("span", "output-badge", "from the library"));
  outWrap.append(outHead);
  outWrap.append(make("pre", "output", step.output));
  item.append(outWrap);

  if (step.note) {
    item.append(make("p", "step-note", step.note));
  }

  return item;
}

async function boot() {
  try {
    const payload = await getJson("/api/tutorial");
    nodes.source.textContent = payload.source;
    nodes.steps.replaceChildren(...payload.steps.map(renderStep));
  } catch (error) {
    nodes.steps.append(
      make("li", "step error", `Could not load the tutorial: ${error.message}`),
    );
  }

  try {
    const config = await getJson("/api/config");
    nodes.version.textContent = `v${config.version}`;
  } catch (error) {
    /* the version pill is decoration; a failure here is not worth a message */
  }
}

boot();
