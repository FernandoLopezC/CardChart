(() => {
  const form = document.querySelector("#goal-authoring-form");
  if (!form) return;

  const setSearch = form.querySelector("#set-search");
  const setSelect = form.querySelector("#set-code");
  const language = form.querySelector("#goal-language");
  const collectorFrom = form.querySelector("#collector-from");
  const collectorTo = form.querySelector("#collector-to");
  const metadataFilters = form.querySelector("#metadata-filters");
  const selectedInput = form.querySelector("#selected-entry-keys");
  const submitButton = form.querySelector("#review-selected");
  const selectionCount = form.querySelector("#selection-count");
  const emptyState = form.querySelector("#preview-empty");
  const loadingState = form.querySelector("#preview-loading");
  const errorState = form.querySelector("#preview-error");
  const results = form.querySelector("#preview-results");
  const treatmentFilters = form.querySelector("#treatment-filters");
  const selectedPreview = form.querySelector("#selected-card-preview");
  const cardGrid = form.querySelector("#preview-card-grid");
  const visibleCount = form.querySelector("#visible-count");
  const selectVisible = form.querySelector("#select-visible");
  const deselectVisible = form.querySelector("#deselect-visible");
  const selectedOnlyButton = form.querySelector("#toggle-selected-only");

  const setOptions = Array.from(setSelect.options);
  let entries = [];
  let knownKeys = new Set();
  let selectedKeys = new Set();
  let submittedKeys = null;
  try {
    const submitted = selectedInput.value.trim();
    if (submitted) {
      const parsed = JSON.parse(submitted);
      if (Array.isArray(parsed) && parsed.every((key) => typeof key === "string")) {
        submittedKeys = new Set(parsed);
      }
    }
  } catch (_error) {
    // Invalid hidden input is treated like a fresh form.
  }
  let hasLoadedPreview = false;
  let activeTreatments = new Set();
  let selectedOnly = false;
  let requestController = null;
  let debounceTimer = null;
  let lastSetCode = "";

  function filterSetOptions() {
    const query = setSearch.value.trim().toLowerCase();
    for (const option of setOptions) {
      if (!option.value) continue;
      option.hidden = Boolean(query) && !option.dataset.search.includes(query);
    }
  }

  function previewParameters() {
    return new URLSearchParams({
      set_code: setSelect.value,
      language: language.value,
      collector_from: collectorFrom.value,
      collector_to: collectorTo.value,
      metadata_filters: metadataFilters.value,
    });
  }

  async function loadPreview() {
    if (!setSelect.value) {
      entries = [];
      showState("empty");
      updateSelection();
      return;
    }
    if (requestController) requestController.abort();
    requestController = new AbortController();
    showState("loading");
    try {
      const response = await fetch(
        `${form.dataset.previewUrl}?${previewParameters()}`,
        {signal: requestController.signal, headers: {Accept: "application/json"}},
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not load cards.");

      const setChanged = lastSetCode !== setSelect.value;
      const nextKeys = new Set(payload.entries.map((entry) => entry.key));
      if (!hasLoadedPreview && submittedKeys !== null) {
        selectedKeys = new Set(
          Array.from(submittedKeys).filter((key) => nextKeys.has(key)),
        );
      } else if (setChanged || !knownKeys.size) {
        selectedKeys = new Set(nextKeys);
      } else {
        selectedKeys = new Set(
          Array.from(selectedKeys).filter((key) => nextKeys.has(key)),
        );
        for (const key of nextKeys) {
          if (!knownKeys.has(key)) selectedKeys.add(key);
        }
      }
      lastSetCode = setSelect.value;
      hasLoadedPreview = true;
      knownKeys = nextKeys;
      entries = payload.entries;
      activeTreatments = new Set(payload.treatments.map((item) => item.key));
      selectedOnly = false;
      selectedOnlyButton.textContent = "Show selected only";
      renderTreatments(payload.treatments);
      renderCards();
      showState("results");
      updateSelection();
    } catch (error) {
      if (error.name === "AbortError") return;
      entries = [];
      errorState.textContent = error.message;
      showState("error");
      updateSelection();
    }
  }

  function showState(state) {
    emptyState.hidden = state !== "empty";
    loadingState.hidden = state !== "loading";
    errorState.hidden = state !== "error";
    results.hidden = state !== "results";
  }

  function renderTreatments(treatments) {
    treatmentFilters.replaceChildren();
    for (const treatment of treatments) {
      const label = document.createElement("label");
      label.className = "treatment-filter";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = treatment.key;
      checkbox.checked = true;
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) activeTreatments.add(treatment.key);
        else activeTreatments.delete(treatment.key);
        renderCards();
      });
      label.append(checkbox, `${treatment.label} (${treatment.count})`);
      treatmentFilters.append(label);
    }
  }

  function visibleEntries() {
    return entries.filter((entry) => {
      const matchesTreatment = entry.treatment_keys.some((key) =>
        activeTreatments.has(key),
      );
      return matchesTreatment && (!selectedOnly || selectedKeys.has(entry.key));
    });
  }

  function renderCards() {
    const visible = visibleEntries();
    cardGrid.replaceChildren();
    for (const entry of visible) {
      const article = document.createElement("article");
      article.className = "preview-card";
      if (selectedKeys.has(entry.key)) article.classList.add("selected");

      const selector = document.createElement("label");
      selector.className = "preview-card-selector";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = selectedKeys.has(entry.key);
      checkbox.setAttribute("aria-label", `Include ${entry.name}`);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedKeys.add(entry.key);
        else selectedKeys.delete(entry.key);
        article.classList.toggle("selected", checkbox.checked);
        updateSelection();
        if (selectedOnly && !checkbox.checked) renderCards();
      });
      selector.append(checkbox, document.createTextNode("Include"));
      article.append(selector);

      if (entry.image_url) {
        const image = document.createElement("img");
        image.src = entry.image_url;
        image.alt = "";
        image.loading = "lazy";
        article.append(image);
      } else {
        const placeholder = document.createElement("div");
        placeholder.className = "preview-card-placeholder";
        placeholder.textContent = "No image";
        article.append(placeholder);
      }

      const body = document.createElement("div");
      body.className = "preview-card-body";
      const heading = document.createElement("h3");
      heading.textContent = entry.name;
      const metadata = document.createElement("p");
      metadata.textContent = `#${entry.collector_number} · ${entry.version_count} version${entry.version_count === 1 ? "" : "s"}`;
      const badges = document.createElement("div");
      badges.className = "treatment-badges";
      for (const treatment of entry.treatments) {
        const badge = document.createElement("span");
        badge.textContent = treatment;
        badges.append(badge);
      }
      body.append(heading, metadata, badges);
      article.append(body);
      cardGrid.append(article);
    }
    visibleCount.textContent = `${visible.length} visible of ${entries.length}`;
  }

  function updateSelection() {
    const selected = entries.filter((entry) => selectedKeys.has(entry.key));
    selectedInput.value = JSON.stringify(selected.map((entry) => entry.key));
    selectionCount.textContent = entries.length
      ? `${selected.length} of ${entries.length} selected`
      : "Choose a set";
    submitButton.disabled = selected.length === 0;
    selectedPreview.replaceChildren();
    for (const entry of selected.slice(0, 8)) {
      const item = document.createElement("span");
      if (entry.image_url) {
        const image = document.createElement("img");
        image.src = entry.image_url;
        image.alt = "";
        item.append(image);
      }
      item.append(document.createTextNode(entry.name));
      selectedPreview.append(item);
    }
    if (selected.length > 8) {
      const more = document.createElement("span");
      more.className = "selected-card-more";
      more.textContent = `+${selected.length - 8} more`;
      selectedPreview.append(more);
    }
  }

  function schedulePreview() {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(loadPreview, 350);
  }

  setSearch.addEventListener("input", filterSetOptions);
  setSelect.addEventListener("change", loadPreview);
  language.addEventListener("change", loadPreview);
  collectorFrom.addEventListener("input", schedulePreview);
  collectorTo.addEventListener("input", schedulePreview);
  metadataFilters.addEventListener("input", schedulePreview);
  selectVisible.addEventListener("click", () => {
    for (const entry of visibleEntries()) selectedKeys.add(entry.key);
    renderCards();
    updateSelection();
  });
  deselectVisible.addEventListener("click", () => {
    for (const entry of visibleEntries()) selectedKeys.delete(entry.key);
    renderCards();
    updateSelection();
  });
  selectedOnlyButton.addEventListener("click", () => {
    selectedOnly = !selectedOnly;
    selectedOnlyButton.textContent = selectedOnly
      ? "Show all matching"
      : "Show selected only";
    renderCards();
  });
  form.addEventListener("submit", (event) => {
    if (!selectedKeys.size) {
      event.preventDefault();
      errorState.textContent = "Select at least one card before continuing.";
      showState("error");
    }
  });

  filterSetOptions();
  if (setSelect.value) loadPreview();
})();
