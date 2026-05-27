# NEXARA MEP

**NEXARA MEP** ist ein IFC-gestütztes Planungswerkzeug für die automatisierte Trassierung von Lüftungs-, Heizungs- und Sanitärleitungen (MEP) sowie für die Schacht- und Technikraumplanung in Gebäuden.

Das Werkzeug liest IFC-Modelle, ermittelt Raumbedarfe aus Excel-Raumlisten, plant optimierte Leitungstrassen durch ein 3D-Voxel-Raster und exportiert die Ergebnisse als masshaltige IFC-Volumenkörper.

> **NEXARA MEP** is a BIM-based planning tool for the automated routing of HVAC and plumbing (MEP) systems, shaft planning, and plant room analysis in buildings. It reads IFC models, derives space requirements from Excel lists, computes optimised routing paths on a 3D voxel grid, and exports results as dimensionally-accurate IFC solid bodies.

> Developed as part of the Bachelor Thesis at **Hochschule Luzern – Technik & Architektur** (HSLU T&A), Bachelor Digital Construction, FS26.

---

## Bachelorarbeit / Bachelor Thesis

| | |
|---|---|
| **Titel** | Automatisierte Generierung von HLKS-Platzbedarfen auf Basis von BIM-Volumenmodellen in frühen Planungsphasen |
| **Title** | Automated Generation of MEP Space Requirements Based on BIM Volume Models in Early Design Phases |
| **Autor** | Jonas Andri Weiss |
| **Hochschule** | Hochschule Luzern – Technik & Architektur |
| **Studiengang** | Bachelor Digital Construction |
| **Semester** | FS26 (2026) |
| **Betreuer** | Dipl.-Ing. Michal Rontsinsky |
| **Experte** | Martin Loucka |
| **Industriepartner** | [Penzel Valier AG, Zürich](https://www.penzelvalier.ch) |

---

## Schnellstart

### Voraussetzungen

- Python 3.11+
- Node.js 18+ (für den Frontend-Build)
- numba (wird über `requirements.txt` installiert, beschleunigt den A\*-Algorithmus)

### 1. Backend starten

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Das Backend startet auf `http://localhost:5000`. Beim ersten Start kompiliert numba den A\*-Kern (~20–40 s). Ab dem zweiten Start entfällt die Kompilierung.

### 2. Frontend bauen

```bash
cd frontend
npm install
npm run build
```

Der Build-Output landet in `frontend/dist/` und wird vom Flask-Backend automatisch ausgeliefert.

### 3. Anwendung öffnen

`http://localhost:5000` im Browser öffnen.

---

## Projektstruktur

```
NEXARA_MEP/
├── backend/                        Python-Backend (Flask)
│   ├── app.py                      Flask-Anwendungseinstiegspunkt
│   ├── planner_runtime.py          Laufzeit-Koordination
│   ├── project_io.py               Bundle-Serialisierung / -Deserialisierung
│   ├── requirements.txt            Python-Abhängigkeiten
│   ├── planner_config_example.json Beispielkonfiguration (alle Parameter)
│   ├── pipe_planner/               Kern-Planungs-Engine
│   │   ├── config.py               Projektkonfiguration und Standardwerte
│   │   ├── routing.py              A*-Trassierung + Penalty-Replanning (numba)
│   │   ├── section_sizing.py       Querschnittsdimensionierung HEI/LUE/SAN
│   │   ├── voxel_grid.py           3D-Voxel-Raster-Aufbau
│   │   ├── cost_fields.py          NumPy-Kostenfelder für den Pfad-Sucher
│   │   ├── ifc_reader.py           IFC-Modell einlesen
│   │   ├── ifc_exporter.py         IFC-Ausgabe als extrudierte Volumenkörper
│   │   ├── demand_loader.py        Excel-Raumbedarfe laden
│   │   ├── scoring.py              Trassengewichtung und -bewertung
│   │   ├── system_builder.py       Systemaufbau aus Variantenauswahl
│   │   ├── floor_detection.py      Geschossbandermittlung aus IFC
│   │   ├── domain/                 Domänen-Datenklassen
│   │   └── routing_helpers/        Routing-Hilfsfunktionen
│   ├── routes/                     Flask-API-Endpunkte
│   │   ├── session_routes.py       Session aufbauen / importieren / exportieren
│   │   ├── config_routes.py        Konfiguration importieren / exportieren
│   │   ├── routing_routes.py       Varianten, Auswahl, Design Explorer
│   │   ├── file_routes.py          Dateidownloads (IFC)
│   │   └── study_routes.py         Studie-Seiten-API
│   ├── services/
│   │   ├── study/                  Studie-Seite (Steigzonen-Bewertung)
│   │   └── technikraum/            VDI 2050 Technikraum-Analyse
│   ├── static/                     CSS, Logos, Favicon
│   ├── templates/                  HTML-Templates (Jinja2)
│   ├── study_data/                 Digitalisierte VDI-Diagrammdaten
│   └── study_templates/            VDI-Tabellen-Templates
├── frontend/                       JavaScript-Frontend (Vite)
│   ├── src/
│   │   ├── main.js                 Anwendungseinstieg
│   │   ├── api.js                  Fetch-Hilfsfunktionen
│   │   ├── state/                  Globaler Anwendungsstatus
│   │   ├── layout/                 Shell-Layout und Panels
│   │   └── features/               Funktionsmodule
│   │       ├── viewer/             3D-IFC-Viewer (@thatopen)
│   │       ├── browser/            IFC-Struktur-Browser
│   │       ├── rooms/              Raumdetail-Panel
│   │       ├── routing/            Trassierungs- und Systemkontrolle
│   │       └── designExplorer/     Design-Explorer
│   ├── package.json
│   └── vite.config.js
└── uploads/                        Laufzeit-Uploads (leer im Repo)
    └── .gitkeep
```

---

## Seiten und Arbeitsbereiche

| URL | Beschreibung |
|-----|-------------|
| `/` | **Startseite** — IFC- und Excel-Dateien hochladen, Bundle importieren/exportieren, Konfiguration verwalten |
| `/vorprojekt` | **Vorprojekt** — 3D-IFC-Viewer mit Trassierungs-Workflow und Design Explorer |
| `/studie` | **Studie** — Schachtraum-Bewertung nach VDI-Kriterien, Technikraum-Analyse nach VDI 2050 |

---

## Workflow

1. **Startseite**: IFC-Modell und Bedarfs-Excel hochladen → Berechnung starten
2. **Vorprojekt**: Raum auswählen → Gewerk wählen → Variante prüfen → auf System anwenden
3. **Studie**: Steigzonen-Kriterien bewerten → Technikräume prüfen → Excel exportieren
4. **Export**: Projekt-Bundle speichern oder Trassierungs-IFC herunterladen

---

## Trassierungs-Algorithmus

### Gewichteter A* mit numba-Beschleunigung

Jede Trasse wird mit gewichtetem A* auf dem 3D-Voxel-Raster berechnet. Der A\*-Kern ist mit `@numba.njit(cache=True)` kompiliert — das eliminiert den Python-Interpreter-Overhead im Inner Loop und ergibt einen Speedup von ~10–50× gegenüber reinem Python.

Alle positionsabhängigen Kosten (Wand-, Decken-, Ganggewichte) werden vor dem A\*-Lauf einmalig vektorisiert in ein NumPy-Array eingebacken (`build_cell_cost_array`). Im Inner Loop reduziert sich die Kostenberechnung auf einen einzigen Array-Lookup pro Nachbar-Voxel.

Pro Bedarf (Raum × Gewerk) werden bis zu `candidate_shaft_limit` Schächte × 6 Strategieprofile getestet.

### Penalty-based Replanning

Pro Strategie × Schacht werden bis zu `k_routes_per_strategy` verschiedene Pfade berechnet:

1. A* findet einen Pfad auf dem unmodifizierten Gitter.
2. Alle Zellen des Pfads werden in einer temporären Overlay-Maske mit einem Zusatzkostenwert belegt (`penalty_factor × voxel_size`).
3. Der nächste A\*-Lauf wird dadurch räumlich in andere Korridore gelenkt.
4. Schritte 2–3 wiederholen sich bis zu `k`-mal.
5. Alle Kandidaten werden auf den **originalen** Gitterkosten bewertet — der beste Pfad gewinnt.

Das Frontend sieht weiterhin genau eine Variante pro Strategie.

### Route-Cache und Worker-Gruppierung

Da das Voxel-Raster gewerkneutral ist, sind die Pfade für Heizung, Sanitär und Lüftung vom gleichen Raum zum gleichen Schacht identisch. Ein zweistufiger Cache vermeidet redundante Berechnungen: Level 1 cached das NumPy-Kostenfeld pro Strategie, Level 2 den fertigen Pfad pro (Start, Ziel, Strategie). Im Parallelbetrieb werden Tasks nach Raum gruppiert damit der Cache auch über Worker-Grenzen wirkt.

---

## Querschnittsdimensionierung

| Gewerk | Norm | Methode |
|--------|------|---------|
| **HEI** (Heizung) | SIA 384.101 / suissetec | Darcy-Weisbach bei R = 50 Pa/m; Vorlauf + Rücklauf → doppelte Breite |
| **LUE** (Lüftung) | EN 13779 / suissetec | Stufengeschwindigkeit, Kanal 2:1 (B/H) |
| **SAN** (Sanitär) | SVGW W3 / SIA 385 | Nussbaum Optipress Belastungswert-Tabelle (1 LU = 0,1 l/s); Kaltwasser + Warmwasser (eine DN-Stufe kleiner) → kombinierte Breite |

Die kombinierten Bounding-Boxes aller Gewerke auf einem Segment werden mit einem Clearance-Faktor von 1,05 vergrössert und bilden den Volumenkörper im IFC-Export.

---

## Konfiguration

Die Planungskonfiguration kann als JSON-Datei importiert/exportiert werden (`backend/planner_config_example.json` als Vorlage).

| Parameter | Abschnitt | Standard | Beschreibung |
|-----------|-----------|----------|-------------|
| `voxel_size` | `voxel_grid` | `0.5` | Voxel-Kantenlänge in Metern |
| `default_workers` | `runtime` | `4` | CPU-Threads für parallele Berechnung |
| `candidate_shaft_limit` | `runtime` | `4` | Maximale Schachtkandidaten pro Bedarf |
| `k_routes_per_strategy` | `runtime` | `5` | Penalty-Replan-Iterationen pro Strategie (`1` = deaktiviert) |
| `penalty_factor` | `runtime` | `3.0` | Stärke der Zell-Bestrafung (typisch: 2,0–6,0) |
| `corridor_keywords` | `keywords` | — | Namensfragmente zur Erkennung von Fluren |
| `shaft_keywords` | `keywords` | — | Namensfragmente zur Erkennung von Schächten |
| `strategies` | — | — | Gewichtungsprofile für die Trassenbewertung |

---

## API-Endpunkte (Auswahl)

| Methode | Endpunkt | Beschreibung |
|---------|----------|-------------|
| `POST` | `/api/session/build` | Neue Sitzung aus IFC und Excel aufbauen |
| `POST` | `/api/session/import` | Gespeichertes Projekt-Bundle importieren |
| `GET` | `/api/session/export` | Aktuelles Projekt-Bundle exportieren |
| `GET` | `/api/session/summary` | Aktuelle Sitzungsübersicht |
| `GET` | `/api/session/config` | Aktive Konfiguration abrufen |
| `GET` | `/api/config/export` | Konfiguration als JSON herunterladen |
| `POST` | `/api/config/import` | Konfiguration aus JSON laden |
| `GET` | `/api/variants` | Trassenvarianten für Raum und Gewerk |
| `POST` | `/api/selection` | Variantenauswahl auf System anwenden |
| `GET` | `/api/studie/data` | Studie-Seitendaten |
| `GET` | `/api/studie/export` | Studie-Excel exportieren |
| `GET` | `/api/session/export-routing-ifc` | Trassierungs-IFC exportieren |

---

## Code-Konventionen

- **Backend** (Python): Englisch — Variablennamen, Kommentare, Docstrings, Typen
- **Frontend** (JavaScript): Englisch — Variablennamen, Kommentare, Funktionsnamen
- **Benutzeroberfläche**: Deutsch — alle Labels, Fehlermeldungen, Schaltflächen

Alle Python-Klassen und -Funktionen sind mit Docstrings (Args / Returns) und Typannotationen versehen.

---

## Abhängigkeiten

Vollständige Lizenz- und Quellinformationen: [`OPEN_SOURCE_LIZENZEN.md`](OPEN_SOURCE_LIZENZEN.md) und [`ANHANG_SOFTWAREVERZEICHNIS.md`](ANHANG_SOFTWAREVERZEICHNIS.md).

---

## Lizenz / License

**MIT License** — see [`LICENSE`](LICENSE) for full terms.

© 2026 Jonas Andri Weiss — Bachelor Thesis, Hochschule Luzern – Technik & Architektur
