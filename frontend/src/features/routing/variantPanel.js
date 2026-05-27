import { escapeHtml } from "../../utils/format.js";

export function createVariantPanel(ctx) {
  const { state, apiGet } = ctx;

  const renderDesignExplorer = (...args) => ctx.explorer.renderDesignExplorer(...args);
  const renderKpis = (...args) => ctx.system.renderKpis(...args);
  const renderSystemAndSelectionRoutes = (...args) => ctx.system.renderSystemAndSelectionRoutes(...args);

async function updateVariantState() {
  if (!state.selectedRoomGuid || !state.selectedService) {
    clearVariantOutputs();
    renderSystemAndSelectionRoutes();
    renderKpis(null, state.summary?.system);
    return;
  }

  const demandResult = await apiGet(
    `/api/demand-id?room_guid=${encodeURIComponent(state.selectedRoomGuid)}&service=${encodeURIComponent(state.selectedService)}`
  );
  state.selectedDemandId = demandResult.demand_id || "";

  const payload = await apiGet(
    `/api/variants?room_guid=${encodeURIComponent(state.selectedRoomGuid)}&service=${encodeURIComponent(state.selectedService)}`
  );
  state.selectedVariantRows = payload.rows || [];
  state.deViewMode = "room"; // auto-switch DE to this room's variants

  populateVariantControls(payload);
  renderVariantTable(payload.rows || []);

  let chosenRow = null;

  if (payload.selected) {
    chosenRow = payload.selected;
  } else if (state.selectedVariantKey) {
    chosenRow = state.selectedVariantRows.find((row) => {
      return `${row.shaft_guid}|${row.strategy}` === state.selectedVariantKey;
    }) || null;
  }

  if (!chosenRow && state.selectedVariantRows.length) {
    chosenRow = state.selectedVariantRows[0];
  }

  if (chosenRow) {
    state.selectedShaftGuid = chosenRow.shaft_guid;
    state.selectedStrategy = chosenRow.strategy;
    state.selectedVariantKey = `${chosenRow.shaft_guid}|${chosenRow.strategy}`;
    syncVariantSelectionControls();
  } else {
    state.selectedShaftGuid = "";
    state.selectedStrategy = "";
    state.selectedVariantKey = "";
    syncVariantSelectionControls();
  }

  renderKpis(chosenRow, state.summary?.system);
  renderSystemAndSelectionRoutes();
  highlightVariantTable();
  renderDesignExplorer(state.selectedVariantRows || []);
}

function populateVariantControls(payload) {
  const rows = payload.rows || [];
  const shaftOptions = [];
  const strategyOptions = [];

  for (const row of rows) {
    if (!shaftOptions.some((item) => item.guid === row.shaft_guid)) {
      shaftOptions.push({ guid: row.shaft_guid, label: row.shaft_name });
    }

    if (!strategyOptions.includes(row.strategy)) {
      strategyOptions.push(row.strategy);
    }
  }

  document.getElementById("shaft-select").innerHTML = shaftOptions.length
    ? shaftOptions
        .map((shaft) => `<option value="${shaft.guid}">${escapeHtml(shaft.label)}</option>`)
        .join("")
    : `<option value="">Keine erfolgreichen Trassen</option>`;

  document.getElementById("strategy-select").innerHTML = strategyOptions.length
    ? strategyOptions
        .map((strategy) => `<option value="${strategy}">${escapeHtml(strategy)}</option>`)
        .join("")
    : `<option value="">Keine erfolgreichen Trassen</option>`;
}

function renderVariantTable(rows) {
  const body = document.getElementById("variant-table-body");

  if (!rows.length) {
    body.innerHTML = `
      <tr>
        <td colspan="4" class="muted">Keine erfolgreichen Varianten für den gewählten Raum und das gewählte Gewerk.</td>
      </tr>
    `;
    return;
  }

  // Find min/max score for relative bar sizing
  const scores = rows.map((r) => Number(r.score) || 0);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const scoreRange = maxScore - minScore || 1;

  body.innerHTML = rows
    .map((row, index) => {
      const key = `${row.shaft_guid}|${row.strategy}`;
      const activeClass = key === state.selectedVariantKey ? "active" : "";
      const score = Number(row.score);
      const rank = index + 1;
      // Bar fill: best (lowest) score = small bar, worst = full bar
      const barPct = Math.round(((score - minScore) / scoreRange) * 100);
      const barClass = barPct < 30 ? "score-good" : barPct < 65 ? "score-ok" : "score-poor";
      return `
        <tr class="${activeClass}" data-key="${key}">
          <td>
            <span class="rank-badge${rank === 1 ? " rank-1" : ""}">${rank}</span>${escapeHtml(row.shaft_name)}
          </td>
          <td>${escapeHtml(row.strategy)}</td>
          <td class="score-bar-cell">
            <span class="score-val">${Number(row.score).toFixed(2)}</span>
            <div class="score-bar-track">
              <div class="score-bar-fill ${barClass}" style="width:${Math.max(barPct, 4)}%"></div>
            </div>
          </td>
          <td>${Number(row.length_m || 0).toFixed(1)}</td>
        </tr>
      `;
    })
    .join("");

  [...body.querySelectorAll("tr")].forEach((rowElement) => {
    rowElement.addEventListener("click", () => {
      const key = rowElement.dataset.key;
      const row = state.selectedVariantRows.find(
        (item) => `${item.shaft_guid}|${item.strategy}` === key
      );
      if (!row) {
        return;
      }

      selectVariantRow(row, true);
    });
  });
}

function highlightVariantTable() {
  const rows = document.querySelectorAll("#variant-table-body tr");
  rows.forEach((row) => {
    if (row.dataset.key === state.selectedVariantKey) {
      row.classList.add("active");
    } else {
      row.classList.remove("active");
    }
  });
}

function getSelectedVariantRow() {
  if (!state.selectedVariantRows.length || !state.selectedVariantKey) {
    return null;
  }

  return (
    state.selectedVariantRows.find((row) => {
      return `${row.shaft_guid}|${row.strategy}` === state.selectedVariantKey;
    }) || null
  );
}

function setRoutingSelectionMessage(message) {
  const target = document.getElementById("routing-selection-status");
  if (target) {
    target.textContent = message;
  }

  const note = document.getElementById("variant-panel-note");
  if (note) {
    note.textContent = message;
  }
}

function setRoomRoutingControlsEnabled(enabled) {
  const targetIds = [
    "service-select",
    "shaft-select",
    "strategy-select",
    "apply-button",
    "center-button",
  ];

  for (const targetId of targetIds) {
    const element = document.getElementById(targetId);
    if (element) {
      element.disabled = !enabled;
    }
  }
}

function clearVariantOutputs(message = "Raum auswählen, um Trassierungsoptionen anzuzeigen.") {
  state.selectedService = "";
  state.selectedDemandId = "";
  state.selectedShaftGuid = "";
  state.selectedStrategy = "";
  state.selectedVariantRows = [];
  state.selectedVariantKey = "";

  document.getElementById("service-select").innerHTML = `<option value="">Zuerst Raum auswählen</option>`;
  document.getElementById("shaft-select").innerHTML = `<option value="">Zuerst Raum auswählen</option>`;
  document.getElementById("strategy-select").innerHTML = `<option value="">Zuerst Raum auswählen</option>`;
  document.getElementById("variant-table-body").innerHTML = `
    <tr>
      <td colspan="4" class="muted">Kein Raum ausgewählt</td>
    </tr>
  `;
  renderDesignExplorer([], { message });

  setRoutingSelectionMessage(message);
  setRoomRoutingControlsEnabled(false);
}

function syncVariantSelectionControls() {
  document.getElementById("shaft-select").value = state.selectedShaftGuid || "";
  document.getElementById("strategy-select").value = state.selectedStrategy || "";
}

function syncSelectedVariantFromControls() {
  state.selectedVariantKey = `${state.selectedShaftGuid}|${state.selectedStrategy}`;
  const selectedRow = getSelectedVariantRow();
  renderKpis(selectedRow, state.summary?.system);
  renderSystemAndSelectionRoutes();
  highlightVariantTable();
  renderDesignExplorer(state.selectedVariantRows || []);
}

function selectVariantRow(row, rerenderExplorer = false) {
  if (!row) {
    return;
  }

  state.selectedShaftGuid = row.shaft_guid || "";
  state.selectedStrategy = row.strategy || "";
  state.selectedVariantKey = `${state.selectedShaftGuid}|${state.selectedStrategy}`;
  syncVariantSelectionControls();
  renderKpis(row, state.summary?.system);
  renderSystemAndSelectionRoutes();
  highlightVariantTable();

  if (rerenderExplorer) {
    renderDesignExplorer(state.selectedVariantRows || []);
  }
}

function resetRoomDrivenUi(message = "Raum auswählen, um Trassierungsoptionen anzuzeigen.") {
  state.selectedRoomGuid = "";
  document.getElementById("room-select").value = "";
  document.getElementById("room-detail").innerHTML = `
    <div class="muted">Status</div><div>Kein Raum ausgewählt</div>
    <div class="muted">Hinweis</div><div>Raum im Viewer oder aus der Liste auswählen.</div>
  `;
  clearVariantOutputs(message);
  renderKpis(null, state.summary?.system);
  renderSystemAndSelectionRoutes();
}


  return {
    updateVariantState,
    populateVariantControls,
    renderVariantTable,
    highlightVariantTable,
    getSelectedVariantRow,
    setRoutingSelectionMessage,
    setRoomRoutingControlsEnabled,
    clearVariantOutputs,
    syncVariantSelectionControls,
    syncSelectedVariantFromControls,
    selectVariantRow,
    resetRoomDrivenUi,
  };
}
