# Quiet

A small place to write, without distractions. Quiet is a local writing app: a single executable with no dependencies that opens a page to write on in your browser. Your writing stays on your computer, in an SQLite database.

## Requirements

A modern browser (Firefox, Chrome, Edge, Safari). Nothing else to install.

## Running

```sh
./quiet
```

The server starts at <http://127.0.0.1:8765> and opens the browser. To stop it, press `Ctrl+C` in the terminal.

You can keep several windows or tabs open at once (see [Several windows](#several-windows)). You can't run two servers at once, though: the second one finds the port taken and exits with an error (`address already in use`).

## Where your data lives

| What | Where |
| --- | --- |
| Drafts (including those in the trash) | `quiet.db` in your user data directory (see below) |
| Theme, focus mode, font, text size and text language | The browser's `localStorage` |
| Changes the server hasn't confirmed yet | The browser's `localStorage`, until the server saves them |

The data directory depends on the system, and the exact path is printed at startup:

| System | Directory |
| --- | --- |
| Linux | `~/.local/share/quiet` (or `$XDG_DATA_HOME/quiet`) |
| macOS | `~/Library/Application Support/Quiet` |
| Windows | `%AppData%\Quiet` |

To use a different database, start Quiet with `-db path/to/file.db`.

**Backups.** The safest way is to copy the database with SQLite, even while the server is running:

```sh
sqlite3 quiet.db ".backup quiet-backup.db"
```

Otherwise, stop the server and copy `quiet.db`. To restore a backup, replace `quiet.db` while the server is stopped.

**Updates.** When a new version of Quiet changes the database layout, `quiet.db` is upgraded on its own at startup, without losing anything. After an update, restart the server and reload every open window.

**Coming from the Python version.** It kept `quiet.db` next to `quiet.py`. Move that file into the data directory above, or point Quiet at it with `-db`. The very first versions kept drafts only in the browser: they are imported into the database automatically on first load, and a copy stays in the browser under the key `quiet-writing-drafts-v1-migrated`.

## Using Quiet

### Writing

- **Autosave:** every change is saved shortly after you stop typing, and at least every 2 seconds if you type without pausing. The label at the top left reads *Saving…*, *Saved* or *Not saved*.
- **New draft:** the **+** button or `Alt+N`. If an empty draft already exists, it opens that one instead of making another.
- **Export:** **Export .md** or `Ctrl+Shift+E` downloads the draft as Markdown. The title becomes the `# Title` heading, so use `##` and `###` for chapters and sections.

### Trash

**Move to trash** doesn't ask for confirmation: a notice with **Undo** shows for a few seconds instead. The **Trash** link under the list shows deleted drafts. From there you can open them read-only, **Restore** them or **Delete them for good**, and **Empty** deletes them all. Only these last two actions can't be undone, and they ask first. The trash never empties itself.

### Appearance

- **Mood:** three themes, *Warm paper*, *Light studio* and *Midnight*.
- **Aa:** font (Serif, Sans, Mono), text size (16 to 28 px, 20 by default) and text language.
- **Text language:** sets how words break across lines in the book style, and which dictionary the browser's spellcheck uses. *Auto*, the default, follows the browser's language; *English* and *Italiano* fix it, for example when you write in Italian in an English browser.
- **Book style:** with *Warm paper* and *Serif* the page looks like a printed book. It uses EB Garamond, old-style figures, justified and hyphenated text, a centered title and an ornament below it.

### Focus mode

**Focus mode** or `Ctrl+Shift+F` leaves only the page and the words. To leave it, press `Esc` or use the button that appears when you move the mouse. If saving fails, a small notice appears at the bottom left.

### Keyboard shortcuts

On macOS, `Cmd` works in place of `Ctrl`.

| Keys | Action |
| --- | --- |
| `Ctrl+S` | Save now (not needed: saving is automatic) |
| `Ctrl+Shift+E` | Export the draft as Markdown |
| `Alt+N` | New draft |
| `Ctrl+Shift+F` | Enter or leave focus mode |
| `Enter` in the title | Move to the text |
| `Esc` | Close the **Aa** panel, then leave focus mode, then go back from the trash to your drafts |

## Several windows

You can write in several windows or tabs, even in different browsers:

- **Sync:** changes made in one window show up in the others. Between tabs of the same browser this is almost immediate; another browser catches up when it comes to the foreground, and every 15 seconds anyway.
- **Conflicts:** if two windows edit the same draft at almost the same moment, neither overwrites the other. The draft keeps the version saved first, and the other window's changes become a copy titled *"Title (conflicting version)"*. You merge the two by hand.

## If the server stops responding

If the server is stopped while you write, the label turns to *Not saved* and your changes are kept in the browser. Quiet retries every 5 seconds and saves them as soon as the server is back. If the server was restarted, reload the page: pending changes are saved on load, even if the window that held them was closed.

## Security

The server listens only on `127.0.0.1` and can't be reached from other devices on the network. The API only accepts requests whose `Host` header is `127.0.0.1` or `localhost`, and that carry a random token generated at every start. This way a web page open in the same browser can't read or change your drafts.

## Options

| Option | Effect |
| --- | --- |
| `-port 8765` | Port the server listens on |
| `-db path` | Database to use instead of `quiet.db` in the data directory |
| `-no-browser` | Don't open the browser at startup |

Changing the port doesn't affect your drafts, since they live in the database. The theme and reading settings are tied to the address, though, so on a new port they start from the defaults.

## Project layout

```
LICENSE                    the GNU GPL v3
main.go                    server, API and database
index.html                 the page (HTML, CSS and JavaScript)
fonts/EBGaramond.woff2     font for the book style, served locally
fonts/OFL-EBGaramond.txt   the font's license
```

The page and the font are embedded in the executable at build time.

## Building from source

You need Go 1.26 or later. SQLite comes as a pure Go library, so no C compiler is needed:

```sh
go build
```

Or, without cloning the repository:

```sh
go install github.com/gosub/quiet@latest
```

## Credits

The [EB Garamond](https://github.com/octaviopardo/EBGaramond12) typeface is by Georg Duffner and Octavio Pardo, released under the SIL Open Font License 1.1 (`fonts/OFL-EBGaramond.txt`). The included version is trimmed to the Latin alphabet and a few ornaments, but keeps all its OpenType features.

## Author

Giampaolo Guiducci

## License

Quiet is free software, released under the [GNU General Public License version 3](LICENSE) or, at your option, any later version (GPL-3.0-or-later). You can use, study, change and share it; if you distribute a modified version, it must stay under the GPL and include its source code.

The font in `fonts/` is not covered by the GPL: it keeps its own license, the SIL Open Font License 1.1 (see [Credits](#credits)).
