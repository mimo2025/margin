"use strict";

const byId = (id) => document.getElementById(id);
const searchForm = byId("search-form");
const documentFilter = byId("document-filter");
const query = byId("query");
const results = byId("results");
const editForm = byId("edit-form");
const replacement = byId("replacement");
const instruction = byId("instruction");
let selectedMatch = null;
let busy = false;

function showStatus(message, kind = "info") {
  byId("status").textContent = message;
  byId("status").dataset.kind = kind;
}

function updateControls() {
  for (const control of document.querySelectorAll("input, select, textarea, button")) {
    control.disabled = busy;
  }
  replacement.disabled = busy || !selectedMatch;
  instruction.disabled = busy || !selectedMatch;
  byId("suggest-button").disabled = busy || !selectedMatch || !instruction.value.trim();
  byId("save-button").disabled = busy || !selectedMatch || replacement.value === selectedMatch.target.text;
  byId("deletion-note").hidden = !selectedMatch || replacement.value !== "";
  byId("workspace").setAttribute("aria-busy", String(busy));
}

// One action at a time prevents a slow AI response from overwriting a newer selection.
async function runAction(action) {
  if (busy) return;
  busy = true;
  updateControls();
  showStatus("");
  try {
    await action();
  } catch (error) {
    if (error.status === 409 || error.status === 404) {
      invalidateSearch("Search again to select current text.");
    }
    showStatus(error.message, "error");
  } finally {
    busy = false;
    updateControls();
  }
}

async function api(path, method = "GET", body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Unable to reach the server. Check that it is running and try again.");
  }
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "The request failed. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function clearSelection() {
  selectedMatch = null;
  editForm.hidden = true;
  byId("review-empty").hidden = false;
  replacement.value = "";
  instruction.value = "";
  for (const button of results.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", "false");
  }
}

function invalidateSearch(message) {
  clearSelection();
  results.replaceChildren();
  byId("document-preview").hidden = true;
  byId("results-summary").textContent = message;
}

function showDocument(doc) {
  byId("document-preview").hidden = false;
  byId("document-heading").textContent = `${doc.title} · Version ${doc.version} · View document`;
  // Cap display size only. Never calculate edit positions using JavaScript string indices.
  const maxPreview = 20000;
  byId("document-text").textContent = doc.text.length > maxPreview
    ? doc.text.slice(0, maxPreview) + "\n\n… Document preview shortened."
    : doc.text;
}

async function selectMatch(match, button) {
  clearSelection();
  const doc = await api(`/documents/${encodeURIComponent(match.document_id)}`);
  if (doc.version !== match.version) {
    const error = new Error("This document has changed. Search again before editing.");
    error.status = 409;
    throw error;
  }
  selectedMatch = match;
  button.setAttribute("aria-pressed", "true");
  byId("selection-title").textContent = `${match.title} · Version ${match.version}`;
  byId("original").textContent = match.target.text;
  replacement.value = match.target.text;
  byId("review-empty").hidden = true;
  editForm.hidden = false;
  showDocument(doc);
  showStatus("Edit the replacement yourself, or ask AI for wording. Nothing is saved yet.");
}

async function searchDocuments() {
  invalidateSearch("Searching…");
  const params = new URLSearchParams({ q: query.value, limit: "50", context_chars: "60" });
  if (documentFilter.value) params.set("document_id", documentFilter.value);
  const data = await api(`/documents/search?${params}`);
  const count = data.matches.length;
  byId("results-summary").textContent = data.truncated
    ? "Showing the first 50 matches. Narrow your phrase or choose one document."
    : count === 0 ? "No exact matches. Try a different phrase or document."
      : `${count} ${count === 1 ? "match" : "matches"}. Select one to review.`;
  for (const match of data.matches) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "match";
    button.setAttribute("aria-pressed", "false");
    const title = document.createElement("span");
    title.className = "match-title";
    title.textContent = `${match.title} · v${match.version}`;
    const context = document.createElement("span");
    context.className = "match-context";
    const highlight = document.createElement("mark");
    highlight.textContent = match.target.text;
    // Use text nodes: document content must never become executable HTML.
    context.append(match.context_before, highlight, match.context_after);
    button.append(title, context);
    button.addEventListener("click", () => runAction(() => selectMatch(match, button)));
    item.append(button);
    results.append(item);
  }
}

async function suggestWording() {
  showStatus("Asking AI for replacement wording…");
  const suggestion = await api(
    `/documents/${encodeURIComponent(selectedMatch.document_id)}/suggest`,
    "POST",
    {
      expected_version: selectedMatch.version,
      target: selectedMatch.target,
      instruction: instruction.value,
    },
  );
  replacement.value = suggestion.replacement;
  showStatus("Suggestion ready. Review or edit it, then save when you’re satisfied.", "success");
}

async function saveChange() {
  showStatus("Saving your reviewed change…");
  let updated;
  try {
    updated = await api(`/documents/${encodeURIComponent(selectedMatch.document_id)}`, "PATCH", {
      expected_version: selectedMatch.version,
      target: selectedMatch.target,
      replacement: replacement.value,
    });
  } catch (error) {
    // A disconnected response may still have been saved on the server. Refresh before retrying.
    invalidateSearch("Search again to check the document before retrying the save.");
    throw error;
  }
  invalidateSearch("Search again to make another change.");
  showDocument(updated);
  byId("document-preview").open = true;
  showStatus(`Saved to ${updated.title}, version ${updated.version}.`, "success");
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAction(searchDocuments);
});
editForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAction(saveChange);
});
byId("suggest-button").addEventListener("click", () => runAction(suggestWording));
replacement.addEventListener("input", updateControls);
instruction.addEventListener("input", updateControls);
for (const control of [documentFilter, query]) {
  control.addEventListener("input", () => {
    invalidateSearch("Search to see matches for this phrase and document.");
    updateControls();
  });
}

runAction(async () => {
  const documents = await api("/documents");
  for (const doc of documents) {
    const option = document.createElement("option");
    option.value = doc.id;
    option.textContent = doc.title;
    documentFilter.append(option);
  }
});
