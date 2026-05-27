# Open-Source-Lizenzen und Drittanbieter-Software

Dieses Dokument listet alle in NEXARA MEP verwendeten Open-Source-Bibliotheken und Werkzeuge auf, die für die Bachelorarbeit nachgewiesen werden müssen.

---

## 1. Python-Backend-Abhängigkeiten

### Flask
- **Beschreibung:** Leichtgewichtiges Python-Webframework für die REST-API
- **Version:** 3.1.x
- **Lizenz:** BSD 3-Clause License
- **Repository:** <https://github.com/pallets/flask>
- **Verwendung:** HTTP-Server, Routing der API-Endpunkte (`/api/session/build`, `/api/variants`, u.a.), Jinja2-Template-Rendering
- **Zitation:** Grinberg, M. (2018). *Flask Web Development* (2nd ed.). O'Reilly Media. / Pallets Projects. (2024). Flask (Version 3.1) [Software]. <https://flask.palletsprojects.com>

---

### Flask-CORS
- **Beschreibung:** CORS-Middleware für Flask (Cross-Origin Resource Sharing)
- **Version:** 5.x
- **Lizenz:** MIT License
- **Repository:** <https://github.com/corydolphin/flask-cors>
- **Verwendung:** Ermöglicht dem Vite-Dev-Server (Port 5173) den Zugriff auf das Flask-Backend (Port 5000) während der Entwicklung

---

### pandas
- **Beschreibung:** Datenanalyse- und -manipulationsbibliothek für Python
- **Version:** 3.0.x
- **Lizenz:** BSD 3-Clause License
- **Repository:** <https://github.com/pandas-dev/pandas>
- **Verwendung:** Speicherung und Filterung der Trassenmatrix (`route_matrix.csv`/`.json`), Selektion von Varianten nach `demand_id`, `success`, Strategie
- **Zitation:** The Pandas Development Team. (2024). pandas (Version 3.0) [Software]. <https://doi.org/10.5281/zenodo.3509134>

---

### NumPy
- **Beschreibung:** Grundlegende Bibliothek für numerische Berechnungen in Python
- **Version:** 2.x
- **Lizenz:** BSD 3-Clause License
- **Repository:** <https://github.com/numpy/numpy>
- **Verwendung:** Voxel-Raster-Operationen, Kostenfeld-Berechnung, 3D-Array-Handling in `voxel_grid.py` und `cost_fields.py`; Penalty-Overlay-Maske (`np.ndarray`, `dtype=float32`) für das Penalty-based Replanning in `routing.py`
- **Zitation:** Harris, C. R., et al. (2020). Array programming with NumPy. *Nature*, *585*, 357–362. <https://doi.org/10.1038/s41586-020-2649-2>

---

### openpyxl
- **Beschreibung:** Python-Bibliothek zum Lesen und Schreiben von Excel-Dateien (`.xlsx`)
- **Version:** 3.1.x
- **Lizenz:** MIT License
- **Repository:** <https://github.com/theorchard/openpyxl>
- **Verwendung:** Einlesen der Raumlisten-Excel-Datei (`demand_loader.py`), Erstellen und Befüllen der Studie-Excel-Exportdatei (`workbook_service.py`)

---

### IfcOpenShell
- **Beschreibung:** Open-Source-Bibliothek zum Lesen, Schreiben und Verarbeiten von IFC-Dateien (Industry Foundation Classes)
- **Version:** 0.8.x (ifcopenshell)
- **Lizenz:** LGPL-3.0 (Lesser GNU General Public License)
- **Repository:** <https://github.com/IfcOpenShell/IfcOpenShell>
- **Verwendung:** Einlesen des IFC-Gebäudemodells (`ifc_reader.py`), Extraktion von `IfcSpace`-, `IfcWall`-, `IfcSlab`-Geometrien, Georeferenzierung; Export der Trassierungsvolumen als IFC-Körper (`ifc_exporter.py`)
- **Zitation:** Krijnen, T. F., & Beetz, J. (2015). IfcOpenShell: An open-source IFC toolkit for geometric interpretation and analysis. In *eWork and eBusiness in Architecture, Engineering and Construction* (pp. 153–160). CRC Press. <https://doi.org/10.1201/b17396-23>

---

## 1b. Algorithmen und Verfahren (keine externen Bibliotheken)

Die folgenden Algorithmen und Verfahren sind direkt in NEXARA MEP implementiert. Sie stützen sich auf wissenschaftliche Originalquellen, erfordern aber keine externen Softwarebibliotheken.

### A*-Suchalgorithmus (Weighted A*)

- **Beschreibung:** Heuristischer Kürzeste-Pfad-Algorithmus auf einem gewichteten Graphen. In NEXARA MEP wird eine richtungscodierte Zustandsraumdarstellung verwendet (`(Zelle, letzte_Richtung)`), die Abbiegekosten direkt in die Kostenfunktion einbettet.
- **Implementierung:** `backend/pipe_planner/routing.py` — Funktion `a_star_route()`
- **Keine Lizenz erforderlich** (gemeinfrei, mathematisches Verfahren)
- **Originalquelle:** Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. *IEEE Transactions on Systems Science and Cybernetics*, *4*(2), 100–107. <https://doi.org/10.1109/TSSC.1968.300136>

---

### Penalty-based Replanning

- **Beschreibung:** Verfahren zur Erzeugung räumlich unterschiedlicher Alternativpfade auf demselben Kostengitter. Nach jedem A*-Lauf werden alle Zellen des gefundenen Pfads in einer temporären Overlay-Maske mit einem Zusatzkostenwert belegt (`penalty_factor × voxel_size`). Nachfolgende A*-Läufe werden dadurch in andere Korridore gelenkt. Alle Kandidatenpfade werden abschließend auf den originalen Gitterkosten bewertet; der beste Pfad wird zurückgegeben. Das Verfahren ist verwandt mit dem *Rip-up and Reroute*-Ansatz aus dem PCB-Auto-Routing.
- **Implementierung:** `backend/pipe_planner/routing.py` — Funktion `penalty_replan_k_routes()`
- **Keine Lizenz erforderlich** (algorithmisches Verfahren, keine Drittanbieterbibliothek)
- **Verwandte Originalquelle:** Lee, C. Y. (1961). An algorithm for path connections and its applications. *IRE Transactions on Electronic Computers*, *EC-10*(3), 346–365. <https://doi.org/10.1109/TEC.1961.5219222>
- **Konfigurationsparameter:** `k_routes_per_strategy` (Anzahl Iterationen), `penalty_factor` (Stärke der Zellenstrafe)

---

## 2. JavaScript-Frontend-Abhängigkeiten

### Three.js
- **Beschreibung:** JavaScript-3D-Rendering-Bibliothek auf Basis von WebGL
- **Version:** 0.182.0
- **Lizenz:** MIT License
- **Repository:** <https://github.com/mrdoob/three.js>
- **Verwendung:** Unterliegende 3D-Engine für den IFC-Viewer; Darstellung von Szene, Kamera, Geometrien, Materialien und Beleuchtung im Vorprojekt-Bereich
- **Zitation:** Cabello, R. (2010–2024). Three.js (Version r182) [Software]. <https://threejs.org>

---

### That Open Company — Components (`@thatopen/components`)
- **Beschreibung:** Framework-Komponenten für BIM-Webanwendungen auf Basis von Three.js
- **Version:** 3.4.2
- **Lizenz:** MIT License
- **Repository:** <https://github.com/ThatOpen/engine_components>
- **Verwendung:** Kernkomponenten des IFC-Viewers: `FragmentsManager`, `Raycaster`, `IfcLoader`, Kamerasteuerung, Exploder, Klassifizierer

---

### That Open Company — Components Front (`@thatopen/components-front`)
- **Beschreibung:** Erweiterte Frontend-Komponenten für den BIM-Viewer
- **Version:** 3.4.2
- **Lizenz:** MIT License
- **Repository:** <https://github.com/ThatOpen/engine_components>
- **Verwendung:** `PostproductionRenderer` (Antialiasing, Umgebungsverdeckung), `Highlighter` (Raumselektion), `Plans` (Grundrissschnitte), Edge-Rendering

---

### That Open Company — Fragments (`@thatopen/fragments`)
- **Beschreibung:** Effizientes Streaming und Rendering großer IFC-Modelle durch Fragmentierung
- **Version:** 3.4.0
- **Lizenz:** MIT License
- **Repository:** <https://github.com/ThatOpen/engine_fragment>
- **Verwendung:** `FragmentsManager` zum Laden, Verwalten und Entladen fragmentierter IFC-Modellteile; Worker-basiertes Parsen

---

### That Open Company — UI (`@thatopen/ui`)
- **Beschreibung:** Web-Component-UI-Bibliothek für BIM-Anwendungen
- **Version:** 3.4.0
- **Lizenz:** MIT License
- **Repository:** <https://github.com/ThatOpen/engine_ui>
- **Verwendung:** Vorkompilierte Lit-basierte Webkomponenten (Panels, Buttons, Toolbars) als Basis für die Viewer-Bedienoberfläche

---

### web-ifc
- **Beschreibung:** WebAssembly-basierter IFC-Parser — ermöglicht das Einlesen von IFC-Dateien direkt im Browser
- **Version:** 0.0.77
- **Lizenz:** Mozilla Public License 2.0 (MPL-2.0)
- **Repository:** <https://github.com/ThatOpen/engine_web-ifc>
- **Verwendung:** Unterliegende WebAssembly-Engine für die IFC-Geometrie-Extraktion im Browser; wird von `@thatopen/fragments` und `@thatopen/components` verwendet
- **Zitation:** That Open Company. (2024). web-ifc (Version 0.0.77) [Software]. <https://github.com/ThatOpen/engine_web-ifc>

---

### Lit (`lit`, `lit-html`, `lit-element`)
- **Beschreibung:** Bibliothek für Web Components mit reaktivem Templating
- **Version:** 3.3.x
- **Lizenz:** BSD 3-Clause License
- **Repository:** <https://github.com/lit/lit>
- **Verwendung:** Transitive Abhängigkeit über `@thatopen/ui`; definiert die Webkomponenten-Basis für die UI-Elemente des Viewers

---

### camera-controls
- **Beschreibung:** Kamerasteuerungsbibliothek für Three.js (Orbit, Pan, Zoom, Animationen)
- **Version:** 3.1.2
- **Lizenz:** MIT License
- **Repository:** <https://github.com/yomotsu/camera-controls>
- **Verwendung:** Transitive Abhängigkeit über `@thatopen/components-front`; steuert die 3D-Kamera im Viewer

---

### three-mesh-bvh
- **Beschreibung:** Bounding Volume Hierarchy für Three.js-Meshes — beschleunigt Raycast und Kollisionserkennung
- **Version:** 0.9.9
- **Lizenz:** MIT License
- **Repository:** <https://github.com/gkjohnson/three-mesh-bvh>
- **Verwendung:** Transitive Abhängigkeit über `@thatopen/components`; beschleunigt die Raumselektion per Klick im 3D-Viewer

---

### JSZip
- **Beschreibung:** Erstellt und liest ZIP-Dateien in JavaScript
- **Version:** 3.10.1
- **Lizenz:** MIT License / GPL-3.0-or-later
- **Repository:** <https://github.com/Stuk/jszip>
- **Verwendung:** Transitive Abhängigkeit über `@thatopen/fragments`; Verarbeitung komprimierter Fragmentdateien

---

### flatbuffers
- **Beschreibung:** Effizientes Serialisierungsformat für Binärdaten (Google)
- **Version:** 25.2.10
- **Lizenz:** Apache License 2.0
- **Repository:** <https://github.com/google/flatbuffers>
- **Verwendung:** Transitive Abhängigkeit über `@thatopen/fragments`; serialisiert Fragmentdaten für schnelles Streaming

---

### fast-xml-parser
- **Beschreibung:** XML-Parser für JavaScript — schnell, ohne DOM-Abhängigkeit
- **Version:** 5.3.7
- **Lizenz:** MIT License
- **Repository:** <https://github.com/NaturalIntelligence/fast-xml-parser>
- **Verwendung:** Transitive Abhängigkeit über `@thatopen/components`; parst IFC-XML-Metadaten

---

### pako
- **Beschreibung:** Hochperformante zlib-Portierung in JavaScript (gzip/deflate)
- **Version:** 2.1.0
- **Lizenz:** MIT License / Zlib
- **Repository:** <https://github.com/nodeca/pako>
- **Verwendung:** Transitive Abhängigkeit; Komprimierung/Dekomprimierung von IFC-Daten im Browser

---

### earcut
- **Beschreibung:** Schneller Polygon-Triangulator für JavaScript
- **Version:** 3.0.2
- **Lizenz:** ISC License
- **Repository:** <https://github.com/mapbox/earcut>
- **Verwendung:** Transitive Abhängigkeit über Three.js/`@thatopen`; trianguliert IFC-Raumpolygone für das WebGL-Rendering

---

## 3. Build-Werkzeuge (Entwicklungsabhängigkeiten)

### Vite
- **Beschreibung:** Moderner JavaScript-Build-Bundler und Entwicklungsserver
- **Version:** 6.2.0
- **Lizenz:** MIT License
- **Repository:** <https://github.com/vitejs/vite>
- **Verwendung:** Baut das Vorprojekt-Frontend zu optimierten statischen Dateien (`frontend/dist/`); stellt im Entwicklungsmodus Hot Module Replacement (HMR) bereit

---

### Rollup
- **Beschreibung:** JavaScript-Modul-Bundler
- **Version:** 4.60.2
- **Lizenz:** MIT License
- **Repository:** <https://github.com/rollup/rollup>
- **Verwendung:** Transitive Abhängigkeit über Vite; fasst ES-Module zu optimierten Bundles zusammen

---

### esbuild
- **Beschreibung:** Extrem schneller JavaScript/TypeScript-Transpiler und -Minifier
- **Version:** 0.25.12
- **Lizenz:** MIT License
- **Repository:** <https://github.com/evanw/esbuild>
- **Verwendung:** Transitive Abhängigkeit über Vite; führt das schnelle Transpilieren und Minifizieren des Frontend-Codes durch

---

### PostCSS
- **Beschreibung:** CSS-Transformations-Werkzeug
- **Version:** 8.5.x
- **Lizenz:** MIT License
- **Repository:** <https://github.com/postcss/postcss>
- **Verwendung:** Transitive Abhängigkeit über Vite; verarbeitet CSS-Dateien im Build-Prozess

---

## 4. Daten und Standards

### VDI 2050 Blatt 1 (Technische Gebäudeausrüstung)
- **Beschreibung:** Richtlinie für die Berechnung des Flächenbedarfs von Technischen Gebäudeausrüstungsanlagen
- **Herausgeber:** Verein Deutscher Ingenieure e.V. (VDI)
- **Verwendung:** Die in `study_data/vdi2050/` abgelegten digitalisierten Diagrammdaten (`diagramm_v1_*.csv` bis `diagramm_k2_*.csv`) basieren auf den Kurven aus VDI 2050 Blatt 1; sie werden zur Bewertung des Technikraumflächenbedarfs im Studie-Bereich verwendet
- **Hinweis:** Die Diagramme wurden zur Nutzung in dieser Software digitalisiert. Eine Nutzung der Originalrichtlinie erfordert eine Lizenz vom VDI.

### IFC-Standard (ISO 16739)
- **Beschreibung:** Industry Foundation Classes — offenes Datenformat für Building Information Modelling (BIM)
- **Herausgeber:** buildingSMART International / ISO
- **Version:** IFC 4 / IFC 4x3
- **Verwendung:** Standardformat für alle eingelesenen Gebäudemodelle und exportierten Trassierungsvolumen
- **Zitation:** ISO. (2018). *ISO 16739-1:2018: Industry Foundation Classes (IFC) for data sharing in the construction and facility management industries*. International Organization for Standardization.

---

## 5. Zusammenfassung nach Lizenz

| Lizenz | Bibliotheken |
|--------|-------------|
| **MIT** | Flask-CORS, openpyxl, Three.js, @thatopen/components, @thatopen/components-front, @thatopen/fragments, @thatopen/ui, camera-controls, three-mesh-bvh, JSZip, fast-xml-parser, pako, esbuild, Vite, Rollup, PostCSS, chart.js, chartjs-plugin-datalabels, nanoid, iconify-icon |
| **BSD 3-Clause** | Flask, pandas, NumPy, Lit/lit-html/lit-element, source-map-js |
| **LGPL-3.0** | IfcOpenShell |
| **MPL-2.0** | web-ifc |
| **Apache-2.0** | FlatBuffers |
| **ISC** | earcut, lru-cache, picocolors |
| **BSD-3 / MIT** | @lit/reactive-element, @lit-labs/ssr-dom-shim |

---

## 6. Hinweise zur Quellenangabe in der Bachelorarbeit

Für die korrekte Quellenangabe in wissenschaftlichen Arbeiten wird folgendes Format empfohlen (nach IEEE oder DIN ISO 690):

**Software-Zitation (allgemein):**
> [Autorenname]. ([Jahr]). *[Bibliotheksname]* (Version [X.Y.Z]) [Software]. Abgerufen von [URL]

**Beispiele:**

> Ronacher, A., & Pallets-Team. (2024). *Flask* (Version 3.1) [Software]. Abgerufen von https://flask.palletsprojects.com

> The Pandas Development Team. (2024). *pandas* (Version 3.0) [Software]. https://doi.org/10.5281/zenodo.3509134

> That Open Company. (2024). *@thatopen/components* (Version 3.4.2) [Software]. Abgerufen von https://github.com/ThatOpen/engine_components

> Krijnen, T., & Beetz, J. (2015). IfcOpenShell: An open-source IFC toolkit. In *eWork and eBusiness in Architecture, Engineering and Construction* (S. 153–160). CRC Press. https://doi.org/10.1201/b17396-23

> Harris, C. R., et al. (2020). Array programming with NumPy. *Nature*, *585*, 357–362. https://doi.org/10.1038/s41586-020-2649-2

---

*Dieses Dokument wurde automatisch aus den Projektabhängigkeiten (`requirements.txt`, `package.json`, `package-lock.json`) erstellt und manuell mit Lizenz- und Zitationsinformationen ergänzt. Letzter Stand: Mai 2026. Zuletzt aktualisiert: Ergänzung Abschnitt 1b (A\*-Algorithmus, Penalty-based Replanning).*
