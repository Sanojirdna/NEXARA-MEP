import { escapeHtml } from "../../utils/format.js";

export function getIfcFieldValue(source, key) {
  if (!source || typeof source !== "object") {
    return "";
  }

  const normalizedKey = String(key || "").replace(/^_+/, "");
  const candidateKeys = [
    normalizedKey,
    `_${normalizedKey}`,
    normalizedKey.toLowerCase(),
    `_${normalizedKey.toLowerCase()}`,
  ];

  for (const candidateKey of candidateKeys) {
    if (!(candidateKey in source)) {
      continue;
    }

    const rawValue = source[candidateKey];
    if (rawValue && typeof rawValue === "object" && "value" in rawValue) {
      return rawValue.value === null || rawValue.value === undefined ? "" : String(rawValue.value);
    }

    if (rawValue !== null && rawValue !== undefined && typeof rawValue !== "object") {
      return String(rawValue);
    }
  }

  return "";
}

export function renderIfcValue(label, value, startOpen = false) {
  if (value === null || value === undefined) {
    return `
      <div class="ifc-leaf">
        <span class="ifc-key">${escapeHtml(label)}</span>
        <span class="ifc-value">-</span>
      </div>
    `;
  }

  if (Array.isArray(value)) {
    const itemsHtml = value.length
      ? value.map((item, index) => renderIfcValue(`${label} [${index}]`, item)).join("")
      : `<div class="ifc-leaf"><span class="ifc-key">Empty</span><span class="ifc-value">[]</span></div>`;

    return `
      <details class="ifc-group" ${startOpen ? "open" : ""}>
        <summary>${escapeHtml(label)} <span class="muted">[${value.length}]</span></summary>
        <div class="ifc-children">${itemsHtml}</div>
      </details>
    `;
  }

  if (typeof value === "object") {
    if ("value" in value && Object.keys(value).length <= 2) {
      return `
        <div class="ifc-leaf">
          <span class="ifc-key">${escapeHtml(label)}</span>
          <span class="ifc-value">${escapeHtml(String(value.value))}</span>
        </div>
      `;
    }

    const childrenHtml = Object.entries(value)
      .map(([key, childValue]) => renderIfcValue(key, childValue))
      .join("");

    return `
      <details class="ifc-group" ${startOpen ? "open" : ""}>
        <summary>${escapeHtml(label)}</summary>
        <div class="ifc-children">${childrenHtml}</div>
      </details>
    `;
  }

  return `
    <div class="ifc-leaf">
      <span class="ifc-key">${escapeHtml(label)}</span>
      <span class="ifc-value">${escapeHtml(String(value))}</span>
    </div>
  `;
}
