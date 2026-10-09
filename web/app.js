"use strict";

/* ================= shared state ================= */

const state = {
  root: null,         // scanned project root (server-resolved path)
  markdown: "",       // generated markdown
  contents: {},       // relative path -> exported content (for patching)
  encodings: {},      // relative path -> encoding detected at export time
  parsedChanges: {},  // relative path -> change dict from the parser
};

const $ = (id) => document.getElementById(id);

/* ================= API ================= */

async function api(name, data = {}) {
  const res = await fetch("/api/" + name, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-PTM-Token": window.PTM_TOKEN,
    },
    body: JSON.stringify(data),
  });
  let body = {};
  try {
    body = await res.json();
  } catch (_) {
    /* empty or non-JSON body */
  }
  if (!res.ok) throw new Error(body.error || "HTTP " + res.status);
  return body;
}

/* ================= messages ================= */

function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.textContent = message;
  el.addEventListener("click", () => el.remove());
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

function showError(err) {
  toast(err instanceof Error ? err.message : String(err), "err");
}

function msgEl(kind, text) {
  const el = document.createElement("div");
  el.className = "msg " + kind;
  el.textContent = text;
  return el;
}

/* ================= clipboard ================= */

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_) {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}

async function copyAndToast(text, message) {
  const ok = await copyText(text);
  toast(ok ? message : "Copy failed — select the text manually.", ok ? "ok" : "err");
}

/* ================= tabs ================= */

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      $("tab-" + btn.dataset.tab).classList.add("active");
    });
  });
}

/* ================= confirm / info dialog ================= */

function showDialog({ message, title = "Confirm", okLabel = "OK", showCancel = true, cancelLabel = "Cancel" }) {
  return new Promise((resolve) => {
    $("confirm-title").textContent = title;
    $("confirm-message").textContent = message;
    $("confirm-ok").textContent = okLabel;
    $("confirm-cancel").textContent = cancelLabel;
    $("confirm-cancel").classList.toggle("hidden", !showCancel);
    const modal = $("modal-confirm");
    const done = (value) => {
      modal.classList.add("hidden");
      $("confirm-ok").onclick = null;
      $("confirm-cancel").onclick = null;
      resolve(value);
    };
    $("confirm-ok").onclick = () => done(true);
    $("confirm-cancel").onclick = () => done(false);
    modal.classList.remove("hidden");
    $("confirm-ok").focus();
  });
}

function askConfirm(message, title = "Confirm") {
  return showDialog({ message, title, okLabel: "Yes", cancelLabel: "No" });
}

/* ================= save-file dialog (returns path or null) ================= */

function openSaveDialog(title, defaultPath) {
  return new Promise((resolve) => {
    $("save-title").textContent = title;
    $("save-path").value = defaultPath || "";
    $("save-error").textContent = "";
    const modal = $("modal-save");
    const close = (value) => {
      modal.classList.add("hidden");
      $("save-confirm").onclick = null;
      $("save-cancel").onclick = null;
      resolve(value);
    };
    $("save-confirm").onclick = () => {
      const path = $("save-path").value.trim();
      if (!path) {
        $("save-error").textContent = "Enter an absolute path.";
        return;
      }
      close(path);
    };
    $("save-cancel").onclick = () => close(null);
    modal.classList.remove("hidden");
    $("save-path").focus();
    $("save-path").select();
  });
}

function suggestPath(name) {
  return state.root ? state.root.replace(/[\\/]+$/, "") + "/" + name : name;
}

/* ================= folder picker ================= */

const picker = { current: null, parent: null, onChoose: null, selected: null };

function openFolderPicker(title, startPath, onChoose) {
  picker.onChoose = onChoose;
  picker.selected = null;
  $("picker-title").textContent = title;
  $("picker-error").textContent = "";
  $("modal-picker").classList.remove("hidden");
  loadPickerDir(startPath || picker.current || null);
}

async function loadPickerDir(path) {
  try {
    const data = await api("fs_list", path ? { path } : {});
    picker.current = data.path;
    picker.parent = data.parent;
    picker.selected = data.path; // by default, "this folder"
    $("picker-path").value = data.path;
    renderPicker(data.entries);
    $("picker-error").textContent = "";
  } catch (err) {
    $("picker-error").textContent = err.message;
  }
}

function renderPicker(entries) {
  const list = $("picker-list");
  list.textContent = "";
  const dirs = entries.filter((e) => e.is_dir);
  if (!dirs.length) {
    const empty = document.createElement("div");
    empty.className = "empty muted";
    empty.textContent = "(no subfolders)";
    list.appendChild(empty);
    return;
  }
  for (const d of dirs) {
    const row = document.createElement("div");
    row.className = "check-row";
    row.dataset.path = picker.current.replace(/[\\/]+$/, "") + "/" + d.name;
    const icon = document.createElement("span");
    icon.textContent = "📁";
    const nameEl = document.createElement("span");
    nameEl.className = "path";
    nameEl.textContent = d.name;
    row.append(icon, nameEl);
    row.addEventListener("click", () => {
      list.querySelectorAll(".check-row").forEach((r) => r.classList.remove("selected"));
      row.classList.add("selected");
      picker.selected = row.dataset.path;
    });
    row.addEventListener("dblclick", () => loadPickerDir(row.dataset.path));
    list.appendChild(row);
  }
}

function initPicker() {
  $("picker-up").addEventListener("click", () => {
    if (picker.parent) loadPickerDir(picker.parent);
  });
  $("picker-path").addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadPickerDir($("picker-path").value.trim());
  });
  $("picker-cancel").addEventListener("click", () => {
    $("modal-picker").classList.add("hidden");
    picker.onChoose = null;
  });
  $("picker-choose").addEventListener("click", () => {
    const chosen = picker.selected;
    $("modal-picker").classList.add("hidden");
    if (chosen && picker.onChoose) picker.onChoose(chosen);
    picker.onChoose = null;
  });
}

/* ================= export tab ================= */

function renderFileList(files) {
  const list = $("file-list");
  list.textContent = "";
  for (const rel of files) {
    const row = document.createElement("label");
    row.className = "check-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.value = rel;
    const span = document.createElement("span");
    span.className = "path";
    span.textContent = rel;
    row.append(cb, span);
    list.appendChild(row);
  }
  $("file-count").textContent = "(" + files.length + ")";
}

function checkedValues(listId) {
  return Array.from(
    $(listId).querySelectorAll('input[type="checkbox"]:checked')
  ).map((cb) => cb.value);
}

function setPreview(md) {
  $("preview").textContent = md || "";
}

function enableExportButtons(on) {
  ["btn-copy-md", "btn-save-md", "btn-full-prompt", "btn-save-prompt"].forEach((id) => {
    $(id).disabled = !on;
  });
}

async function onScan() {
  const path = $("project-path").value.trim();
  if (!path) {
    showError("Please select a valid project folder.");
    return;
  }
  const btn = $("btn-scan");
  btn.disabled = true;
  btn.textContent = "Scanning…";
  try {
    const data = await api("scan", { root: path });
    state.root = data.root;
    $("project-path").value = data.root;
    renderFileList(data.files);
    $("btn-generate").disabled = false;
    enableExportButtons(false);
    setPreview("");
    $("token-label").textContent = "";
  } catch (err) {
    showError(err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Scan Project";
  }
}

async function onGenerate() {
  const selected = checkedValues("file-list");
  if (!selected.length) {
    showError("No files selected. Check at least one file.");
    return;
  }
  const btn = $("btn-generate");
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    const data = await api("export", { root: state.root, files: selected });
    state.markdown = data.markdown;
    state.contents = data.contents;
    state.encodings = data.encodings;
    setPreview(data.markdown);
    $("token-label").textContent = "Markdown tokens: ~" + data.tokens;
    enableExportButtons(true);
  } catch (err) {
    showError(err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Markdown from Selected";
  }
}

async function onSaveMarkdown() {
  const path = await openSaveDialog("Save Markdown File", suggestPath("project_export.md"));
  if (!path) return;
  try {
    const r = await api("save_file", { path, content: state.markdown });
    toast("Markdown saved to " + r.path, "ok");
  } catch (err) {
    showError("Failed to save: " + err.message);
  }
}

async function onFullPrompt() {
  try {
    const data = await api("prompt", { markdown: state.markdown });
    await copyAndToast(data.full_prompt,
      "Full prompt (with foolproof instructions) copied to clipboard.");
    $("token-label").textContent =
      "Markdown tokens: ~" + data.tokens_md + "  |  Full prompt tokens: ~" + data.tokens_full;
  } catch (err) {
    showError(err);
  }
}

async function onSavePrompt() {
  try {
    const data = await api("prompt", { markdown: state.markdown });
    const path = await openSaveDialog("Save Full Prompt", suggestPath("full_prompt.md"));
    if (!path) return;
    const r = await api("save_file", { path, content: data.full_prompt });
    toast("Full prompt saved to " + r.path, "ok");
  } catch (err) {
    showError("Failed to save: " + err.message);
  }
}

async function onSystemPrompt() {
  try {
    const data = await api("system_prompt", {});
    await copyAndToast(data.text, "System prompt copied to clipboard.");
  } catch (err) {
    showError(err);
  }
}

function initExportTab() {
  $("btn-browse-project").addEventListener("click", () => {
    openFolderPicker("Select Project Folder", null, (path) => {
      $("project-path").value = path;
    });
  });
  $("btn-scan").addEventListener("click", onScan);
  $("btn-generate").addEventListener("click", onGenerate);
  $("btn-select-all").addEventListener("click", () => {
    $("file-list").querySelectorAll('input[type="checkbox"]').forEach((cb) => { cb.checked = true; });
  });
  $("btn-select-none").addEventListener("click", () => {
    $("file-list").querySelectorAll('input[type="checkbox"]').forEach((cb) => { cb.checked = false; });
  });
  $("btn-copy-md").addEventListener("click", () =>
    copyAndToast(state.markdown, "Markdown copied to clipboard."));
  $("btn-save-md").addEventListener("click", onSaveMarkdown);
  $("btn-full-prompt").addEventListener("click", onFullPrompt);
  $("btn-save-prompt").addEventListener("click", onSavePrompt);
  $("btn-system-prompt").addEventListener("click", onSystemPrompt);
}

/* ================= project builder tab ================= */

function renderParseMessages(errors, warnings) {
  const box = $("parse-messages");
  box.textContent = "";
  if (errors.length) {
    box.appendChild(msgEl("err",
      "The response could not be parsed safely for " + errors.length + " block(s):\n\n" +
      errors.map((e) => "• " + e).join("\n\n") +
      "\n\nNothing was applied for those files."));
  }
  if (warnings.length) {
    box.appendChild(msgEl("warn",
      "Parsed with warnings:\n\n" + warnings.map((w) => "• " + w).join("\n\n")));
  }
}

function renderChangeList() {
  const list = $("change-list");
  list.textContent = "";
  const paths = Object.keys(state.parsedChanges);
  if (!paths.length) {
    const empty = document.createElement("div");
    empty.className = "empty muted";
    empty.textContent = "Parsed changes appear here.";
    list.appendChild(empty);
    $("change-count").textContent = "";
    return;
  }
  for (const path of paths) {
    const change = state.parsedChanges[path];
    const row = document.createElement("label");
    row.className = "check-row";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.value = path;

    const action = change && change.action ? change.action : "other";
    const badge = document.createElement("span");
    const known = ["create", "modify", "delete"].includes(action);
    badge.className = "badge " + (known ? action : "other");
    badge.textContent = action;

    const span = document.createElement("span");
    span.className = "path";
    span.textContent = path;

    row.append(cb, badge, span);
    list.appendChild(row);
  }
  $("change-count").textContent = "(" + paths.length + ")";
}

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

async function onParse() {
  try {
    const data = await api("parse", { text: $("ai-response").value });
    state.parsedChanges = data.changes;
    renderChangeList();
    renderParseMessages(data.errors, data.warnings);
    $("parse-stats").textContent =
      Object.keys(data.changes).length + " file change(s) parsed";
  } catch (err) {
    showError(err);
  }
}

function onClear() {
  $("ai-response").value = "";
  state.parsedChanges = {};
  renderChangeList();
  $("parse-messages").textContent = "";
  $("parse-stats").textContent = "";
  $("apply-report").textContent = "";
}

function renderApplyReport(data) {
  const box = $("apply-report");
  box.textContent = "";
  box.appendChild(msgEl(data.skipped.length ? "err" : "ok", data.summary));
}

async function onApply() {
  const mode = currentMode();
  if ((mode === "inplace" || mode === "export") && !state.root) {
    showError("No project loaded. Go to Export tab and scan a project first.");
    return;
  }
  const selected = {};
  for (const path of checkedValues("change-list")) {
    if (state.parsedChanges[path]) selected[path] = state.parsedChanges[path];
  }
  if (!Object.keys(selected).length) {
    showError("No changes selected. Check at least one file.");
    return;
  }
  const dest = $("dest-path").value.trim();
  if (mode !== "inplace" && !dest) {
    showError("Please choose a destination folder.");
    return;
  }
  if (mode === "inplace") {
    const sure = await askConfirm(
      "Modify original project (a backup will be created). Are you sure?",
      "Confirm");
    if (!sure) return;
  }

  const btn = $("btn-apply");
  btn.disabled = true;
  try {
    const data = await api("apply", {
      mode: mode,
      root: state.root,
      dest: dest,
      changes: selected,
      contents: state.contents,
      encodings: state.encodings,
    });
    renderApplyReport(data);
    if (mode === "export") {
      toast("Project exported to " + dest + " with changes applied.", "ok");
    } else if (mode === "create") {
      toast("New project created at " + dest + " with all changes applied.", "ok");
    }
  } catch (err) {
    showError("Error applying changes: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

function initBuilderTab() {
  $("btn-parse").addEventListener("click", onParse);
  $("btn-clear").addEventListener("click", onClear);
  $("btn-apply").addEventListener("click", onApply);
  document.querySelectorAll('input[name="mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      $("dest-row").classList.toggle("hidden", currentMode() === "inplace");
    });
  });
  $("btn-browse-dest").addEventListener("click", () => {
    openFolderPicker("Select Destination Folder", null, (path) => {
      $("dest-path").value = path;
    });
  });
}

/* ================= settings tab ================= */

function fillSettings(cfg) {
  $("set-extensions").value = cfg.text_extensions.join("\n");
  $("set-dirs").value = cfg.excluded_dirs.join("\n");
  $("set-size").value = String(cfg.max_file_size_kb);
  $("set-autosave").checked = cfg.output_auto_save;
}

function linesOf(id) {
  return $(id).value.split("\n").map((s) => s.trim()).filter(Boolean);
}

async function onSaveSettings() {
  try {
    const cfg = await api("config_save", {
      extensions: linesOf("set-extensions"),
      excluded_dirs: linesOf("set-dirs"),
      max_file_size_kb: parseInt($("set-size").value, 10),
      output_auto_save: $("set-autosave").checked,
    });
    fillSettings(cfg);
    toast("Settings saved. Changes will apply to the next scan.", "ok");
  } catch (err) {
    showError(err.message);
  }
}

async function onResetSettings() {
  const sure = await askConfirm(
    "Restore all settings to their original defaults?", "Reset Settings");
  if (!sure) return;
  try {
    const cfg = await api("config_reset", {});
    fillSettings(cfg);
    toast("Settings have been reset to defaults.", "ok");
  } catch (err) {
    showError(err);
  }
}

async function onAbout() {
  await showDialog({
    title: "About ProjectToMarkdown",
    message:
      "ProjectToMarkdown v1.0.0\n\n" +
      "Bridge your local projects to free chat LLMs — no API keys needed.\n" +
      "100% offline: no API calls, no telemetry.\n\n" +
      "License: GPL-3.0",
    okLabel: "Close",
    showCancel: false,
  });
}

function initSettingsTab() {
  $("btn-settings-save").addEventListener("click", onSaveSettings);
  $("btn-settings-reset").addEventListener("click", onResetSettings);
  $("btn-about").addEventListener("click", onAbout);
}

/* ================= boot ================= */

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initPicker();
  initExportTab();
  initBuilderTab();
  initSettingsTab();
  try {
    fillSettings(await api("config_get", {}));
  } catch (err) {
    showError("Could not load settings: " + err.message);
  }
});
