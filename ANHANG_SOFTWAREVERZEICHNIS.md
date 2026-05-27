# Anhang: Verzeichnis verwendeter Software und Bibliotheken

Die folgende Tabelle listet alle in der Softwareentwicklung von NEXARA MEP eingesetzten Open-Source-Bibliotheken und Drittanbieter-Werkzeuge auf. Alle aufgeführten Komponenten sind für den nicht-kommerziellen akademischen Einsatz lizenzkonform verwendbar.

## A.1 Python-Backend

| Bibliothek | Version | Lizenz | Verwendungszweck |
|-----------|---------|--------|-----------------|
| Flask | 3.1.x | BSD 3-Clause | REST-API-Server, HTTP-Routing, Template-Engine |
| Flask-CORS | 5.x | MIT | Cross-Origin Resource Sharing für den Entwicklungsserver |
| pandas | 3.0.x | BSD 3-Clause | Trassenmatrix-Verwaltung, Variantenfilterung und -selektion |
| NumPy | 2.x | BSD 3-Clause | Voxel-Raster-Operationen, numerische Feldberechnungen; vektorisiertes Vorbacken der Zellkostenfelder (`build_cell_cost_array`) für den A\*-Algorithmus |
| openpyxl | 3.1.x | MIT | Lesen der Raumlisten-Excel, Schreiben des Studie-Exports |
| IfcOpenShell | 0.8.x | LGPL-3.0 | IFC-Modell einlesen, Geometrie extrahieren, IFC-Export |

## A.2 JavaScript-Frontend (Laufzeit)

| Bibliothek | Version | Lizenz | Verwendungszweck |
|-----------|---------|--------|-----------------|
| Three.js | 0.182.0 | MIT | 3D-WebGL-Rendering-Engine für den IFC-Viewer |
| @thatopen/components | 3.4.2 | MIT | BIM-Framework: IFC-Loader, Klassifizierer, Kamera, Raycast |
| @thatopen/components-front | 3.4.2 | MIT | Postprocessing, Highlighter, Grundrissschnitte |
| @thatopen/fragments | 3.4.0 | MIT | Streaming großer IFC-Modelle durch Fragmentierung |
| @thatopen/ui | 3.4.0 | MIT | Web-Component-UI-Bibliothek (Panels, Buttons) |
| web-ifc | 0.0.77 | MPL-2.0 | WebAssembly-IFC-Parser für den Browser |
| Lit | 3.3.x | BSD-3-Clause | Web-Components-Basisframework (via @thatopen/ui) |
| camera-controls | 3.1.2 | MIT | Kameranavigation im 3D-Viewer (Orbit, Pan, Zoom) |
| three-mesh-bvh | 0.9.9 | MIT | Beschleunigte Raumselektion per BVH-Raycast |
| JSZip | 3.10.1 | MIT | ZIP-Verarbeitung für IFC-Fragmentdateien |
| FlatBuffers | 25.2.10 | Apache-2.0 | Binäre Datenserialisierung für IFC-Fragments |
| fast-xml-parser | 5.3.7 | MIT | XML-Parsing für IFC-Metadaten |
| pako | 2.1.0 | MIT / Zlib | gzip-Komprimierung für IFC-Daten im Browser |
| earcut | 3.0.2 | ISC | Polygon-Triangulation für WebGL-Rendering |

## A.3 Build-Werkzeuge (Entwicklung)

| Werkzeug | Version | Lizenz | Verwendungszweck |
|---------|---------|--------|-----------------|
| Vite | 6.2.0 | MIT | Frontend-Build und Entwicklungsserver mit HMR |
| Rollup | 4.60.2 | MIT | ES-Modul-Bundler (via Vite) |
| esbuild | 0.25.12 | MIT | JavaScript-Transpiler und -Minifier (via Vite) |
| PostCSS | 8.5.x | MIT | CSS-Verarbeitung im Build-Prozess |

## A.4 Standards und Normen

| Standard | Herausgeber | Verwendung |
|---------|------------|-----------|
| IFC 4 / IFC 4x3 (ISO 16739) | buildingSMART / ISO | Gebäudemodell-Eingabeformat und Trassierungs-Export |
| VDI 2050 Blatt 1 | Verein Deutscher Ingenieure (VDI) | Grundlage der Technikraum-Flächenbewertungsdiagramme |

## A.5 Implementierte Algorithmen (keine externen Bibliotheken)

| Algorithmus | Implementierungsort | Beschreibung |
|------------|--------------------|-|
| Gewichteter A\* (Weighted A\*) | `backend/pipe_planner/routing.py` — `a_star_route()` | Heuristischer Kürzeste-Pfad-Algorithmus auf dem 3-D-Voxel-Raster mit richtungscodierter Zustandsraumdarstellung. Grundlage: Hart et al. (1968) |
| NumPy Cost-Array Pre-Baking | `backend/pipe_planner/routing.py` — `build_cell_cost_array()` | Alle positionsabhängigen Schrittkosten (Wand-, Decken-, Ganggewichte) werden vor dem A\*-Lauf einmalig vektorisiert in ein NumPy-Array eingebacken und danach per Einzelabfrage abgerufen, anstatt pro Voxel-Expansion in Python berechnet zu werden |
| Penalty-based Replanning | `backend/pipe_planner/routing.py` — `penalty_replan_k_routes()` | Nach jedem A\*-Lauf werden Pfadzellen in einer temporären Overlay-Maske bestraft, sodass Folgeläufe räumlich andere Korridore nutzen. Verwandt mit dem Rip-up-and-Reroute-Verfahren aus dem PCB-Auto-Routing. Grundlage: Lee (1961) |
| Zweistufiger Route-Cache | `backend/pipe_planner/routing.py` — `_evaluate_sequential()` | Stufe 1: ein Cost-Array pro Strategie (vermeidet mehrfaches Pre-Baking). Stufe 2: ein Pfad-Payload pro (Start-Voxel, Ziel-Voxel, Strategie), dienst-agnostisch, da das Voxel-Raster keine Gewerk-Unterschiede kennt. Cache-Treffer werden mit den jeweils richtigen Bedarf-Metadaten (demand\_id, service) befüllt |

## A.6 Ausgewählte Literatur zu den Kernwerkzeugen

- **IfcOpenShell:** Krijnen, T. F., & Beetz, J. (2015). IfcOpenShell: An open-source IFC toolkit for geometric interpretation and analysis. In *eWork and eBusiness in Architecture, Engineering and Construction* (pp. 153–160). CRC Press. https://doi.org/10.1201/b17396-23

- **NumPy:** Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020). Array programming with NumPy. *Nature*, *585*(7825), 357–362. https://doi.org/10.1038/s41586-020-2649-2

- **pandas:** McKinney, W. (2010). Data structures for statistical computing in Python. In *Proceedings of the 9th Python in Science Conference* (pp. 56–61). https://doi.org/10.25080/Majora-92bf1922-00a

- **Three.js:** Cabello, R. (2010–2024). *Three.js — JavaScript 3D Library* (Version r182) [Software]. https://threejs.org

- **Flask:** Ronacher, A., & Pallets-Team. (2024). *Flask — The Pallets Projects* (Version 3.1) [Software]. https://flask.palletsprojects.com

- **IFC-Standard:** ISO. (2018). *ISO 16739-1:2018: Industry Foundation Classes (IFC) for data sharing in the construction and facility management industries*. Genf: International Organization for Standardization.

- **buildingSMART:** buildingSMART International. (2024). *IFC — The open standard for BIM*. https://www.buildingsmart.org/standards/bsi-standards/industry-foundation-classes

- **A\*-Algorithmus:** Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. *IEEE Transactions on Systems Science and Cybernetics*, *4*(2), 100–107. https://doi.org/10.1109/TSSC.1968.300136

- **Penalty-based Replanning / Rip-up-and-Reroute:** Lee, C. Y. (1961). An algorithm for path connections and its applications. *IRE Transactions on Electronic Computers*, *EC-10*(3), 346–365. https://doi.org/10.1109/TEC.1961.5219222

---

*Vollständige Lizenz- und Quelltext-Informationen: Datei `OPEN_SOURCE_LIZENZEN.md` im Projektverzeichnis.*
