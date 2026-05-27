import { formatMetricValue, formatNumber, escapeHtml } from "../../utils/format.js";
import { getVariantColor } from "../designExplorer/designExplorerMetrics.js";

export const SYSTEM_METRIC_DEFS = [
  { key: "avg_score",           label: "Ø Bewertung",       type: "number", digits: 2 },
  { key: "total_length_m",      label: "Gesamt [m]",       type: "number", digits: 0 },
  { key: "total_horizontal_m",  label: "Horizontal [m]",  type: "number", digits: 0 },
  { key: "total_vertical_m",    label: "Vertikal [m]",    type: "number", digits: 0 },
  { key: "total_bends",         label: "Bögen",           type: "number", digits: 0 },
  { key: "total_wall_cross",    label: "Wand ✕",          type: "number", digits: 0 },
  { key: "total_slab_cross",    label: "Decke ✕",          type: "number", digits: 0 },
  { key: "total_shared_m",      label: "Geteilt [m]",      type: "number", digits: 0 },
  { key: "demand_coverage_pct", label: "Abdeckung [%]",    type: "number", digits: 1 },
];

export function createSystemPanel(ctx) {
  const { state } = ctx;

  const getSelectedVariantRow = (...args) => ctx.variants.getSelectedVariantRow(...args);

function renderSystemRowDetail(row) {
  if (!row) {
    return `
      <div class="de-empty-state" style="min-height:120px;">
        Click a line in the chart to inspect a strategy.
      </div>
    `;
  }
  const fmt = (v, d = 0) => formatMetricValue(v, d);
  const items = [
    ["Strategie",     row.strategy || "-"],
    ["Ø Bewertung",    fmt(row.avg_score, 2)],
    ["Gesamt [m]",    fmt(row.total_length_m)],
    ["Horizontal",   fmt(row.total_horizontal_m) + " m"],
    ["Vertikal",     fmt(row.total_vertical_m) + " m"],
    ["Bögen",        fmt(row.total_bends)],
    ["Wand ✕",       fmt(row.total_wall_cross)],
    ["Decke ✕",       fmt(row.total_slab_cross)],
    ["Geteilt [m]",   fmt(row.total_shared_m)],
    ["Abdeckung",     fmt(row.demand_coverage_pct, 1) + " %"],
    ["Bedarfe ok",   `${row.success_count || "-"} / ${row.demand_count || "-"}`],
  ];
  return `
    <div class="de-detail-title" style="color:${getVariantColor(row, 'strategy')};">▶ ${escapeHtml(row.strategy || "-")}</div>
    <div class="de-detail-list">
      ${items.map(([label, value]) => `
        <div class="muted">${escapeHtml(label)}</div>
        <div><strong>${escapeHtml(String(value))}</strong></div>
      `).join("")}
    </div>
  `;
}

function renderKpis(route, system) {
  const cards = document.getElementById("kpi-cards");
  const metrics = route?.metrics || route || {};
  const systemMetrics = system?.system_metrics || {};
  const activeServiceFilter =
    state.systemServiceFilter && state.systemServiceFilter !== "__all__" ? state.systemServiceFilter : "All";

  const routeItems = [
    ["Trassenbewertung", formatNumber(route?.score), "Niedriger ist besser. Gewichtete Summe aus Länge, Durchbrüchen und Bögen."],
    ["Länge (m)", formatNumber(metrics.length_m)],
    ["Bögen", formatNumber(metrics.bend_count)],
    ["Wanddurchbrüche", formatNumber(metrics.wall_crossings)],
    ["Vertikal (m)", formatNumber(metrics.vertical_length_m)],
    ["Geteilt (m)", formatNumber(metrics.shared_length_m)],
  ];

  const systemItems = [
    ["Filter", activeServiceFilter],
    ["Trassen ok", formatNumber(system?.success_count)],
    ["Gesamt (m)", formatNumber(systemMetrics.total_length_m)],
    ["Eindeutig (m)", formatNumber(systemMetrics.unique_length_m)],
    ["Geteilt (m)", formatNumber(systemMetrics.shared_length_m)],
    ["Fehlgeschlagen", formatNumber(system?.failed_count)],
  ];

  const makeCard = ([label, value, tooltip]) => `
    <div class="kpi-card">
      <div class="label">${escapeHtml(label)}${tooltip ? ` <span class="score-info" title="${escapeHtml(tooltip)}">?</span>` : ""}</div>
      <div class="value">${escapeHtml(value)}</div>
    </div>
  `;

  cards.innerHTML =
    routeItems.map(makeCard).join("") +
    `<div class="kpi-group-label">Systemmetriken</div>` +
    systemItems.map(makeCard).join("");
}

function renderTimingSummary() {
  const timingContainer = document.getElementById("timing-summary");
  const timings = state.summary?.timings?.timings || [];
  timingContainer.innerHTML = timings
    .map((item) => `${escapeHtml(item.stage || item.name)}: ${Number(item.seconds || 0).toFixed(3)} s`)
    .join("<br>");
}

function getServiceColor(service) {
  const key = String(service || "").trim().toUpperCase();

  if (key === "HEI") {
    return "#FF9800";
  }

  if (key === "LUE") {
    return "#00BCD4";
  }

  if (key === "SAN") {
    return "#E91E63";
  }

  return "#0D47A1";
}

function getSystemRoutes() {
  return state.summary?.system?.routes || [];
}

function getAvailableServices() {
  const serviceSet = new Set();

  for (const demand of state.summary?.demands || []) {
    const serviceKey = String(demand?.service || "").trim().toUpperCase();
    if (serviceKey) {
      serviceSet.add(serviceKey);
    }
  }

  return [...serviceSet].sort();
}

function renderSystemAndSelectionRoutes() {
  if (!state.viewer) {
    return;
  }

  const selectedRow = getSelectedVariantRow();
  const roomSelected = Boolean(state.selectedRoomGuid);

  if (roomSelected) {
    const hiddenDemandIds = [];
    if (selectedRow?.demand_id) {
      hiddenDemandIds.push(selectedRow.demand_id);
    }

    state.viewer.drawSystemNetwork(getSystemRoutes(), {
      serviceFilter: state.systemServiceFilter,
      hiddenDemandIds,
    });

    state.viewer.drawVariantRoutes(state.selectedVariantRows, state.selectedVariantKey, {
      optionColor: "#90A4AE",
    });

    if (selectedRow?.path_xyz?.length) {
      state.viewer.drawSystemRoute(selectedRow.path_xyz, getServiceColor(selectedRow.service));
    } else {
      state.viewer.drawSystemRoute([], "#00E676");
    }

    return;
  }

  const hiddenDemandIds = [];
  if (selectedRow?.demand_id) {
    hiddenDemandIds.push(selectedRow.demand_id);
  }

  state.viewer.drawSystemNetwork(getSystemRoutes(), {
    serviceFilter: state.systemServiceFilter,
    hiddenDemandIds,
  });
  state.viewer.drawVariantRoutes([], "", {
    optionColor: "#90A4AE",
  });
  state.viewer.drawSystemRoute([], "#00E676");
}


  return {
    renderSystemRowDetail,
    renderKpis,
    renderTimingSummary,
    getServiceColor,
    getSystemRoutes,
    getAvailableServices,
    renderSystemAndSelectionRoutes,
  };
}
