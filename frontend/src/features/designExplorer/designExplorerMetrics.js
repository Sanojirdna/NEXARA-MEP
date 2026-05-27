import { getDefaultDesignExplorerState, state } from "../../state/appState.js";
import { formatMetricValue } from "../../utils/format.js";

export const DESIGN_EXPLORER_CATEGORY_DEFS = [
  {
    key: "identity",
    label: "Identity",
    metrics: [
      { key: "shaft_name", label: "Shaft", type: "text" },
      { key: "strategy", label: "Strategy", type: "text" },
    ],
  },
  {
    key: "performance",
    label: "Performance",
    metrics: [
      { key: "score", label: "Score", type: "number", digits: 2 },
      { key: "length_m", label: "Length [m]", type: "number", digits: 2 },
      { key: "shared_length_m", label: "Shared [m]", type: "number", digits: 2 },
    ],
  },
  {
    key: "geometry",
    label: "Geometry",
    metrics: [
      { key: "horizontal_length_m", label: "Horizontal [m]", type: "number", digits: 2 },
      { key: "vertical_length_m", label: "Vertical [m]", type: "number", digits: 2 },
      { key: "bend_count", label: "Bends", type: "number", digits: 0 },
    ],
  },
  {
    key: "crossings",
    label: "Crossings and zones",
    metrics: [
      { key: "wall_crossings", label: "Wall crossings", type: "number", digits: 0 },
      { key: "slab_crossings", label: "Slab crossings", type: "number", digits: 0 },
      { key: "corridor_steps", label: "Corridor steps", type: "number", digits: 0 },
      { key: "shaft_steps", label: "Shaft steps", type: "number", digits: 0 },
      { key: "room_steps", label: "Room steps", type: "number", digits: 0 },
    ],
  },
  {
    key: "quality",
    label: "Spatial quality",
    metrics: [
      { key: "mean_ceiling_score", label: "Ceiling score", type: "number", digits: 2 },
      { key: "mean_wall_distance", label: "Wall distance", type: "number", digits: 2 },
      { key: "mean_corridor_distance", label: "Corridor distance", type: "number", digits: 2 },
    ],
  },
];

export function getDesignExplorerMetricCatalog() {
  const allMetrics = [];
  for (const category of DESIGN_EXPLORER_CATEGORY_DEFS) {
    for (const metric of category.metrics) {
      allMetrics.push(metric);
    }
  }
  return allMetrics;
}

export function getDesignExplorerActiveCategories() {
  const selectedKeys = state.designExplorer?.categoryKeys || [];
  const active = [DESIGN_EXPLORER_CATEGORY_DEFS[0]];

  for (const category of DESIGN_EXPLORER_CATEGORY_DEFS.slice(1)) {
    if (selectedKeys.includes(category.key)) {
      active.push(category);
    }
  }

  return active;
}

export function getDesignExplorerActiveMetricDefs() {
  const seen = new Set();
  const result = [];

  for (const category of getDesignExplorerActiveCategories()) {
    for (const metric of category.metrics) {
      if (seen.has(metric.key)) {
        continue;
      }
      seen.add(metric.key);
      result.push(metric);
    }
  }

  return result;
}

export function getDesignExplorerNumericMetricDefs() {
  return getDesignExplorerActiveMetricDefs().filter((metric) => metric.type === "number");
}

export function ensureDesignExplorerState(rows) {
  if (!state.designExplorer) {
    state.designExplorer = getDefaultDesignExplorerState();
  }

  const strategies = new Set(["__all__"]);
  const shafts = new Set(["__all__"]);

  for (const row of rows) {
    strategies.add(String(row.strategy || ""));
    shafts.add(String(row.shaft_guid || ""));
  }

  if (!strategies.has(state.designExplorer.strategyFilter)) {
    state.designExplorer.strategyFilter = "__all__";
  }

  if (!shafts.has(state.designExplorer.shaftFilter)) {
    state.designExplorer.shaftFilter = "__all__";
  }

  const numericMetricDefs = getDesignExplorerNumericMetricDefs();
  const numericKeys = numericMetricDefs.map((metric) => metric.key);

  if (!numericKeys.includes(state.designExplorer.xMetricKey)) {
    state.designExplorer.xMetricKey = numericKeys[0] || "score";
  }

  const fallbackY = numericKeys.find((key) => key !== state.designExplorer.xMetricKey) || numericKeys[0] || "length_m";
  if (!numericKeys.includes(state.designExplorer.yMetricKey) || state.designExplorer.yMetricKey === state.designExplorer.xMetricKey) {
    state.designExplorer.yMetricKey = fallbackY;
  }

  const validColorModes = ["strategy", "shaft_name", "none"];
  if (!validColorModes.includes(state.designExplorer.colorBy)) {
    state.designExplorer.colorBy = "strategy";
  }
}

export function getVariantMetricValue(row, key) {
  if (!row) {
    return null;
  }

  if (row[key] !== undefined && row[key] !== null && row[key] !== "") {
    return row[key];
  }

  const metrics = row.metrics || {};
  if (metrics[key] !== undefined && metrics[key] !== null && metrics[key] !== "") {
    return metrics[key];
  }

  return null;
}

export function getVariantMetricLabel(key) {
  const metric = getDesignExplorerMetricCatalog().find((item) => item.key === key);
  return metric?.label || key;
}

export function getVariantDisplayValue(row, metricDef) {
  const value = getVariantMetricValue(row, metricDef.key);
  if (metricDef.type === "number") {
    return formatMetricValue(value, metricDef.digits ?? 2);
  }
  return String(value ?? "-");
}

export function getFilteredExplorerRows(rows) {
  return rows.filter((row) => {
    if (state.designExplorer.strategyFilter !== "__all__" && row.strategy !== state.designExplorer.strategyFilter) {
      return false;
    }
    if (state.designExplorer.shaftFilter !== "__all__" && row.shaft_guid !== state.designExplorer.shaftFilter) {
      return false;
    }
    return true;
  });
}

export function getRoomColor(row) {
  const palette = [
    "#0D47A1", "#00897B", "#F4511E", "#5E35B1",
    "#7CB342", "#6D4C41", "#039BE5", "#C62828",
    "#F9A825", "#00695C", "#AD1457", "#283593",
  ];
  const base = String(row.room_name || row.room_guid || "");
  let hash = 0;
  for (const ch of base) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
}

export function getVariantColor(row, mode) {
  if (mode === "none") {
    return "#0D47A1";
  }

  const palette = [
    "#0D47A1",
    "#00897B",
    "#F4511E",
    "#5E35B1",
    "#7CB342",
    "#6D4C41",
    "#039BE5",
    "#C62828",
  ];

  const baseValue = mode === "shaft_name" ? String(row.shaft_name || "") : String(row.strategy || "");
  let hash = 0;
  for (const character of baseValue) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return palette[hash % palette.length];
}
