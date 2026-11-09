(() => {
  const form = document.querySelector(".reconcile-review-form");
  if (!form) return;
  const rows = Array.from(form.querySelectorAll("[data-reconcile-row]"));

  function updatePreview() {
    const remaining = new Map();
    for (const row of rows) {
      const selected = row.querySelector('input[type="checkbox"]');
      const printing = row.querySelector("select");
      const choice = printing.selectedOptions[0];
      const identity = printing.value || row.dataset.newIdentity;
      const before = printing.value ? Number(choice.dataset.quantity) : identity ? 0 : null;
      const current = identity && remaining.has(identity) ? remaining.get(identity) : before;
      row.querySelector("[data-current]").textContent = current ?? "—";
      const proposed = row.querySelector("[data-proposed]");
      if (!selected.checked || selected.disabled) {
        proposed.textContent = "Not selected";
        continue;
      }
      const total = row.querySelector('input[type="number"]');
      const amount = Number(total ? total.value : row.dataset.quantity);
      if (!identity || !Number.isSafeInteger(amount) || amount < 0 || current === null) {
        proposed.textContent = "Review required";
        continue;
      }
      const after = form.dataset.kind === "snapshot" ? amount : current - (form.dataset.basis === "already_reflected" ? 0 : amount);
      proposed.textContent = after < 0 ? "Exceeds owned quantity" : String(after);
      remaining.set(identity, after);
    }
  }

  form.addEventListener("change", updatePreview);
  form.addEventListener("input", updatePreview);
  updatePreview();
})();
