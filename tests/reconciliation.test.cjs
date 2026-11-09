const {readFileSync} = require("node:fs");
const {runInNewContext} = require("node:vm");
const {test} = require("node:test");
const assert = require("node:assert/strict");
const script = readFileSync("cardchart/static/reconciliation.js", "utf8");

function preview(kind, basis, inputs) {
  const rows = inputs.map(({checked = true, quantity = 2, current = 5, id = "1", total}) => {
    const proposed = {textContent: ""};
    const currentCell = {textContent: ""};
    const controls = {
      'input[type="checkbox"]': {checked, disabled: false},
      select: {value: id, selectedOptions: [{dataset: {quantity: String(current)}}]},
      'input[type="number"]': total === undefined ? null : {value: String(total)},
      "[data-current]": currentCell, "[data-proposed]": proposed,
    };
    return {dataset: {quantity: String(quantity), newIdentity: ""}, querySelector: (selector) => controls[selector], proposed, currentCell};
  });
  const form = {dataset: {kind, basis}, querySelectorAll: () => rows, addEventListener() {}};
  runInNewContext(script, {document: {querySelector: () => form}});
  return rows.map((row) => [row.currentCell.textContent, row.proposed.textContent]);
}

test("selected transactions for the same printing show their combined deduction", () => {
  assert.deepEqual(preview("disposal", "unreflected", [{quantity: 2}, {quantity: 1}]), [[5, "3"], [3, "2"]]);
});
test("unselected rows do not change the next transaction's count", () => {
  assert.deepEqual(preview("disposal", "unreflected", [{checked: false}, {quantity: 1}]), [[5, "Not selected"], [5, "4"]]);
});
test("already reflected transactions preview unchanged stock", () => {
  assert.deepEqual(preview("disposal", "already_reflected", [{}]), [[5, "5"]]);
});
test("snapshots preview entered absolute totals and overselling is explicit", () => {
  assert.deepEqual(preview("snapshot", "", [{total: 3}]), [[5, "3"]]);
  assert.deepEqual(preview("disposal", "unreflected", [{quantity: 6}]), [[5, "Exceeds owned quantity"]]);
});
