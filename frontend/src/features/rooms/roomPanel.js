import { updateViewerModeChip } from "../../layout/shellPanels.js";
import { setStatus } from "../../utils/dom.js";
import { escapeHtml } from "../../utils/format.js";

export function createRoomPanel(ctx) {
  const { state, apiGet } = ctx;

  const updateVariantState = (...args) => ctx.variants.updateVariantState(...args);
  const renderKpis = (...args) => ctx.system.renderKpis(...args);
  const setRoutingSelectionMessage = (...args) => ctx.variants.setRoutingSelectionMessage(...args);
  const setRoomRoutingControlsEnabled = (...args) => ctx.variants.setRoomRoutingControlsEnabled(...args);
  const clearVariantOutputs = (...args) => ctx.variants.clearVariantOutputs(...args);
  const renderSystemAndSelectionRoutes = (...args) => ctx.system.renderSystemAndSelectionRoutes(...args);
  const resetRoomDrivenUi = (...args) => ctx.variants.resetRoomDrivenUi(...args);

async function updateRoomState(syncViewerSelection = false) {
  if (!state.selectedRoomGuid) {
    resetRoomDrivenUi();
    return;
  }

  const detail = await apiGet(`/api/room/${state.selectedRoomGuid}`);
  renderRoomDetail(detail);

  const serviceSelect = document.getElementById("service-select");
  const serviceOptions = detail.demands.length
    ? detail.demands
        .map((demand) => `<option value="${demand.service}">${escapeHtml(demand.service)}</option>`)
        .join("")
    : `<option value="">Keine Bedarfe gefunden</option>`;
  serviceSelect.innerHTML = serviceOptions;

  if (detail.demands.length) {
    const keepCurrentService = detail.demands.some((demand) => demand.service === state.selectedService);
    state.selectedService = keepCurrentService ? state.selectedService : detail.demands[0].service;
    serviceSelect.value = state.selectedService;
    setRoutingSelectionMessage("Trassierungsoption für den gewählten Raum auswählen und auf das System anwenden.");
    setRoomRoutingControlsEnabled(true);
    await updateVariantState();
  } else {
    clearVariantOutputs("Dieser Raum hat keine Trassierungsbedarfe.");
    renderKpis(null, state.summary?.system);
    renderSystemAndSelectionRoutes();
  }

  if (syncViewerSelection) {
    state.ignoreNextViewerRoomPicked = true;
    await state.viewer.selectByGuid(state.selectedRoomGuid, false);
  }
}

function renderRoomDetail(detail) {
  const room = detail?.room || null;
  const demands = detail?.demands || [];

  if (!room) {
    document.getElementById("room-detail").innerHTML = `
      <div class="muted">Status</div><div>Kein Raum ausgewählt</div>
      <div class="muted">Hinweis</div><div>Raum im Viewer oder aus der Liste auswählen.</div>
    `;
    return;
  }

  const demandText = demands.length
    ? demands.map((demand) => `${demand.service} (${demand.kind || "demand"})`).join(", ")
    : "Keine Trassierungsbedarfe";

  document.getElementById("room-detail").innerHTML = `
    <div class="muted">Bezeichnung</div><div>${escapeHtml(room.label)}</div>
    <div class="muted">GUID</div><div>${escapeHtml(room.guid)}</div>
    <div class="muted">Geschoss</div><div>${escapeHtml(String(room.floor_index))}</div>
    <div class="muted">Gewerke</div><div>${escapeHtml(demandText)}</div>
  `;
}

function getMatchedRoomForSelection(selection) {
  if (!selection) {
    return null;
  }

  if (selection.room) {
    return selection.room;
  }

  if (selection.guid) {
    const allSpaces = [...(state.summary?.rooms || []), ...(state.summary?.shafts || [])];
    const matchedRoom = allSpaces.find((s) => s.guid === selection.guid);
    if (matchedRoom) {
      return matchedRoom;
    }
  }

  const selectionType = String(selection.category || "").toUpperCase();
  const looksLikeRoomSelection =
    selectionType.includes("SPACE") ||
    (!selection.guid && (selection.localId === 0 || selection.label === "Item #0"));

  if (looksLikeRoomSelection && state.selectedRoomGuid) {
    const allSpaces = [...(state.summary?.rooms || []), ...(state.summary?.shafts || [])];
    return allSpaces.find((s) => s.guid === state.selectedRoomGuid) || null;
  }

  return null;
}

function getSelectedRoom() {
  const rooms = state.summary?.rooms || [];
  const shafts = state.summary?.shafts || [];
  return [...rooms, ...shafts].find((s) => s.guid === state.selectedRoomGuid) || null;
}

function centerOnSelectedRoom() {
  const room = getSelectedRoom();
  if (room) {
    state.viewer.focusOnBBox(room.bbox);
  }
}

async function setViewerMode(mode) {
  state.viewerMode = mode;
  if (mode === "spaces") {
    await state.viewer.showSpacesOnly();
    setStatus("IfcSpaces-Ansicht mit blauen Raumüberlagerungen");
  } else {
    await state.viewer.showFullIfc();
    setStatus("Vollständige IFC-Ansicht mit blauen Raumüberlagerungen");
  }
  updateViewerModeChip();
}


  return {
    updateRoomState,
    renderRoomDetail,
    getMatchedRoomForSelection,
    getSelectedRoom,
    centerOnSelectedRoom,
    setViewerMode,
  };
}
