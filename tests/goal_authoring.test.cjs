const {readFileSync} = require("node:fs");
const {runInNewContext} = require("node:vm");
const {test} = require("node:test");
const assert = require("node:assert/strict");

const script = readFileSync("cardchart/static/goal_authoring.js", "utf8");

class Element {
  constructor(value = "") {
    this.value = value;
    this.options = [];
    this.dataset = {};
    this.hidden = false;
    this.textContent = "";
    this.disabled = false;
    this.listeners = {};
    this.children = [];
    this.classList = {add() {}, toggle() {}};
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children.push(...children); }
  setAttribute() {}
}

async function selectedKeys(initial, responses, changeSet = false) {
  const elements = Object.fromEntries([
    "#set-search", "#set-code", "#goal-language", "#collector-from",
    "#collector-to", "#metadata-filters", "#selected-entry-keys",
    "#review-selected", "#selection-count", "#preview-empty",
    "#preview-loading", "#preview-error", "#preview-results",
    "#treatment-filters", "#selected-card-preview", "#preview-card-grid",
    "#visible-count", "#select-visible", "#deselect-visible",
    "#toggle-selected-only",
  ].map((selector) => [selector, new Element()]));
  elements["#set-code"].value = "tst";
  elements["#set-code"].options = [new Element("")];
  elements["#goal-language"].value = "en";
  elements["#selected-entry-keys"].value = initial;
  const form = Object.assign(new Element(), {
    dataset: {previewUrl: "/preview"},
    querySelector: (selector) => elements[selector],
  });
  let responseIndex = 0;
  runInNewContext(script, {
    document: {
      querySelector: () => form,
      createElement: () => new Element(),
      createTextNode: (text) => text,
    },
    window: {clearTimeout, setTimeout},
    URLSearchParams,
    AbortController,
    fetch: async () => ({
      ok: true,
      json: async () => responses[responseIndex++],
    }),
  });
  await new Promise((resolve) => setImmediate(resolve));
  if (changeSet) {
    elements["#set-code"].value = "other";
    await elements["#set-code"].listeners.change();
  }
  return JSON.parse(elements["#selected-entry-keys"].value);
}

const entry = (key) => ({
  key, name: key, image_url: "", collector_number: key,
  version_count: 1, treatment_keys: ["base"], treatments: [],
});
const payload = (...keys) => ({
  entries: keys.map(entry), treatments: [{key: "base", label: "Base", count: keys.length}],
});

test("fresh form selects all preview entries", async () => {
  assert.deepEqual(await selectedKeys("", [payload("a", "b")]), ["a", "b"]);
});

test("validation resubmission restores the submitted subset", async () => {
  assert.deepEqual(await selectedKeys('["b"]', [payload("a", "b", "c")]), ["b"]);
});

test("submitted empty selection stays empty and malformed input defaults to all", async () => {
  assert.deepEqual(await selectedKeys("[]", [payload("a")]), []);
  assert.deepEqual(await selectedKeys("not-json", [payload("a")]), ["a"]);
});

test("submitted selection is intersected with available preview keys", async () => {
  assert.deepEqual(await selectedKeys('["b", "gone"]', [payload("a", "b")]), ["b"]);
});

test("changing sets keeps the existing select-all behavior", async () => {
  assert.deepEqual(
    await selectedKeys('["b"]', [payload("a", "b"), payload("x", "y")], true),
    ["x", "y"],
  );
});
