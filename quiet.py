#!/usr/bin/env python3
"""A tiny, dependency-free local writing app.

Run:
    python3 app.py
Then open http://127.0.0.1:8765 in your browser.
Drafts are stored in the browser's localStorage, not on the Python server.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser

HOST = "127.0.0.1"
PORT = 8765

PAGE = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Quiet — writing space</title>
<style>
  :root {
    --bg: #f4f1eb;
    --panel: #fbf9f5;
    --text: #292b2b;
    --muted: #85837d;
    --line: #ded9cf;
    --accent: #6c7564;
    --accent-soft: #e6e9e0;
    --editor: #fbf9f5;
    --shadow: 0 18px 55px rgba(54, 48, 37, .07);
    --font: Georgia, "Times New Roman", serif;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body {
    margin: 0; min-height: 100vh; background: var(--bg); color: var(--text);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    transition: background .25s ease, color .25s ease;
  }
  body[data-theme="midnight"] {
    --bg: #171b20; --panel: #20262d; --text: #e5e3dc; --muted: #929ba4;
    --line: #353d46; --accent: #b7c9dc; --accent-soft: #2c3947; --editor: #20262d;
    --shadow: 0 18px 55px rgba(0, 0, 0, .18);
  }
  body[data-theme="paper"] {
    --bg: #e9dfca; --panel: #f6eedc; --text: #40352a; --muted: #8f806b;
    --line: #d8c9ae; --accent: #9a6049; --accent-soft: #ead9c8; --editor: #f6eedc;
    --shadow: 0 18px 55px rgba(83, 58, 31, .08);
  }
  body[data-theme="studio"] {
    --bg: #e9e9e7; --panel: #f8f8f6; --text: #202322; --muted: #777c79;
    --line: #d6d9d6; --accent: #476f68; --accent-soft: #dce9e5; --editor: #f8f8f6;
    --shadow: 0 18px 55px rgba(30, 40, 36, .06);
  }
  button, input, textarea, select { font: inherit; }
  button { cursor: pointer; }
  .shell { max-width: 1120px; margin: 0 auto; padding: 24px 30px 30px; min-height: 100vh; display: flex; flex-direction: column; }
  header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 4px 0 24px; }
  .brand { display: flex; align-items: center; gap: 11px; }
  .mark { width: 30px; height: 30px; border: 1px solid var(--accent); border-radius: 50%; display: grid; place-items: center; color: var(--accent); font-family: var(--font); font-size: 19px; }
  .brand-name { font-size: 13px; font-weight: 750; letter-spacing: .16em; text-transform: uppercase; }
  .brand-note { color: var(--muted); font-size: 11px; margin-top: 3px; letter-spacing: .04em; }
  .header-actions { display: flex; align-items: center; gap: 9px; }
  .quiet-label { color: var(--muted); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; }
  select, .small-btn {
    border: 1px solid var(--line); border-radius: 999px; color: var(--text); background: var(--panel);
    padding: 9px 13px; font-size: 12px; outline: none;
  }
  .small-btn:hover, select:hover { border-color: var(--accent); }
  .workspace { flex: 1; display: grid; grid-template-columns: 205px minmax(0, 1fr); gap: 25px; min-height: 600px; }
  aside { padding-top: 8px; display: flex; flex-direction: column; min-height: 0; }
  .aside-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 13px; }
  .section-label { color: var(--muted); text-transform: uppercase; font-size: 10px; letter-spacing: .16em; font-weight: 700; }
  .new-btn { border: 0; background: var(--accent-soft); color: var(--accent); border-radius: 50%; width: 28px; height: 28px; font-size: 19px; line-height: 1; }
  .draft-list { display: flex; flex-direction: column; gap: 5px; overflow-y: auto; max-height: calc(100vh - 230px); padding-right: 3px; }
  .draft-item { position: relative; border: 1px solid transparent; border-radius: 9px; padding: 12px 10px; text-align: left; background: transparent; color: var(--text); }
  .draft-item:hover { background: var(--panel); }
  .draft-item.active { background: var(--panel); border-color: var(--line); box-shadow: 0 3px 12px rgba(0,0,0,.025); }
  .draft-title { display: block; font-family: var(--font); font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 5px; }
  .draft-meta { display: block; font-size: 10px; color: var(--muted); }
  .empty-list { color: var(--muted); font-size: 12px; line-height: 1.6; padding: 12px 2px; }
  .aside-bottom { margin-top: auto; padding-top: 18px; color: var(--muted); font-size: 11px; line-height: 1.6; }
  .editor-card { background: var(--editor); border: 1px solid var(--line); border-radius: 15px; box-shadow: var(--shadow); min-height: 620px; display: flex; flex-direction: column; overflow: hidden; }
  .editor-toolbar { min-height: 48px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 24px; border-bottom: 1px solid var(--line); }
  .save-state { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 11px; }
  .save-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .toolbar-right { display: flex; align-items: center; gap: 15px; }
  .text-action { background: none; border: 0; color: var(--muted); font-size: 11px; padding: 7px 0; }
  .text-action:hover { color: var(--text); }
  .text-action.danger:hover { color: #c45b50; }
  .writing-area { width: min(100%, 760px); margin: 0 auto; padding: 52px clamp(25px, 7vw, 82px) 34px; flex: 1; display: flex; flex-direction: column; }
  .date-line { color: var(--muted); text-transform: uppercase; letter-spacing: .14em; font-size: 10px; margin-bottom: 28px; }
  #title { width: 100%; border: 0; outline: 0; resize: none; overflow: hidden; background: transparent; color: var(--text); font-family: var(--font); font-size: clamp(29px, 4vw, 43px); font-weight: 400; line-height: 1.15; letter-spacing: -.035em; padding: 0; margin: 0 0 24px; min-height: 52px; }
  #title::placeholder { color: var(--muted); opacity: .58; }
  #content { width: 100%; flex: 1; min-height: 340px; border: 0; outline: 0; resize: vertical; background: transparent; color: var(--text); font-family: var(--font); font-size: 17px; line-height: 1.85; padding: 0; }
  #content::placeholder { color: var(--muted); opacity: .68; }
  .editor-footer { border-top: 1px solid var(--line); min-height: 43px; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 24px; color: var(--muted); font-size: 10px; }
  .footer-hint kbd { font-family: inherit; border: 1px solid var(--line); border-radius: 4px; padding: 2px 5px; margin: 0 2px; }
  .empty-state { flex: 1; display: grid; place-items: center; text-align: center; color: var(--muted); padding: 30px; }
  .empty-state .glyph { font-family: var(--font); font-size: 46px; color: var(--accent); margin-bottom: 14px; }
  .empty-state h2 { font-family: var(--font); font-size: 25px; font-weight: 400; color: var(--text); margin: 0 0 9px; }
  .empty-state p { max-width: 260px; font-size: 12px; line-height: 1.7; margin: 0 auto 20px; }
  .primary-btn { border: 0; border-radius: 999px; background: var(--accent); color: var(--panel); padding: 11px 17px; font-size: 12px; }
  .primary-btn:hover { opacity: .88; }
  .notice { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%) translateY(12px); opacity: 0; pointer-events: none; background: var(--text); color: var(--bg); border-radius: 8px; padding: 10px 14px; font-size: 12px; transition: .2s; }
  .notice.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  @media (max-width: 720px) {
    .shell { padding: 17px 13px 18px; }
    header { padding-bottom: 17px; }
    .brand-note, .quiet-label { display: none; }
    .workspace { grid-template-columns: 1fr; gap: 12px; min-height: 0; }
    aside { order: 2; }
    .draft-list { flex-direction: row; max-height: none; overflow-x: auto; padding-bottom: 5px; }
    .draft-item { min-width: 145px; border-color: var(--line); background: var(--panel); }
    .aside-bottom { display: none; }
    .editor-card { min-height: 68vh; }
    .writing-area { padding: 35px 24px 26px; }
    .editor-toolbar { padding: 0 15px; }
    .editor-footer { padding: 0 15px; }
    .footer-hint { display: none; }
  }
  @media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; } }
</style>
</head>
<body data-theme="paper">
<div class="shell">
  <header>
    <div class="brand">
      <div class="mark">q</div>
      <div><div class="brand-name">Quiet</div><div class="brand-note">a small place to think on paper</div></div>
    </div>
    <div class="header-actions">
      <span class="quiet-label">Atmosphere</span>
      <select id="theme" aria-label="Tema">
        <option value="paper">Warm paper</option>
        <option value="studio">Soft studio</option>
        <option value="midnight">Midnight</option>
      </select>
      <button class="small-btn" id="focusToggle" title="Nascondi la lista degli scritti">Focus mode</button>
    </div>
  </header>

  <main class="workspace" id="workspace">
    <aside id="sidebar">
      <div class="aside-top"><span class="section-label">Your drafts</span><button class="new-btn" id="newDraft" aria-label="Nuovo scritto" title="Nuovo scritto">+</button></div>
      <div class="draft-list" id="draftList"></div>
      <div class="aside-bottom">Un posto per scrivere.<br>Niente feed, niente distrazioni.</div>
    </aside>

    <section class="editor-card" aria-label="Editor di scrittura">
      <div class="editor-toolbar">
        <div class="save-state"><span class="save-dot"></span><span id="saveLabel">Salvato in questo browser</span></div>
        <div class="toolbar-right">
          <button class="text-action" id="exportBtn" title="Esporta il testo in un file Markdown (Ctrl+Shift+E)">Export .md</button>
          <button class="text-action danger" id="deleteBtn">Elimina</button>
        </div>
      </div>
      <div class="writing-area" id="writingArea">
        <div class="date-line" id="dateLine"></div>
        <textarea id="title" rows="1" maxlength="240" placeholder="Dai un titolo al pensiero…" aria-label="Titolo"></textarea>
        <textarea id="content" placeholder="Comincia da qui. Non serve sapere dove andrai a finire." aria-label="Contenuto"></textarea>
      </div>
      <div class="empty-state" id="emptyState" hidden>
        <div><div class="glyph">¶</div><h2>Uno spazio vuoto.</h2><p>Un'idea, un appunto, una prima frase. Comincia da quello che hai.</p><button class="primary-btn" id="firstDraft">Comincia a scrivere</button></div>
      </div>
      <div class="editor-footer">
        <span id="wordCount">0 parole</span>
        <span class="footer-hint"><kbd>Ctrl</kbd><kbd>⇧</kbd><kbd>E</kbd> esporta · autosalvataggio attivo</span>
        <span id="charCount">0 caratteri</span>
      </div>
    </section>
  </main>
</div>
<div class="notice" id="notice" role="status"></div>
<script>
(() => {
  const STORAGE_KEY = "quiet-writing-drafts-v1";
  const SETTINGS_KEY = "quiet-writing-settings-v1";
  const $ = (id) => document.getElementById(id);
  const titleInput = $("title"), contentInput = $("content");
  let drafts = [], activeId = null, saveTimer = null, noticeTimer = null, focusMode = false;

  const uid = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);
  const now = () => new Date().toISOString();
  const formatDate = (iso) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "Bozza";
    return new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric" }).format(d);
  };
  const activeDraft = () => drafts.find(d => d.id === activeId);
  const wordTotal = (text) => (text.trim().match(/\S+/g) || []).length;

  function readStorage() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      drafts = Array.isArray(parsed) ? parsed.filter(d => d && typeof d.id === "string") : [];
    } catch (e) { drafts = []; }
    try {
      const settings = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
      if (settings.theme && ["paper", "studio", "midnight"].includes(settings.theme)) $("theme").value = settings.theme;
      document.body.dataset.theme = $("theme").value;
      focusMode = !!settings.focusMode;
    } catch (e) { document.body.dataset.theme = "paper"; }
    applyFocusMode();
  }
  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
      $("saveLabel").textContent = "Salvato in questo browser";
      $("saveLabel").title = "Ultimo salvataggio: " + new Date().toLocaleTimeString("it-IT");
    } catch (e) {
      $("saveLabel").textContent = "Impossibile salvare";
      showNotice("Spazio di archiviazione non disponibile. Esporta una copia.");
    }
  }
  function persistSettings() {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ theme: $("theme").value, focusMode }));
  }
  function makeDraft() {
    const d = { id: uid(), title: "", content: "", createdAt: now(), updatedAt: now() };
    drafts.unshift(d); activeId = d.id; persist(); renderList(); showEditor(); titleInput.focus();
  }
  function saveCurrent() {
    clearTimeout(saveTimer);
    const d = activeDraft();
    if (!d) return;
    if (d.title === titleInput.value && d.content === contentInput.value) {
      $("saveLabel").textContent = "Salvato in questo browser";
      return;
    }
    d.title = titleInput.value;
    d.content = contentInput.value;
    d.updatedAt = now();
    persist();
    renderList();
    updateCounts();
  }
  function scheduleSave() {
    if (!activeDraft()) {
      // Never let typed text exist without a draft to hold it.
      const d = { id: uid(), title: "", content: "", createdAt: now(), updatedAt: now() };
      drafts.unshift(d); activeId = d.id; showEditorChrome();
    }
    $("saveLabel").textContent = "Salvataggio…";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveCurrent, 180);
    updateCounts();
  }
  function renderList() {
    const list = $("draftList");
    list.replaceChildren();
    const sorted = [...drafts].sort((a,b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
    if (!sorted.length) {
      const empty = document.createElement("div");
      empty.className = "empty-list";
      empty.textContent = "I tuoi scritti appariranno qui.";
      list.appendChild(empty);
      return;
    }
    sorted.forEach(d => {
      const b = document.createElement("button");
      b.className = "draft-item" + (d.id === activeId ? " active" : "");
      b.type = "button";
      const t = document.createElement("span"); t.className = "draft-title"; t.textContent = d.title.trim() || "Senza titolo";
      const m = document.createElement("span"); m.className = "draft-meta"; m.textContent = formatDate(d.updatedAt || d.createdAt);
      b.append(t, m);
      b.addEventListener("click", () => {
        if (d.id === activeId) return;
        saveCurrent(); activeId = d.id; showEditor(); renderList();
      });
      list.appendChild(b);
    });
  }
  function showEditorChrome() {
    const empty = !activeDraft();
    $("emptyState").hidden = !empty;
    $("writingArea").hidden = empty;
    $("deleteBtn").style.visibility = empty ? "hidden" : "visible";
    $("exportBtn").style.visibility = empty ? "hidden" : "visible";
  }
  function showEditor() {
    const d = activeDraft();
    showEditorChrome();
    if (d) {
      titleInput.value = d.title || "";
      contentInput.value = d.content || "";
      fitTitle();
      $("dateLine").textContent = "Iniziato il " + formatDate(d.createdAt || d.updatedAt);
      $("saveLabel").textContent = "Salvato in questo browser";
      updateCounts();
    } else {
      titleInput.value = ""; contentInput.value = "";
      $("wordCount").textContent = "0 parole"; $("charCount").textContent = "0 caratteri";
    }
  }
  function fitTitle() {
    titleInput.style.height = "auto"; titleInput.style.height = titleInput.scrollHeight + "px";
  }
  function updateCounts() {
    const text = contentInput.value;
    const words = wordTotal(text);
    $("wordCount").textContent = words + (words === 1 ? " parola" : " parole");
    $("charCount").textContent = text.length + (text.length === 1 ? " carattere" : " caratteri");
  }
  function showNotice(message) {
    const el = $("notice"); el.textContent = message; el.classList.add("show");
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => el.classList.remove("show"), 2200);
  }
  function applyFocusMode() {
    $("sidebar").hidden = focusMode;
    $("workspace").style.gridTemplateColumns = focusMode ? "minmax(0, 1fr)" : "";
    $("focusToggle").textContent = focusMode ? "Show drafts" : "Focus mode";
    $("focusToggle").title = focusMode ? "Mostra la lista degli scritti" : "Nascondi la lista degli scritti";
  }
  function exportMarkdown() {
    saveCurrent();
    const d = activeDraft(); if (!d) return;
    const title = d.title.replace(/\s+/g, " ").trim();
    const markdown = (title ? "# " + title + "\n\n" : "") + d.content;
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeTitle = (d.title.trim() || "senza-titolo").replace(/[\\/:*?"<>|]+/g, "-").slice(0, 80);
    a.href = url; a.download = safeTitle + ".md"; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    showNotice("File Markdown esportato");
  }
  function deleteCurrent() {
    const d = activeDraft(); if (!d) return;
    if (!confirm('Eliminare "' + (d.title.trim() || "Senza titolo") + '"? Questa azione non si può annullare.')) return;
    drafts = drafts.filter(item => item.id !== activeId);
    activeId = drafts.length ? [...drafts].sort((a,b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""))[0].id : null;
    persist(); renderList(); showEditor();
    showNotice("Scritto eliminato");
  }

  $("newDraft").addEventListener("click", makeDraft);
  $("firstDraft").addEventListener("click", makeDraft);
  titleInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); contentInput.focus(); }
  });
  titleInput.addEventListener("input", () => {
    if (/[\r\n]/.test(titleInput.value)) titleInput.value = titleInput.value.replace(/\s*[\r\n]+\s*/g, " ");
    fitTitle();
    scheduleSave();
  });
  contentInput.addEventListener("input", scheduleSave);
  $("theme").addEventListener("change", () => {
    document.body.dataset.theme = $("theme").value; persistSettings();
  });
  $("focusToggle").addEventListener("click", () => { focusMode = !focusMode; applyFocusMode(); persistSettings(); });
  $("exportBtn").addEventListener("click", exportMarkdown);
  $("deleteBtn").addEventListener("click", deleteCurrent);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "s") {
      e.preventDefault(); saveCurrent(); showNotice("Salvato");
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "e") {
      e.preventDefault(); exportMarkdown();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
      e.preventDefault(); makeDraft();
    }
    if (e.key === "Escape" && focusMode) {
      focusMode = false; applyFocusMode(); persistSettings();
    }
  });

  readStorage();
  renderList();
  if (drafts.length) {
    activeId = [...drafts].sort((a,b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""))[0].id;
  }
  showEditor();
})();
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404, "Not found")
            return
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Keep the terminal quiet; the app is intentionally minimal.
        pass

def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Quiet is running at {url}")
    print("Press Ctrl+C to stop the server.")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nStopping Quiet.")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
