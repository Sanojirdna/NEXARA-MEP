import { escapeHtml } from "../../utils/format.js";
import { getIfcFieldValue, renderIfcValue } from "./ifcBrowserValues.js";

export function createIfcBrowser(ctx) {
  const { state } = ctx;

  const getMatchedRoomForSelection = (...args) => ctx.rooms.getMatchedRoomForSelection(...args);

function renderIfcSelection() {
  const meta = document.getElementById("ifc-selection-meta");
  const properties = document.getElementById("ifc-properties");
  const selection = state.selectedIfcSelection;
  const selectedRoom = getMatchedRoomForSelection(selection);

  if (!selection && !selectedRoom) {
    meta.innerHTML = `<div class="muted">Status</div><div>Kein IFC-Element ausgewählt</div>`;
    properties.innerHTML = `<div class="small muted">IFC-Objekt im Viewer oder Baum auswählen, um dessen Daten zu prüfen.</div>`;
    return;
  }

  const label = selection?.label || selectedRoom?.label || "-";
  const category = selection?.category || selectedRoom?.space_type || "IfcSpace";
  const guid = selection?.guid || selectedRoom?.guid || "-";
  const modelId = selection?.modelId || "-";
  const localId = selection?.localId ?? "-";
  const ifcName = getIfcFieldValue(selection?.data, "Name") || selectedRoom?.name || "-";
  const ifcLongName = getIfcFieldValue(selection?.data, "LongName") || selectedRoom?.long_name || "-";

  meta.innerHTML = `
    <div class="muted">Label</div><div>${escapeHtml(label)}</div>
    <div class="muted">Type</div><div>${escapeHtml(category)}</div>
    <div class="muted">IFC Name</div><div>${escapeHtml(ifcName)}</div>
    <div class="muted">IFC LongName</div><div>${escapeHtml(ifcLongName)}</div>
    <div class="muted">GUID</div><div>${escapeHtml(guid)}</div>
    <div class="muted">Model</div><div>${escapeHtml(modelId)}</div>
    <div class="muted">Local ID</div><div>${escapeHtml(String(localId))}</div>
  `;

  const blocks = [];
  if (selectedRoom) {
    blocks.push(
      renderIfcValue("Raumdaten", {
        label: selectedRoom.label,
        name: selectedRoom.name,
        long_name: selectedRoom.long_name,
        floor_index: selectedRoom.floor_index,
        guid: selectedRoom.guid,
      }, true),
    );
  }

  if (selection?.data) {
    blocks.push(renderIfcValue("IFC-Daten", selection.data, blocks.length === 0));
  } else if (!blocks.length) {
    blocks.push(`<div class="small muted">Keine IFC-Daten für das ausgewählte Element gefunden.</div>`);
  }

  properties.innerHTML = blocks.join("");
}

function renderBrowser() {
  const container = document.getElementById("model-browser");
  const browserData = state.viewer ? state.viewer.getBrowserData() : state.browserData;
  const sourceNodes = state.browserTab === "structure" ? browserData.structure : browserData.categories;
  const filteredNodes = filterBrowserNodes(sourceNodes, state.browserSearch.trim().toLowerCase());

  if (!filteredNodes.length) {
    container.innerHTML = `<div class="small muted">Keine IFC-Knoten entsprechen der Suche.</div>`;
    return;
  }

  container.innerHTML = filteredNodes
    .map((node) => renderBrowserNode(node, 0))
    .join("");

  wireBrowserNodeEvents(container);
}

function filterBrowserNodes(nodes, searchText) {
  if (!searchText) {
    return nodes;
  }

  const filtered = [];
  for (const node of nodes) {
    const ownText = `${node.label || ""} ${node.category || ""}`.toLowerCase();
    const childMatches = filterBrowserNodes(node.children || [], searchText);
    if (ownText.includes(searchText) || childMatches.length) {
      filtered.push({
        ...node,
        children: childMatches,
      });
    }
  }

  return filtered;
}

function renderBrowserNode(node, depth) {
  const visible = state.viewer ? state.viewer.isBrowserNodeVisible(node.key) : true;
  const isSelected = node.key === state.selectedBrowserKey;
  const shouldOpen = depth < 2 || state.browserOpenKeys.has(node.key) || isSelected;
  const countBadge = Number.isFinite(node.itemCount) ? `<span class="browser-count">${node.itemCount}</span>` : "";
  const categoryText = node.category ? `<span class="browser-category">${escapeHtml(node.category)}</span>` : "";
  const rowHtml = `
    <div class="browser-row ${isSelected ? "selected" : ""}">
      <input class="browser-visibility" data-key="${node.key}" type="checkbox" ${visible ? "checked" : ""} />
      <button class="browser-label" data-key="${node.key}" type="button">${escapeHtml(node.label)} ${categoryText}</button>
      ${countBadge}
      <button class="browser-focus" data-key="${node.key}" type="button" title="Focus">⌖</button>
    </div>
  `;

  if (!node.children || !node.children.length) {
    return `<div class="browser-node leaf">${rowHtml}</div>`;
  }

  return `
    <details class="browser-node" data-key="${node.key}" ${shouldOpen ? "open" : ""}>
      <summary>${rowHtml}</summary>
      <div class="browser-children">
        ${node.children.map((child) => renderBrowserNode(child, depth + 1)).join("")}
      </div>
    </details>
  `;
}

function wireBrowserNodeEvents(container) {
  container.querySelectorAll(".browser-label").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const nodeKey = button.dataset.key;
      state.selectedBrowserKey = nodeKey;
      await state.viewer.selectBrowserNode(nodeKey);
      renderBrowser();
    });
  });

  container.querySelectorAll(".browser-focus").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const nodeKey = button.dataset.key;
      await state.viewer.focusBrowserNode(nodeKey);
    });
  });

  container.querySelectorAll(".browser-visibility").forEach((input) => {
    input.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    input.addEventListener("change", async (event) => {
      const nodeKey = input.dataset.key;
      await state.viewer.toggleBrowserNodeVisibility(nodeKey, event.target.checked);
      renderBrowser();
    });
  });

  container.querySelectorAll("details.browser-node").forEach((detail) => {
    detail.addEventListener("toggle", () => {
      const nodeKey = detail.dataset.key;
      if (detail.open) {
        state.browserOpenKeys.add(nodeKey);
      } else {
        state.browserOpenKeys.delete(nodeKey);
      }
    });
  });

  container.querySelectorAll("summary").forEach((summary) => {
    summary.addEventListener("click", (event) => {
      const target = event.target;
      if (
        target.closest(".browser-label") ||
        target.closest(".browser-focus") ||
        target.closest(".browser-visibility")
      ) {
        event.preventDefault();
      }
    });
  });
}


  return {
    renderIfcSelection,
    renderBrowser,
    filterBrowserNodes,
    renderBrowserNode,
    wireBrowserNodeEvents,
  };
}
