/* Saved widths for collapse/restore */
const _savedWidths = { sidebar: null, inspector: null };

export function createLayout() {
  document.querySelector("#app").innerHTML = `
    <div class="app-shell">

      <header class="header">
        <div class="header-brand">
          <img src="/static/nexara-logo_rem.png" alt="NEXARA" class="nexara-logo">
          <div class="header-brand-text">
            <div class="app-title">Vorprojekt</div>
            <div class="app-subtitle">IFC-Trassierung &amp; Schachtplanung</div>
          </div>
        </div>
        <div class="header-actions">
          <a href="/" class="back-link">← Startseite</a>
          <a href="/studie" class="back-link">Studie</a>
          <div id="build-status" class="status-pill">Kein Modell geladen</div>
        </div>
      </header>

      <!-- ── Linke Seitenleiste ──────────────────────── -->
      <aside class="sidebar shell-panel" id="project-panel">
        <div class="panel-header collapsible-header">
          <span class="panel-header-title" id="sidebar-project-name">Projekt</span>
          <button id="toggle-project-panel" class="panel-collapse-button"
            data-shell-toggle="sidebar" data-expanded-symbol="⟨" data-collapsed-symbol="⟩"
            type="button">⟨</button>
        </div>
        <div class="sidebar-resize-handle" id="sidebar-resize-handle"></div>

        <div class="panel-content stack">
          <div class="panel-card">
            <div class="section-title">Aktuelles Projekt</div>
            <div class="stack compact-stack">
              <div id="project-panel-note" class="small muted">IFC und Excel werden aus der Hauptseiten-Sitzung geladen.</div>
              <div id="project-panel-meta" class="detail-list compact-detail-list">
                <div class="muted">IFC</div><div>Nicht geladen</div>
                <div class="muted">Bedarfe</div><div>Nicht geladen</div>
                <div class="muted">Geschosse</div><div>—</div>
                <div class="muted">Räume</div><div>—</div>
                <div class="muted">Schächte</div><div>—</div>
              </div>
              <div class="button-row">
                <button id="export-routing-ifc-button" class="secondary" type="button" style="flex:1;">&#11015; Trassierungs-IFC exportieren</button>
              </div>
              <div id="export-ifc-status" class="small muted" style="display:none;"></div>
            </div>
          </div>

          <div class="panel-card browser-card" style="flex:1;min-height:0;">
            <div class="section-title" style="display:flex;align-items:center;justify-content:space-between;">
              IFC-Elemente
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M21 21v-2a4 4 0 0 0-3-3.87"/></svg>
            </div>
            <div class="browser-tabs">
              <button id="browser-tab-structure"  class="tab-button active" type="button">Struktur</button>
              <button id="browser-tab-categories" class="tab-button"        type="button">Kategorien</button>
            </div>
            <div class="field"><label for="browser-search">Suche</label><input id="browser-search" type="text" placeholder="IFC-Elemente suchen…" /></div>
            <div id="model-browser" class="model-browser"><div class="small muted">Modell laden, um den IFC-Baum zu durchsuchen.</div></div>
          </div>
        </div>
      </aside>

      <!-- ── Mittlerer Viewer ───────────────────────── -->
      <section class="viewer-panel">
        <div class="viewer-canvas-wrap">
          <div class="viewer-overlay-dock">
            <div id="viewer-visibility-panel" class="viewer-overlay-card collapsed">
              <button id="toggle-visibility-panel" class="viewer-overlay-toggle" data-viewer-panel="viewer-visibility-panel" type="button">
                <span class="viewer-overlay-icon">👁</span><span class="viewer-overlay-text">Sichtbarkeit</span>
              </button>
              <div class="viewer-overlay-body">
                <div class="tool-group-actions">
                  <button id="spaces-only-button" class="ghost" type="button">Räume</button>
                  <button id="full-ifc-button"    class="ghost" type="button">Vollständiges IFC</button>
                </div>
                <div class="tool-group-actions">
                  <button id="hide-selected-button" class="ghost" type="button">Auswahl ausblenden</button>
                  <button id="reset-hidden-button"  class="ghost" type="button">Alle anzeigen</button>
                </div>
                <div class="tool-group-actions">
                  <button id="focus-route-button" class="ghost" type="button">Raum fokussieren</button>
                  <button id="reset-view-button"  class="ghost" type="button">Geschosse zurücksetzen</button>
                </div>
                <div class="field viewer-inline-field">
                  <label for="floor-select">Geschossfilter</label>
                  <select id="floor-select"></select>
                </div>
                <div class="tool-group-actions">
                  <button id="toggle-room-centers-button" class="ghost" type="button">Mittelpunkte an</button>
                  <button id="toggle-room-labels-button"  class="ghost" type="button">Beschriftungen aus</button>
                </div>
              </div>
            </div>

            <div id="viewer-section-panel" class="viewer-overlay-card collapsed">
              <button id="toggle-sections-panel" class="viewer-overlay-toggle" data-viewer-panel="viewer-section-panel" type="button">
                <span class="viewer-overlay-icon">✂</span><span class="viewer-overlay-text">Schnitte</span>
              </button>
              <div class="viewer-overlay-body">
                <div class="tool-group-actions">
                  <button id="section-pick-button"       class="ghost" type="button">Schnitt wählen</button>
                  <button id="section-horizontal-button" class="ghost" type="button">Horizontalschnitt</button>
                  <button id="section-front-button"      class="ghost" type="button">Vorderschnitt</button>
                  <button id="section-right-button"      class="ghost" type="button">Seitenschnitt</button>
                  <button id="section-delete-button"     class="ghost" type="button">Rückgängig</button>
                  <button id="section-clear-button"      class="ghost" type="button">Löschen</button>
                </div>
              </div>
            </div>
          </div>

          <div id="viewer"></div>
          <div id="viewer-empty-hint" class="viewer-empty-hint visible">
            Klicken Sie im Viewer auf einen Raum oder wählen Sie einen aus dem linken Bereich, um die Trassierung zu starten
          </div>

          <div class="viewer-corner-widget">
            <div class="cube-shell">
              <button class="cube-face cube-top"   data-view-target="top"   type="button">OBEN</button>
              <button class="cube-face cube-front" data-view-target="front" type="button">VORNE</button>
              <button class="cube-face cube-right" data-view-target="right" type="button">RECHTS</button>
            </div>
            <div class="cube-side-actions">
              <button class="ghost mini" data-view-target="left"   type="button">Links</button>
              <button class="ghost mini" data-view-target="back"   type="button">Hinten</button>
              <button class="ghost mini" data-view-target="bottom" type="button">Unten</button>
              <button class="ghost mini" data-view-target="iso"    type="button">3D</button>
            </div>
          </div>

          <div class="viewer-legend">
            <div class="viewer-legend-title">Legende</div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-room"></span><span>Räume</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-shaft"></span><span>Schacht</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-corridor"></span><span>Flure</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-selected"></span><span>Ausgewählt</span></div>
            <div class="viewer-legend-divider"></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-route-hei"></span><span>HEI-System</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-route-lue"></span><span>LÜE-System</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-route-san"></span><span>SAN-System</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-route-active"></span><span>Gewählte Raumleitung</span></div>
            <div class="viewer-legend-row"><span class="legend-swatch legend-route-option"></span><span>Weitere Raumoptionen</span></div>
          </div>

          <div class="viewer-status-bar">
            <div id="viewer-mode-chip" class="viewer-chip">Räume hervorgehoben</div>
            <div id="section-status"   class="viewer-chip">0 Schnitte</div>
          </div>
        </div><!-- /viewer-canvas-wrap -->

        <!-- Untere Tabs -->
        <div class="viewer-bottom-tabs" id="viewer-bottom-tabs">
          <div class="bottom-resize-handle" id="bottom-resize-handle"></div>
          <div class="bottom-tabs-strip">
            <button class="bottom-tab-btn active" data-btab="btab-kpi">Trassen-KPIs</button>
            <button class="bottom-tab-btn"        data-btab="btab-explorer">Design Explorer</button>
          </div>
          <div class="bottom-tab-panels">

            <!-- Trassen-KPIs: zwei Spalten + Timing darunter -->
            <div id="btab-kpi" class="bottom-tab-panel active">
              <div class="kpi-split">
                <div class="kpi-split-col">
                  <div class="kpi-col-label">Systemmetriken</div>
                  <div class="kpi-list kpi-system" id="kpi-system-cards"></div>
                </div>
                <div class="kpi-split-divider"></div>
                <div class="kpi-split-col">
                  <div class="kpi-col-label">Trassenbewertung</div>
                  <div class="kpi-list kpi-route" id="kpi-route-cards"></div>
                </div>
              </div>
              <div class="kpi-timing-row">
                <div class="kpi-col-label">Zeitübersicht</div>
                <div id="timing-summary" class="timing-compact"></div>
              </div>
            </div>

            <!-- Design Explorer -->
            <div id="btab-explorer" class="bottom-tab-panel">
              <div class="design-explorer-shell">
                <div class="de-toolbar">
                  <div id="design-explorer-note" class="small muted"></div>
                </div>
                <div id="design-explorer-embed" class="design-explorer-embed-fill"></div>
              </div>
            </div>

          </div>
        </div>
      </section>

      <!-- ── Rechter Inspektor ─────────────────────── -->
      <aside class="inspector shell-panel" id="inspection-panel">
        <div class="panel-header collapsible-header">
          <span class="panel-header-title">Eigenschaften</span>
          <button id="toggle-inspection-panel" class="panel-collapse-button"
            data-shell-toggle="inspector" data-expanded-symbol="⟩" data-collapsed-symbol="⟨"
            type="button">⟩</button>
        </div>
        <div class="inspector-resize-handle" id="inspector-resize-handle"></div>

        <div class="panel-content stack" id="inspector-panel-content">

          <div class="panel-card">
            <div class="section-title">Trassierung und System</div>
            <div class="stack compact-stack">
              <div class="field"><label for="system-service-filter">Systemfilter</label><select id="system-service-filter"></select></div>
              <div class="field"><label for="system-strategy-select">Gesamtsystem-Strategie</label><select id="system-strategy-select"></select></div>
              <div class="button-row">
                <button id="apply-system-strategy-button" class="secondary" type="button" style="flex:1;">Auf System anwenden</button>
              </div>
              <div id="routing-selection-status" class="small muted route-helper-text">Raum auswählen, um Trassierungsoptionen anzuzeigen.</div>
              <div class="field"><label for="room-select">Raum</label><select id="room-select"></select></div>
              <div class="field"><label for="service-select">Gewerk</label><select id="service-select"></select></div>
              <div class="field"><label for="shaft-select">Schacht</label><select id="shaft-select"></select></div>
              <div class="field"><label for="strategy-select">Strategie</label><select id="strategy-select"></select></div>
              <div class="button-row">
                <button id="apply-button"  type="button"                   style="flex:1;">Raum anwenden</button>
                <button id="center-button" class="secondary" type="button" style="flex:1;">Zentrieren</button>
              </div>
            </div>
          </div>

          <div class="panel-card">
            <div class="section-title">Ausgewählter Raum</div>
            <div id="ifc-selection-meta" class="detail-list" style="margin-bottom:6px;">
              <div class="muted">Status</div><div>Kein IFC-Element ausgewählt</div>
            </div>
            <div id="room-detail" class="detail-list"></div>
            <div id="ifc-properties" style="display:none;"></div>
          </div>

          <div class="panel-card variant-card-dynamic" id="variant-card">
            <div class="section-title">Trassierungsvarianten</div>
            <div id="variant-panel-note" class="small muted" style="margin-bottom:8px;">Raum auswählen, um Trassierungsoptionen anzuzeigen.</div>
            <div id="variant-score-bars" class="stack compact-stack" style="margin-bottom:8px;"></div>
            <div class="variant-table-wrap variant-table-dynamic">
              <table class="route-table">
                <thead><tr>
                  <th>Schacht</th><th>Strategie</th>
                  <th>Bewertung <span class="score-info" title="Niedriger ist besser.">?</span></th>
                  <th>Länge (m)</th>
                </tr></thead>
                <tbody id="variant-table-body"></tbody>
              </table>
            </div>
          </div>

        </div>

        <div class="inspector-footer">
          <button id="isolate-button" class="secondary" type="button" style="flex:1;">Isolieren</button>
          <button type="button" style="flex:1;" onclick="document.getElementById('apply-button').click()">Variante anwenden</button>
        </div>
      </aside>

      <!-- Versteckter KPI-Behälter — systemPanel.js schreibt hier hinein -->
      <div id="kpi-cards" style="display:none;"></div>

    </div><!-- /app-shell -->
  `;

  requestAnimationFrame(() => {
    _initCollapseOverride();
    _initBottomTabs();
    _initResize();
    _initInspectorDynamic();
    _patchKpiCards();
    _patchTimingSummary();
    _hideDesignExplorerTable();
  });
}

/* ── Collapse fix: save/restore inline width on toggle ─── */
function _initCollapseOverride() {
  // Intercept in capture phase (before shellPanels.js bubble handler)
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-shell-toggle]');
    if (!btn) return;

    const shell = document.querySelector('.app-shell');
    if (!shell) return;

    const target      = btn.dataset.shellToggle;   // 'sidebar' | 'inspector'
    const collapseClass = `${target}-collapsed`;
    const propName    = target === 'sidebar' ? '--sidebar-width' : '--inspector-width';
    const isCollapsed = shell.classList.contains(collapseClass);

    if (!isCollapsed) {
      // About to collapse: save current inline value, then force to 40px
      _savedWidths[target] = shell.style.getPropertyValue(propName) || null;
      shell.style.setProperty(propName, '40px');
    } else {
      // About to expand: restore saved width (or remove inline so CSS default applies)
      const saved = _savedWidths[target];
      if (saved) {
        shell.style.setProperty(propName, saved);
      } else {
        shell.style.removeProperty(propName);
      }
    }
  }, true); // capture phase
}

/* ── Bottom tab switcher + Design Explorer auto-expand ── */
function _initBottomTabs() {
  const EXPLORE_H = Math.round(window.innerHeight * 0.57); // 52 vh — viewer bleibt sichtbar
  const NORMAL_H  = () => {
    const v = getComputedStyle(document.querySelector('.app-shell') || document.documentElement)
                .getPropertyValue('--bottom-h').trim();
    return parseInt(v) || 300;
  };

  const shell  = document.querySelector('.app-shell');
  const tabsEl = document.getElementById('viewer-bottom-tabs');

  document.querySelectorAll('.bottom-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.bottom-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.bottom-tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.btab)?.classList.add('active');

      const h = btn.dataset.btab === 'btab-explorer' ? EXPLORE_H : NORMAL_H();
      if (shell)  shell.style.setProperty('--bottom-h', h + 'px');
      if (tabsEl) tabsEl.style.height = h + 'px';
    });
  });
}

/* ── Resize handles ──────────────────────────────────── */
function _initResize() {
  const shell = document.querySelector('.app-shell');
  if (!shell) return;

  // Sidebar (left edge → right drag)
  _makeHorizDrag(
    document.getElementById('sidebar-resize-handle'),
    e => Math.max(200, Math.min(560, e.clientX)),
    w => { _savedWidths.sidebar = w + 'px'; shell.style.setProperty('--sidebar-width', w + 'px'); }
  );

  // Inspector (left edge of panel → left drag)
  _makeHorizDrag(
    document.getElementById('inspector-resize-handle'),
    e => Math.max(240, Math.min(620, window.innerWidth - e.clientX)),
    w => { _savedWidths.inspector = w + 'px'; shell.style.setProperty('--inspector-width', w + 'px'); }
  );

  // Bottom panel (top edge → up drag)
  _makeVertDrag(
    document.getElementById('bottom-resize-handle'),
    e => {
      const r = document.querySelector('.app-shell').getBoundingClientRect();
      return Math.max(80, Math.min(Math.round(window.innerHeight * 0.85), r.bottom - e.clientY));
    },
    h => {
      shell.style.setProperty('--bottom-h', h + 'px');
      const tabs = document.getElementById('viewer-bottom-tabs');
      if (tabs) tabs.style.height = h + 'px';
    }
  );
}

function _makeHorizDrag(handle, calcW, applyW) {
  if (!handle) return;
  let active = false;
  handle.addEventListener('mousedown', e => { active = true; e.preventDefault(); document.body.style.cursor = 'col-resize'; });
  window.addEventListener('mousemove', e => { if (active) applyW(calcW(e)); });
  window.addEventListener('mouseup',   () => { if (active) { active = false; document.body.style.cursor = ''; } });
}

function _makeVertDrag(handle, calcH, applyH) {
  if (!handle) return;
  let active = false;
  handle.addEventListener('mousedown', e => { active = true; e.preventDefault(); document.body.style.cursor = 'row-resize'; });
  window.addEventListener('mousemove', e => { if (active) applyH(calcH(e)); });
  window.addEventListener('mouseup',   () => { if (active) { active = false; document.body.style.cursor = ''; } });
}

/* ── Variant card dynamic height ───────────────────── */
function _initInspectorDynamic() {
  const content     = document.getElementById('inspector-panel-content');
  const variantCard = document.getElementById('variant-card');
  const tableWrap   = variantCard?.querySelector('.variant-table-dynamic');
  if (!content || !variantCard || !tableWrap) return;

  function recalc() {
    variantCard.style.flex = '1 1 0';
    requestAnimationFrame(() => {
      let siblingH = 0;
      Array.from(content.children).forEach(el => {
        if (el !== variantCard) siblingH += el.offsetHeight + 8;
      });
      const avail = Math.max(100, content.clientHeight - siblingH - 60);
      tableWrap.style.maxHeight = avail + 'px';
      tableWrap.style.overflowY = 'auto';
    });
  }

  recalc();
  window.addEventListener('resize', recalc);
  window._recalcVariantHeight = recalc;
}

/* ── KPI split: mirror hidden #kpi-cards to split cols ── */
function _patchKpiCards() {
  function attach() {
    const kpiEl = document.getElementById('kpi-cards');
    if (!kpiEl) { requestAnimationFrame(attach); return; }

    const obs = new MutationObserver(() => {
      const routeTarget  = document.getElementById('kpi-route-cards');
      const systemTarget = document.getElementById('kpi-system-cards');
      if (!routeTarget || !systemTarget) return;

      const children = Array.from(kpiEl.children);
      const groupIdx = children.findIndex(el => el.classList.contains('kpi-group-label'));
      const routeCards = groupIdx >= 0 ? children.slice(0, groupIdx) : children;
      const sysCards   = groupIdx >= 0 ? children.slice(groupIdx + 1) : [];

      routeTarget.innerHTML  = routeCards.map(c => c.outerHTML).join('');
      systemTarget.innerHTML = sysCards.map(c => c.outerHTML).join('');

      if (window._recalcVariantHeight) window._recalcVariantHeight();
    });

    obs.observe(kpiEl, { childList: true, subtree: true, characterData: true });
  }
  attach();
}

/* ── Timing summary: compact inline pill layout ──────── */
function _patchTimingSummary() {
  function attach() {
    const el = document.getElementById('timing-summary');
    if (!el) { requestAnimationFrame(attach); return; }

    const obs = new MutationObserver(() => {
      const raw = el.innerHTML;
      if (!raw.includes('<br>') && !raw.includes('&lt;')) return;

      // Parse each "Stage: 0.123 s" item into compact pills
      const lines = raw.split(/<br\s*\/?>/gi)
        .map(l => l.replace(/<[^>]+>/g, '').trim())
        .filter(Boolean);

      if (!lines.length) return;

      obs.disconnect(); // prevent loop
      el.innerHTML = lines
        .map(l => `<span class="timing-pill">${l}</span>`)
        .join('');
      obs.observe(el, { childList: true, subtree: true, characterData: true });
    });

    obs.observe(el, { childList: true, subtree: true, characterData: true });
  }
  attach();
}

/* ── Hide route-table inside Design Explorer ─────────── */
function _hideDesignExplorerTable() {
  function attach() {
    const embed = document.getElementById('design-explorer-embed');
    if (!embed) { requestAnimationFrame(attach); return; }

    const obs = new MutationObserver(() => {
      // Hide any full-width data table (not the parallel coords chart)
      embed.querySelectorAll('table.route-table, .de-table-wrap, .variant-table-wrap table').forEach(t => {
        t.closest('.variant-table-wrap, .de-table-wrap, table')?.style &&
          (t.style.display = 'none');
      });
    });
    obs.observe(embed, { childList: true, subtree: true });
  }
  attach();
}
