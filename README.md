# Quiet

Un piccolo posto per scrivere, senza distrazioni. Quiet è un'app di scrittura locale: un solo eseguibile, senza dipendenze, che apre nel browser un foglio su cui scrivere. Gli scritti restano sul tuo computer, in un database SQLite.

## Requisiti

Un browser moderno (Firefox, Chrome, Edge, Safari). Non serve installare nient'altro.

## Avvio

```sh
./quiet
```

Il server parte su <http://127.0.0.1:8765> e apre il browser. Per fermarlo, premi `Ctrl+C` nel terminale.

Puoi tenere aperte più finestre o schede contemporaneamente (vedi [Più finestre aperte](#più-finestre-aperte)). Non puoi invece avviare due server insieme: il secondo trova la porta già occupata e termina con un errore (`Address already in use`).

## Dove sono i dati

| Cosa | Dove |
| --- | --- |
| Scritti (anche quelli nel cestino) | `quiet.db` nella cartella dati dell'utente (vedi sotto) |
| Tema, modalità focus, carattere e dimensione del testo | `localStorage` del browser |
| Modifiche non ancora confermate dal server | `localStorage` del browser, finché il server non le salva |

La cartella dati dipende dal sistema, e il percorso esatto viene stampato all'avvio:

| Sistema | Cartella |
| --- | --- |
| Linux | `~/.local/share/quiet` (o `$XDG_DATA_HOME/quiet`) |
| macOS | `~/Library/Application Support/Quiet` |
| Windows | `%AppData%\Quiet` |

Per usare un altro database, avvia Quiet con `-db percorso/del/file.db`.

**Backup.** Il modo più sicuro è copiare il database con SQLite, anche a server avviato:

```sh
sqlite3 quiet.db ".backup quiet-backup.db"
```

In alternativa, ferma il server e copia `quiet.db`. Per riprendere da un backup, sostituisci `quiet.db` a server fermo.

**Aggiornamenti.** Quando una nuova versione di Quiet cambia la struttura del database, `quiet.db` viene aggiornato da solo all'avvio, senza perdere dati. Dopo un aggiornamento, riavvia il server e ricarica tutte le finestre aperte.

**Versioni precedenti.** Le prime versioni salvavano gli scritti solo nel browser. Al primo avvio vengono importati automaticamente nel database, e una copia resta nel browser sotto la chiave `quiet-writing-drafts-v1-migrated`.

## Come si usa

### Scrivere

- **Salvataggio automatico:** ogni modifica viene salvata poco dopo che smetti di scrivere, e comunque almeno ogni 2 secondi se scrivi senza pause. L'etichetta in alto a sinistra mostra *Salvataggio…*, *Salvato* o *Non salvato*.
- **Nuovo scritto:** il pulsante **+** o `Alt+N`. Se esiste già uno scritto vuoto, si apre quello invece di crearne un altro.
- **Esportare:** **Esporta .md** o `Ctrl+Shift+E` scarica lo scritto in Markdown. Il titolo diventa l'intestazione `# Titolo`, quindi per capitoli e sottocapitoli usa `##` e `###`.

### Cestino

**Sposta nel cestino** non chiede conferma: per qualche secondo compare un avviso con **Annulla**. Il link **Cestino** sotto la lista mostra gli scritti eliminati. Da lì puoi aprirli in sola lettura, **Ripristinarli** o **Eliminarli definitivamente**, e **Svuota** li elimina tutti. Solo queste ultime due azioni sono irreversibili e chiedono conferma. Il cestino non si svuota mai da solo.

### Aspetto

- **Atmosfera:** tre temi, *Carta calda*, *Studio chiaro* e *Mezzanotte*.
- **Aa:** carattere del testo (Serif, Sans, Mono) e dimensione (da 16 a 28 px, predefinita 20).
- **Stile libro:** con *Carta calda* e *Serif* la pagina imita un libro stampato. Usa EB Garamond, numeri all'antica, testo giustificato e sillabato, titolo centrato e un ornamento sotto il titolo.

### Modalità focus

**Modalità focus** o `Ctrl+Shift+F` lascia solo il foglio e il testo. Per uscire usa `Esc`, oppure il pulsante che compare quando muovi il mouse. Se il salvataggio non riesce, un piccolo avviso compare in basso a sinistra.

### Scorciatoie da tastiera

Su macOS `Cmd` funziona al posto di `Ctrl`.

| Tasti | Azione |
| --- | --- |
| `Ctrl+S` | Salva subito (non serve: il salvataggio è automatico) |
| `Ctrl+Shift+E` | Esporta lo scritto in Markdown |
| `Alt+N` | Nuovo scritto |
| `Ctrl+Shift+F` | Entra o esce dalla modalità focus |
| `Invio` nel titolo | Passa al testo |
| `Esc` | Chiude il pannello **Aa**, poi esce dalla modalità focus, poi torna dal cestino agli scritti |

## Più finestre aperte

Puoi scrivere in più finestre o schede, anche in browser diversi:

- **Sincronizzazione:** le modifiche fatte in una finestra compaiono nelle altre. Tra schede dello stesso browser l'aggiornamento è quasi immediato; un altro browser si aggiorna quando torna in primo piano, e comunque ogni 15 secondi.
- **Conflitti:** se due finestre modificano lo stesso scritto quasi nello stesso momento, nessuna sovrascrive l'altra. Lo scritto conserva la versione salvata per prima, e le modifiche dell'altra finestra diventano una copia intitolata *"Titolo (versione in conflitto)"*. Le due versioni si uniscono a mano.

## Se il server non risponde

Se il server viene fermato mentre scrivi, l'etichetta diventa *Non salvato* e le modifiche restano conservate nel browser. Quiet riprova ogni 5 secondi e le salva appena il server torna. Se il server è stato riavviato, ricarica la pagina: le modifiche in sospeso vengono salvate al caricamento, anche se la finestra che le conteneva è stata chiusa.

## Sicurezza

Il server risponde solo su `127.0.0.1` e non è raggiungibile da altri dispositivi della rete. L'API accetta richieste solo con l'header `Host` di `127.0.0.1` o `localhost`, e con un token casuale generato a ogni avvio. In questo modo una pagina web aperta nello stesso browser non può leggere o modificare gli scritti.

## Configurazione

| Opzione | Effetto |
| --- | --- |
| `-port 8765` | Porta su cui ascolta il server |
| `-db percorso` | Database da usare al posto di `quiet.db` nella cartella dati |
| `-no-browser` | Non apre il browser all'avvio |

Se cambi la porta, gli scritti non ne risentono, perché stanno nel database. Tema e impostazioni di lettura invece sono legati all'indirizzo, quindi con la nuova porta ripartono dai valori predefiniti.

## Struttura del progetto

```
LICENSE                    testo della GNU GPL v3
main.go                    server, API e database
index.html                 la pagina (HTML, CSS e JavaScript)
fonts/EBGaramond.woff2     carattere dello stile libro, servito in locale
fonts/OFL-EBGaramond.txt   licenza del carattere
```

La pagina e il carattere sono incorporati nell'eseguibile al momento della compilazione.

## Compilare dai sorgenti

Serve Go 1.26 o successivo. SQLite è una libreria in Go puro, quindi non serve un compilatore C:

```sh
go build
```

Oppure, senza scaricare il repository:

```sh
go install github.com/gosub/quiet@latest
```

## Crediti

Il carattere [EB Garamond](https://github.com/octaviopardo/EBGaramond12) è di Georg Duffner e Octavio Pardo, distribuito con la SIL Open Font License 1.1 (`fonts/OFL-EBGaramond.txt`). La versione inclusa è ridotta all'alfabeto latino e a pochi ornamenti, ma conserva tutte le funzioni OpenType.

## Autore

Giampaolo Guiducci

## Licenza

Quiet è software libero, distribuito con la [GNU General Public License versione 3](LICENSE) o, a tua scelta, qualsiasi versione successiva (GPL-3.0-or-later). Puoi usarlo, studiarlo, modificarlo e ridistribuirlo; se ne distribuisci una versione modificata, anche quella deve restare sotto GPL e includere il codice sorgente.

Il carattere in `fonts/` non è coperto dalla GPL: mantiene la propria licenza, la SIL Open Font License 1.1 (vedi [Crediti](#crediti)).
