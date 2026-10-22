// Quiet, a small local writing app.
// Copyright (C) 2026 Giampaolo Guiducci
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU General Public License as published by the Free
// Software Foundation, either version 3 of the License, or (at your option)
// any later version. See the LICENSE file for details.
//
// SPDX-License-Identifier: GPL-3.0-or-later

// Quiet is a tiny local writing app: a single executable that serves a page
// to write on at http://127.0.0.1:8765 and opens it in the browser.
//
// Drafts are stored in quiet.db (SQLite) in the user's data directory. Drafts
// left in the browser's localStorage by older versions are imported on first
// load. The page and EB Garamond, used for the book typography, are embedded
// in the executable.
package main

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"database/sql"
	"embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	_ "modernc.org/sqlite"
)

const (
	host    = "127.0.0.1"
	maxBody = 20 * 1024 * 1024
)

var (
	//go:embed index.html
	page []byte
	//go:embed fonts/*.woff2
	fonts embed.FS

	draftPath = regexp.MustCompile(`^/api/drafts/([A-Za-z0-9-]{1,64})$`)
	fontPath  = regexp.MustCompile(`^/fonts/([A-Za-z0-9-]+\.woff2)$`)
	intLit    = regexp.MustCompile(`^-?[0-9]+$`)
)

const schema = `
CREATE TABLE IF NOT EXISTS drafts (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,           -- last edit of title/content, shown to the user
    deleted_at TEXT,                    -- set while the draft is in the trash
    changed_at TEXT,                    -- last change of any kind (edit, trash, restore)
    rev        INTEGER NOT NULL DEFAULT 1  -- bumped on every write; detects edits made on a stale copy
)`

const selectDrafts = "SELECT id, title, content, created_at, updated_at, deleted_at, changed_at, rev FROM drafts"

const insertDraft = "INSERT INTO drafts (id, title, content, created_at, updated_at, deleted_at, changed_at)" +
	" VALUES (?, ?, ?, ?, ?, ?, ?)"

// dataDir is where quiet.db lives unless -db says otherwise.
func dataDir() (string, error) {
	switch runtime.GOOS {
	case "windows", "darwin":
		// %AppData% on Windows, ~/Library/Application Support on macOS.
		dir, err := os.UserConfigDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(dir, "Quiet"), nil
	default:
		if dir := os.Getenv("XDG_DATA_HOME"); filepath.IsAbs(dir) {
			return filepath.Join(dir, "quiet"), nil
		}
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, ".local", "share", "quiet"), nil
	}
}

func openDB(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", "file:"+filepath.ToSlash(path)+"?_pragma=busy_timeout(10000)")
	if err != nil {
		return nil, err
	}
	// One connection serializes the writes of concurrent requests, so they
	// never trip over SQLite's locks; the busy timeout covers other processes,
	// such as sqlite3 taking a backup.
	db.SetMaxOpenConns(1)
	return db, initDB(db)
}

func initDB(db *sql.DB) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(schema); err != nil {
		return err
	}
	rows, err := tx.Query("SELECT name FROM pragma_table_info('drafts')")
	if err != nil {
		return err
	}
	columns := map[string]bool{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return err
		}
		columns[name] = true
	}
	rows.Close()
	// Databases from older versions lack these columns.
	added := [][2]string{{"deleted_at", "TEXT"}, {"changed_at", "TEXT"}, {"rev", "INTEGER NOT NULL DEFAULT 1"}}
	for _, c := range added {
		if !columns[c[0]] {
			if _, err := tx.Exec("ALTER TABLE drafts ADD COLUMN " + c[0] + " " + c[1]); err != nil {
				return err
			}
		}
	}
	if _, err := tx.Exec("UPDATE drafts SET changed_at = updated_at WHERE changed_at IS NULL"); err != nil {
		return err
	}
	return tx.Commit()
}

type draft struct {
	ID        string  `json:"id"`
	Title     string  `json:"title"`
	Content   string  `json:"content"`
	CreatedAt string  `json:"createdAt"`
	UpdatedAt string  `json:"updatedAt"`
	DeletedAt *string `json:"deletedAt"`
	ChangedAt *string `json:"changedAt"`
	Rev       int64   `json:"rev"`
}

func (d *draft) row() []any {
	return []any{d.ID, d.Title, d.Content, d.CreatedAt, d.UpdatedAt, d.DeletedAt, d.ChangedAt}
}

type scanner interface{ Scan(dest ...any) error }

func scanDraft(s scanner) (*draft, error) {
	var d draft
	err := s.Scan(&d.ID, &d.Title, &d.Content, &d.CreatedAt, &d.UpdatedAt, &d.DeletedAt, &d.ChangedAt, &d.Rev)
	return &d, err
}

// badRequest is an invalid payload, answered with 400.
type badRequest string

func (e badRequest) Error() string { return string(e) }

// jsonString decodes raw if it holds a JSON string, and only then.
func jsonString(raw json.RawMessage) (string, bool) {
	var s string
	if len(raw) == 0 || raw[0] != '"' || json.Unmarshal(raw, &s) != nil {
		return "", false
	}
	return s, true
}

// parseDraft validates a draft payload. The fields are checked by hand, since
// encoding/json would quietly accept null for a string.
func parseDraft(id string, raw json.RawMessage) (*draft, map[string]json.RawMessage, error) {
	var data map[string]json.RawMessage
	if len(raw) == 0 || raw[0] != '{' || json.Unmarshal(raw, &data) != nil {
		return nil, nil, badRequest("draft must be an object")
	}
	d := &draft{ID: id}
	var changedAt string
	for _, f := range []struct {
		key string
		dst *string
	}{{"title", &d.Title}, {"content", &d.Content}, {"createdAt", &d.CreatedAt}, {"updatedAt", &d.UpdatedAt}, {"changedAt", &changedAt}} {
		s, ok := jsonString(data[f.key])
		if !ok {
			return nil, nil, badRequest("title, content, createdAt, updatedAt and changedAt must be strings")
		}
		*f.dst = s
	}
	d.ChangedAt = &changedAt
	if raw, ok := data["deletedAt"]; ok && string(raw) != "null" {
		s, ok := jsonString(raw)
		if !ok {
			return nil, nil, badRequest("deletedAt must be a string or null")
		}
		d.DeletedAt = &s
	}
	if !draftPath.MatchString("/api/drafts/" + id) {
		return nil, nil, badRequest("invalid id")
	}
	return d, data, nil
}

type server struct {
	db           *sql.DB
	token        string
	page         []byte
	allowedHosts map[string]bool
}

func newServer(db *sql.DB, port int) *server {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	token := base64.RawURLEncoding.EncodeToString(b)
	return &server{
		db:    db,
		token: token,
		page:  []byte(strings.Replace(string(page), "__QUIET_TOKEN__", token, 1)),
		allowedHosts: map[string]bool{
			fmt.Sprintf("127.0.0.1:%d", port): true,
			fmt.Sprintf("localhost:%d", port): true,
		},
	}
}

func send(w http.ResponseWriter, status int, body []byte, contentType, cache string) {
	h := w.Header()
	h.Set("Content-Type", contentType)
	h.Set("Content-Length", strconv.Itoa(len(body)))
	h.Set("Cache-Control", cache)
	w.WriteHeader(status)
	w.Write(body)
}

func sendJSON(w http.ResponseWriter, status int, payload any) {
	var buf strings.Builder
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(payload); err != nil {
		panic(err)
	}
	send(w, status, []byte(strings.TrimSuffix(buf.String(), "\n")), "application/json", "no-store")
}

func sendError(w http.ResponseWriter, status int, msg string) {
	sendJSON(w, status, map[string]string{"error": msg})
}

func (s *server) allowed(w http.ResponseWriter, r *http.Request, api bool) bool {
	// Host check stops DNS rebinding; the per-launch token stops other
	// pages (or a stale tab from a previous run) from touching the database.
	if !s.allowedHosts[r.Host] {
		sendError(w, http.StatusForbidden, "forbidden host")
		return false
	}
	if api && subtle.ConstantTimeCompare([]byte(r.Header.Get("X-Quiet-Token")), []byte(s.token)) != 1 {
		sendError(w, http.StatusForbidden, "invalid token")
		return false
	}
	return true
}

func body(r *http.Request) (json.RawMessage, error) {
	data, err := io.ReadAll(io.LimitReader(r.Body, maxBody+1))
	if err != nil {
		return nil, badRequest(err.Error())
	}
	if len(data) > maxBody {
		return nil, badRequest("payload too large")
	}
	if len(strings.TrimSpace(string(data))) == 0 {
		return json.RawMessage("null"), nil
	}
	if !json.Valid(data) {
		return nil, badRequest("invalid JSON")
	}
	return data, nil
}

func (s *server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := r.URL.EscapedPath()
	if !s.allowed(w, r, strings.HasPrefix(path, "/api/")) {
		return
	}
	var err error
	switch r.Method {
	case http.MethodGet:
		err = s.get(w, path)
	case http.MethodPut:
		err = s.put(w, r, path)
	case http.MethodDelete:
		err = s.delete(w, path)
	case http.MethodPost:
		err = s.post(w, r, path)
	default:
		sendError(w, http.StatusNotImplemented, "unsupported method")
	}
	var bad badRequest
	if errors.As(err, &bad) {
		sendError(w, http.StatusBadRequest, bad.Error())
	} else if err != nil {
		fmt.Fprintf(os.Stderr, "Database error: %v\n", err)
		sendError(w, http.StatusInternalServerError, "database error")
	}
}

func (s *server) get(w http.ResponseWriter, path string) error {
	if path == "/" || path == "/index.html" {
		send(w, http.StatusOK, s.page, "text/html; charset=utf-8", "no-store")
		return nil
	}
	if m := fontPath.FindStringSubmatch(path); m != nil {
		if font, err := fonts.ReadFile("fonts/" + m[1]); err == nil {
			send(w, http.StatusOK, font, "font/woff2", "public, max-age=86400")
			return nil
		}
	}
	if path != "/api/drafts" {
		sendError(w, http.StatusNotFound, "not found")
		return nil
	}
	rows, err := s.db.Query(selectDrafts + " ORDER BY updated_at DESC")
	if err != nil {
		return err
	}
	defer rows.Close()
	drafts := []*draft{}
	for rows.Next() {
		d, err := scanDraft(rows)
		if err != nil {
			return err
		}
		drafts = append(drafts, d)
	}
	if err := rows.Err(); err != nil {
		return err
	}
	sendJSON(w, http.StatusOK, drafts)
	return nil
}

func (s *server) put(w http.ResponseWriter, r *http.Request, path string) error {
	m := draftPath.FindStringSubmatch(path)
	if m == nil {
		sendError(w, http.StatusNotFound, "not found")
		return nil
	}
	raw, err := body(r)
	if err != nil {
		return err
	}
	d, data, err := parseDraft(m[1], raw)
	if err != nil {
		return err
	}
	baseRev, err := strconv.ParseInt(string(data["baseRev"]), 10, 64)
	if !intLit.Match(data["baseRev"]) || err != nil || baseRev < 0 {
		return badRequest("baseRev must be a non-negative integer")
	}
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	// Optimistic concurrency: a write applies only on top of the revision
	// the client last saw. If another window changed the draft meanwhile,
	// answer 409 with the current version and let the client reconcile.
	res, err := tx.Exec(
		"UPDATE drafts SET title = ?, content = ?, updated_at = ?, deleted_at = ?,"+
			" changed_at = ?, rev = rev + 1 WHERE id = ? AND rev = ?",
		d.Title, d.Content, d.UpdatedAt, d.DeletedAt, d.ChangedAt, d.ID, baseRev)
	if err != nil {
		return err
	}
	if n, err := res.RowsAffected(); err != nil {
		return err
	} else if n == 0 {
		current, err := scanDraft(tx.QueryRow(selectDrafts+" WHERE id = ?", d.ID))
		if err == nil {
			sendJSON(w, http.StatusConflict, map[string]*draft{"draft": current})
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		// A new draft, or one deleted for good in another window while
		// this one was editing it: (re)create it rather than lose the text.
		if _, err := tx.Exec(insertDraft, d.row()...); err != nil {
			return err
		}
	}
	var rev int64
	if err := tx.QueryRow("SELECT rev FROM drafts WHERE id = ?", d.ID).Scan(&rev); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	sendJSON(w, http.StatusOK, map[string]int64{"rev": rev})
	return nil
}

func (s *server) delete(w http.ResponseWriter, path string) error {
	m := draftPath.FindStringSubmatch(path)
	if m == nil {
		sendError(w, http.StatusNotFound, "not found")
		return nil
	}
	if _, err := s.db.Exec("DELETE FROM drafts WHERE id = ?", m[1]); err != nil {
		return err
	}
	send(w, http.StatusNoContent, nil, "application/json", "no-store")
	return nil
}

func (s *server) post(w http.ResponseWriter, r *http.Request, path string) error {
	if path != "/api/import" {
		sendError(w, http.StatusNotFound, "not found")
		return nil
	}
	raw, err := body(r)
	if err != nil {
		return err
	}
	var items []json.RawMessage
	if len(raw) == 0 || raw[0] != '[' || json.Unmarshal(raw, &items) != nil {
		return badRequest("expected a list of drafts")
	}
	drafts := make([]*draft, len(items))
	for i, item := range items {
		var obj map[string]json.RawMessage
		json.Unmarshal(item, &obj)
		id, _ := jsonString(obj["id"])
		if drafts[i], _, err = parseDraft(id, item); err != nil {
			return err
		}
	}
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var imported int64
	for _, d := range drafts {
		res, err := tx.Exec(insertDraft+" ON CONFLICT(id) DO NOTHING", d.row()...)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		imported += n
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	sendJSON(w, http.StatusOK, map[string]int64{"imported": imported})
	return nil
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	// Opening the browser is a convenience: the address is printed anyway.
	if cmd.Start() == nil {
		go cmd.Wait()
	}
}

func main() {
	port := flag.Int("port", 8765, "port to listen on")
	dbPath := flag.String("db", "", "database file (default: quiet.db in the user's data directory)")
	noBrowser := flag.Bool("no-browser", false, "do not open the browser")
	flag.Parse()

	if err := run(*port, *dbPath, !*noBrowser); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func run(port int, dbPath string, browser bool) error {
	if dbPath == "" {
		dir, err := dataDir()
		if err != nil {
			return err
		}
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return err
		}
		dbPath = filepath.Join(dir, "quiet.db")
	}
	db, err := openDB(dbPath)
	if err != nil {
		return fmt.Errorf("opening %s: %w", dbPath, err)
	}
	defer db.Close()

	ln, err := net.Listen("tcp", net.JoinHostPort(host, strconv.Itoa(port)))
	if err != nil {
		return err
	}
	srv := &http.Server{Handler: newServer(db, port)}
	url := fmt.Sprintf("http://%s:%d", host, port)
	fmt.Println("Quiet is running at", url)
	fmt.Println("Drafts are stored in", dbPath)
	fmt.Println("Press Ctrl+C to stop the server.")
	if browser {
		openBrowser(url)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	stopped := make(chan struct{})
	go func() {
		<-ctx.Done()
		fmt.Println("\nStopping Quiet.")
		// Let saves in flight reach the database before it closes.
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		srv.Shutdown(shutdown)
		close(stopped)
	}()
	if err := srv.Serve(ln); !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	<-stopped
	return nil
}
