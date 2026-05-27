import { getDefaultDesignExplorerState } from "../../state/appState.js";
import {
  updateSectionStatus,
  updateRoomCenterButton,
  updateRoomLabelButton,
  updateViewerModeChip,
} from "../../layout/shellPanels.js";
import { setStatus } from "../../utils/dom.js";
import { escapeHtml } from "../../utils/format.js";

export function createProjectPanel(ctx) {
  const { state, apiGet } = ctx;

  const renderIfcSelection = (...args) => ctx.browser.renderIfcSelection(...args);
  const renderBrowser = (...args) => ctx.browser.renderBrowser(...args);
  const renderDesignExplorer = (...args) => ctx.explorer.renderDesignExplorer(...args);
  const renderTimingSummary = (...args) => ctx.system.renderTimingSummary(...args);
  const getAvailableServices = (...args) => ctx.system.getAvailableServices(...args);
  const setRoomRoutingControlsEnabled = (...args) => ctx.variants.setRoomRoutingControlsEnabled(...args);
  const resetRoomDrivenUi = (...args) => ctx.variants.resetRoomDrivenUi(...args);

async function tryLoadExistingSession() {
  try {
    const summary = await apiGet("/api/session/summary");
    if (!summary.loaded) {
      renderProjectPanel(summary);
      setStatus("Kein Projekt geladen. Bitte IFC und Excel auf der Hauptseite hochladen.");
      return;
    }

    await loadSummaryIntoUi(summary);
    try {
      const [allPayload, sysPayload] = await Promise.all([
        apiGet("/api/variants/all"),
        apiGet("/api/variants/system-overview"),
      ]);
      state.allVariantRows = allPayload.rows || [];
      state.systemOverviewRows = sysPayload.rows || [];
    } catch (_) {
      state.allVariantRows = [];
      state.systemOverviewRows = [];
    }
    renderDesignExplorer([]);
  } catch (error) {
    console.warn("No existing session", error);
  }
}

async function loadSummaryIntoUi(summary) {
  state.summary = summary;
  state.selectedRoomGuid = "";
  state.selectedService = "";
  state.selectedDemandId = "";
  state.selectedShaftGuid = "";
  state.selectedStrategy = "";
  state.selectedVariantRows = [];
  state.selectedVariantKey = "";
  state.designExplorer = getDefaultDesignExplorerState();
  state.viewer.setFloorDefinitions(summary.floors || []);
  renderProjectPanel(summary);
  setStatus(`${summary.ifc_name} geladen (BIM-Viewer bereit)`);
  await state.viewer.loadIfcFromUrl(summary.ifc_url);
  await state.viewer.setRoomCenters(summary.rooms || [], summary.shafts || []);
  state.viewer.setRoomCentersVisible(state.roomCentersVisible);
  state.viewer.setRoomLabelsVisible(state.roomLabelsVisible);

  populateSummaryControls();
  state.browserData = state.viewer.getBrowserData();
  renderBrowser();
  updateRoomCenterButton();
  updateRoomLabelButton();
  updateSectionStatus();
  updateViewerModeChip();
  renderTimingSummary();
  renderIfcSelection();
  resetRoomDrivenUi();
  if (ctx.updateWorkflowStepper) ctx.updateWorkflowStepper();
}

function renderProjectPanel(summary) {
  const container = document.getElementById("project-panel-meta");
  const note = document.getElementById("project-panel-note");
  if (!container) {
    return;
  }

  if (!summary?.loaded) {
  container.innerHTML = `
      <div class="muted">IFC</div><div>Not loaded</div>
      <div class="muted">Bedarfe</div><div>Not loaded</div>
      <div class="muted">Hinweis</div><div>Zur Hauptseite gehen, um Dateien hochzuladen oder zu ersetzen.</div>
    `;
    if (note) {
      note.textContent = "Das Vorprojekt verwendet das aktuell aktive Projekt der Hauptseite.";
    }
    return;
  }

  container.innerHTML = `
    <div class="muted">IFC</div><div>${escapeHtml(summary.ifc_name || "-")}</div>
    <div class="muted">Bedarfe</div><div>${escapeHtml(summary.excel_name || "-")}</div>
    <div class="muted">Geschosse</div><div>${escapeHtml(String((summary.floors || []).length))}</div>
    <div class="muted">Räume</div><div>${escapeHtml(String((summary.rooms || []).length))}</div>
    <div class="muted">Schächte</div><div>${escapeHtml(String((summary.shafts || []).length))}</div>
  `;
  if (note) {
    note.textContent = "Das Modell wurde bereits von der Hauptseite geladen. Diese Seite nur für Trassierung und Prüfung verwenden.";
  }
}

function populateSummaryControls() {
  const summary = state.summary;
  if (!summary || !summary.loaded) {
    return;
  }

  const roomSelect = document.getElementById("room-select");
  // Include shafts that appear as demand sources (shaft→technikraum)
  const demandSourceGuids = new Set((summary.demands || []).map((d) => d.room_guid));
  const shaftsWithDemands = (summary.shafts || []).filter((s) => demandSourceGuids.has(s.guid));
  const roomOptions = ['<option value="">Raum auswählen</option>']
    .concat(summary.rooms.map((room) => `<option value="${room.guid}">${escapeHtml(room.label)}</option>`))
    .concat(shaftsWithDemands.map((s) => `<option value="${s.guid}">${escapeHtml(s.label)} → Technikzentrale</option>`))
    .join("");
  roomSelect.innerHTML = roomOptions;

  const floorOptions = ['<option value="__all__">Alle Geschosse</option>']
    .concat(summary.floors.map((floor) => `<option value="${floor.name}">${escapeHtml(floor.name)}</option>`))
    .join("");
  document.getElementById("floor-select").innerHTML = floorOptions;

  const strategyOptions = summary.strategies
    .map((strategy) => `<option value="${strategy.name}">${escapeHtml(strategy.name)}</option>`)
    .join("");

  document.getElementById("strategy-select").innerHTML = `<option value="">Zuerst Raum auswählen</option>`;
  document.getElementById("system-strategy-select").innerHTML = strategyOptions;

  const availableServices = getAvailableServices();
  const systemServiceOptions = ['<option value="__all__">Alle Gewerke</option>']
    .concat(availableServices.map((service) => `<option value="${service}">${escapeHtml(service)}</option>`))
    .join("");
  document.getElementById("system-service-filter").innerHTML = systemServiceOptions;

  if (availableServices.includes(state.systemServiceFilter)) {
    document.getElementById("system-service-filter").value = state.systemServiceFilter;
  } else {
    state.systemServiceFilter = "__all__";
    document.getElementById("system-service-filter").value = "__all__";
  }

  state.systemStrategy = summary.strategies?.[0]?.name || "";
  document.getElementById("system-strategy-select").value = state.systemStrategy;
  document.getElementById("apply-system-strategy-button").disabled = !state.systemStrategy;
  setRoomRoutingControlsEnabled(false);
}


  return {
    tryLoadExistingSession,
    loadSummaryIntoUi,
    renderProjectPanel,
    populateSummaryControls,
  };
}
