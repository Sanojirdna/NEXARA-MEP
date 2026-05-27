export function formatMetricValue(value, digits = 2) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  const numericValue = Number(value);
  if (Number.isFinite(numericValue)) {
    return numericValue.toFixed(digits);
  }

  return String(value);
}

export function formatNumber(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 2);
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
