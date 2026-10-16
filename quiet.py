#!/usr/bin/env python3
"""A tiny, dependency-free local writing app.

Run:
    python3 quiet.py
Then open http://127.0.0.1:8765 in your browser.
Drafts are stored in quiet.db (SQLite), next to this script. Drafts left in
the browser's localStorage by older versions are imported on first load.
"""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json
import re
import secrets
import sqlite3
import sys
import webbrowser

HOST = "127.0.0.1"
PORT = 8765
DB_PATH = Path(__file__).resolve().with_name("quiet.db")
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
TOKEN = secrets.token_urlsafe(32)

PAGE = r"""<!doctype html>
<html lang="it" data-theme="paper">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Quiet — spazio di scrittura</title>
<style>
  /* Carta calda is the default theme; the others override these tokens. */
  :root {
    color-scheme: light;
    --bg: #e9dfca; --panel: #f6eedc; --text: #40352a; --muted: #6b5d4a;
    --line: #d8c9ae; --accent: #87523e; --accent-soft: #ead9c8; --editor: #f6eedc;
    --shadow: 0 18px 55px rgba(83, 58, 31, .08);
    --font: Georgia, "Times New Roman", serif;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body {
    margin: 0; min-height: 100vh; background: var(--bg); color: var(--text);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    transition: background .25s ease, color .25s ease;
  }
  :root[data-theme="midnight"] {
    color-scheme: dark;
    --bg: #171b20; --panel: #20262d; --text: #e5e3dc; --muted: #929ba4;
    --line: #353d46; --accent: #b7c9dc; --accent-soft: #2c3947; --editor: #20262d;
    --shadow: 0 18px 55px rgba(0, 0, 0, .18);
  }
  :root[data-theme="studio"] {
    --bg: #e9e9e7; --panel: #f8f8f6; --text: #202322; --muted: #5e635f;
    --line: #d6d9d6; --accent: #476f68; --accent-soft: #dce9e5; --editor: #f8f8f6;
    --shadow: 0 18px 55px rgba(30, 40, 36, .06);
  }
  button, input, textarea, select { font: inherit; }
  button { cursor: pointer; }
  /* Keyboard focus ring. The writing fields skip it: the caret shows where you are. */
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .notice :focus-visible { outline-color: var(--bg); }
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
    padding: 9px 13px; font-size: 12px;
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
  .trash-toggle { align-self: flex-start; margin-top: 12px; background: none; border: 0; padding: 6px 2px; color: var(--muted); font-size: 11px; letter-spacing: .04em; }
  .trash-toggle:hover { color: var(--text); }
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
  .notice.show.actionable { pointer-events: auto; }
  .notice-action { margin-left: 14px; background: none; border: 0; padding: 0; color: inherit; font-size: inherit; font-weight: 700; text-decoration: underline; text-underline-offset: 3px; }
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
<body>
<div class="shell">
  <header>
    <div class="brand">
      <div class="mark">q</div>
      <div><div class="brand-name">Quiet</div><div class="brand-note">un piccolo posto per pensare su carta</div></div>
    </div>
    <div class="header-actions">
      <span class="quiet-label">Atmosfera</span>
      <select id="theme" aria-label="Tema">
        <option value="paper">Carta calda</option>
        <option value="studio">Studio chiaro</option>
        <option value="midnight">Mezzanotte</option>
      </select>
      <button class="small-btn" id="focusToggle" title="Nascondi la lista degli scritti">Modalità focus</button>
    </div>
  </header>

  <main class="workspace" id="workspace">
    <aside id="sidebar">
      <div class="aside-top"><span class="section-label" id="listLabel">I tuoi scritti</span><button class="new-btn" id="newDraft" aria-label="Nuovo scritto" title="Nuovo scritto (Alt+N)">+</button><button class="text-action danger" id="emptyTrash" title="Elimina definitivamente tutti gli scritti nel cestino" hidden>Svuota</button></div>
      <div class="draft-list" id="draftList"></div>
      <button class="trash-toggle" id="trashToggle" type="button">Cestino</button>
      <div class="aside-bottom">Un posto per scrivere.<br>Niente feed, niente distrazioni.</div>
    </aside>

    <section class="editor-card" aria-label="Editor di scrittura">
      <div class="editor-toolbar">
        <div class="save-state"><span class="save-dot"></span><span id="saveLabel">Caricamento…</span></div>
        <div class="toolbar-right">
          <button class="text-action" id="exportBtn" title="Esporta il testo in un file Markdown (Ctrl+Shift+E)">Esporta .md</button>
          <button class="text-action" id="restoreBtn" hidden>Ripristina</button>
          <button class="text-action danger" id="purgeBtn" hidden>Elimina definitivamente</button>
          <button class="text-action danger" id="deleteBtn">Sposta nel cestino</button>
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
  const LEGACY_KEY = "quiet-writing-drafts-v1";  // drafts lived here before the SQLite backend
  const SETTINGS_KEY = "quiet-writing-settings-v1";
  const OUTBOX_PREFIX = "quiet-unsaved-v1";      // edits not yet confirmed by the server, one key per window
  const TOKEN = "__QUIET_TOKEN__";
  const $ = (id) => document.getElementById(id);
  const titleInput = $("title"), contentInput = $("content");
  let drafts = [], activeId = null, saveTimer = null, noticeTimer = null, focusMode = false, view = "drafts";
  let outbox = {}, flushing = false, flushAgain = false, retryTimer = null, saveError = null, lastSavedAt = null, firstPendingAt = 0;

  const uid = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);
  const now = () => new Date().toISOString();
  const formatDate = (iso) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "Bozza";
    return new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric" }).format(d);
  };
  const activeDraft = () => drafts.find(d => d.id === activeId);
  const live = () => drafts.filter(d => !d.deletedAt);
  const trashed = () => drafts.filter(d => d.deletedAt);
  const byUpdated = (a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || "");
  const byDeleted = (a, b) => (b.deletedAt || "").localeCompare(a.deletedAt || "");
  const latestLiveId = () => (live().sort(byUpdated)[0] || {}).id || null;
  const titleOf = (d) => d.title.trim() || "Senza titolo";
  // rev: last server revision this window saw (0 = not on the server yet).
  // edited: title/content changed locally since the server last confirmed them.
  const newDraft = () => { const t = now(); return { id: uid(), title: "", content: "", createdAt: t, updatedAt: t, changedAt: t, deletedAt: null, rev: 0, edited: false }; };
  const fromServer = (d) => ({ ...d, edited: false });
  const OUTBOX_KEY = OUTBOX_PREFIX + ":" + uid();
  const wordTotal = (text) => (text.trim().match(/\S+/g) || []).length;

  function readSettings() {
    try {
      const settings = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
      if (settings.theme && ["paper", "studio", "midnight"].includes(settings.theme)) $("theme").value = settings.theme;
      document.documentElement.dataset.theme = $("theme").value;
      focusMode = !!settings.focusMode;
    } catch (e) { document.documentElement.dataset.theme = "paper"; }
    applyFocusMode();
  }

  // --- Server storage -------------------------------------------------------
  // Every change goes to the outbox (mirrored in localStorage) first and leaves
  // it only once the server has confirmed it, so a stopped or restarted server
  // never costs typed text: the outbox is replayed on the next flush or load.
  function api(method, path, body, keepalive) {
    return fetch(path, {
      method, keepalive: !!keepalive,
      headers: { "Content-Type": "application/json", "X-Quiet-Token": TOKEN },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(async r => {
      if (!r.ok) {
        const err = new Error("HTTP " + r.status); err.status = r.status;
        try { err.body = await r.json(); } catch (e) { /* no JSON body */ }
        throw err;
      }
      return r.status === 204 ? null : r.json();
    });
  }
  // Each window holds a lock named after its outbox for as long as it lives,
  // so another window can tell a live outbox from one a closed window left.
  function holdOutboxLock() {
    if (!navigator.locks) return Promise.resolve();
    return new Promise(granted => navigator.locks.request(OUTBOX_KEY, () => { granted(); return new Promise(() => {}); }));
  }
  async function adoptOrphanOutboxes() {
    const keys = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k === OUTBOX_PREFIX || (k.startsWith(OUTBOX_PREFIX + ":") && k !== OUTBOX_KEY)) keys.push(k);
      }
    } catch (e) { return; }
    const stamp = (e) => e.op === "delete" ? "\uffff" : (e.draft.changedAt || e.draft.updatedAt || "");
    const adopt = (key) => {
      let entries;
      try { entries = JSON.parse(localStorage.getItem(key) || "{}"); localStorage.removeItem(key); } catch (e) { return; }
      for (const [id, entry] of Object.entries(entries || {})) {
        if (!outbox[id] || stamp(entry) > stamp(outbox[id])) outbox[id] = entry;
      }
    };
    for (const key of keys) {
      // The unsuffixed key predates per-window outboxes and has no owner.
      if (key === OUTBOX_PREFIX || !navigator.locks) adopt(key);
      else await navigator.locks.request(key, { ifAvailable: true }, lock => { if (lock) adopt(key); });
    }
    writeOutbox();
  }
  function writeOutbox() {
    try {
      if (Object.keys(outbox).length) localStorage.setItem(OUTBOX_KEY, JSON.stringify(outbox));
      else localStorage.removeItem(OUTBOX_KEY);
    } catch (e) { /* the in-memory outbox still holds the change */ }
  }
  function send(id, entry, keepalive) {
    const path = "/api/drafts/" + encodeURIComponent(id);
    if (entry.op === "delete") return api("DELETE", path, undefined, keepalive);
    // Outbox entries saved before the trash existed lack changedAt/deletedAt.
    const d = entry.draft;
    return api("PUT", path, { ...d, changedAt: d.changedAt || d.updatedAt, deletedAt: d.deletedAt || null, baseRev: d.rev || 0 }, keepalive);
  }
  function queuePut(d) { outbox[d.id] = { op: "put", draft: { ...d } }; writeOutbox(); flush(); }
  function queueDelete(id) { outbox[id] = { op: "delete" }; writeOutbox(); flush(); }
  async function flush() {
    if (flushing) { flushAgain = true; return; }
    flushing = true; clearTimeout(retryTimer);
    let wrote = false;
    try {
      for (const [id, entry] of Object.entries(outbox)) {
        wrote = true;
        let res;
        try { res = await send(id, entry, false); }
        catch (e) {
          if (e.status !== 409 || !e.body || !e.body.draft) throw e;
          const latest = outbox[id] && outbox[id].op === "put" ? outbox[id].draft : entry.draft;
          if (outbox[id] === entry || outbox[id] && outbox[id].op === "put") delete outbox[id];
          resolveConflict(latest, fromServer(e.body.draft));
          continue;
        }
        if (outbox[id] === entry) delete outbox[id];  // keep it if a newer edit replaced it meanwhile
        if (entry.op === "put") acknowledge(id, res.rev);
      }
      writeOutbox();
      if (wrote && channel) channel.postMessage("changed");
      if (saveError) showNotice("Salvataggio ripristinato");
      saveError = null; lastSavedAt = new Date();
    } catch (e) {
      writeOutbox();
      if (!saveError) {
        showNotice(e.status === 403
          ? "Il server è stato riavviato: ricarica la pagina. Le modifiche sono conservate."
          : "Server non raggiungibile. Le modifiche restano in questo browser finché non torna.");
      }
      saveError = e;
      if (e.status !== 403) retryTimer = setTimeout(flush, 5000);
    } finally {
      flushing = false;
      refreshSaveLabel();
      if (flushAgain) { flushAgain = false; flush(); }
    }
  }
  function acknowledge(id, rev) {
    const d = drafts.find(x => x.id === id);
    if (d) { d.rev = rev; if (!outbox[id]) d.edited = false; }
    // A newer snapshot queued while this write was in flight builds on it.
    if (outbox[id] && outbox[id].op === "put") outbox[id].draft.rev = rev;
  }
  // Another window changed this draft since this one last saw it. Nothing is
  // overwritten: the server version stays, and local edits become a copy.
  function resolveConflict(local, server) {
    const wasActive = activeId === server.id;
    let mine = local;
    if (wasActive) {
      // The editor may hold keystrokes newer than the queued snapshot.
      clearTimeout(saveTimer); saveTimer = null; firstPendingAt = 0;
      const changed = titleInput.value !== local.title || contentInput.value !== local.content;
      mine = { ...local, title: titleInput.value, content: contentInput.value, edited: local.edited || changed };
    }
    const i = drafts.findIndex(d => d.id === server.id);
    if (i >= 0) drafts[i] = server; else drafts.push(server);
    // Snapshots from before revisions existed carry no 'edited' flag: assume edited.
    const edited = mine.edited !== false;
    if (edited && (mine.title !== server.title || mine.content !== server.content)) {
      const copy = { ...newDraft(), title: (mine.title.trim() || "Senza titolo") + " (versione in conflitto)", content: mine.content, edited: true };
      drafts.unshift(copy); queuePut(copy);
      if (wasActive) { activeId = copy.id; view = "drafts"; }
      showNotice("«" + titleOf(server) + "» è stato modificato in un'altra finestra. Le tue modifiche sono in una copia.");
    } else if ((mine.deletedAt || null) !== (server.deletedAt || null)) {
      // Only the trash state differed: reapply it on top of the newer version.
      server.deletedAt = mine.deletedAt || null; server.changedAt = now(); queuePut(server);
    }
    renderList();
    if (wasActive) showEditor();
  }
  function flushOnExit() {
    saveCurrent();
    // Regular fetches may be cancelled on unload; keepalive ones are not.
    for (const [id, entry] of Object.entries(outbox)) send(id, entry, true).catch(() => {});
  }
  function refreshSaveLabel() {
    const label = $("saveLabel");
    if (saveError) { label.textContent = "Non salvato"; label.title = "Le modifiche sono conservate in questo browser"; }
    else if (Object.keys(outbox).length || saveTimer) { label.textContent = "Salvataggio…"; label.title = ""; }
    else {
      label.textContent = "Salvato";
      label.title = lastSavedAt ? "Salvato in quiet.db alle " + lastSavedAt.toLocaleTimeString("it-IT") : "Salvato in quiet.db";
    }
  }
  // --- Sync with other windows ----------------------------------------------
  // Windows in this browser ping each other after every save; windows in
  // other browsers catch up when focused and every 15s while visible.
  // Drafts with edits still pending here are left alone: if another window
  // changed them too, the revision check settles it when they are sent.
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("quiet-drafts") : null;
  let refreshTimer = null, loaded = false;
  function scheduleRefresh(delay) { clearTimeout(refreshTimer); refreshTimer = setTimeout(refreshFromServer, delay); }
  async function refreshFromServer() {
    if (!loaded) return;
    let server;
    try { server = (await api("GET", "/api/drafts")).map(fromServer); } catch (e) { return; }
    const busy = (id) => !!outbox[id] || (id === activeId && !!saveTimer);
    const ids = new Set(server.map(d => d.id));
    let activeChanged = false;
    for (const d of server) {
      if (busy(d.id)) continue;
      const i = drafts.findIndex(x => x.id === d.id);
      if (i < 0) drafts.push(d);
      else if ((d.rev || 0) > (drafts[i].rev || 0)) { drafts[i] = d; if (d.id === activeId) activeChanged = true; }
    }
    // Drafts deleted for good in another window, unless edits for them are pending here.
    drafts = drafts.filter(d => ids.has(d.id) || busy(d.id));
    if (!activeDraft()) { activeId = latestLiveId(); activeChanged = true; }
    renderList();
    if (activeChanged) showEditor();
  }
  async function migrateLegacy() {
    let raw, legacy;
    try { raw = localStorage.getItem(LEGACY_KEY); } catch (e) { return; }
    if (!raw) return;
    try { legacy = JSON.parse(raw); } catch (e) { return; }
    if (!Array.isArray(legacy)) return;
    const rows = legacy.filter(d => d && typeof d.id === "string").map(d => ({
      id: d.id, title: String(d.title || ""), content: String(d.content || ""),
      createdAt: d.createdAt || d.updatedAt || now(), updatedAt: d.updatedAt || d.createdAt || now(),
    })).map(d => ({ ...d, changedAt: d.updatedAt, deletedAt: null }));
    try {
      const res = await api("POST", "/api/import", rows);
      localStorage.setItem(LEGACY_KEY + "-migrated", raw);  // keep a copy, just in case
      localStorage.removeItem(LEGACY_KEY);
      if (res.imported) showNotice(res.imported + (res.imported === 1 ? " scritto importato" : " scritti importati") + " nel database");
    } catch (e) { /* left in place; retried on next load */ }
  }
  async function load() {
    readSettings();
    await holdOutboxLock();
    await adoptOrphanOutboxes();
    await migrateLegacy();
    try { drafts = (await api("GET", "/api/drafts")).map(fromServer); }
    catch (e) { drafts = []; saveError = e; showNotice("Impossibile leggere gli scritti dal server. Ricarica la pagina."); }
    // Overlay edits the server hasn't confirmed yet, so nothing typed is hidden.
    for (const [id, entry] of Object.entries(outbox)) {
      const i = drafts.findIndex(d => d.id === id);
      if (entry.op === "delete") { if (i >= 0) drafts.splice(i, 1); }
      else if (i < 0) drafts.push(entry.draft);
      else if ((entry.draft.changedAt || entry.draft.updatedAt) >= (drafts[i].changedAt || drafts[i].updatedAt)) drafts[i] = entry.draft;
    }
    activeId = latestLiveId();
    renderList();
    showEditor();
    if (Object.keys(outbox).length && !saveError) flush();
    loaded = true;
  }
  function persistSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify({ theme: $("theme").value, focusMode }));
    } catch (e) { /* settings are a convenience; the change still applies to this session */ }
  }
  function makeDraft() {
    saveCurrent();
    view = "drafts";
    // Reuse an untouched draft instead of piling up empty "Senza titolo" entries.
    const blank = live().find(d => !d.title.trim() && !d.content.trim());
    if (blank) {
      activeId = blank.id; renderList(); showEditor(); titleInput.focus();
      return;
    }
    const d = newDraft();
    drafts.unshift(d); activeId = d.id; queuePut(d); renderList(); showEditor(); titleInput.focus();
  }
  function saveCurrent() {
    clearTimeout(saveTimer); saveTimer = null; firstPendingAt = 0;
    const d = activeDraft();
    if (!d) return;
    if (d.title === titleInput.value && d.content === contentInput.value) {
      refreshSaveLabel();
      return;
    }
    d.title = titleInput.value;
    d.content = contentInput.value;
    d.updatedAt = d.changedAt = now();
    d.edited = true;
    queuePut(d);
    renderList();
    updateCounts();
  }
  // Autosave: 180ms after typing pauses, and at least every 2s during
  // continuous typing so a long uninterrupted burst is never all at risk.
  function scheduleSave() {
    if (activeDraft() && activeDraft().deletedAt) return;  // trashed drafts are read-only
    if (!activeDraft()) {
      // Never let typed text exist without a draft to hold it.
      const d = newDraft();
      drafts.unshift(d); activeId = d.id; showEditorChrome();
    }
    clearTimeout(saveTimer);
    if (!firstPendingAt) firstPendingAt = Date.now();
    saveTimer = setTimeout(saveCurrent, Date.now() - firstPendingAt >= 2000 ? 0 : 180);
    refreshSaveLabel();
    updateCounts();
  }
  function renderList() {
    const list = $("draftList");
    list.replaceChildren();
    const inTrash = view === "trash";
    const items = inTrash ? trashed().sort(byDeleted) : live().sort(byUpdated);
    const trashCount = trashed().length;
    $("listLabel").textContent = inTrash ? "Cestino" : "I tuoi scritti";
    $("newDraft").hidden = inTrash;
    $("emptyTrash").hidden = !inTrash || !items.length;
    $("trashToggle").textContent = inTrash ? "← Torna agli scritti" : "Cestino" + (trashCount ? " · " + trashCount : "");
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-list";
      empty.textContent = inTrash ? "Il cestino è vuoto." : "I tuoi scritti appariranno qui.";
      list.appendChild(empty);
      return;
    }
    items.forEach(d => {
      const b = document.createElement("button");
      b.className = "draft-item" + (d.id === activeId ? " active" : "");
      b.type = "button";
      if (d.id === activeId) b.setAttribute("aria-current", "true");
      const t = document.createElement("span"); t.className = "draft-title"; t.textContent = titleOf(d);
      const m = document.createElement("span"); m.className = "draft-meta";
      m.textContent = inTrash ? "Eliminato il " + formatDate(d.deletedAt) : formatDate(d.updatedAt || d.createdAt);
      b.append(t, m);
      b.addEventListener("click", () => {
        if (d.id === activeId) return;
        saveCurrent(); activeId = d.id; showEditor(); renderList();
      });
      list.appendChild(b);
    });
  }
  function showEditorChrome() {
    const d = activeDraft(), empty = !d, inTrash = !!(d && d.deletedAt);
    $("emptyState").hidden = !empty;
    $("writingArea").hidden = empty;
    $("exportBtn").style.visibility = empty ? "hidden" : "visible";
    $("deleteBtn").hidden = empty || inTrash;
    $("restoreBtn").hidden = $("purgeBtn").hidden = !inTrash;
    titleInput.readOnly = contentInput.readOnly = inTrash;
  }
  function showEditor() {
    const d = activeDraft();
    showEditorChrome();
    if (d) {
      setValue(titleInput, d.title || "");
      setValue(contentInput, d.content || "");
      fitTitle();
      $("dateLine").textContent = d.deletedAt
        ? "Nel cestino dal " + formatDate(d.deletedAt) + " · sola lettura"
        : "Iniziato il " + formatDate(d.createdAt || d.updatedAt);
      refreshSaveLabel();
      updateCounts();
    } else {
      titleInput.value = ""; contentInput.value = "";
      $("wordCount").textContent = "0 parole"; $("charCount").textContent = "0 caratteri";
    }
  }
  // Replace a field's text without moving the caret when nothing changed,
  // and keeping it roughly in place when something did.
  function setValue(el, value) {
    if (el.value === value) return;
    const start = el.selectionStart, end = el.selectionEnd, focused = document.activeElement === el;
    el.value = value;
    if (focused) el.setSelectionRange(Math.min(start, value.length), Math.min(end, value.length));
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
  function showNotice(message, action) {
    const el = $("notice");
    el.replaceChildren(document.createTextNode(message));
    if (action) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "notice-action"; b.textContent = action.label;
      b.addEventListener("click", () => { el.classList.remove("show"); action.run(); });
      el.append(b);
    }
    el.classList.toggle("actionable", !!action);
    el.classList.add("show");
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => el.classList.remove("show"), action ? 6000 : 2200);
  }
  function applyFocusMode() {
    $("sidebar").hidden = focusMode;
    $("workspace").style.gridTemplateColumns = focusMode ? "minmax(0, 1fr)" : "";
    $("focusToggle").textContent = focusMode ? "Mostra scritti" : "Modalità focus";
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
  // Trash: deleting only sets deletedAt. Trashed drafts stay in the database,
  // read-only, until restored or deleted for good from the trash view.
  function trashCurrent() {
    const d = activeDraft(); if (!d || d.deletedAt) return;
    saveCurrent();
    d.deletedAt = d.changedAt = now();
    queuePut(d);
    activeId = latestLiveId();
    renderList(); showEditor();
    showNotice("Spostato nel cestino", { label: "Annulla", run: () => restoreDraft(d.id) });
  }
  function restoreDraft(id) {
    const d = drafts.find(x => x.id === id); if (!d || !d.deletedAt) return;
    saveCurrent();
    d.deletedAt = null; d.changedAt = now();
    queuePut(d);
    view = "drafts"; activeId = d.id;
    renderList(); showEditor();
    showNotice("Ripristinato");
  }
  function purgeCurrent() {
    const d = activeDraft(); if (!d || !d.deletedAt) return;
    if (!confirm('Eliminare definitivamente "' + titleOf(d) + '"? Questa azione non si può annullare.')) return;
    drafts = drafts.filter(x => x.id !== d.id);
    queueDelete(d.id);
    activeId = (view === "trash" && trashed().sort(byDeleted)[0] || {}).id || latestLiveId();
    renderList(); showEditor();
    showNotice("Eliminato definitivamente");
  }
  function emptyTrash() {
    const items = trashed(); if (!items.length) return;
    const what = items.length === 1 ? "lo scritto" : "i " + items.length + " scritti";
    if (!confirm("Eliminare definitivamente " + what + " nel cestino? Questa azione non si può annullare.")) return;
    drafts = live();
    items.forEach(d => queueDelete(d.id));
    if (!activeDraft()) activeId = latestLiveId();
    renderList(); showEditor();
    showNotice("Cestino svuotato");
  }
  function setView(next) {
    saveCurrent();
    view = next;
    if (next === "trash") {
      const first = trashed().sort(byDeleted)[0];
      if (first) activeId = first.id;
    } else if (activeDraft() && activeDraft().deletedAt) {
      activeId = latestLiveId();
    }
    renderList(); showEditor();
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
    document.documentElement.dataset.theme = $("theme").value; persistSettings();
  });
  $("focusToggle").addEventListener("click", () => { focusMode = !focusMode; applyFocusMode(); persistSettings(); });
  $("exportBtn").addEventListener("click", exportMarkdown);
  $("deleteBtn").addEventListener("click", trashCurrent);
  $("restoreBtn").addEventListener("click", () => restoreDraft(activeId));
  $("purgeBtn").addEventListener("click", purgeCurrent);
  $("emptyTrash").addEventListener("click", emptyTrash);
  $("trashToggle").addEventListener("click", () => setView(view === "trash" ? "drafts" : "trash"));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "s") {
      e.preventDefault(); saveCurrent(); if (!saveError) showNotice("Salvato");
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "e") {
      e.preventDefault(); exportMarkdown();
    }
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === "KeyN") {
      e.preventDefault(); makeDraft();
    }
    if (e.key === "Escape" && focusMode) {
      focusMode = false; applyFocusMode(); persistSettings();
    } else if (e.key === "Escape" && view === "trash") {
      setView("drafts");
    }
  });

  // Flush the debounced save before the page goes away.
  window.addEventListener("pagehide", flushOnExit);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushOnExit(); else scheduleRefresh(0);
  });
  window.addEventListener("focus", () => scheduleRefresh(0));
  if (channel) channel.onmessage = () => scheduleRefresh(100);
  setInterval(() => { if (document.visibilityState === "visible") refreshFromServer(); }, 15000);

  load();
})();
</script>
</body>
</html>
"""

PAGE_BYTES = PAGE.replace("__QUIET_TOKEN__", TOKEN).encode("utf-8")
DRAFT_PATH = re.compile(r"^/api/drafts/([A-Za-z0-9-]{1,64})$")
MAX_BODY = 20 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,           -- last edit of title/content, shown to the user
    deleted_at TEXT,                    -- set while the draft is in the trash
    changed_at TEXT,                    -- last change of any kind (edit, trash, restore)
    rev        INTEGER NOT NULL DEFAULT 1  -- bumped on every write; detects edits made on a stale copy
)
"""
SELECT_DRAFTS = (
    "SELECT id, title, content, created_at AS createdAt, updated_at AS updatedAt,"
    " deleted_at AS deletedAt, changed_at AS changedAt, rev FROM drafts")

def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(connect()) as conn, conn:
        conn.execute(SCHEMA)
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(drafts)")}
        # Databases from older versions lack these columns.
        added = {"deleted_at": "TEXT", "changed_at": "TEXT", "rev": "INTEGER NOT NULL DEFAULT 1"}
        for column, definition in added.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE drafts ADD COLUMN {column} {definition}")
        conn.execute("UPDATE drafts SET changed_at = updated_at WHERE changed_at IS NULL")

def draft_row(draft_id, data):
    """Validate a draft payload and return it as a row tuple."""
    if not isinstance(data, dict):
        raise ValueError("draft must be an object")
    fields = [data.get(k) for k in ("title", "content", "createdAt", "updatedAt", "changedAt")]
    if not all(isinstance(v, str) for v in fields):
        raise ValueError("title, content, createdAt, updatedAt and changedAt must be strings")
    deleted_at = data.get("deletedAt")
    if deleted_at is not None and not isinstance(deleted_at, str):
        raise ValueError("deletedAt must be a string or null")
    if not DRAFT_PATH.match("/api/drafts/" + draft_id):
        raise ValueError("invalid id")
    title, content, created_at, updated_at, changed_at = fields
    return (draft_id, title, content, created_at, updated_at, deleted_at, changed_at)

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body=b"", content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _allowed(self, api):
        # Host check stops DNS rebinding; the per-launch token stops other
        # pages (or a stale tab from a previous run) from touching the database.
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self._json(403, {"error": "forbidden host"})
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Quiet-Token", "").encode(), TOKEN.encode()):
            self._json(403, {"error": "invalid token"})
            return False
        return True

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(length) or b"null")

    def _handle(self, route):
        path = urlsplit(self.path).path
        if not self._allowed(api=path.startswith("/api/")):
            return
        try:
            route(path)
        except (ValueError, json.JSONDecodeError) as e:
            self._json(400, {"error": str(e)})
        except sqlite3.Error as e:
            print(f"Database error: {e}", file=sys.stderr)
            self._json(500, {"error": "database error"})

    def do_GET(self):
        self._handle(self._get)

    def do_PUT(self):
        self._handle(self._put)

    def do_DELETE(self):
        self._handle(self._delete)

    def do_POST(self):
        self._handle(self._post)

    def _get(self, path):
        if path in ("/", "/index.html"):
            self._send(200, PAGE_BYTES, "text/html; charset=utf-8")
        elif path == "/api/drafts":
            with closing(connect()) as conn:
                rows = conn.execute(SELECT_DRAFTS + " ORDER BY updated_at DESC").fetchall()
            self._json(200, [dict(r) for r in rows])
        else:
            self._json(404, {"error": "not found"})

    def _put(self, path):
        m = DRAFT_PATH.match(path)
        if not m:
            return self._json(404, {"error": "not found"})
        data = self._body()
        row = draft_row(m.group(1), data)
        draft_id, title, content, _, updated_at, deleted_at, changed_at = row
        base_rev = data.get("baseRev")
        if not isinstance(base_rev, int) or isinstance(base_rev, bool) or base_rev < 0:
            raise ValueError("baseRev must be a non-negative integer")
        with closing(connect()) as conn, conn:
            # Optimistic concurrency: a write applies only on top of the revision
            # the client last saw. If another window changed the draft meanwhile,
            # answer 409 with the current version and let the client reconcile.
            cur = conn.execute(
                "UPDATE drafts SET title = ?, content = ?, updated_at = ?, deleted_at = ?,"
                " changed_at = ?, rev = rev + 1 WHERE id = ? AND rev = ?",
                (title, content, updated_at, deleted_at, changed_at, draft_id, base_rev))
            if cur.rowcount == 0:
                current = conn.execute(SELECT_DRAFTS + " WHERE id = ?", (draft_id,)).fetchone()
                if current is not None:
                    return self._json(409, {"draft": dict(current)})
                # A new draft, or one deleted for good in another window while
                # this one was editing it: (re)create it rather than lose the text.
                conn.execute(
                    "INSERT INTO drafts (id, title, content, created_at, updated_at, deleted_at, changed_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)", row)
            rev = conn.execute("SELECT rev FROM drafts WHERE id = ?", (draft_id,)).fetchone()[0]
        self._json(200, {"rev": rev})

    def _delete(self, path):
        m = DRAFT_PATH.match(path)
        if not m:
            return self._json(404, {"error": "not found"})
        with closing(connect()) as conn, conn:
            conn.execute("DELETE FROM drafts WHERE id = ?", (m.group(1),))
        self._send(204)

    def _post(self, path):
        if path != "/api/import":
            return self._json(404, {"error": "not found"})
        data = self._body()
        if not isinstance(data, list):
            raise ValueError("expected a list of drafts")
        rows = [draft_row(str(d.get("id", "")) if isinstance(d, dict) else "", d) for d in data]
        with closing(connect()) as conn, conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT INTO drafts (id, title, content, created_at, updated_at, deleted_at, changed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING", rows)
            imported = conn.total_changes - before
        self._json(200, {"imported": imported})

    def log_message(self, fmt, *args):
        # Keep the terminal quiet; the app is intentionally minimal.
        pass

def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Quiet is running at {url}")
    print(f"Drafts are stored in {DB_PATH}")
    print("Press Ctrl+C to stop the server.")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Quiet.")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
