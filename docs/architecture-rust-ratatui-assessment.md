# Einschätzung: Portierung auf Rust und Ratatui

Datum: 2026-09-14

## Kurzfazit

Eine vollständige Portierung von `jira-cli` auf Rust/Ratatui ist technisch gut machbar, aber aktuell kein wirtschaftlicher 1:1-Ersatz für die laufende Produktarbeit. Ratatui ist ein reifes, aktives Rust-TUI-Framework mit einer starken Community, vielen Beispielen und stabiler Terminal-Abstraktion. Der Hauptaufwand liegt jedoch nicht im TUI-Rendering, sondern in der erneuten Implementierung der gesamten Anwendungs- und Provider-Schicht.

**Empfehlung:** keinen Big-Bang-Port starten. Zuerst einen kleinen Rust-Pilot bauen, der einen read-only GitHub-Project-Kontext lädt und als Ratatui-Tabelle/Board darstellt. Danach anhand von Binary-Größe, Startzeit, UX, API-Aufwand und Wartbarkeit entscheiden.

## Ausgangslage

Das bestehende Projekt ist eine funktionsreiche Python-Anwendung:

- Click-CLI mit Issue-, User-, Version- und Workflow-Kommandos
- Textual-TUI mit Tabelle, Kanban-Board, Detailansicht, Modals und Tastatur-Workflows
- Provider-Abstraktion für Jira, GitHub Repository Issues, GitHub Projects V2 und Demo
- REST über Jira/GitHub sowie GraphQL für GitHub Projects V2
- Pydantic-Modelle und Provider-Deskriptoren
- serverseitige Filter und Sortierung
- asynchrone bzw. thread-basierte TUI-Worker für blockierende Netzwerkaktionen
- Markdown/ADF-Konvertierung über `md-adf`
- 117 Tests, davon ein großer Anteil Textual-Pilot-/TUI-Tests
- MkDocs-Dokumentation, PyPI-Distribution und Renovate

Der Port müsste diese Verträge und Verhaltensweisen erhalten, nicht nur die sichtbare Oberfläche.

## Ratatui-Einschätzung

Ratatui passt grundsätzlich gut zu einer terminalzentrierten Anwendung:

- MIT-lizenziert
- sehr aktiv gepflegt
- viele Releases und Contributors
- Crossterm als üblicher Backend-/Event-Layer
- Tabellen, Listen, Layouts, Paragraphs, Scrollbars und eigene Widgets
- gute Dokumentation, Beispiele und Templates
- deterministisches Rendern über `Frame`, dadurch gut testbare View-Funktionen

Ratatui ist bewusst weniger anwendungsintegriert als Textual. Es liefert Rendering und Widgets, aber keinen vergleichbaren kompletten Application-Framework-Layer mit automatisch verwaltetem Widget-Tree, Messages, Screens, Workers, Modals und CSS.

Das ist gleichzeitig Stärke und Kostenpunkt: Die UI wird expliziter und kontrollierbarer, aber Fokus, Navigation, Modals, Events, Resize-Verhalten, Loading-Zustände und Background-Tasks müssen als Anwendungscode modelliert werden.

## Was neu gebaut werden müsste

### CLI und Prozessmodell

Click-Kommandos müssten durch `clap` ersetzt werden. Dabei müssten erhalten bleiben:

- aktuelle Unterkommandos und Optionen
- Exit-Codes und Fehlermeldungen
- JSON/CSV/Markdown/Table-Ausgaben
- `.env`/`local.env`-Erkennung und Quote-Normalisierung
- Demo-Modus
- Provider-Auto-Detection und interaktive Kontextauswahl

### Provider-Schicht

Jira, GitHub REST und GitHub GraphQL müssten neue Rust-Clients bekommen. Mögliche Bausteine wären:

- `reqwest` für HTTP
- `serde`/`serde_json` für Modelle und Payloads
- `tokio` für asynchrone API-Aufrufe
- GraphQL entweder per handgeschriebenen Queries oder mit einem Rust-GraphQL-Client
- `octocrab` oder direkte GitHub-REST-Aufrufe für GitHub
- Jira REST direkt über `reqwest`, da kein gleichwertiger offizieller Rust-Client vorausgesetzt werden sollte

Besonders teuer wären die kleinen, aber wichtigen Kompatibilitätsdetails:

- Jira ADF und Markdown
- GitHub Project V2 Field-/Status-IDs
- Pagination und API-Fehler
- Provider-neutraler `reporter`-/`assignee`-Umgang
- Draft Issues, Pull Requests und Multi-Repository-Items
- Schreiboperationen mit unterschiedlichen Berechtigungen

### Datenmodelle

Pydantic würde durch `serde`-Strukturen ersetzt. Die Typisierung wäre strenger und zur Compile-Zeit überprüft, aber viele dynamische Providerantworten müssten explizit modelliert werden:

- Jira ADF als rekursive Enums/Strukturen
- optionale und providerabhängige Felder
- GitHub REST- und GraphQL-Varianten
- kanonische `IssueRow`- und `ProviderDescriptor`-Modelle
- saubere Fehler- und Fallbacktypen

### TUI

Die aktuelle Textual-TUI müsste als Event-Loop-Anwendung neu modelliert werden:

- `Terminal`/`Frame`-Renderfunktion
- eigener App-State
- Fokusmodell zwischen Tabelle, Board, Detailbereich und Modals
- Keymap und Command Palette
- Tabellen- und Board-Navigation
- Modal-Stack
- Markdown-/ADF-Rendering
- Thread- und Kommentar-Ansicht
- Loading-/Error-/Empty-States
- Background-Tasks und Cancel-Verhalten

Ratatui bringt die visuellen Primitive, aber nicht automatisch die bestehende Interaktionsarchitektur.

## Was Rust besser machen würde

### Laufzeit und Distribution

- einzelnes natives Binary statt Python-/uv-/Interpreter-Umgebung
- sehr schneller Start
- einfache Verteilung über GitHub Releases, Homebrew, Scoop oder `cargo-binstall`
- geringere Gefahr fehlender Runtime-Abhängigkeiten
- reproduzierbare Builds mit Cargo Lockfile

### Robustheit

- starke Typen für Providerantworten und Zustandsübergänge
- `Result`/`Option` erzwingen explizite Fehlerpfade
- weniger Laufzeitfehler durch fehlende Attribute oder falsche Dict-Strukturen
- gutes Modell für konkurrierende Requests mit `tokio`

### TUI-Kontrolle

- deterministisches Rendering
- sehr direkte Kontrolle über Layout, Fokus und Tastatur
- weniger Framework-Magie
- gute Basis für ein fokussiertes, schnelles Terminalprodukt

## Was Rust zunächst schlechter machen würde

- deutlich höhere Einstiegshürde für Änderungen
- längere Iterationszyklen bei UX-Änderungen
- mehr Boilerplate für API-Modelle, Modals und State-Handling
- Debugging von Terminal-/Async-Problemen ist anspruchsvoller
- ADF/Markdown-Konvertierung müsste neu evaluiert oder portiert werden
- zwei Implementierungen wären während einer Übergangsphase teuer
- bestehende Python-Funktionalität könnte beim Port unbemerkt regressieren

## Grobe Aufwandsschätzung

Die Zahlen sind Größenordnungen für eine einzelne Person mit Rust-Erfahrung und setzen voraus, dass die bestehende Funktionalität erhalten bleiben soll.

| Phase                        | Inhalt                                        |   Aufwand |
| ---------------------------- | --------------------------------------------- | --------: |
| Rust-Grundgerüst             | Cargo, clap, Konfiguration, Fehler, Logging   |  2–4 Tage |
| Modelle und Provider-Vertrag | kanonische Modelle, serde, Deskriptoren       |  3–6 Tage |
| Jira read-only               | Auth, Search, Issues, Users, Labels, Versions |  4–8 Tage |
| GitHub REST                  | Issues, Assignees, Comments, Status           |  3–6 Tage |
| GitHub Projects V2           | GraphQL, Pagination, Board-Status, Cross-Repo | 5–10 Tage |
| Basis-TUI                    | Tabelle, Detail, Filter, Navigation           | 5–10 Tage |
| Board und Modals             | Board, Edit, Comments, Focus, Keyboard UX     | 5–10 Tage |
| Writes und Dogfooding        | Transitions, Assign, Edit, Comments, Tests    | 5–10 Tage |
| Distribution und Docs        | Releases, Packaging, CI, Docs                 |  2–5 Tage |

Für einen funktional vergleichbaren Port sind damit grob **5–10 Personenwochen** realistisch. Ein vollständiger Parallelbetrieb mit Python, Rust und Migration der Nutzer-/Releasepfade erhöht den Aufwand.

Ein read-only Pilot für GitHub Project V2 ist dagegen in etwa **3–7 Tagen** realistisch.

## Teststrategie für einen Port

Ratatui selbst ist nicht der kritische Testumfang. Die fachlichen Verträge sollten unabhängig von der UI getestet werden:

1. Provider-Contract-Tests für Jira, GitHub Repo und GitHub Project.
2. Golden Tests für kanonische IssueRows und Filterergebnisse.
3. Fixture-basierte Tests für Jira ADF und GitHub GraphQL.
4. Ratatui Render-/Snapshot-Tests für Tabelle, Board und Detailansicht.
5. Integrationstests mit Mock-HTTP-Servern.
6. Wenige optische End-to-End-Tests im echten Terminal.

Die vorhandenen 117 Python-Tests wären nicht direkt portierbar. Die Testfälle und Provider-Fixtures wären aber wertvoll und sollten als Verhaltensvertrag übernommen werden.

## Migrationsvarianten

### 1. Vollständiger Rewrite

Python wird durch Rust ersetzt.

**Vorteil:** klares Zielbild und am Ende nur ein Stack.

**Nachteil:** hoher einmaliger Aufwand, lange Phase ohne neue Features und hohes Regressionsrisiko.

### 2. Rust-TUI mit Python-Providerprozess

Ratatui rendert die UI, Python bleibt zunächst als Backendprozess bestehen. Die Kommunikation könnte über JSON-RPC oder stdio laufen.

**Vorteil:** schnelle TUI-Erprobung.

**Nachteil:** zwei Laufzeiten, Prozessprotokoll, Fehlerweitergabe und Deployment werden komplizierter. Für dieses Projekt vermutlich zu viel Architektur.

### 3. Rust-Pilot als separates Binary

Ein kleines `jira-ratatui` lädt zunächst nur GitHub Project V2 read-only. Die Python-Anwendung bleibt produktiv.

**Vorteil:** niedriges Risiko und echte Erkenntnisse zu UX, Startzeit und API-Modellen.

**Nachteil:** vorübergehend zwei Produkte.

**Empfehlung:** Diese Variante ist die sinnvollste.

### 4. Python beibehalten und TUI weiterentwickeln

Die aktuelle Implementierung bleibt die Hauptlinie.

**Vorteil:** höchste Feature-Geschwindigkeit und kein Migrationsaufwand.

**Nachteil:** Packaging und Laufzeit bleiben Python-basiert.

## Empfohlener Pilotumfang

Ein separates Rust-Pilotverzeichnis, beispielsweise `rust/ratatui-poc/`, sollte enthalten:

- `clap` mit `--project owner/number`
- GitHub-Token aus `GH_TOKEN` oder `gh auth token`
- ein `reqwest`-basierter GraphQL-Client
- Project V2 Items mit Repository, Titel, Status, Assignee, Reporter
- Tabelle und drei Statusspalten
- `repo`-Filter
- Loading-, Error- und Empty-State
- keine Writes im ersten Schritt
- Snapshot-Tests für Tabelle und Board

Der Pilot sollte gegen `colenio/21` laufen, aber keine produktiven Änderungen durchführen.

## Entscheidung

**Nicht sofort portieren.** Die bestehende Python-Anwendung ist funktional weit genug, dass ein Rewrite kurzfristig hauptsächlich bereits gelöste Arbeit wiederholt. Ratatui ist als technische Basis überzeugend, rechtfertigt aber allein keinen Rewrite.

**Rust-Pilot starten, wenn mindestens einer dieser Gründe wichtig wird:**

- native Binary-Verteilung wird zum Hauptziel
- Startzeit und Ressourcenverbrauch sind im Alltag spürbar relevant
- TUI-Komplexität übersteigt Textuals ergonomischen Nutzen
- GitLab kommt hinzu und ein stabiler, stark typisierter Multi-Provider-Kern wird strategisch wertvoll
- das Team kann Rust dauerhaft als zweiten bzw. neuen Hauptstack pflegen

Bis dahin sollte Python die produktive Referenz bleiben. Der Rust-Pilot ist ein Architektur- und UX-Experiment, kein sofortiger Ersatz.

## Quellen

- [Ratatui Repository](https://github.com/ratatui/ratatui)
- [Ratatui Documentation](https://docs.rs/ratatui)
- [Ratatui Templates](https://github.com/ratatui/templates/)
- [Ratatui Architecture](https://github.com/ratatui/ratatui/blob/main/ARCHITECTURE.md)
