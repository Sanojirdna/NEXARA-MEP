import { formatMetricValue, escapeHtml } from "../../utils/format.js";
import {
  getVariantMetricValue,
  getRoomColor,
  getVariantColor,
} from "./designExplorerMetrics.js";

export function mountParallelCoords(ctx, rows, metricDefs, colorBy, colorByRoom = false) {
  const { state } = ctx;
  const renderSystemRowDetail = (...args) => ctx.system.renderSystemRowDetail(...args);
  const selectVariantRow = (...args) => ctx.variants.selectVariantRow(...args);
  const mountEl = document.getElementById("pc-mount");
  const legendEl = document.getElementById("pc-legend");
  if (!mountEl || !rows.length || !metricDefs.length) return;

  // ── Layout ────────────────────────────────────────────────────────────────
  const AXIS_GAP = 110;
  const MT = 56, MB = 24, ML = 54, MR = 54;
  const H = 340;
  const numAxes = metricDefs.length;
  const W = ML + (numAxes - 1) * AXIS_GAP + MR;
  const plotH = H - MT - MB;

  // ── Scales ────────────────────────────────────────────────────────────────
  const scales = {};
  metricDefs.forEach((m, i) => {
    const vals = rows
      .map(r => Number(getVariantMetricValue(r, m.key)))
      .filter(Number.isFinite);
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    if (!vals.length || lo === hi) { lo = lo - 1; hi = hi + 1; }
    scales[m.key] = {
      lo, hi,
      x: ML + i * AXIS_GAP,
      toY: v => MT + plotH - ((v - lo) / (hi - lo)) * plotH,
      toV: y => lo + ((MT + plotH - y) / plotH) * (hi - lo),
    };
  });

  // ── Brush state: {lo, hi} in data-space per key, or null ─────────────────
  const brushes = {};

  // ── SVG ───────────────────────────────────────────────────────────────────
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.style.fontFamily = "Inter, sans-serif";
  svg.style.userSelect = "none";
  svg.style.display = "block";

  function el(tag, attrs = {}) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  }
  function txt(content, attrs = {}) {
    const node = el("text", attrs);
    node.textContent = content;
    return node;
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function rowKey(row) { return `${row.shaft_guid}|${row.strategy}`; }

  function isRowVisible(row) {
    return metricDefs.every(m => {
      const b = brushes[m.key];
      if (!b) return true;
      const v = Number(getVariantMetricValue(row, m.key));
      return Number.isFinite(v) && v >= b.lo && v <= b.hi;
    });
  }

  function linePoints(row) {
    return metricDefs.map(m => {
      const v = Number(getVariantMetricValue(row, m.key));
      const s = scales[m.key];
      return [s.x, Number.isFinite(v) ? s.toY(v) : MT + plotH / 2];
    });
  }

  function polylineD(pts) {
    return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  }

  // ── Lines layer ───────────────────────────────────────────────────────────
  const linesG = el("g");
  svg.appendChild(linesG);

  const pathEls = rows.map(row => {
    const path = el("path", {
      d: polylineD(linePoints(row)),
      fill: "none",
      stroke: colorByRoom ? getRoomColor(row) : getVariantColor(row, colorBy),
      "stroke-width": "1.5",
      opacity: "0.55",
    });
    path.style.cursor = "pointer";
    path.dataset.variantKey = rowKey(row);

    path.addEventListener("mouseenter", () => {
      if (rowKey(row) !== state.selectedVariantKey) {
        path.setAttribute("stroke-width", "2.5");
        path.setAttribute("opacity", "1");
      }
    });
    path.addEventListener("mouseleave", () => refreshLine(path, row));
    path.addEventListener("click", () => {
      if (state.deViewMode === "all") {
        state.selectedSystemRow = row;
        state.selectedVariantKey = rowKey(row);
        refreshAllLines();
        const detailEl = document.getElementById("de-detail-card");
        if (detailEl) detailEl.innerHTML = renderSystemRowDetail(row);
      } else {
        selectVariantRow(row, true);
      }
    });

    linesG.appendChild(path);
    return path;
  });

  function refreshLine(path, row) {
    const selected = rowKey(row) === state.selectedVariantKey;
    const visible = isRowVisible(row);
    path.setAttribute("stroke", colorByRoom ? getRoomColor(row) : getVariantColor(row, colorBy));
    path.setAttribute("stroke-width", selected ? "3" : "1.5");
    path.setAttribute("opacity", selected ? "1" : visible ? "0.5" : "0.06");
  }

  function refreshAllLines() {
    rows.forEach((row, i) => refreshLine(pathEls[i], row));
    // Bring selected path to top
    const selKey = state.selectedVariantKey;
    const selPath = linesG.querySelector(`[data-variant-key="${CSS.escape(selKey)}"]`);
    if (selPath) linesG.appendChild(selPath);
  }

  // ── Axes + ticks + labels ─────────────────────────────────────────────────
  const axesG = el("g");
  metricDefs.forEach(m => {
    const s = scales[m.key];

    axesG.appendChild(el("line", {
      x1: s.x, x2: s.x, y1: MT, y2: MT + plotH,
      stroke: "#666", "stroke-width": "1.5",
    }));

    // Label
    const labelEl = txt(m.label, {
      x: s.x, y: MT - 10,
      "text-anchor": "middle",
      "font-size": "10",
      "font-weight": "600",
      fill: "#bbb",
    });
    axesG.appendChild(labelEl);

    // 5 tick marks + values
    for (let t = 0; t <= 4; t++) {
      const v = s.lo + (s.hi - s.lo) * (t / 4);
      const y = s.toY(v);
      axesG.appendChild(el("line", {
        x1: s.x - 4, x2: s.x + 4, y1: y, y2: y,
        stroke: "#555", "stroke-width": "1",
      }));
      axesG.appendChild(txt(formatMetricValue(v, 1), {
        x: s.x - 7, y: y + 3.5,
        "text-anchor": "end",
        "font-size": "9",
        fill: "#777",
      }));
    }
  });
  svg.appendChild(axesG);

  // ── Brush layer ───────────────────────────────────────────────────────────
  const brushG = el("g");
  svg.appendChild(brushG);

  metricDefs.forEach(m => {
    const s = scales[m.key];

    const brushRect = el("rect", {
      x: s.x - 10, width: "20",
      y: MT, height: "0",
      fill: "rgba(99,179,255,0.22)",
      stroke: "rgba(99,179,255,0.85)",
      "stroke-width": "1",
      rx: "2",
    });
    brushG.appendChild(brushRect);

    // Invisible wide hit area for dragging
    const hit = el("rect", {
      x: s.x - 22, width: "44",
      y: MT, height: plotH,
      fill: "transparent",
    });
    hit.style.cursor = "ns-resize";
    brushG.appendChild(hit);

    let dragStartY = null;

    function getSvgY(event) {
      const r = svg.getBoundingClientRect();
      return event.clientY - r.top;
    }

    hit.addEventListener("mousedown", e => {
      e.preventDefault();
      dragStartY = getSvgY(e);
      brushRect.setAttribute("y", dragStartY);
      brushRect.setAttribute("height", "0");
    });

    const onMove = e => {
      if (dragStartY === null) return;
      const curY = getSvgY(e);
      const top = Math.min(dragStartY, curY);
      const bot = Math.max(dragStartY, curY);
      brushRect.setAttribute("y", top);
      brushRect.setAttribute("height", bot - top);
      if (bot - top > 4) {
        brushes[m.key] = { lo: s.toV(bot), hi: s.toV(top) };
        refreshAllLines();
      }
    };

    const onUp = e => {
      if (dragStartY === null) return;
      const dy = Math.abs(getSvgY(e) - dragStartY);
      if (dy < 4) {
        // Tiny click = clear brush on this axis
        brushes[m.key] = null;
        brushRect.setAttribute("height", "0");
        refreshAllLines();
      }
      dragStartY = null;
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    // Clean up listeners when chart is re-rendered
    mountEl._pcCleanup = mountEl._pcCleanup || [];
    mountEl._pcCleanup.push(() => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    });
  });

  // ── Legend ────────────────────────────────────────────────────────────────
  if (legendEl) {
    let legendHtml = "";
    if (colorByRoom) {
      const allRoomNames = [...new Set(rows.map(r => String(r.room_name || r.room_guid || "-")))];
      legendHtml = allRoomNames.slice(0, 16).map(name => `
        <div class="de-legend-item">
          <span class="de-legend-dot" style="background:${getRoomColor({ room_name: name, room_guid: name })}"></span>
          <span>${escapeHtml(name)}</span>
        </div>`).join("");
      if (allRoomNames.length > 16) legendHtml += `<div class="de-legend-item"><span style="font-size:10px;color:#777;">…and ${allRoomNames.length - 16} more rooms</span></div>`;
    } else {
      const keys = colorBy === "none"
        ? ["All variants"]
        : [...new Set(rows.map(r =>
            String(colorBy === "shaft_name" ? r.shaft_name : r.strategy)
          ))];
      legendHtml = keys.map(k => `
        <div class="de-legend-item">
          <span class="de-legend-dot" style="background:${getVariantColor(
            { strategy: k, shaft_name: k }, colorBy
          )}"></span>
          <span>${escapeHtml(k || "-")}</span>
        </div>`).join("");
    }
    legendEl.innerHTML = legendHtml;
  }

  // Clean up old listeners before replacing DOM
  if (mountEl._pcCleanup) {
    mountEl._pcCleanup.forEach(fn => fn());
    mountEl._pcCleanup = [];
  }

  mountEl.innerHTML = "";
  mountEl.appendChild(svg);
  refreshAllLines();
}

