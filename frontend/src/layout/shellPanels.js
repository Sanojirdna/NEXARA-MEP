import { state } from "../state/appState.js";

export function wireShellCollapses() {
  document.querySelectorAll("[data-shell-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.shellToggle;
      const shell = document.querySelector(".app-shell");
      const className = `${target}-collapsed`;
      shell.classList.toggle(className);
      syncShellCollapseButtons();
    });
  });

  document.querySelectorAll("[data-bottom-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const panelId = button.dataset.bottomToggle;
      document.getElementById(panelId)?.classList.toggle("collapsed");
      syncBottomCollapseButtons();
    });
  });

  syncShellCollapseButtons();
  syncBottomCollapseButtons();
}

export function syncShellCollapseButtons() {
  const shell = document.querySelector(".app-shell");
  document.querySelectorAll("[data-shell-toggle]").forEach((button) => {
    const target = button.dataset.shellToggle;
    const collapsed = shell.classList.contains(`${target}-collapsed`);
    button.textContent = collapsed ? button.dataset.collapsedSymbol || "+" : button.dataset.expandedSymbol || "–";
    button.setAttribute("aria-expanded", String(!collapsed));
  });
}

export function syncBottomCollapseButtons() {
  let expandedCount = 0;

  document.querySelectorAll("[data-bottom-toggle]").forEach((button) => {
    const panelId = button.dataset.bottomToggle;
    const collapsed = document.getElementById(panelId)?.classList.contains("collapsed");
    if (!collapsed) {
      expandedCount += 1;
    }
    button.textContent = collapsed ? button.dataset.collapsedSymbol || "▴" : button.dataset.expandedSymbol || "▾";
    button.setAttribute("aria-expanded", String(!collapsed));
  });

  document.querySelector(".app-shell")?.classList.toggle("bottom-panels-collapsed", expandedCount === 0);
}

export function wireViewerOverlayPanels() {
  document.querySelectorAll("[data-viewer-panel]").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = document.getElementById(button.dataset.viewerPanel);
      panel?.classList.toggle("collapsed");
      syncViewerOverlayButtons();
    });
  });

  syncViewerOverlayButtons();
}

export function syncViewerOverlayButtons() {
  document.querySelectorAll("[data-viewer-panel]").forEach((button) => {
    const panel = document.getElementById(button.dataset.viewerPanel);
    const collapsed = panel?.classList.contains("collapsed");
    button.setAttribute("aria-expanded", String(!collapsed));
  });
}

export function updateViewerModeChip() {
  const chip = document.getElementById("viewer-mode-chip");
  chip.textContent =
    state.viewerMode === "spaces" ? "Räume, Schächte und Flure" : "Vollständiges IFC mit farbigen Räumen";
}

export function updateSectionStatus() {
  const count = state.viewer ? state.viewer.getSectionCount() : 0;
  document.getElementById("section-status").textContent = `${count} Schnitt${count === 1 ? "" : "e"}`;
}

export function updateRoomCenterButton() {
  const button = document.getElementById("toggle-room-centers-button");
  button.textContent = state.roomCentersVisible ? "Mittelpunkte an" : "Mittelpunkte aus";
}

export function updateRoomLabelButton() {
  const button = document.getElementById("toggle-room-labels-button");
  button.textContent = state.roomLabelsVisible ? "Beschriftungen an" : "Beschriftungen aus";
}

export function updateBrowserTabs() {
  document.getElementById("browser-tab-structure").classList.toggle(
    "active",
    state.browserTab === "structure"
  );
  document.getElementById("browser-tab-categories").classList.toggle(
    "active",
    state.browserTab === "categories"
  );
}
