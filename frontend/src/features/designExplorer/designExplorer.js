import { formatMetricValue, escapeHtml } from "../../utils/format.js";
import {
  DESIGN_EXPLORER_CATEGORY_DEFS,
  getDesignExplorerActiveMetricDefs,
  getDesignExplorerNumericMetricDefs,
  ensureDesignExplorerState,
  getVariantMetricValue,
  getVariantDisplayValue,
  getFilteredExplorerRows,
} from "./designExplorerMetrics.js";
import { mountParallelCoords } from "./parallelCoordinates.js";
import { SYSTEM_METRIC_DEFS } from "../routing/systemPanel.js";

export function createDesignExplorer(ctx) {
  const { state } = ctx;

  const renderSystemRowDetail = (...args) => ctx.system.renderSystemRowDetail(...args);
  const getSelectedVariantRow = (...args) => ctx.variants.getSelectedVariantRow(...args);
  const selectVariantRow = (...args) => ctx.variants.selectVariantRow(...args);
  const getSelectedRoom = (...args) => ctx.rooms.getSelectedRoom(...args);

function renderDesignExplorer(rows, options = {}) {
  const message = options.message || "";
  const note = document.getElementById("design-explorer-note");
  const container = document.getElementById("design-explorer-embed");

  const hasRoom = !!(state.selectedRoomGuid && state.selectedService && state.selectedDemandId);
  if (!hasRoom) state.deViewMode = "all";
  const isAllMode = state.deViewMode === "all";
  const sourceRows = isAllMode ? (state.systemOverviewRows || []) : rows;
  const successfulRows = isAllMode
    ? sourceRows  // system overview rows are pre-filtered
    : sourceRows.filter(
        (row) => row.success === true || row.success === 1 || row.success === "True"
      );
  if (!successfulRows.length) {
    container.innerHTML = `
      <div class="variant-empty-state">
        ${escapeHtml(message || (isAllMode
          ? "Noch keine Varianten verfügbar. Zuerst ein Projekt laden."
          : "Keine erfolgreichen Varianten für diesen Raum und dieses Gewerk."))}
      </div>
    `;
    note.textContent = isAllMode
      ? "Projekt laden, um alle Trassenvarianten hier zu sehen."
      : "Nur erfolgreiche Varianten werden angezeigt.";
    return;
  }

  ensureDesignExplorerState(successfulRows);
  const filteredRows = getFilteredExplorerRows(successfulRows);
  const room = getSelectedRoom();
  const roomLabel = room?.label || state.selectedRoomGuid;
  note.innerHTML = isAllMode
    ? `System overview &mdash; comparing <strong>${escapeHtml(String(successfulRows.length))}</strong> strategies across the whole building.
       ${hasRoom
         ? `<button id="de-toggle-mode" style="margin-left:12px;padding:2px 10px;border:1px solid #555;border-radius:4px;background:#222;color:#bbb;cursor:pointer;font-size:11px;">Show this room only</button>`
         : ""}`
    : `Room <strong>${escapeHtml(roomLabel)}</strong> &middot;
       service <strong>${escapeHtml(state.selectedService)}</strong> &middot;
       <strong>${escapeHtml(String(successfulRows.length))}</strong> variants.
       <button id="de-toggle-mode" style="margin-left:12px;padding:2px 10px;border:1px solid #555;border-radius:4px;background:#222;color:#bbb;cursor:pointer;font-size:11px;">Show all rooms</button>`;

  const activeMetricDefs = getDesignExplorerActiveMetricDefs();
  const numericMetricDefs = getDesignExplorerNumericMetricDefs();
  const strategyOptions = ["<option value=\"__all__\">All strategies</option>"]
    .concat(
      [...new Set(successfulRows.map((row) => String(row.strategy || "")))]
        .sort()
        .map((strategy) => `<option value="${escapeHtml(strategy)}">${escapeHtml(strategy)}</option>`)
    )
    .join("");

  const shaftOptions = ["<option value=\"__all__\">All shafts</option>"]
    .concat(
      successfulRows
        .map((row) => ({ guid: String(row.shaft_guid || ""), label: String(row.shaft_name || "-") }))
        .filter((item, index, list) => list.findIndex((entry) => entry.guid === item.guid) === index)
        .sort((left, right) => left.label.localeCompare(right.label))
        .map((shaft) => `<option value="${escapeHtml(shaft.guid)}">${escapeHtml(shaft.label)}</option>`)
    )
    .join("");

  const roomControlsHtml = isAllMode ? "" : `
        <div class="de-field-block">
          <div class="de-label">Categories</div>
          <div class="de-category-list">
            ${DESIGN_EXPLORER_CATEGORY_DEFS.slice(1)
              .map((category) => {
                const active = state.designExplorer.categoryKeys.includes(category.key) ? "active" : "";
                return '<button class="de-category-chip ' + active + '" type="button" data-de-category="' + escapeHtml(category.key) + '">' + escapeHtml(category.label) + '</button>';
              })
              .join("")}
          </div>
        </div>
        <div class="de-grid">
          <label class="de-field">
            <span>Color</span>
            <select id="de-color-mode">
              <option value="strategy">Strategy</option>
              <option value="shaft_name">Shaft</option>
              <option value="none">Single color</option>
            </select>
          </label>
          <label class="de-field">
            <span>Strategy filter</span>
            <select id="de-strategy-filter">${strategyOptions}</select>
          </label>
          <label class="de-field">
            <span>Shaft filter</span>
            <select id="de-shaft-filter">${shaftOptions}</select>
          </label>
          <div class="de-field de-summary-box">
            <span>Visible variants</span>
            <strong>${escapeHtml(String(filteredRows.length))}</strong>
          </div>
        </div>
  `;

  container.innerHTML = `
    <div class="de-panel">
      <div class="de-controls">
        ${roomControlsHtml}
      </div>

      <div class="de-body">
        <div class="de-chart-card">
          ${renderDesignExplorerScatter(filteredRows, state.designExplorer.colorBy)}
        </div>
        <div class="de-detail-card" id="de-detail-card">
          ${isAllMode ? renderSystemRowDetail(state.selectedSystemRow) : renderDesignExplorerDetail(getSelectedVariantRow())}
        </div>
      </div>

      <div class="de-table-card">
        ${renderDesignExplorerTable(filteredRows, isAllMode ? SYSTEM_METRIC_DEFS : activeMetricDefs, isAllMode)}
      </div>
    </div>
  `;

  const activeMetrics = state.deViewMode === "all"
    ? SYSTEM_METRIC_DEFS
    : getDesignExplorerNumericMetricDefs();
  mountParallelCoords(ctx, 
    filteredRows,
    activeMetrics,
    state.deViewMode === "all" ? "strategy" : state.designExplorer.colorBy,
    false  // never color-by-room in system mode
  );

  const colorModeSelect = document.getElementById("de-color-mode");
  const strategyFilterSelect = document.getElementById("de-strategy-filter");
  const shaftFilterSelect = document.getElementById("de-shaft-filter");

  if (colorModeSelect) {
    colorModeSelect.value = state.designExplorer.colorBy;
    colorModeSelect.addEventListener("change", (event) => {
      state.designExplorer.colorBy = event.target.value || "strategy";
      renderDesignExplorer(state.selectedVariantRows || []);
    });
  }

  if (strategyFilterSelect) {
    strategyFilterSelect.value = state.designExplorer.strategyFilter;
    strategyFilterSelect.addEventListener("change", (event) => {
      state.designExplorer.strategyFilter = event.target.value || "__all__";
      renderDesignExplorer(state.selectedVariantRows || []);
    });
  }

  if (shaftFilterSelect) {
    shaftFilterSelect.value = state.designExplorer.shaftFilter;
    shaftFilterSelect.addEventListener("change", (event) => {
      state.designExplorer.shaftFilter = event.target.value || "__all__";
      renderDesignExplorer(state.selectedVariantRows || []);
    });
  }

  const toggleModeBtn = document.getElementById("de-toggle-mode");
  if (toggleModeBtn) {
    toggleModeBtn.addEventListener("click", () => {
      state.deViewMode = state.deViewMode === "all" ? "room" : "all";
      renderDesignExplorer(state.selectedVariantRows || []);
    });
  }

  container.querySelectorAll("[data-de-category]").forEach((button) => {
    button.addEventListener("click", () => {
      const categoryKey = button.dataset.deCategory;
      const keys = new Set(state.designExplorer.categoryKeys || []);
      if (keys.has(categoryKey)) {
        keys.delete(categoryKey);
      } else {
        keys.add(categoryKey);
      }

      if (!keys.size) {
        keys.add("performance");
      }

      state.designExplorer.categoryKeys = [...keys];
      renderDesignExplorer(state.selectedVariantRows || []);
    });
  });

  container.querySelectorAll("[data-variant-key]").forEach((element) => {
    element.addEventListener("click", () => {
      const key = element.dataset.variantKey || "";
      const row = state.selectedVariantRows.find((item) => `${item.shaft_guid}|${item.strategy}` === key);
      if (!row) {
        return;
      }
      selectVariantRow(row, true);
    });
  });
}

function renderDesignExplorerDetail(row) {
  if (!row) {
    return `
      <div class="de-empty-state">
        Eine Variante in der Tabelle oder im Diagramm auswählen, um ihre Werte zu prüfen.
      </div>
    `;
  }

  const detailItems = [
    ["Schacht", row.shaft_name || "-"],
    ["Strategie", row.strategy || "-"],
    ["Bewertung", formatMetricValue(getVariantMetricValue(row, "score"), 2)],
    ["Länge [m]", formatMetricValue(getVariantMetricValue(row, "length_m"), 2)],
    ["Vertikal [m]", formatMetricValue(getVariantMetricValue(row, "vertical_length_m"), 2)],
    ["Bögen", formatMetricValue(getVariantMetricValue(row, "bend_count"), 0)],
    ["Wanddurchbrüche", formatMetricValue(getVariantMetricValue(row, "wall_crossings"), 0)],
    ["Geteilt [m]", formatMetricValue(getVariantMetricValue(row, "shared_length_m"), 2)],
  ];

  return `
    <div class="de-detail-title">Selected variant</div>
    <div class="de-detail-list">
      ${detailItems
        .map(([label, value]) => `
          <div class="muted">${escapeHtml(label)}</div>
          <div>${escapeHtml(String(value))}</div>
        `)
        .join("")}
    </div>
    <div class="small muted de-detail-hint">
      Im Raumbereich „Anwenden" drücken, um diese Variante als Backend-Auswahl zu speichern.
    </div>
  `;
}

function renderDesignExplorerTable(rows, metricDefs, isSystemMode = false) {
  if (!rows.length) {
    return `
      <div class="de-empty-state">
        No variants match the current Design Explorer filters.
      </div>
    `;
  }

  const scoreKey = isSystemMode ? "avg_score" : "score";
  const orderedRows = [...rows].sort((left, right) => {
    const leftScore = Number(getVariantMetricValue(left, scoreKey) || 0);
    const rightScore = Number(getVariantMetricValue(right, scoreKey) || 0);
    return leftScore - rightScore;
  });

  const columns = metricDefs.filter((metric) => metric.key !== "shaft_name" && metric.key !== "strategy");

  return `
    <div class="de-table-wrap">
      <table class="de-table">
        <thead>
          <tr>
            <th>Variant</th>
            ${columns.map((metric) => `<th>${escapeHtml(metric.label)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${orderedRows
            .map((row) => {
              const key = `${row.shaft_guid}|${row.strategy}`;
              const activeClass = key === state.selectedVariantKey ? "active" : "";
              const label = isSystemMode
                ? (row.strategy || "-")
                : `${row.shaft_name || "-"} | ${row.strategy || "-"}`;
              return `
                <tr class="${activeClass}" data-variant-key="${key}">
                  <td>${escapeHtml(label)}</td>
                  ${columns
                    .map((metric) => `<td>${escapeHtml(getVariantDisplayValue(row, metric))}</td>`)
                    .join("")}
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDesignExplorerScatter(rows, colorBy) {
  if (!rows.length) {
    return `<div class="de-empty-state">Keine Varianten entsprechen den aktuellen Filtern.</div>`;
  }
  return `
    <div class="de-chart-title">Parallel Coordinates</div>
    <div id="pc-mount" style="overflow-x:auto;"></div>
    <div class="de-legend" id="pc-legend"></div>
  `;
}


  return {
    renderDesignExplorer,
    renderDesignExplorerDetail,
    renderDesignExplorerTable,
    renderDesignExplorerScatter,
  };
}
