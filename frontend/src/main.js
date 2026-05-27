import { apiGet, apiPost } from "./api.js";
import { PipePlannerViewer } from "./features/viewer/viewer.js";
import { state } from "./state/appState.js";
import { createLayout } from "./layout/createLayout.js";
import {
  wireShellCollapses,
  wireViewerOverlayPanels,
  updateSectionStatus,
  updateRoomCenterButton,
  updateRoomLabelButton,
  updateBrowserTabs,
} from "./layout/shellPanels.js";
import { setStatus } from "./utils/dom.js";

import { createProjectPanel } from "./features/project/projectPanel.js";
import { createRoomPanel } from "./features/rooms/roomPanel.js";
import { createIfcBrowser } from "./features/browser/ifcBrowser.js";
import { createVariantPanel } from "./features/routing/variantPanel.js";
import { createSystemPanel } from "./features/routing/systemPanel.js";
import { createDesignExplorer } from "./features/designExplorer/designExplorer.js";


async function init() {
  createLayout();

  const ctx = {
    state,
    apiGet,
    apiPost,
    viewer: null,
    project: null,
    rooms: null,
    browser: null,
    variants: null,
    system: null,
    explorer: null,
  };

  const viewerContainer = document.getElementById("viewer");
  const viewer = new PipePlannerViewer(viewerContainer, {
    onRoomPicked: async (roomGuid) => {
      const knownRooms = state.summary?.rooms || [];
      const knownShafts = state.summary?.shafts || [];
      const isKnown = [...knownRooms, ...knownShafts].some((s) => s.guid === roomGuid);
      if (!roomGuid || !isKnown) {
        return;
      }

      if (state.ignoreNextViewerRoomPicked && state.selectedRoomGuid === roomGuid) {
        state.ignoreNextViewerRoomPicked = false;
        return;
      }

      state.selectedRoomGuid = roomGuid;
      document.getElementById("room-select").value = roomGuid;
      await ctx.rooms.updateRoomState(false);
      if (ctx.updateWorkflowStepper) ctx.updateWorkflowStepper();
    },
    onSelectionChanged: (selection) => {
      state.selectedIfcSelection = selection;
      state.selectedBrowserKey = selection?.nodeKey || "";
      for (const pathKey of selection?.pathKeys || []) {
        state.browserOpenKeys.add(pathKey);
      }
      ctx.browser.renderIfcSelection();
      ctx.browser.renderBrowser();
    },
  });

  state.viewer = viewer;
  ctx.viewer = viewer;

  ctx.project = createProjectPanel(ctx);
  ctx.rooms = createRoomPanel(ctx);
  ctx.browser = createIfcBrowser(ctx);
  ctx.variants = createVariantPanel(ctx);
  ctx.system = createSystemPanel(ctx);
  ctx.explorer = createDesignExplorer(ctx);

  await viewer.init();

  wireEvents(ctx);
  ctx.browser.renderBrowser();
  ctx.browser.renderIfcSelection();
  updateRoomCenterButton();
  updateRoomLabelButton();
  ctx.project.tryLoadExistingSession();
}

function wireEvents(ctx) {
  const { state, apiGet, apiPost } = ctx;

  const updateRoomState = (...args) => ctx.rooms.updateRoomState(...args);
  const renderSystemAndSelectionRoutes = (...args) => ctx.system.renderSystemAndSelectionRoutes(...args);
  const renderKpis = (...args) => ctx.system.renderKpis(...args);
  const getSelectedVariantRow = (...args) => ctx.variants.getSelectedVariantRow(...args);
  const updateVariantState = (...args) => ctx.variants.updateVariantState(...args);
  const syncSelectedVariantFromControls = (...args) => ctx.variants.syncSelectedVariantFromControls(...args);
  const centerOnSelectedRoom = (...args) => ctx.rooms.centerOnSelectedRoom(...args);
  const setViewerMode = (...args) => ctx.rooms.setViewerMode(...args);
  const renderBrowser = (...args) => ctx.browser.renderBrowser(...args);

  function updateWorkflowStepper() {
    const step1 = document.getElementById("step-1");
    const step2 = document.getElementById("step-2");
    const step3 = document.getElementById("step-3");
    const step4 = document.getElementById("step-4");
    const hint = document.getElementById("viewer-empty-hint");

    const hasModel = !!state.summary;
    const hasRoom = !!state.selectedRoomGuid;
    const hasVariant = !!state.selectedVariantKey;

    // Step 1: Load — done if model is loaded
    if (step1) { step1.className = "workflow-step " + (hasModel ? "done" : "active"); }
    // Step 2: Select room
    if (step2) { step2.className = "workflow-step " + (hasRoom ? "done" : hasModel ? "active" : ""); }
    // Step 3: Pick route
    if (step3) { step3.className = "workflow-step " + (hasVariant ? "done" : hasRoom ? "active" : ""); }
    // Step 4: Export
    if (step4) { step4.className = "workflow-step " + (hasVariant ? "active" : ""); }

    // Hide hint when room is selected
    if (hint) { hint.classList.toggle("visible", !hasRoom); }
  }

  // Expose so other handlers can call it
  ctx.updateWorkflowStepper = updateWorkflowStepper;

  document.getElementById("room-select").addEventListener("change", async (event) => {
    state.selectedRoomGuid = event.target.value;
    await updateRoomState(true);
    updateWorkflowStepper();
  });

  document.getElementById("system-service-filter").addEventListener("change", (event) => {
    state.systemServiceFilter = event.target.value || "__all__";
    renderSystemAndSelectionRoutes();
    renderKpis(getSelectedVariantRow(), state.summary?.system);
  });

  document.getElementById("system-strategy-select").addEventListener("change", (event) => {
    state.systemStrategy = event.target.value || "";
    document.getElementById("apply-system-strategy-button").disabled = !state.systemStrategy;
  });

  document.getElementById("apply-system-strategy-button").addEventListener("click", async () => {
    if (!state.systemStrategy) {
      return;
    }

    setStatus(`${state.systemStrategy} wird auf das gesamte System angewendet…`);
    const payload = await apiPost("/api/selection/strategy-all", {
      strategy: state.systemStrategy,
    });

    if (payload.system) {
      if (!state.summary) {
        state.summary = {};
      }
      state.summary.system = payload.system;
      renderKpis(getSelectedVariantRow(), payload.system);
      renderSystemAndSelectionRoutes();
      setStatus(`${state.systemStrategy} auf ${payload.changed_count || 0} Bedarfe angewendet`);
    }

    if (state.selectedRoomGuid && state.selectedService) {
      await updateVariantState();
    }
  });

  document.getElementById("service-select").addEventListener("change", async (event) => {
    state.selectedService = event.target.value;
    await updateVariantState();
  });

  document.getElementById("shaft-select").addEventListener("change", (event) => {
    state.selectedShaftGuid = event.target.value;
    syncSelectedVariantFromControls();
  });

  document.getElementById("strategy-select").addEventListener("change", (event) => {
    state.selectedStrategy = event.target.value;
    syncSelectedVariantFromControls();
  });

  document.getElementById("apply-button").addEventListener("click", async () => {
    if (!state.selectedDemandId || !state.selectedShaftGuid || !state.selectedStrategy) {
      return;
    }

    const payload = await apiPost("/api/selection", {
      demand_id: state.selectedDemandId,
      shaft_guid: state.selectedShaftGuid,
      strategy: state.selectedStrategy,
    });

    if (payload.system) {
      if (!state.summary) {
        state.summary = {};
      }
      state.summary.system = payload.system;
    }

    setStatus("Raumtrassierung auf das Backend-System angewendet");
    await updateVariantState();
    updateWorkflowStepper();
  });

  document.getElementById("export-routing-ifc-button").addEventListener("click", async () => {
    const btn = document.getElementById("export-routing-ifc-button");
    const statusEl = document.getElementById("export-ifc-status");

    btn.disabled = true;
    btn.textContent = "Größen werden berechnet…";
    statusEl.style.display = "";
    statusEl.textContent = "HEI / LÜE / SAN aus aktiven Trassen dimensionieren…";

    try {
      const response = await fetch("/api/session/export-routing-ifc");

      if (!response.ok) {
        const err = await response.json().catch(() => ({ message: response.statusText }));
        throw new Error(err.message || "Export failed");
      }

      statusEl.textContent = "IFC-Datei wird erstellt…";

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : "routing_volumes.ifc";

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      const routeCount = state.summary?.system?.success_count ?? "?";
      statusEl.textContent = `Fertig — ${routeCount} aktive Trassen exportiert.`;
      setStatus(`Trassierungs-IFC heruntergeladen: ${filename}`);
    } catch (err) {
      statusEl.textContent = `Fehler: ${err.message}`;
      setStatus(`IFC-Export fehlgeschlagen: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "&#11015; Trassierungs-IFC exportieren";
    }
  });

  document.getElementById("center-button").addEventListener("click", () => centerOnSelectedRoom());
  document.getElementById("focus-route-button").addEventListener("click", () => centerOnSelectedRoom());

  document.getElementById("spaces-only-button").addEventListener("click", async () => {
    await setViewerMode("spaces");
  });

  document.getElementById("full-ifc-button").addEventListener("click", async () => {
    await setViewerMode("full");
  });

  document.getElementById("hide-selected-button").addEventListener("click", async () => {
    await state.viewer.hideSelectedItem();
    setStatus("Ausgewähltes IFC-Element ausgeblendet");
    renderBrowser();
  });

  document.getElementById("reset-hidden-button").addEventListener("click", async () => {
    await state.viewer.resetHiddenItems();
    setStatus("Alle ausgeblendeten IFC-Elemente wiederhergestellt");
    renderBrowser();
  });

  document.getElementById("floor-select").addEventListener("change", async (event) => {
    const floorName = event.target.value;
    await state.viewer.isolateFloor(floorName);
    renderSystemAndSelectionRoutes();
  });

  document.getElementById("reset-view-button").addEventListener("click", async () => {
    document.getElementById("floor-select").value = "__all__";
    await state.viewer.isolateFloor("__all__");
    renderSystemAndSelectionRoutes();
  });

  document.getElementById("toggle-room-centers-button").addEventListener("click", () => {
    state.roomCentersVisible = !state.roomCentersVisible;
    state.viewer.setRoomCentersVisible(state.roomCentersVisible);
    updateRoomCenterButton();
  });

  document.getElementById("toggle-room-labels-button").addEventListener("click", () => {
    state.roomLabelsVisible = !state.roomLabelsVisible;
    state.viewer.setRoomLabelsVisible(state.roomLabelsVisible);
    updateRoomLabelButton();
  });

  document.getElementById("section-pick-button").addEventListener("click", async () => {
    await state.viewer.addSectionCut("pick");
    updateSectionStatus();
  });

  document.getElementById("section-horizontal-button").addEventListener("click", async () => {
    await state.viewer.addSectionCut("horizontal");
    updateSectionStatus();
  });

  document.getElementById("section-front-button").addEventListener("click", async () => {
    await state.viewer.addSectionCut("front");
    updateSectionStatus();
  });

  document.getElementById("section-right-button").addEventListener("click", async () => {
    await state.viewer.addSectionCut("right");
    updateSectionStatus();
  });

  document.getElementById("section-delete-button").addEventListener("click", async () => {
    await state.viewer.deleteLastSectionCut();
    updateSectionStatus();
  });

  document.getElementById("section-clear-button").addEventListener("click", () => {
    state.viewer.clearSectionCuts();
    updateSectionStatus();
  });

  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const viewName = button.dataset.viewTarget;
      await state.viewer.setView(viewName);
    });
  });

  document.getElementById("browser-tab-structure").addEventListener("click", () => {
    state.browserTab = "structure";
    updateBrowserTabs();
    renderBrowser();
  });

  document.getElementById("browser-tab-categories").addEventListener("click", () => {
    state.browserTab = "categories";
    updateBrowserTabs();
    renderBrowser();
  });

  document.getElementById("browser-search").addEventListener("input", (event) => {
    state.browserSearch = event.target.value || "";
    renderBrowser();
  });

  wireShellCollapses();
  wireViewerOverlayPanels();
}

init().catch((error) => {
  console.error(error);
});
