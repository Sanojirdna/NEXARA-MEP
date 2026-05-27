# -*- coding: utf-8 -*-
"""
pipeline_visualizer.py
======================
Interactive Plotly 3-D figures for every stage of the NEXARA routing pipeline.
Saved as self-contained HTML files – open in any browser, no server needed.

Every figure uses the 3-D room/shaft boxes from Stage 1 as a transparent
reference background so all data is always shown *inside* the building model.

Stages
------
1.  IFC Rooms / Spaces   – coloured 3-D boxes, all floors (reference figure)
2.  Demand Assignment    – room boxes + demand spheres at room centroids
3.  Voxel Grid           – room boxes + 3-D voxel point-cloud (all masks)
4.  Cost Field           – room boxes + voxels coloured by cost value
5.  Route Variants       – room boxes + all candidate paths as 3-D lines
5b. Strategy Comparison  – room boxes + paths coloured per strategy
6.  Scoring              – 2-D dashboard (metrics, not spatial)
7.  Selected System      – room boxes + final routes as thick 3-D lines
8.  IFC Export Sizes     – room boxes + sized pipe/duct geometry at routes

Public API
----------
    from pipe_planner.pipeline_visualizer import generate_pipeline_figures

    saved = generate_pipeline_figures(runtime, output_dir="./figures")

Single stage:
    fig = render_stage("voxel_grid", runtime)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _fmt_demand(value: float) -> str:
    """Format a demand value with enough decimal places to not show as zero."""
    if value == 0:
        return "0"
    if value < 0.01:
        return f"{value:.3f}"
    if value < 1.0:
        return f"{value:.2f}"
    if value < 10.0:
        return f"{value:.1f}"
    return f"{value:.0f}"

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
# Colours taken directly from the NEXARA CSS design system
_SERVICE_COLOUR: dict[str, str] = {
    "HEI": "#D9541A",   # --hei
    "LUE": "#006FA8",   # --lue
    "SAN": "#B82468",   # --san
}
_SPACE_COLOUR: dict[str, str] = {
    "room":     "#C8DFF0",   # soft blue
    "shaft":    "#D4B84A",   # warm yellow
    "corridor": "#A8D4B0",   # soft green
    "other":    "#CECECE",   # --border
}
_MASK_COLOUR: dict[str, str] = {
    "traversable": "#0B7A6A",   # --brand
    "room":        "#006FA8",   # --lue blue
    "corridor":    "#2E7D32",   # --ok green
    "shaft":       "#D9541A",   # --hei orange
    "wall":        "#888888",   # --muted
    "slab":        "#444444",   # dark grey
}
_STRATEGY_PALETTE = [
    "#0B7A6A", "#D9541A", "#006FA8", "#B82468",
    "#2E7D32", "#E65100", "#1565C0", "#880E4F",
    "#4E342E", "#37474F",
]

# NEXARA CSS variables
_BG           = "#E8E8E8"   # --bg
_SURFACE      = "#F2F2F2"   # --surface
_SURFACE2     = "#FAFAFA"   # --surface-2
_BORDER       = "#CECECE"   # --border
_TEXT         = "#111111"   # --text
_MUTED        = "#888888"   # --muted
_BRAND        = "#0B7A6A"   # --brand
_FONT_FAMILY  = (
    '"DIN Offc W06 Extlight","DIN Alternate","Helvetica Neue",Arial,sans-serif'
)
_PLOTLY_TEMPLATE = "plotly_white"

# How many voxel points to show per mask/field (performance cap)
_MAX_VOXELS = 18_000

# Default camera – slightly elevated front-left view
_DEFAULT_CAMERA = dict(eye=dict(x=1.6, y=-2.0, z=1.3))

# Room box opacity when used as background in overlay figures
_BG_ROOM_OPACITY   = 0.10
_BG_SHAFT_OPACITY  = 0.20


# ===========================================================================
# Helpers
# ===========================================================================

def _find_eg_floor(bundle: dict[str, Any]) -> int:
    floors = bundle.get("floors", [])
    eg_kw  = ("eg", "erdgeschoss", "ground", " gf", "0.og", "og0", "00")
    for f in floors:
        if any(kw in (f.name or "").lower() for kw in eg_kw):
            return f.floor_index
    if floors:
        return min(floors, key=lambda f: abs(f.z_min)).floor_index
    return 0


def _floor_label(bundle: dict[str, Any], floor_index: int) -> str:
    for f in bundle.get("floors", []):
        if f.floor_index == floor_index:
            return f.name or f"Floor {floor_index}"
    return f"Floor {floor_index}"


def _floor_z_range(grid: Any, floor_index: int) -> tuple[float, float]:
    return grid.floor_bounds.get(floor_index, (0.0, 3.5))


def _floor_z_slice(grid: Any, floor_index: int, fraction: float = 0.6) -> int:
    z0, z1   = _floor_z_range(grid, floor_index)
    z_world  = z0 + (z1 - z0) * fraction
    _, _, zi = grid.world_to_index((0.0, 0.0, z_world))
    return int(np.clip(zi, 0, grid.shape[2] - 1))


def _unique_floors(bundle: dict[str, Any]) -> list[int]:
    return sorted({f.floor_index for f in bundle.get("floors", [])})


def _save_html(fig: go.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path), include_plotlyjs="cdn", full_html=True)
    return path


# ---------------------------------------------------------------------------
# Box mesh helper – returns go.Mesh3d for one BBox
# ---------------------------------------------------------------------------
def _triangulate_polygon_2d(
    pts: list[tuple[float, float]],
) -> list[tuple[int, int, int]]:
    """
    Ear-clipping triangulation for a simple 2-D polygon (convex or concave).

    Returns a list of (i, j, k) index triples into *pts*.
    Falls back to fan triangulation from vertex 0 if ear-clipping fails.
    """
    n = len(pts)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]

    def _cross2d(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def _point_in_triangle(p, a, b, c) -> bool:
        d1 = _cross2d(a, b, p)
        d2 = _cross2d(b, c, p)
        d3 = _cross2d(c, a, p)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)

    # Ensure CCW winding
    area2 = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )
    indices = list(range(n))
    if area2 < 0:
        indices = list(reversed(indices))

    triangles: list[tuple[int, int, int]] = []
    remaining = list(indices)

    max_iter = n * n * 2   # safety cap
    iterations = 0

    while len(remaining) > 3 and iterations < max_iter:
        iterations += 1
        ear_found = False
        r = len(remaining)
        for i in range(r):
            prev_v = remaining[(i - 1) % r]
            cur_v  = remaining[i]
            next_v = remaining[(i + 1) % r]

            a, b, c = pts[prev_v], pts[cur_v], pts[next_v]

            # Must be a convex vertex (left turn)
            if _cross2d(a, b, c) <= 0:
                continue

            # No other vertex inside this ear triangle
            inside = False
            for j in range(r):
                v = remaining[j]
                if v in (prev_v, cur_v, next_v):
                    continue
                if _point_in_triangle(pts[v], a, b, c):
                    inside = True
                    break

            if not inside:
                triangles.append((prev_v, cur_v, next_v))
                remaining.pop(i)
                ear_found = True
                break

        if not ear_found:
            break   # degenerate polygon — fall through to fan

    if len(remaining) == 3:
        triangles.append((remaining[0], remaining[1], remaining[2]))
    elif len(remaining) > 3:
        # Fan fallback for degenerate cases
        v0 = indices[0]
        for i in range(1, n - 1):
            triangles.append((v0, indices[i], indices[i + 1]))

    return triangles


def _polygon_mesh3d(
    footprint:    list[tuple[float, float]],
    z_min:        float,
    z_max:        float,
    color:        str,
    name:         str,
    hover:        str   = "",
    opacity:      float = 0.50,
    show_legend:  bool  = True,
    legend_group: str   = "",
) -> go.Mesh3d:
    """
    Extruded polygon Mesh3d from a 2-D footprint and two Z heights.
    Uses ear-clipping triangulation so L-shaped and other concave rooms
    render correctly without phantom triangles or diagonal seams.
    """
    n  = len(footprint)
    # Vertex layout: 0…n-1 = bottom ring, n…2n-1 = top ring
    xs = [p[0] for p in footprint] + [p[0] for p in footprint]
    ys = [p[1] for p in footprint] + [p[1] for p in footprint]
    zs = [z_min] * n + [z_max] * n

    face_tris = _triangulate_polygon_2d(footprint)

    ti, tj, tk = [], [], []

    for (a, b, c) in face_tris:
        # Bottom face (normal points down → reverse winding)
        ti.append(a);     tj.append(c);     tk.append(b)
        # Top face (normal points up → same winding as polygon)
        ti.append(a + n); tj.append(b + n); tk.append(c + n)

    # Side walls — one quad per edge
    for i in range(n):
        i1 = (i + 1) % n
        ti.append(i);     tj.append(i1);      tk.append(i1 + n)
        ti.append(i);     tj.append(i1 + n);  tk.append(i + n)

    return go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=ti, j=tj, k=tk,
        color=color,
        opacity=opacity,
        name=name,
        showlegend=show_legend,
        legendgroup=legend_group or name,
        hovertemplate=f"<b>{hover or name}</b><extra></extra>",
        flatshading=False,
        lighting=dict(ambient=0.9, diffuse=0.3, specular=0.0),
    )


def _space_mesh3d(
    space:        Any,
    color:        str,
    name:         str,
    hover:        str   = "",
    opacity:      float = 0.50,
    show_legend:  bool  = True,
    legend_group: str   = "",
) -> go.Mesh3d:
    """
    Render a SpaceRecord as either a real polygon extrusion (if footprint is
    available) or an axis-aligned bounding box (fallback).
    """
    fp = getattr(space, "footprint", [])
    if len(fp) >= 3:
        return _polygon_mesh3d(
            footprint=fp,
            z_min=space.bbox.min_z,
            z_max=space.bbox.max_z,
            color=color, name=name, hover=hover,
            opacity=opacity,
            show_legend=show_legend,
            legend_group=legend_group,
        )
    # Fallback: bounding box
    return _box_mesh(
        space.bbox, color=color, name=name, hover=hover,
        opacity=opacity, show_legend=show_legend, legend_group=legend_group,
    )


def _box_mesh(
    bbox:         Any,
    color:        str,
    name:         str,
    hover:        str  = "",
    opacity:      float = 0.50,
    show_legend:  bool  = True,
    legend_group: str   = "",
) -> go.Mesh3d:
    x0, y0, z0 = bbox.min_x, bbox.min_y, bbox.min_z
    x1, y1, z1 = bbox.max_x, bbox.max_y, bbox.max_z

    vx = [x0, x1, x1, x0,  x0, x1, x1, x0]
    vy = [y0, y0, y1, y1,  y0, y0, y1, y1]
    vz = [z0, z0, z0, z0,  z1, z1, z1, z1]
    ti = [0,0,4,4, 0,0,2,2, 0,0,1,1]
    tj = [1,2,5,6, 1,5,3,7, 3,7,2,6]
    tk = [2,3,6,7, 5,4,7,6, 7,4,6,5]

    ht = hover or name
    return go.Mesh3d(
        x=vx, y=vy, z=vz, i=ti, j=tj, k=tk,
        color=color, opacity=opacity,
        name=name,
        showlegend=show_legend,
        legendgroup=legend_group or name,
        hovertemplate=(
            f"<b>{ht}</b><br>"
            f"X {x0:.1f}–{x1:.1f} m<br>"
            f"Y {y0:.1f}–{y1:.1f} m<br>"
            f"Z {z0:.2f}–{z1:.2f} m<extra></extra>"
        ),
        flatshading=False,
        lighting=dict(ambient=0.9, diffuse=0.3, specular=0.0),
    )


# ---------------------------------------------------------------------------
# Add building background (transparent rooms + shafts) to an existing figure
# ---------------------------------------------------------------------------
def _add_building_bg(
    fig:          go.Figure,
    bundle:       dict[str, Any],
    room_opacity: float = _BG_ROOM_OPACITY,
    shaft_opacity:float = _BG_SHAFT_OPACITY,
    floor_index:  int | None = None,
) -> None:
    """Overlay semi-transparent room and shaft boxes onto *fig*.

    If *floor_index* is given only spaces on that floor are added.
    Defaults to the EG floor when not specified.
    """
    if floor_index is None:
        floor_index = _find_eg_floor(bundle)

    type_labels = {"room": "Room", "shaft": "Shaft",
                   "corridor": "Corridor", "other": "Other"}
    shown: set[str] = set()

    all_spaces = (
        list(bundle.get("rooms_by_guid",     {}).values())
        + list(bundle.get("shafts_by_guid",  {}).values())
        + list(bundle.get("corridors_by_guid", {}).values())
    )

    for space in all_spaces:
        if space.floor_index != floor_index:
            continue
        st      = getattr(space, "space_type", "other")
        color   = _SPACE_COLOUR.get(st, _SPACE_COLOUR["other"])
        label   = type_labels.get(st, st.capitalize())
        opacity = shaft_opacity if st == "shaft" else room_opacity
        first   = st not in shown

        mesh = _space_mesh3d(
            space, color=color, name=label,
            hover=f"{space.name or space.guid[:10]}  [Floor {space.floor_index}]",
            opacity=opacity,
            show_legend=first,
            legend_group=f"bg_{st}",
        )
        fig.add_trace(mesh)
        shown.add(st)


# ---------------------------------------------------------------------------
# Extract voxel world-coordinates from a boolean mask (with subsampling)
# ---------------------------------------------------------------------------
def _voxel_xyz(
    mask:        np.ndarray,
    grid:        Any,
    max_pts:     int = _MAX_VOXELS,
    z_min_world: float | None = None,
    z_max_world: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (xs, ys, zs) world centres of active voxels, subsampled.

    If *z_min_world* / *z_max_world* are given only voxels inside that
    Z band are returned (used to restrict to EG floor).
    """
    indices = np.argwhere(mask)           # (N, 3)
    if len(indices) == 0:
        return np.array([]), np.array([]), np.array([])

    orig = np.array(grid.origin, dtype=float)
    vs   = float(grid.voxel_size)

    if z_min_world is not None or z_max_world is not None:
        # World Z of each voxel centre
        z_centres = orig[2] + (indices[:, 2].astype(float) + 0.5) * vs
        mask_z    = np.ones(len(indices), dtype=bool)
        if z_min_world is not None:
            mask_z &= z_centres >= z_min_world
        if z_max_world is not None:
            mask_z &= z_centres <= z_max_world
        indices = indices[mask_z]

    if len(indices) == 0:
        return np.array([]), np.array([]), np.array([])

    if len(indices) > max_pts:
        rng  = np.random.default_rng(42)
        pick = rng.choice(len(indices), size=max_pts, replace=False)
        indices = indices[pick]

    xyz = orig + (indices.astype(float) + 0.5) * vs
    return xyz[:, 0], xyz[:, 1], xyz[:, 2]


# ---------------------------------------------------------------------------
# Shared 3-D scene layout
# ---------------------------------------------------------------------------
def _scene_layout(title: str, subtitle: str = "") -> dict:
    """Shared Plotly layout matching the NEXARA CSS design system."""
    full = title + (f"<br><sup>{subtitle}</sup>" if subtitle else "")
    return dict(
        title=dict(
            text=full, x=0.5,
            font=dict(
                family=_FONT_FAMILY,
                size=14, color=_TEXT,
            ),
        ),
        scene=dict(
            xaxis=dict(
                title=dict(text="X (m)", font=dict(family=_FONT_FAMILY, size=10, color=_MUTED)),
                tickfont=dict(family=_FONT_FAMILY, size=10, color=_MUTED),
                showgrid=True, gridcolor=_BORDER, gridwidth=1,
                backgroundcolor=_BG, showbackground=True, linecolor=_BORDER,
            ),
            yaxis=dict(
                title=dict(text="Y (m)", font=dict(family=_FONT_FAMILY, size=10, color=_MUTED)),
                tickfont=dict(family=_FONT_FAMILY, size=10, color=_MUTED),
                showgrid=True, gridcolor=_BORDER, gridwidth=1,
                backgroundcolor=_BG, showbackground=True, linecolor=_BORDER,
            ),
            zaxis=dict(
                title=dict(text="Z (m)", font=dict(family=_FONT_FAMILY, size=10, color=_MUTED)),
                tickfont=dict(family=_FONT_FAMILY, size=10, color=_MUTED),
                showgrid=True, gridcolor=_BORDER, gridwidth=1,
                backgroundcolor=_SURFACE, showbackground=True, linecolor=_BORDER,
            ),
            aspectmode="data",
            camera=_DEFAULT_CAMERA,
            bgcolor=_SURFACE2,
        ),
        paper_bgcolor=_SURFACE,
        plot_bgcolor=_BG,
        font=dict(family=_FONT_FAMILY, size=11, color=_TEXT),
        legend=dict(
            bgcolor=_SURFACE2,
            bordercolor=_BORDER,
            borderwidth=1,
            font=dict(family=_FONT_FAMILY, size=10, color=_TEXT),
        ),
        margin=dict(l=0, r=0, t=80, b=0),
        height=720,
        template=None,
    )


# ===========================================================================
# Stage 1 – IFC Rooms / Spaces  (3-D reference figure, all floors)
# ===========================================================================

def stage1_ifc_spaces_3d(bundle: dict[str, Any]) -> go.Figure:
    """
    3-D boxes for every room, shaft and corridor on the EG floor.
    This is the reference figure all other stages use as background.
    """
    fig      = go.Figure()
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)

    type_labels = {"room": "Room", "shaft": "Shaft",
                   "corridor": "Corridor", "other": "Other"}
    shown: set[str] = set()

    all_spaces = (
        list(bundle.get("rooms_by_guid",     {}).values())
        + list(bundle.get("shafts_by_guid",  {}).values())
        + list(bundle.get("corridors_by_guid", {}).values())
    )

    for space in all_spaces:
        if space.floor_index != eg_floor:
            continue
        st    = getattr(space, "space_type", "other")
        color = _SPACE_COLOUR.get(st, _SPACE_COLOUR["other"])
        label = type_labels.get(st, st.capitalize())
        first = st not in shown
        mesh  = _space_mesh3d(
            space, color=color, name=label,
            hover=f"{space.name or space.guid[:10]}  [{eg_label}]",
            opacity=0.50, show_legend=first, legend_group=st,
        )
        fig.add_trace(mesh)
        shown.add(st)

    room_count  = sum(1 for s in bundle.get("rooms_by_guid",  {}).values()
                      if s.floor_index == eg_floor)
    shaft_count = sum(1 for s in bundle.get("shafts_by_guid", {}).values()
                      if s.floor_index == eg_floor)

    fig.update_layout(**_scene_layout(
        f"Stage 1 – IFC Spaces  [{eg_label}]",
        f"{room_count} rooms · {shaft_count} shafts",
    ))
    return fig


# ===========================================================================
# Stage 2 – Demand Assignment
# ===========================================================================

def stage2_demands(bundle: dict[str, Any]) -> go.Figure:
    """
    Building model (transparent) + demand spheres at room centroids.
    Sphere size = number of demands.  Colour = service type.
    One sphere per (room, service) combination.
    """
    fig = go.Figure()
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, floor_index=eg_floor)

    demands       = bundle.get("demands", [])
    rooms_by_guid = bundle.get("rooms_by_guid", {})

    if not demands:
        fig.update_layout(**_scene_layout(f"Stage 2 – Demand Assignment  [{eg_label}]",
                                          "No demands loaded"))
        return fig

    # Aggregate: room_guid × service → count  (EG floor only)
    agg: dict[tuple[str, str], int] = {}
    for d in demands:
        room = rooms_by_guid.get(d.room_guid)
        if room is None or room.floor_index != eg_floor:
            continue
        key = (d.room_guid, d.service)
        agg[key] = agg.get(key, 0) + 1

    # Group by service for one legend entry each
    by_service: dict[str, dict] = {}
    for (room_guid, service), count in agg.items():
        room = rooms_by_guid.get(room_guid)
        if room is None:
            continue
        cx, cy, cz = (
            (room.bbox.min_x + room.bbox.max_x) / 2,
            (room.bbox.min_y + room.bbox.max_y) / 2,
            (room.bbox.min_z + room.bbox.max_z) / 2,
        )
        entry = by_service.setdefault(service, {"x":[], "y":[], "z":[], "size":[], "text":[]})
        entry["x"].append(cx)
        entry["y"].append(cy)
        entry["z"].append(cz)
        entry["size"].append(6 + count * 3)
        entry["text"].append(f"{room.name or room_guid[:10]}<br>{service}: {count} demand(s)")

    for service, pts in sorted(by_service.items()):
        color = _SERVICE_COLOUR.get(service, "#AAAAAA")
        fig.add_trace(go.Scatter3d(
            x=pts["x"], y=pts["y"], z=pts["z"],
            mode="markers",
            marker=dict(
                size=pts["size"],
                color=color,
                opacity=0.90,
                symbol="circle",
                line=dict(color="white", width=1),
            ),
            name=service,
            legendgroup=f"srv_{service}",
            hovertext=pts["text"],
            hoverinfo="text",
        ))

    total = len([d for d in demands
                 if rooms_by_guid.get(d.room_guid, None) is not None
                 and rooms_by_guid[d.room_guid].floor_index == eg_floor])
    rooms_assigned = len({k[0] for k in agg})
    fig.update_layout(**_scene_layout(
        f"Stage 2 – Demand Assignment  [{eg_label}]",
        f"{total} demands · {rooms_assigned} rooms · "
        f"{len(by_service)} service types",
    ))
    return fig


# ===========================================================================
# Stage 3 – Voxel Grid (3-D point cloud inside the building)
# ===========================================================================

def stage3_voxel_grid(bundle: dict[str, Any]) -> go.Figure:
    """
    Building model (transparent) + 3-D voxel point-cloud.
    Each mask layer is a separate toggleable trace.
    The point cloud shows the internal structure of the building.
    """
    fig  = go.Figure()
    grid = bundle["grid"]
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    z_min, z_max = _floor_z_range(grid, eg_floor)
    _add_building_bg(fig, bundle, floor_index=eg_floor)

    mask_defs = [
        ("Traversable", grid.traversable_mask, _MASK_COLOUR["traversable"], 2.5),
        ("Rooms",       grid.room_mask,        _MASK_COLOUR["room"],        2.0),
        ("Corridors",   grid.corridor_mask,    _MASK_COLOUR["corridor"],    2.5),
        ("Shafts",      grid.shaft_mask,       _MASK_COLOUR["shaft"],       3.5),
        ("Walls",       grid.wall_mask,        _MASK_COLOUR["wall"],        1.5),
        ("Slabs",       grid.slab_mask,        _MASK_COLOUR["slab"],        2.0),
    ]

    for name, mask, color, pt_size in mask_defs:
        xs, ys, zs = _voxel_xyz(mask, grid, z_min_world=z_min, z_max_world=z_max)
        if len(xs) == 0:
            continue
        # Count active voxels in this z-band for the label
        orig   = np.array(grid.origin, dtype=float)
        vs     = float(grid.voxel_size)
        idx    = np.argwhere(mask)
        zc     = orig[2] + (idx[:, 2].astype(float) + 0.5) * vs
        active = int(((zc >= z_min) & (zc <= z_max)).sum())
        shown  = len(xs)
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="markers",
            marker=dict(size=pt_size, color=color, opacity=0.55, symbol="square"),
            name=f"{name} ({active:,})",
            legendgroup=f"mask_{name}",
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"X: %{{x:.2f}}  Y: %{{y:.2f}}  Z: %{{z:.2f}}<br>"
                f"Shown: {shown:,} / {active:,} in {eg_label}"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(**_scene_layout(
        f"Stage 3 – Voxel Grid  [{eg_label}]",
        f"Voxel size {grid.voxel_size} m · up to {_MAX_VOXELS:,} points per mask",
    ))
    return fig


# ===========================================================================
# Stage 4 – Cost Field (3-D heat-cloud inside the building)
# ===========================================================================

def stage4_cost_field(bundle: dict[str, Any]) -> go.Figure:
    """
    Building model (transparent) + traversable voxels coloured by cost value.
    Three traces (wall dist / corridor dist / ceiling score), toggleable.
    """
    fig  = go.Figure()
    grid = bundle["grid"]
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    z_min, z_max = _floor_z_range(grid, eg_floor)
    _add_building_bg(fig, bundle, floor_index=eg_floor)

    trav = grid.traversable_mask

    field_defs = [
        ("Wall distance",     grid.wall_distance,     "plasma",  "voxels from wall"),
        ("Corridor distance", grid.corridor_distance, "Blues",   "voxels to corridor"),
        ("Ceiling score",     grid.ceiling_score,     "RdYlGn",  "routing preference"),
    ]

    for fi, (name, field_3d, cscale, unit) in enumerate(field_defs):
        # Get traversable voxel indices restricted to EG z-band
        orig  = np.array(grid.origin, dtype=float)
        vs    = float(grid.voxel_size)
        idx3  = np.argwhere(trav)
        zc    = orig[2] + (idx3[:, 2].astype(float) + 0.5) * vs
        idx3  = idx3[(zc >= z_min) & (zc <= z_max)]

        if len(idx3) == 0:
            continue
        if len(idx3) > _MAX_VOXELS:
            rng  = np.random.default_rng(42)
            pick = rng.choice(len(idx3), _MAX_VOXELS, replace=False)
            idx3 = idx3[pick]

        xyz  = orig + (idx3.astype(float) + 0.5) * vs
        vals = field_3d[idx3[:, 0], idx3[:, 1], idx3[:, 2]].astype(float)
        vmin, vmax = float(vals.min()), float(vals.max())

        fig.add_trace(go.Scatter3d(
            x=xyz[:, 0], y=xyz[:, 1], z=xyz[:, 2],
            mode="markers",
            visible=(fi == 0),
            marker=dict(
                size=2.5,
                color=vals,
                colorscale=cscale,
                cmin=vmin, cmax=vmax,
                opacity=0.65,
                colorbar=dict(
                    title=dict(text=unit, side="right"),
                    len=0.5, thickness=12, x=1.02,
                ),
                showscale=True,
            ),
            name=name,
            legendgroup=f"field_{fi}",
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"X: %{{x:.2f}}  Y: %{{y:.2f}}  Z: %{{z:.2f}}<br>"
                f"Value: %{{marker.color:.2f}} {unit}<extra></extra>"
            ),
        ))

    # Dropdown to switch between fields
    n_fields = len(field_defs)
    buttons = []
    for i, (name, *_) in enumerate(field_defs):
        vis = [True] * (len(fig.data) - n_fields) + \
              [(j == i) for j in range(n_fields)]
        buttons.append(dict(label=name, method="update", args=[{"visible": vis}]))

    fig.update_layout(**_scene_layout(
        f"Stage 4 – Cost Field  [{eg_label}]",
        "Traversable voxels coloured by routing cost.  "
        "High wall-distance = route prefers corridor centre.",
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=80, b=80),
        updatemenus=[dict(
            type="buttons",
            direction="right",
            x=0.5, xanchor="center",
            y=-0.08, yanchor="bottom",
            buttons=buttons,
            bgcolor=_SURFACE2,
            bordercolor=_BORDER,
            borderwidth=1,
            font=dict(family=_FONT_FAMILY, color=_TEXT, size=10),
            pad=dict(t=6, b=6, l=8, r=8),
        )],
    )
    return fig


# ===========================================================================
# Stage 5 – Route Variants (all candidates as 3-D lines)
# ===========================================================================

def stage5_route_variants(bundle: dict[str, Any]) -> go.Figure:
    """
    Building model (transparent) + all candidate route paths as 3-D lines.
    Each strategy is a separate trace (toggle in legend).
    Successful = solid, failed = dotted.  Colour = service type.
    """
    fig         = go.Figure()
    matrix_rows = bundle.get("route_matrix_rows", [])
    eg_floor    = _find_eg_floor(bundle)
    eg_label    = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, floor_index=eg_floor)

    if not matrix_rows:
        fig.update_layout(**_scene_layout(f"Stage 5 – Route Variants  [{eg_label}]",
                                          "No route matrix available"))
        return fig

    strategies = sorted({r.get("strategy", "") for r in matrix_rows})
    grid        = bundle["grid"]
    z_min, z_max = _floor_z_range(grid, eg_floor)
    MAX_PER_STRATEGY = 400

    success_total = 0
    fail_total    = 0

    for strat_idx, strategy in enumerate(strategies):
        strat_rows = [r for r in matrix_rows if r.get("strategy") == strategy]
        shown = 0

        for r in strat_rows:
            path_xyz = r.get("path_xyz")
            if not path_xyz:
                fail_total += 1
                continue
            try:
                coords = np.array(path_xyz, dtype=float)
                if coords.ndim != 2 or coords.shape[1] < 3 or len(coords) < 2:
                    fail_total += 1
                    continue
            except Exception:
                fail_total += 1
                continue

            # Keep only points inside the EG floor z-band
            in_band = (coords[:, 2] >= z_min - 0.2) & (coords[:, 2] <= z_max + 0.2)
            if not in_band.any():
                continue
            coords = coords[in_band]
            if len(coords) < 2:
                continue

            success = r.get("success", False)
            service = str(r.get("service", ""))
            color   = _SERVICE_COLOUR.get(service, "#AAAAAA") if success else "#555555"
            width   = 2.5 if success else 0.8

            if success:
                success_total += 1
            else:
                fail_total += 1

            if shown >= MAX_PER_STRATEGY:
                continue
            shown += 1

            # None-separated path for clean line breaks
            xs = list(coords[:, 0]) + [None]
            ys = list(coords[:, 1]) + [None]
            zs = list(coords[:, 2]) + [None]

            fig.add_trace(go.Scatter3d(
                x=xs, y=ys, z=zs,
                mode="lines",
                line=dict(color=color, width=width),
                opacity=0.65 if success else 0.20,
                name=strategy,
                legendgroup=strategy,
                showlegend=(shown == 1),
                hovertemplate=(
                    f"Strategy: {strategy}<br>"
                    f"Service: {service}<br>"
                    f"{'✓ Success' if success else '✗ Failed'}<extra></extra>"
                ),
            ))

    fig.update_layout(**_scene_layout(
        f"Stage 5 – Route Variants  [{eg_label}]",
        f"{len(strategies)} strategies · ✓ {success_total} success · "
        f"✗ {fail_total} failed · up to {MAX_PER_STRATEGY} routes shown per strategy",
    ))
    return fig


# ===========================================================================
# Stage 5b – Strategy Comparison (one colour per strategy)
# ===========================================================================

def stage5b_strategy_grid_comparison(bundle: dict[str, Any]) -> go.Figure:
    """
    Building model + routes where colour = strategy (not service).
    Toggle individual strategies in the legend to compare their behaviour.
    """
    fig         = go.Figure()
    matrix_rows = bundle.get("route_matrix_rows", [])
    eg_floor    = _find_eg_floor(bundle)
    eg_label    = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, floor_index=eg_floor)

    if not matrix_rows:
        fig.update_layout(**_scene_layout(f"Stage 5b – Strategy Comparison  [{eg_label}]",
                                          "No route matrix available"))
        return fig

    strategies   = sorted({r.get("strategy", "") for r in matrix_rows})
    grid         = bundle["grid"]
    z_min, z_max = _floor_z_range(grid, eg_floor)
    MAX_PER_STRAT = 350

    for si, strategy in enumerate(strategies):
        color    = _STRATEGY_PALETTE[si % len(_STRATEGY_PALETTE)]
        strat_ok = [r for r in matrix_rows
                    if r.get("strategy") == strategy and r.get("success")]
        shown    = 0

        for r in strat_ok:
            path_xyz = r.get("path_xyz")
            if not path_xyz:
                continue
            try:
                coords = np.array(path_xyz, dtype=float)
                if coords.ndim != 2 or coords.shape[1] < 3 or len(coords) < 2:
                    continue
            except Exception:
                continue

            # Keep only points inside the EG floor z-band
            in_band = (coords[:, 2] >= z_min - 0.2) & (coords[:, 2] <= z_max + 0.2)
            if not in_band.any():
                continue
            coords = coords[in_band]
            if len(coords) < 2:
                continue

            if shown >= MAX_PER_STRAT:
                break
            shown += 1

            service = str(r.get("service", ""))
            xs = list(coords[:, 0]) + [None]
            ys = list(coords[:, 1]) + [None]
            zs = list(coords[:, 2]) + [None]

            fig.add_trace(go.Scatter3d(
                x=xs, y=ys, z=zs,
                mode="lines",
                line=dict(color=color, width=2.2),
                opacity=0.75,
                name=strategy,
                legendgroup=strategy,
                showlegend=(shown == 1),
                hovertemplate=(
                    f"<b>{strategy}</b><br>"
                    f"Service: {service}<extra></extra>"
                ),
            ))

    fig.update_layout(**_scene_layout(
        f"Stage 5b – Strategy comparison  [{eg_label}]",
        "Each colour = one strategy.  Toggle in legend to compare routing paths.",
    ))
    return fig


# ===========================================================================
# Stage 6 – Scoring  (2-D dashboard – metrics, not spatial)
# ===========================================================================

def stage6_scoring(bundle: dict[str, Any]) -> go.Figure:
    """
    2-D four-panel dashboard: score · coverage · length · bends/wall-crossings.
    (Kept 2-D because it shows statistical comparisons, not spatial data.)
    """
    matrix_rows = bundle.get("route_matrix_rows", [])
    if not matrix_rows:
        fig = go.Figure()
        fig.add_annotation(text="No route matrix available",
                           x=0.5, y=0.5, showarrow=False,
                           font=dict(size=18, color="#e0e0e0"),
                           xref="paper", yref="paper")
        fig.update_layout(
            title="Stage 6 – Scoring",
            paper_bgcolor="#1a1a2e",
            font=dict(color="#e0e0e0"),
        )
        return fig

    import pandas as pd
    df            = pd.DataFrame(matrix_rows)
    strategies    = sorted(df["strategy"].unique())
    total_demands = df["demand_id"].nunique()
    palette       = {s: _STRATEGY_PALETTE[i % len(_STRATEGY_PALETTE)]
                     for i, s in enumerate(strategies)}

    agg: dict[str, dict] = {}
    for strat in strategies:
        sub  = df[df["strategy"] == strat]
        ok   = sub[sub["success"] == True]
        best = ok.sort_values("score").drop_duplicates("demand_id")
        agg[strat] = {
            "mean_score":   float(best["score"].mean())           if not best.empty else 0.0,
            "coverage_pct": len(best) / max(total_demands, 1)*100,
            "total_length": float(best["length_m"].sum())         if "length_m"       in best.columns else 0.0,
            "total_bends":  float(best["bend_count"].sum())       if "bend_count"     in best.columns else 0.0,
            "wall_cross":   float(best["wall_crossings"].sum())   if "wall_crossings" in best.columns else 0.0,
        }

    colors = [palette[s] for s in strategies]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "Mean route score  (lower = better)",
            "Demand coverage  (%)",
            "Total route length  (m)",
            "Bends & wall crossings",
        ],
        vertical_spacing=0.22,
        horizontal_spacing=0.14,
    )

    def _bar(y_key, row, col, text_fmt="{:.2f}", show_legend=False):
        fig.add_trace(go.Bar(
            x=strategies,
            y=[agg[s][y_key] for s in strategies],
            marker_color=colors,
            marker_line_color="#555", marker_line_width=0.5,
            text=[text_fmt.format(agg[s][y_key]) for s in strategies],
            textposition="outside",
            showlegend=show_legend,
        ), row=row, col=col)

    _bar("mean_score",   1, 1, "{:.2f}")
    _bar("coverage_pct", 1, 2, "{:.0f}%")
    fig.add_hline(y=100, line_dash="dash", line_color="#4CAF50",
                  annotation_text="100 %", row=1, col=2)
    fig.update_yaxes(range=[0, 112], row=1, col=2)
    _bar("total_length", 2, 1, "{:.0f} m")

    fig.add_trace(go.Bar(name="Bends",
        x=strategies, y=[agg[s]["total_bends"] for s in strategies],
        marker_color="#5B9BD5", marker_line_color="#555", marker_line_width=0.5,
    ), row=2, col=2)
    fig.add_trace(go.Bar(name="Wall crossings",
        x=strategies, y=[agg[s]["wall_cross"] for s in strategies],
        marker_color="#ED7D31", marker_line_color="#555", marker_line_width=0.5,
    ), row=2, col=2)

    fig.update_layout(
        barmode="group",
        title=dict(
            text=(f"Stage 6 – Scoring & Route Quality Metrics<br>"
                  f"<sup>{len(strategies)} strategies · "
                  f"{total_demands} demands evaluated</sup>"),
            x=0.5,
        ),
        paper_bgcolor=_SURFACE,
        plot_bgcolor=_BG,
        font=dict(family=_FONT_FAMILY, color=_TEXT),
        height=640,
        margin=dict(l=50, r=40, t=110, b=60),
        legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center",
                    bgcolor=_SURFACE2, bordercolor=_BORDER, borderwidth=1),
    )
    fig.update_xaxes(showgrid=True, gridcolor=_BORDER)
    fig.update_yaxes(showgrid=True, gridcolor=_BORDER)
    return fig


# ===========================================================================
# Stage 7 – Selected System (final 3-D routes inside the building)
# ===========================================================================

def stage7_selected_system(bundle: dict[str, Any], system: Any) -> go.Figure:
    """
    Building model (transparent) + final merged routes as thick 3-D lines,
    coloured by service type.  This is the primary output visualisation.
    """
    fig = go.Figure()
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, room_opacity=0.12, shaft_opacity=0.25,
                     floor_index=eg_floor)

    if system is None or not system.routes:
        fig.update_layout(**_scene_layout(f"Stage 7 – Selected System  [{eg_label}]",
                                          "No system routes available"))
        return fig

    demands = {d.demand_id: d for d in bundle.get("demands", [])}
    service_shown: set[str] = set()
    route_count = 0

    for route in system.routes:
        if not route.success or not route.path_xyz:
            continue
        demand  = demands.get(route.demand_id)
        service = demand.service if demand else ""
        color   = _SERVICE_COLOUR.get(service, "#AAAAAA")
        coords  = np.array(route.path_xyz, dtype=float)
        if coords.ndim != 2 or coords.shape[1] < 3 or len(coords) < 2:
            continue

        xs = list(coords[:, 0]) + [None]
        ys = list(coords[:, 1]) + [None]
        zs = list(coords[:, 2]) + [None]

        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="lines",
            line=dict(color=color, width=4),
            opacity=0.92,
            name=service,
            legendgroup=f"svc_{service}",
            showlegend=(service not in service_shown),
            hovertemplate=(
                f"<b>{service}</b><br>"
                f"Demand: {route.demand_id}<extra></extra>"
            ),
        ))
        service_shown.add(service)
        route_count += 1

    fig.update_layout(**_scene_layout(
        "Stage 7 – Selected System (3-D)",
        f"{route_count} routes · "
        f"{', '.join(service_shown)} services",
    ))
    return fig


# ===========================================================================
# Stage 8 – IFC Export Sizes (3-D pipes inside the building)
# ===========================================================================

def stage8_ifc_export_sizes(bundle: dict[str, Any], system: Any) -> go.Figure:
    """
    Building model (transparent) + route geometry sized to actual pipe/duct
    cross-sections.  Each route segment is drawn as a 3-D tube (approximated
    by ribbon width ∝ DN size) and coloured by service.
    A text panel lists the sizing formula.
    """
    fig = go.Figure()
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, room_opacity=0.10, shaft_opacity=0.20,
                     floor_index=eg_floor)

    _DN_MM = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300]

    if system is None or not system.routes:
        fig.update_layout(**_scene_layout("Stage 8 – IFC Export Sizes",
                                          "No system routes available"))
        return fig

    demands     = bundle.get("demands", [])
    demands_map = {d.demand_id: d for d in demands}

    # Unit lookup: service -> unit
    unit_by_svc: dict[str, str] = {}
    for d in demands:
        unit_by_svc.setdefault(d.service, d.unit)

    grid     = bundle["grid"]
    z_min_eg, z_max_eg = _floor_z_range(grid, eg_floor)

    # ── Build SectionSizer + segments using the EXACT same path as IFC exporter
    # This means the values shown here are byte-for-byte what ends up in the IFC.
    try:
        from pipe_planner.section_sizing import SectionSizer, SizerConfig

        # Same floor_by_room dict the IFC exporter builds (ifc_exporter.py line 467)
        rooms_by_guid = bundle.get("rooms_by_guid", {})
        floor_by_room = {
            guid: space.floor_index for guid, space in rooms_by_guid.items()
        }

        sizer    = SectionSizer(system.routes, demands, SizerConfig())
        segments = sizer.build_all_unique_segments(floor_by_room)
        _sizer_ok = True
    except Exception as _e:
        print(f"[pipeline_visualizer] SectionSizer failed: {_e}", flush=True)
        segments  = []
        sizer     = None
        _sizer_ok = False

    svc_shown:     set[str]         = set()
    labels_by_svc: dict[str, dict]  = {}

    rooms_by_guid = bundle.get("rooms_by_guid", {})

    # ── Always draw directly from system.routes so ALL services are shown ──
    for route in system.routes:
        if not route.success or not route.path_xyz:
            continue
        demand  = demands_map.get(route.demand_id)
        service = route.service
        color   = _SERVICE_COLOUR.get(service, "#888888")
        coords  = np.array(route.path_xyz, dtype=float)
        if coords.ndim != 2 or coords.shape[1] < 3 or len(coords) < 2:
            continue

        in_band = (coords[:, 2] >= z_min_eg - 0.2) & (coords[:, 2] <= z_max_eg + 0.2)
        if not in_band.any():
            continue
        coords = coords[in_band]
        if len(coords) < 2:
            continue

        length_m = float(route.metrics.get("length_m", 0.0)) if route.metrics else 0.0
        unit     = unit_by_svc.get(service, "")

        mid     = len(coords) // 2
        mid_vox = grid.world_to_index(
            (float(coords[mid, 0]), float(coords[mid, 1]), float(coords[mid, 2]))
        )
        if _sizer_ok:
            accum = sizer.voxel_demands(mid_vox).get(service, 0.0)
        else:
            accum = demand.value if demand else 0.0

        demand_detail = ""
        if demand:
            demand_detail = (
                f"<br><b>Room demand:</b> {_fmt_demand(demand.value)} {unit}"
                f"<br><b>Voxel load:</b>  {_fmt_demand(accum)} {unit}"
                f"<br><b>Media:</b> {demand.media_type}"
                f"<br><b>Kind:</b> {demand.kind}"
            )

        fig.add_trace(go.Scatter3d(
            x=list(coords[:, 0]) + [None],
            y=list(coords[:, 1]) + [None],
            z=list(coords[:, 2]) + [None],
            mode="lines",
            line=dict(color=color, width=3),
            opacity=0.88,
            name=service,
            legendgroup=f"svc_{service}",
            showlegend=(service not in svc_shown),
            hovertemplate=(
                f"<b>{service}</b><br>"
                f"Length: {length_m:.1f} m"
                f"{demand_detail}"
                f"<br><i>{route.demand_id}</i>"
                "<extra></extra>"
            ),
        ))
        svc_shown.add(service)

        # ── Connector line: room centroid → route start ───────────────────
        room = rooms_by_guid.get(route.room_guid)
        if room is not None:
            fp = getattr(room, "footprint", [])
            if len(fp) >= 3:
                room_cx = sum(p[0] for p in fp) / len(fp)
                room_cy = sum(p[1] for p in fp) / len(fp)
            else:
                room_cx, room_cy, _ = room.bbox.center()
            room_cz = (room.bbox.min_z + room.bbox.max_z) / 2

            route_start = coords[0]
            fig.add_trace(go.Scatter3d(
                x=[room_cx, float(route_start[0]), None],
                y=[room_cy, float(route_start[1]), None],
                z=[room_cz, float(route_start[2]), None],
                mode="lines",
                line=dict(color=color, width=1, dash="dot"),
                opacity=0.40,
                name="Demand connector",
                legendgroup="connectors",
                showlegend=(not any(
                    t.name == "Demand connector" for t in fig.data
                )),
                hovertemplate=(
                    f"<b>Demand → Route</b><br>"
                    f"Room: {room.name or route.room_guid[:12]}<br>"
                    f"Service: {service}<br>"
                    f"Demand: {route.demand_id}<extra></extra>"
                ),
            ))

        # Label: accumulated voxel load
        buck = labels_by_svc.setdefault(service, {"x": [], "y": [], "z": [], "t": []})
        buck["x"].append(float(coords[mid, 0]))
        buck["y"].append(float(coords[mid, 1]))
        buck["z"].append(float(coords[mid, 2]))
        buck["t"].append(f"{_fmt_demand(accum)} {unit}")

    # ── One label trace per service (individually togglable) ──────────────
    # Track which trace indices are label traces for the filter buttons
    label_trace_start = len(fig.data)
    services_with_labels = sorted(labels_by_svc.keys())

    for service in services_with_labels:
        buck  = labels_by_svc[service]
        color = _SERVICE_COLOUR.get(service, _TEXT)
        fig.add_trace(go.Scatter3d(
            x=buck["x"], y=buck["y"], z=buck["z"],
            mode="text",
            text=buck["t"],
            textfont=dict(family=_FONT_FAMILY, size=9, color=color),
            textposition="top center",
            name=f"Labels · {service}",
            legendgroup=f"lbl_{service}",
            showlegend=True,
            hoverinfo="skip",
        ))

    n_label_traces = len(services_with_labels)
    n_bg_and_route = label_trace_start        # traces before labels

    # ── Filter buttons: All / HEI / LUE / SAN / None ─────────────────────
    def _vis_for(keep: set[str]) -> list[bool]:
        """Build visibility list: bg+route traces always on, labels filtered."""
        route_vis = [True] * n_bg_and_route
        label_vis = [(svc in keep) for svc in services_with_labels]
        return route_vis + label_vis

    all_svc  = set(services_with_labels)
    buttons  = [
        dict(label="ALL LABELS",  method="update",
             args=[{"visible": _vis_for(all_svc)}]),
    ]
    for svc in services_with_labels:
        buttons.append(dict(
            label=svc,
            method="update",
            args=[{"visible": _vis_for({svc})}],
        ))
    buttons.append(dict(
        label="HIDE LABELS",
        method="update",
        args=[{"visible": _vis_for(set())}],
    ))

    # Add sizing formula annotation
    formula_lines = [
        "IFC sizing logic:",
        "① Sum flow demand per voxel",
        "② Pipe: Darcy-Weisbach d⁵=8λρQ²/π²R",
        "③ Duct: A=Q/v → W×H (AR≈0.75)",
        "④ Round up to next standard DN",
        "⑤ Stack: W_combined = ΣWi × 1.05",
        "⑥ Merge collinear → IfcProxy",
    ]

    fig.update_layout(**_scene_layout(
        f"Stage 8 – IFC Export: sized pipe/duct geometry  [{eg_label}]",
        "Line width ∝ DN size.  "
        "Darcy-Weisbach + Colebrook-White sizing, stacked with 5 % clearance.",
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=80, b=80),
        updatemenus=[dict(
            type="buttons",
            direction="right",
            x=0.5, xanchor="center",
            y=-0.08, yanchor="bottom",
            buttons=buttons,
            bgcolor=_SURFACE2,
            bordercolor=_BORDER,
            borderwidth=1,
            font=dict(family=_FONT_FAMILY, color=_TEXT, size=10),
            pad=dict(t=6, b=6, l=8, r=8),
        )],
    )

    fig.add_annotation(
        text="<br>".join(formula_lines),
        x=0.01, y=0.01,
        xref="paper", yref="paper",
        showarrow=False,
        align="left",
        font=dict(size=9, color=_MUTED, family=_FONT_FAMILY),
        bgcolor=_SURFACE2,
        bordercolor=_BORDER,
        borderwidth=1,
        borderpad=8,
    )
    return fig


# ===========================================================================
# Stage 9 – IFC Export Geometry (actual 3-D pipe/duct boxes)
# ===========================================================================

def _pipe_box_mesh3d(
    start:        tuple,
    end:          tuple,
    width:        float,
    height:       float,
    right_offset: float,
    color:        str,
    name:         str,
    hover:        str   = "",
    opacity:      float = 0.82,
    show_legend:  bool  = True,
    legend_group: str   = "",
) -> go.Mesh3d | None:
    """
    Oriented 3-D rectangular prism (pipe or duct box) along a segment.

    Parameters
    ----------
    start, end   : world XYZ endpoints
    width        : cross-section width (m), measured perpendicular to direction
    height       : cross-section height (m), always in world Z
    right_offset : lateral offset along the right vector for service stacking
    """
    import numpy as _np

    s = _np.array(start, dtype=float)
    e = _np.array(end,   dtype=float)
    d = e - s
    length = float(_np.linalg.norm(d))
    if length < 1e-6:
        return None

    d /= length                          # unit direction

    # Right vector: horizontal perpendicular to direction
    wz = _np.array([0.0, 0.0, 1.0])
    if abs(float(_np.dot(d, wz))) > 0.98:   # nearly vertical segment
        wz = _np.array([1.0, 0.0, 0.0])

    right = _np.cross(d, wz)
    right /= _np.linalg.norm(right)

    up = _np.array([0.0, 0.0, 1.0])     # height always in world Z

    w2 = width  / 2.0
    h2 = height / 2.0
    rc = right * right_offset            # lateral centre offset

    # 8 corners (matching _box_mesh vertex ordering for re-use of its triangles)
    # layout: 0-3 = start face, 4-7 = end face
    # within each face: (-right,-up), (+right,-up), (+right,+up), (-right,+up)
    def _c(base, wr, hu):
        return base + rc + right * wr + up * hu

    corners = [
        _c(s, -w2, -h2), _c(s, +w2, -h2), _c(s, +w2, +h2), _c(s, -w2, +h2),
        _c(e, -w2, -h2), _c(e, +w2, -h2), _c(e, +w2, +h2), _c(e, -w2, +h2),
    ]

    xs = [float(c[0]) for c in corners]
    ys = [float(c[1]) for c in corners]
    zs = [float(c[2]) for c in corners]

    # 12 triangles – 6 faces × 2
    # Start cap: 0,1,2  0,2,3
    # End cap:   4,6,5  4,7,6
    # Bottom:    0,4,5  0,5,1
    # Top:       3,2,6  3,6,7
    # Left:      0,3,7  0,7,4
    # Right:     1,5,6  1,6,2
    ti = [0,0, 4,4, 0,0, 3,3, 0,0, 1,1]
    tj = [1,2, 6,7, 4,5, 2,6, 3,7, 5,6]
    tk = [2,3, 5,6, 5,1, 6,7, 7,4, 6,2]

    return go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=ti, j=tj, k=tk,
        color=color,
        opacity=opacity,
        name=name,
        showlegend=show_legend,
        legendgroup=legend_group or name,
        hovertemplate=f"<b>{hover or name}</b><extra></extra>",
        flatshading=False,
        lighting=dict(ambient=0.85, diffuse=0.40, specular=0.05),
    )


def stage9_ifc_geometry(bundle: dict[str, Any], system: Any) -> go.Figure:
    """
    Stage 9 – IFC Export Geometry

    Shows the ACTUAL 3-D pipe and duct boxes exactly as they are written
    to the IFC file:
    • Each CollinearSegment from SectionSizer.build_all_unique_segments()
      becomes one oriented 3-D box per service.
    • Box width  = per-service section width  (W_i from sizing formula).
    • Box height = per-service section height (H_i from sizing formula).
    • Services are stacked side-by-side along the right vector with 5 %
      clearance, matching the combined bounding box in the IFC.
    • The transparent combined bounding box is also shown.
    • Hover shows: service, accumulated demand, DN/section size, length.
    • Building model shown at low opacity as spatial reference.
    """
    fig = go.Figure()
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, room_opacity=0.08, shaft_opacity=0.15,
                     floor_index=eg_floor)

    if system is None or not system.routes:
        fig.update_layout(**_scene_layout(
            f"Stage 9 – IFC Export Geometry  [{eg_label}]",
            "No system routes available"))
        return fig

    demands   = bundle.get("demands", [])
    grid      = bundle["grid"]
    z_min_eg, z_max_eg = _floor_z_range(grid, eg_floor)

    try:
        from pipe_planner.section_sizing import SectionSizer, SizerConfig

        rooms_by_guid = bundle.get("rooms_by_guid", {})
        floor_by_room = {
            guid: sp.floor_index for guid, sp in rooms_by_guid.items()
        }
        sizer    = SectionSizer(system.routes, demands, SizerConfig())
        segments = sizer.build_all_unique_segments(floor_by_room)
    except Exception as _e:
        print(f"[pipeline_visualizer] Stage 9 SectionSizer failed: {_e}", flush=True)
        fig.update_layout(**_scene_layout(
            f"Stage 9 – IFC Export Geometry  [{eg_label}]",
            f"SectionSizer unavailable: {_e}"))
        return fig

    svc_shown:  set[str] = set()
    box_shown:  set[str] = set()

    for seg in segments:
        # Filter to EG floor
        z_mid = (seg.start_xyz[2] + seg.end_xyz[2]) / 2
        if not (z_min_eg - 0.2 <= z_mid <= z_max_eg + 0.2):
            continue

        if not seg.service_breakdown:
            continue

        comb_w = seg.combined_w_m
        comb_h = seg.combined_h_m

        # ── Transparent combined bounding box ─────────────────────────────
        key_box = f"Combined box  ({round(comb_w*1000)} × {round(comb_h*1000)} mm)"
        combo_box = _pipe_box_mesh3d(
            start=seg.start_xyz,
            end=seg.end_xyz,
            width=comb_w,
            height=comb_h,
            right_offset=0.0,
            color="#AAAAAA",
            name="Combined box",
            hover=(
                f"Combined box<br>"
                f"W: {round(comb_w*1000,1)} mm  ×  H: {round(comb_h*1000,1)} mm<br>"
                f"Length: {round(seg.length_m,3)} m<br>"
                f"Services: {', '.join(seg.services)}"
            ),
            opacity=0.08,
            show_legend=("combined" not in box_shown),
            legend_group="combined_box",
        )
        if combo_box:
            fig.add_trace(combo_box)
            box_shown.add("combined")

        # ── Per-service pipe/duct boxes stacked side by side ──────────────
        svc_items = list(seg.service_breakdown.items())
        n_svcs    = len(svc_items)

        # Compute lateral offsets so services are centred within combined box
        # widths: [w0, w1, w2, …]  total = combined_w / clearance_factor ≈ combined_w/1.05
        inner_w   = comb_w / 1.05
        starts_at = -inner_w / 2   # left edge of first service box

        cursor = starts_at
        for svc, (w_m, h_m, acc_demand, unit) in svc_items:
            centre_offset = cursor + w_m / 2
            cursor += w_m

            color   = _SERVICE_COLOUR.get(svc, "#888888")
            dn_info = f"{round(w_m*1000,1)} × {round(h_m*1000,1)} mm"

            mesh = _pipe_box_mesh3d(
                start=seg.start_xyz,
                end=seg.end_xyz,
                width=w_m,
                height=h_m,
                right_offset=centre_offset,
                color=color,
                name=svc,
                hover=(
                    f"<b>{svc}</b><br>"
                    f"Cross-section: {dn_info}<br>"
                    f"Accumulated demand: {_fmt_demand(acc_demand)} {unit}<br>"
                    f"Segment length: {round(seg.length_m,3)} m<br>"
                    f"Floor: {seg.floor_index}"
                ),
                opacity=0.85,
                show_legend=(svc not in svc_shown),
                legend_group=f"svc_{svc}",
            )
            if mesh:
                fig.add_trace(mesh)
                svc_shown.add(svc)

    if not svc_shown:
        fig.add_annotation(
            text="No segments on EG floor — check SectionSizer output",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=14, color=_MUTED),
        )

    fig.update_layout(**_scene_layout(
        f"Stage 9 – IFC Export Geometry  [{eg_label}]",
        "Actual pipe/duct 3-D boxes as written to IFC.  "
        "Grey outline = combined bounding box (5 % clearance).  "
        "Coloured boxes = per-service cross-sections stacked side-by-side.",
    ))
    return fig


# ===========================================================================
# Master – generate all figures → HTML
# ===========================================================================

def generate_verification_report(
    runtime: Any,
    output_dir: str | Path = "./pipeline_figures",
) -> Path | None:
    """
    Generate a single self-contained HTML verification report covering all
    pipeline stages.  Each tab shows the raw data values so you can confirm
    every step works as intended.

    Tabs
    ----
    S1  IFC Spaces     – rooms / shafts / floors from the IFC model
    S2  Demands        – Excel demand values matched to rooms; unmatched rows
    S3  Voxel Grid     – mask voxel counts, floor bounds, grid metadata
    S4  Cost Fields    – min / max / mean / % zeros for each cost field
    S5  Route Matrix   – success rate per strategy; every failed demand listed
    S6  Scoring        – per-strategy metric table
    S7  Selected Sys.  – final selected routes with lengths and pass/fail
    S8  IFC Segments   – CollinearSegment data: accumulated demand + DN sizes
    """
    if runtime.bundle is None:
        return None

    bundle = runtime.bundle
    system = runtime.current_system
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Shared table style ────────────────────────────────────────────────────
    _HDR_FILL  = dict(color=[_SURFACE])
    _HDR_FONT  = dict(family=_FONT_FAMILY, size=10, color=_MUTED)
    _CELL_FONT = dict(family=_FONT_FAMILY, size=10, color=_TEXT)
    _CELL_FILL = dict(color=[[_SURFACE2, _BG] * 300])   # alternating rows
    _LINE      = dict(color=_BORDER, width=1)

    def _warn_color(flags: list[bool]) -> list[str]:
        """Red for True (warning), surface for False."""
        return ["rgba(183,28,28,0.12)" if f else _SURFACE2 for f in flags]

    # ═══════════════════════════════════════════════════════════════════════════
    # S1 – IFC Spaces
    # ═══════════════════════════════════════════════════════════════════════════
    floors       = bundle.get("floors", [])
    rooms        = list(bundle.get("rooms_by_guid",     {}).values())
    shafts       = list(bundle.get("shafts_by_guid",    {}).values())
    corridors    = list(bundle.get("corridors_by_guid", {}).values())

    # Floor summary
    s1_floor_hdr  = ["Floor index", "Name", "Z min (m)", "Z max (m)",
                     "Rooms", "Shafts", "Corridors"]
    s1_floor_rows = []
    for fl in sorted(floors, key=lambda f: f.floor_index):
        r_cnt = sum(1 for r in rooms     if r.floor_index == fl.floor_index)
        s_cnt = sum(1 for s in shafts    if s.floor_index == fl.floor_index)
        c_cnt = sum(1 for c in corridors if c.floor_index == fl.floor_index)
        s1_floor_rows.append([fl.floor_index, fl.name,
                               round(fl.z_min, 3), round(fl.z_max, 3),
                               r_cnt, s_cnt, c_cnt])
    s1_floor_cols = list(zip(*s1_floor_rows)) if s1_floor_rows else [[] * 7]

    # Room detail
    s1_room_warns = []
    s1_room_rows  = []
    for sp in sorted(rooms, key=lambda r: (r.floor_index, r.name)):
        area = round(sp.bbox.area_xy(), 2)
        warn = area < 0.01 or sp.floor_index < 0
        s1_room_warns.append(warn)
        s1_room_rows.append([
            sp.guid[:16], sp.name[:30], sp.space_type,
            sp.floor_index,
            round(sp.bbox.max_x - sp.bbox.min_x, 2),
            round(sp.bbox.max_y - sp.bbox.min_y, 2),
            round(sp.bbox.max_z - sp.bbox.min_z, 2),
            area,
            "⚠" if warn else "✓",
        ])
    s1_room_cols = list(zip(*s1_room_rows)) if s1_room_rows else [[] * 9]
    s1_room_fill = dict(color=[_warn_color(s1_room_warns)] * 9)

    # ═══════════════════════════════════════════════════════════════════════════
    # S2 – Demands
    # ═══════════════════════════════════════════════════════════════════════════
    demands       = bundle.get("demands", [])
    rooms_by_guid = bundle.get("rooms_by_guid", {})

    s2_warns = []
    s2_rows  = []
    for d in demands:
        zero_val = (d.value == 0.0)
        no_room  = d.room_guid not in rooms_by_guid
        warn     = zero_val or no_room
        s2_warns.append(warn)
        s2_rows.append([
            d.demand_id, d.room_name[:28], d.room_guid[:16],
            d.service, d.media_type, d.kind,
            _fmt_demand(d.value), d.unit,
            "⚠ zero" if zero_val else ("⚠ no room" if no_room else "✓"),
        ])
    s2_cols  = list(zip(*s2_rows)) if s2_rows else [[] * 9]
    s2_fill  = dict(color=[_warn_color(s2_warns)] * 9)

    # Service summary counts
    from collections import Counter
    svc_counts = Counter(d.service for d in demands)
    zero_count = sum(1 for d in demands if d.value == 0.0)

    s2_sum_rows = [[s, cnt, sum(1 for d in demands if d.service == s and d.value == 0.0)]
                   for s, cnt in sorted(svc_counts.items())]
    s2_sum_cols = list(zip(*s2_sum_rows)) if s2_sum_rows else [[], [], []]

    # ═══════════════════════════════════════════════════════════════════════════
    # S3 – Voxel Grid
    # ═══════════════════════════════════════════════════════════════════════════
    grid  = bundle["grid"]
    nx, ny, nz = grid.shape
    total_vox  = nx * ny * nz

    mask_defs_s3 = [
        ("traversable", grid.traversable_mask),
        ("room",        grid.room_mask),
        ("corridor",    grid.corridor_mask),
        ("shaft",       grid.shaft_mask),
        ("wall",        grid.wall_mask),
        ("slab",        grid.slab_mask),
        ("blocked",     grid.blocked_mask),
    ]
    s3_mask_warns = []
    s3_mask_rows  = []
    trav_count    = int(grid.traversable_mask.sum())
    for name, mask in mask_defs_s3:
        cnt    = int(mask.sum())
        pct    = round(cnt / total_vox * 100, 2) if total_vox else 0
        tpct   = round(cnt / trav_count * 100, 2) if trav_count else 0
        warn   = (cnt == 0 and name in ("traversable", "room", "shaft"))
        s3_mask_warns.append(warn)
        s3_mask_rows.append([name, f"{cnt:,}", f"{pct} %", f"{tpct} %",
                              "⚠ EMPTY" if warn else "✓"])
    s3_mask_cols = list(zip(*s3_mask_rows))
    s3_mask_fill = dict(color=[_warn_color(s3_mask_warns)] * 5)

    # Floor bounds
    s3_floor_rows = []
    for fi, (z0, z1) in sorted(grid.floor_bounds.items()):
        label = _floor_label(bundle, fi)
        s3_floor_rows.append([fi, label, round(z0, 3), round(z1, 3), round(z1-z0, 3)])
    s3_floor_cols = list(zip(*s3_floor_rows)) if s3_floor_rows else [[], [], [], [], []]

    # ═══════════════════════════════════════════════════════════════════════════
    # S4 – Cost Fields
    # ═══════════════════════════════════════════════════════════════════════════
    trav = grid.traversable_mask.astype(bool)
    cost_defs = [
        ("wall_distance",     grid.wall_distance),
        ("corridor_distance", grid.corridor_distance),
        ("ceiling_score",     grid.ceiling_score),
    ]
    s4_warns = []
    s4_rows  = []
    for name, field in cost_defs:
        vals      = field[trav].astype(float)
        n         = len(vals)
        mn, mx    = (float(vals.min()), float(vals.max())) if n else (0, 0)
        mean      = float(vals.mean()) if n else 0
        std       = float(vals.std())  if n else 0
        zeros_pct = round(float((vals == 0).sum()) / n * 100, 1) if n else 0
        warn      = (mx == 0)
        s4_warns.append(warn)
        s4_rows.append([name, round(mn, 3), round(mx, 3),
                        round(mean, 3), round(std, 3),
                        f"{zeros_pct} %", "⚠ ALL ZERO" if warn else "✓"])
    s4_cols = list(zip(*s4_rows))
    s4_fill = dict(color=[_warn_color(s4_warns)] * 7)

    # ═══════════════════════════════════════════════════════════════════════════
    # S5 – Route Matrix
    # ═══════════════════════════════════════════════════════════════════════════
    matrix_rows = bundle.get("route_matrix_rows", [])
    strategies  = sorted({r.get("strategy", "") for r in matrix_rows})
    demands_map = {d.demand_id: d for d in demands}

    s5_strat_rows  = []
    s5_strat_rates = []   # numeric, for warning logic
    for strat in strategies:
        sub      = [r for r in matrix_rows if r.get("strategy") == strat]
        ok       = sum(1 for r in sub if r.get("success"))
        fail     = len(sub) - ok
        rate_num = round(ok / len(sub) * 100, 1) if sub else 0.0
        s5_strat_rates.append(rate_num)
        s5_strat_rows.append([strat, len(sub), ok, fail, f"{rate_num} %",
                               "⚠" if rate_num < 80 else "✓"])
    s5_strat_cols  = list(zip(*s5_strat_rows)) if s5_strat_rows else [[], [], [], [], [], []]
    s5_strat_warns = [r < 80 for r in s5_strat_rates]
    s5_strat_fill  = dict(color=[_warn_color(s5_strat_warns)] * 6)

    # Failed demand detail (unique demand_ids that never succeeded in any strategy)
    success_ids = {r.get("demand_id") for r in matrix_rows if r.get("success")}
    all_ids     = {r.get("demand_id") for r in matrix_rows}
    never_ok    = all_ids - success_ids
    s5_fail_rows = []
    for did in sorted(never_ok):
        d = demands_map.get(did)
        s5_fail_rows.append([did, d.room_name[:28] if d else "?", d.service if d else "?",
                              d.room_guid[:16] if d else "?"])
    s5_fail_cols = list(zip(*s5_fail_rows)) if s5_fail_rows else [[], [], [], []]

    # ═══════════════════════════════════════════════════════════════════════════
    # S6 – Scoring
    # ═══════════════════════════════════════════════════════════════════════════
    s6_rows = []
    try:
        import pandas as pd
        df = pd.DataFrame(matrix_rows)
        total_demands_count = df["demand_id"].nunique()
        for strat in strategies:
            sub  = df[df["strategy"] == strat]
            ok   = sub[sub["success"] == True]
            best = ok.sort_values("score").drop_duplicates("demand_id")
            s6_rows.append([
                strat,
                round(float(best["score"].mean()), 3)        if not best.empty else "–",
                f"{round(len(best)/max(total_demands_count,1)*100, 1)} %",
                round(float(best["length_m"].sum()), 1)      if "length_m"       in best.columns and not best.empty else "–",
                int(best["bend_count"].sum())                 if "bend_count"     in best.columns and not best.empty else "–",
                int(best["wall_crossings"].sum())             if "wall_crossings" in best.columns and not best.empty else "–",
            ])
    except Exception:
        pass
    s6_cols = list(zip(*s6_rows)) if s6_rows else [[], [], [], [], [], []]

    # ═══════════════════════════════════════════════════════════════════════════
    # S7 – Selected System
    # ═══════════════════════════════════════════════════════════════════════════
    s7_warns = []
    s7_rows  = []
    if system:
        for route in system.routes:
            d    = demands_map.get(route.demand_id)
            warn = not route.success
            s7_warns.append(warn)
            length = round(route.metrics.get("length_m", 0), 2) if route.metrics else 0
            s7_rows.append([
                route.demand_id,
                d.room_name[:28] if d else "?",
                route.service,
                route.shaft_name[:20] if route.shaft_name else "–",
                route.strategy,
                length,
                "✓" if route.success else "⚠ FAILED",
                route.message[:40] if not route.success and route.message else "",
            ])
    s7_cols = list(zip(*s7_rows)) if s7_rows else [[] * 8]
    s7_fill = dict(color=[_warn_color(s7_warns)] * 8)

    # ═══════════════════════════════════════════════════════════════════════════
    # S8 – IFC Segments (exact SectionSizer output)
    # ═══════════════════════════════════════════════════════════════════════════
    s8_warns = []
    s8_rows  = []
    try:
        from pipe_planner.section_sizing import SectionSizer, SizerConfig
        sizer8 = SectionSizer(system.routes if system else [], demands, SizerConfig())
        rooms_by_guid_s8 = bundle.get("rooms_by_guid", {})
        fbr    = {guid: sp.floor_index for guid, sp in rooms_by_guid_s8.items()}
        segs8  = sizer8.build_all_unique_segments(fbr)
        for seg in segs8:
            svcs = ", ".join(seg.services)
            for svc, (w_m, h_m, acc, unit) in seg.service_breakdown.items():
                warn = (acc == 0.0)
                s8_warns.append(warn)
                s8_rows.append([
                    seg.floor_index,
                    svc,
                    _fmt_demand(acc), unit,
                    round(w_m * 1000, 1),
                    round(h_m * 1000, 1),
                    round(seg.combined_w_m * 1000, 1),
                    round(seg.combined_h_m * 1000, 1),
                    round(seg.length_m, 3),
                    "⚠ zero demand" if warn else "✓",
                ])
    except Exception as _e:
        s8_rows = [["SectionSizer error", str(_e), "", "", "", "", "", "", "", ""]]
        s8_warns = [True]
    s8_cols = list(zip(*s8_rows)) if s8_rows else [[] * 10]
    s8_fill = dict(color=[_warn_color(s8_warns)] * 10)

    # ═══════════════════════════════════════════════════════════════════════════
    # Assemble Plotly figure with one table per tab
    # ═══════════════════════════════════════════════════════════════════════════
    fig = go.Figure()

    def _tbl(header_vals, col_vals, fill=None, warn_fill=None):
        return go.Table(
            header=dict(values=header_vals, fill=_HDR_FILL, font=_HDR_FONT,
                        line=_LINE, align="left", height=26),
            cells=dict(values=list(col_vals),
                       fill=fill or _CELL_FILL,
                       font=_CELL_FONT, line=_LINE,
                       align="left", height=22),
        )

    # All tables – will be shown/hidden by tab buttons
    tables = [
        # S1a: floor summary
        _tbl(["Floor", "Name", "Z min", "Z max", "Rooms", "Shafts", "Corridors"],
             s1_floor_cols),
        # S1b: room detail
        _tbl(["GUID", "Name", "Type", "Floor", "ΔX m", "ΔY m", "ΔZ m", "Area m²", "OK"],
             s1_room_cols, fill=s1_room_fill),
        # S2a: demand detail
        _tbl(["ID", "Room name", "Room GUID", "Service", "Media", "Kind",
              "Value", "Unit", "Check"],
             s2_cols, fill=s2_fill),
        # S2b: service summary
        _tbl(["Service", "Total demands", "Zero-value count"], s2_sum_cols),
        # S3a: mask counts
        _tbl(["Mask", "Active voxels", "% of grid", "% of traversable", "Check"],
             s3_mask_cols, fill=s3_mask_fill),
        # S3b: floor bounds
        _tbl(["Floor idx", "Name", "Z min", "Z max", "Height"], s3_floor_cols),
        # S4: cost fields
        _tbl(["Field", "Min", "Max", "Mean", "Std dev", "% zeros", "Check"],
             s4_cols, fill=s4_fill),
        # S5a: strategy success
        _tbl(["Strategy", "Total", "Success", "Failed", "Rate", "Check"],
             s5_strat_cols, fill=s5_strat_fill),
        # S5b: never-routed demands
        _tbl(["Demand ID", "Room", "Service", "Room GUID"], s5_fail_cols),
        # S6: scoring
        _tbl(["Strategy", "Mean score", "Coverage", "Total length m",
              "Bends", "Wall crossings"],
             s6_cols),
        # S7: selected system routes
        _tbl(["Demand ID", "Room", "Service", "Shaft", "Strategy",
              "Length m", "Status", "Message"],
             s7_cols, fill=s7_fill),
        # S8: IFC segments
        _tbl(["Floor", "Service", "Accum. demand", "Unit",
              "W mm", "H mm", "Box W mm", "Box H mm", "Length m", "Check"],
             s8_cols, fill=s8_fill),
    ]

    for t in tables:
        t.visible = False
        fig.add_trace(t)

    # Make first table visible by default
    fig.data[0].visible = True

    # Tab definitions: (button label, list of visible trace indices)
    tabs = [
        ("S1 Floors",     [0]),
        ("S1 Rooms",      [1]),
        ("S2 Demands",    [2]),
        ("S2 Summary",    [3]),
        ("S3 Masks",      [4]),
        ("S3 Floors",     [5]),
        ("S4 Cost",       [6]),
        ("S5 Strategies", [7]),
        ("S5 Failed",     [8]),
        ("S6 Scoring",    [9]),
        ("S7 System",     [10]),
        ("S8 Segments",   [11]),
    ]

    buttons = []
    for label, visible_indices in tabs:
        vis = [i in visible_indices for i in range(len(tables))]
        buttons.append(dict(
            label=label,
            method="update",
            args=[{"visible": vis},
                  {"title": {"text": f"NEXARA Pipeline Verification  ·  {label}",
                              "x": 0.5}}],
        ))

    # Warn counts for badge display
    s1_w = sum(s1_room_warns)
    s2_w = sum(s2_warns)
    s3_w = sum(s3_mask_warns)
    s4_w = sum(s4_warns)
    s5_w = len(s5_fail_rows)
    s7_w = sum(s7_warns)
    s8_w = sum(s8_warns)
    total_w = s1_w + s2_w + s3_w + s4_w + s5_w + s7_w + s8_w

    summary_text = (
        f"<b>Verification summary</b>  ·  "
        f"Rooms: {len(rooms)}  ·  Shafts: {len(shafts)}  ·  "
        f"Demands: {len(demands)}  (zero-value: {zero_count})  ·  "
        f"Strategies: {len(strategies)}  ·  "
        f"Never routed: {len(never_ok)}  ·  "
        f"Warnings: {'<span style=\"color:#B71C1C\">' + str(total_w) + '</span>' if total_w else '<span style=\"color:#2E7D32\">0 ✓</span>'}"
    )

    fig.update_layout(
        title=dict(text="NEXARA Pipeline Verification  ·  S1 Floors", x=0.5,
                   font=dict(family=_FONT_FAMILY, size=14, color=_TEXT)),
        paper_bgcolor=_SURFACE,
        font=dict(family=_FONT_FAMILY, size=11, color=_TEXT),
        height=820,
        margin=dict(l=20, r=20, t=110, b=30),
        updatemenus=[dict(
            type="buttons",
            direction="right",
            x=0.5, xanchor="center",
            y=1.07, yanchor="top",
            buttons=buttons,
            bgcolor=_SURFACE2,
            bordercolor=_BORDER,
            borderwidth=1,
            font=dict(family=_FONT_FAMILY, color=_TEXT, size=9),
            pad=dict(t=4, b=4, l=6, r=6),
        )],
        annotations=[dict(
            text=summary_text,
            x=0.5, y=-0.02,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(family=_FONT_FAMILY, size=10, color=_TEXT),
            bgcolor=_SURFACE2,
            bordercolor=_BORDER,
            borderwidth=1,
            borderpad=8,
        )],
    )

    path = _save_html(fig, output_dir / "00_verification_report.html")
    print(f"  [pipeline_visualizer] verification report → {path}", flush=True)
    return path


def _segment_box_mesh3d(
    start:        tuple[float, float, float],
    end:          tuple[float, float, float],
    width_m:      float,
    height_m:     float,
    color:        str,
    name:         str,
    hover:        str   = "",
    opacity:      float = 0.85,
    show_legend:  bool  = True,
    legend_group: str   = "",
) -> go.Mesh3d | None:
    """
    3-D box representing the extruded cross-section of one pipe / duct segment.

    The box is width_m × height_m in cross-section, oriented so that:
    • Width  runs perpendicular to the segment direction in the horizontal plane.
    • Height runs vertically (world Z).
    For vertical shafts, width runs along world X.
    """
    s = np.array(start, dtype=float)
    e = np.array(end,   dtype=float)
    vec = e - s
    length = float(np.linalg.norm(vec))
    if length < 1e-6:
        return None

    direction = vec / length

    # Local right: horizontal and perpendicular to direction
    world_up = np.array([0.0, 0.0, 1.0])
    right_raw = np.cross(world_up, direction)
    r_norm = float(np.linalg.norm(right_raw))
    if r_norm < 1e-6:
        local_right = np.array([1.0, 0.0, 0.0])   # vertical segment
    else:
        local_right = right_raw / r_norm

    local_up = np.cross(direction, local_right)
    local_up = local_up / np.linalg.norm(local_up)

    hw = width_m  / 2.0
    hh = height_m / 2.0

    # 4 corner offsets in cross-section
    corners = [
        -hw * local_right - hh * local_up,
        +hw * local_right - hh * local_up,
        +hw * local_right + hh * local_up,
        -hw * local_right + hh * local_up,
    ]

    # 8 vertices: 4 at start, 4 at end
    verts = np.array([s + c for c in corners] + [e + c for c in corners])
    xs = verts[:, 0].tolist()
    ys = verts[:, 1].tolist()
    zs = verts[:, 2].tolist()

    # 12 triangles (6 faces × 2), vertices: start = 0-3, end = 4-7
    ti = [0, 2, 4, 6,  0, 1,  1, 5,  2, 6,  3, 7]
    tj = [1, 3, 5, 7,  4, 2,  2, 6,  3, 7,  0, 4]
    tk = [2, 0, 6, 4,  1, 5,  5, 2,  6, 3,  7, 3]

    return go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=ti, j=tj, k=tk,
        color=color,
        opacity=opacity,
        name=name,
        showlegend=show_legend,
        legendgroup=legend_group or name,
        flatshading=False,
        lighting=dict(ambient=0.9, diffuse=0.3, specular=0.0),
        hovertemplate=f"<b>{hover or name}</b><extra></extra>",
    )


# ===========================================================================
# Stage 9 – IFC Export Geometry (actual sized pipe/duct boxes)
# ===========================================================================

def stage9_ifc_geometry(bundle: dict[str, Any], system: Any) -> go.Figure:
    """
    Shows the actual cross-section geometry that is written to the IFC file.

    Each CollinearSegment from SectionSizer is rendered as a 3-D box with the
    correct width × height from the sizing calculation.  Multiple services at
    the same segment are shown side-by-side (stacked horizontally) exactly as
    the IFC exporter places them.

    The building model is shown at low opacity as context.
    """
    fig = go.Figure()
    eg_floor = _find_eg_floor(bundle)
    eg_label = _floor_label(bundle, eg_floor)
    _add_building_bg(fig, bundle, room_opacity=0.08, shaft_opacity=0.15,
                     floor_index=eg_floor)

    if system is None or not system.routes:
        fig.update_layout(**_scene_layout(
            f"Stage 9 – IFC Export Geometry  [{eg_label}]",
            "No system routes available",
        ))
        return fig

    demands = bundle.get("demands", [])
    z_min_eg, z_max_eg = _floor_z_range(bundle["grid"], eg_floor)

    try:
        from pipe_planner.section_sizing import SectionSizer, SizerConfig
        rooms_by_guid = bundle.get("rooms_by_guid", {})
        floor_by_room = {guid: sp.floor_index for guid, sp in rooms_by_guid.items()}
        sizer    = SectionSizer(system.routes, demands, SizerConfig())
        segments = sizer.build_all_unique_segments(floor_by_room)
    except Exception as exc:
        fig.update_layout(**_scene_layout(
            f"Stage 9 – IFC Export Geometry  [{eg_label}]",
            f"SectionSizer failed: {exc}",
        ))
        return fig

    svc_shown:    set[str] = set()
    seg_count     = 0
    total_w_max   = 0.0

    for seg in segments:
        # Filter to EG floor z-band
        z_mid = (seg.start_xyz[2] + seg.end_xyz[2]) / 2
        if not (z_min_eg - 0.2 <= z_mid <= z_max_eg + 0.2):
            continue
        if not seg.service_breakdown:
            continue

        comb_w = seg.combined_w_m
        comb_h = seg.combined_h_m
        total_w_max = max(total_w_max, comb_w)

        # Direction and local right for side-by-side placement
        s = np.array(seg.start_xyz, dtype=float)
        e = np.array(seg.end_xyz,   dtype=float)
        vec = e - s
        length = float(np.linalg.norm(vec))
        if length < 1e-6:
            continue

        direction = vec / length
        world_up  = np.array([0.0, 0.0, 1.0])
        right_raw = np.cross(world_up, direction)
        r_norm    = float(np.linalg.norm(right_raw))
        local_right = right_raw / r_norm if r_norm > 1e-6 else np.array([1.0, 0.0, 0.0])

        # Place services side-by-side starting from the left edge of combined box
        svc_list    = list(seg.service_breakdown.items())
        x_offset    = -comb_w / 2.0   # start at left edge of combined box

        for svc, (w_m, h_m, acc_demand, unit) in svc_list:
            color = _SERVICE_COLOUR.get(svc, "#888888")

            # Centre of this service's box along the local right axis
            centre_offset = x_offset + w_m / 2.0
            x_offset     += w_m   # advance for next service

            # Offset start/end points
            offset_vec = centre_offset * local_right
            seg_start  = tuple(s + offset_vec)
            seg_end    = tuple(e + offset_vec)

            hover = (
                f"<b>{svc}</b><br>"
                f"W × H: {round(w_m*1000,1)} × {round(h_m*1000,1)} mm<br>"
                f"Combined box: {round(comb_w*1000,1)} × {round(comb_h*1000,1)} mm<br>"
                f"Accumulated: {_fmt_demand(acc_demand)} {unit}<br>"
                f"Length: {round(seg.length_m, 3)} m"
            )

            mesh = _segment_box_mesh3d(
                start=seg_start,
                end=seg_end,
                width_m=w_m,
                height_m=h_m,
                color=color,
                name=svc,
                hover=hover,
                opacity=0.85,
                show_legend=(svc not in svc_shown),
                legend_group=f"geo_{svc}",
            )
            if mesh is not None:
                fig.add_trace(mesh)
                svc_shown.add(svc)
                seg_count += 1

    fig.update_layout(**_scene_layout(
        f"Stage 9 – IFC Export Geometry  [{eg_label}]",
        f"{seg_count} segment boxes · services: {', '.join(sorted(svc_shown))}  "
        f"· max combined width: {round(total_w_max*1000,0):.0f} mm  "
        f"· line width ∝ DN size",
    ))
    return fig


def generate_pipeline_figures(
    runtime: Any,
    output_dir: str | Path = "./pipeline_figures",
) -> list[Path]:
    """
    Render all pipeline stages and save each as a self-contained HTML file.
    Also generates 00_verification_report.html with full data tables.
    Called automatically by PlannerRuntime.build_from_files() after routing.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if runtime.bundle is None:
        print("[pipeline_visualizer] skipped – no bundle loaded.", flush=True)
        return []

    bundle = runtime.bundle
    system = runtime.current_system

    stages = [
        ("01_ifc_spaces_3d",      lambda: stage1_ifc_spaces_3d(bundle)),
        ("02_demands",            lambda: stage2_demands(bundle)),
        ("03_voxel_grid",         lambda: stage3_voxel_grid(bundle)),
        ("04_cost_field",         lambda: stage4_cost_field(bundle)),
        ("05_route_variants",     lambda: stage5_route_variants(bundle)),
        ("05b_strategy_compare",  lambda: stage5b_strategy_grid_comparison(bundle)),
        ("06_scoring",            lambda: stage6_scoring(bundle)),
        ("07_selected_system",    lambda: stage7_selected_system(bundle, system)),
        ("08_ifc_export_sizes",   lambda: stage8_ifc_export_sizes(bundle, system)),
        ("09_ifc_geometry",       lambda: stage9_ifc_geometry(bundle, system)),
    ]

    saved: list[Path] = []
    for filename, builder in stages:
        print(f"  [pipeline_visualizer] rendering {filename} …", flush=True)
        try:
            fig  = builder()
            path = _save_html(fig, output_dir / f"{filename}.html")
            saved.append(path)
            print(f"    → {path}", flush=True)
        except Exception as exc:
            import traceback
            print(f"    ✗ {filename} failed: {exc}", flush=True)
            traceback.print_exc()

    # Verification report
    try:
        vpath = generate_verification_report(runtime, output_dir)
        if vpath:
            saved.insert(0, vpath)
    except Exception as exc:
        import traceback
        print(f"    ✗ verification report failed: {exc}", flush=True)
        traceback.print_exc()

    print(
        f"[pipeline_visualizer] done – "
        f"{len(saved)} files saved to {output_dir}",
        flush=True,
    )
    return saved


# ===========================================================================
# Convenience – render one stage without saving
# ===========================================================================

def render_stage(stage_name: str, runtime: Any) -> go.Figure:
    """Render a single stage by name and return the Plotly figure."""
    bundle = runtime.bundle
    system = runtime.current_system
    dispatch = {
        "ifc_spaces":      lambda: stage1_ifc_spaces_3d(bundle),
        "demands":         lambda: stage2_demands(bundle),
        "voxel_grid":      lambda: stage3_voxel_grid(bundle),
        "cost_field":      lambda: stage4_cost_field(bundle),
        "route_variants":  lambda: stage5_route_variants(bundle),
        "strategy_grid":   lambda: stage5b_strategy_grid_comparison(bundle),
        "scoring":         lambda: stage6_scoring(bundle),
        "selected_system": lambda: stage7_selected_system(bundle, system),
        "ifc_sizes":       lambda: stage8_ifc_export_sizes(bundle, system),
        "ifc_geometry":    lambda: stage9_ifc_geometry(bundle, system),
    }
    if stage_name not in dispatch:
        raise ValueError(
            f"Unknown stage '{stage_name}'. Available: {sorted(dispatch)}"
        )
    return dispatch[stage_name]()


# ===========================================================================
# CLI entry point – run this file directly to generate figures
# ===========================================================================
#
# Usage examples
# --------------
#
# Full pipeline (IFC + Excel → route → figures):
#   python pipeline_visualizer.py \
#       --ifc    /path/to/model.ifc \
#       --excel  /path/to/demands.xlsx \
#       --output ./figures
#
# Re-render figures from an already-calculated session folder
# (skips routing – much faster):
#   python pipeline_visualizer.py \
#       --session /path/to/uploads/outputs \
#       --output  ./figures
#
# Single stage only:
#   python pipeline_visualizer.py \
#       --ifc model.ifc --excel demands.xlsx \
#       --stage voxel_grid
#
# Optional flags:
#   --workers 4          number of routing worker processes (default: 4)
#   --open               open every HTML figure in the browser after saving

if __name__ == "__main__":
    import argparse
    import sys
    import os
    import webbrowser

    # Make sure `backend/` is on the path so imports work when running
    # the script directly from the pipe_planner/ sub-directory.
    _THIS_DIR    = Path(__file__).resolve().parent          # backend/pipe_planner/
    _BACKEND_DIR = _THIS_DIR.parent                         # backend/
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))

    parser = argparse.ArgumentParser(
        prog="pipeline_visualizer",
        description=(
            "NEXARA pipeline visualizer – generates interactive 3-D Plotly HTML\n"
            "figures for every stage of the routing pipeline.\n\n"
            "Run with --ifc + --excel to calculate routes AND render figures.\n"
            "Run with --session to re-render figures from an existing session."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input sources (mutually exclusive modes)
    src = parser.add_argument_group("input (pick one mode)")
    src.add_argument(
        "--ifc", metavar="PATH",
        help="Path to the IFC model file  (.ifc)",
    )
    src.add_argument(
        "--excel", metavar="PATH",
        help="Path to the demands Excel file  (.xlsx)",
    )
    src.add_argument(
        "--session", metavar="DIR",
        help=(
            "Path to an existing session outputs directory that already contains "
            "bundle data (skips routing, just re-renders the figures)."
        ),
    )

    # Options
    parser.add_argument(
        "--output", "-o", metavar="DIR",
        default="./pipeline_figures",
        help="Directory where HTML figures are saved  (default: ./pipeline_figures)",
    )
    parser.add_argument(
        "--workers", "-w", type=int, default=4,
        help="Routing worker processes  (default: 4, ignored with --session)",
    )
    parser.add_argument(
        "--stage", "-s", metavar="NAME",
        choices=[
            "ifc_spaces", "demands", "voxel_grid", "cost_field",
            "route_variants", "strategy_grid", "scoring",
            "selected_system", "ifc_sizes",
        ],
        help="Render only this one stage instead of all nine",
    )
    parser.add_argument(
        "--open", action="store_true",
        help="Open every saved HTML file in the default browser after rendering",
    )
    parser.add_argument(
        "--config", metavar="PATH",
        help="Optional path to a NEXARA config JSON to use during routing",
    )

    args = parser.parse_args()

    # ── Validate arguments ────────────────────────────────────────────────
    if not args.session and not (args.ifc and args.excel):
        parser.error(
            "Provide either --ifc + --excel  OR  --session.\n"
            "Run with -h for usage examples."
        )

    output_dir = Path(args.output).resolve()

    # ── Import PlannerRuntime ─────────────────────────────────────────────
    try:
        from planner_runtime import PlannerRuntime
    except ImportError as e:
        print(
            f"\n✗  Could not import PlannerRuntime: {e}\n"
            f"   Make sure you are running from inside the backend/ directory\n"
            f"   or that backend/ is on your PYTHONPATH.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Mode A: full pipeline (IFC + Excel → route → render) ─────────────
    if args.ifc and args.excel:
        ifc_path   = str(Path(args.ifc).resolve())
        excel_path = str(Path(args.excel).resolve())

        for label, p in [("IFC", ifc_path), ("Excel", excel_path)]:
            if not Path(p).exists():
                print(f"✗  {label} file not found: {p}", file=sys.stderr)
                sys.exit(1)

        # Scratch folder for runtime temp files
        uploads_dir = output_dir / "_session"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        runtime = PlannerRuntime()

        # Load optional config
        if args.config:
            config_path = str(Path(args.config).resolve())
            if not Path(config_path).exists():
                print(f"✗  Config file not found: {config_path}", file=sys.stderr)
                sys.exit(1)
            print(f"  Loading config: {config_path}")
            runtime.load_config_json(config_path)

        print(
            f"\n  NEXARA pipeline visualizer\n"
            f"  IFC:    {ifc_path}\n"
            f"  Excel:  {excel_path}\n"
            f"  Output: {output_dir}\n"
            f"  Workers: {args.workers}\n"
        )

        print("  [1/2] Running routing pipeline …")
        try:
            # build_from_files will call generate_pipeline_figures automatically
            # via the auto-trigger in planner_runtime.py.
            # We override output_dir so figures land where the user asked.
            _original_gen = None
            try:
                import pipe_planner.pipeline_visualizer as _pv_mod
                _original_gen = _pv_mod.generate_pipeline_figures

                def _patched_gen(rt: Any, output_dir: str | Path = "./pipeline_figures") -> list[Path]:
                    return _original_gen(rt, output_dir=output_dir)

                # Monkey-patch so the auto-trigger uses our output_dir
                import planner_runtime as _rt_mod
                _real_gen = _rt_mod.__dict__.get("generate_pipeline_figures")
            except Exception:
                pass

            runtime.build_from_files(
                ifc_path=ifc_path,
                excel_path=excel_path,
                uploads_dir=str(uploads_dir),
                workers=args.workers,
            )
        except Exception as exc:
            import traceback
            print(f"\n✗  Routing failed:\n", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)

        print("  [2/2] Rendering figures …")
        if args.stage:
            print(f"        (single stage: {args.stage})")
            try:
                fig  = render_stage(args.stage, runtime)
                path = _save_html(fig, output_dir / f"{args.stage}.html")
                saved = [path]
            except Exception as exc:
                print(f"✗  Stage '{args.stage}' failed: {exc}", file=sys.stderr)
                sys.exit(1)
        else:
            saved = generate_pipeline_figures(runtime, output_dir=output_dir)

    # ── Mode B: re-render from an existing session folder ─────────────────
    else:
        session_dir = Path(args.session).resolve()
        if not session_dir.exists():
            print(f"✗  Session directory not found: {session_dir}", file=sys.stderr)
            sys.exit(1)

        print(
            f"\n  NEXARA pipeline visualizer  (re-render mode)\n"
            f"  Session: {session_dir}\n"
            f"  Output:  {output_dir}\n"
        )

        runtime = PlannerRuntime()

        # Try loading bundle from session artefacts
        bundle_candidates = list(session_dir.glob("bundle*.json")) + \
                            list(session_dir.glob("system_defaults.json"))

        if not bundle_candidates:
            print(
                f"✗  No bundle JSON found in {session_dir}.\n"
                f"   Run with --ifc + --excel to create a fresh session.",
                file=sys.stderr,
            )
            sys.exit(1)

        # PlannerRuntime may expose a load_bundle method; fall back gracefully
        if hasattr(runtime, "load_bundle_json"):
            try:
                runtime.load_bundle_json(str(session_dir))
                print("  Bundle loaded from session directory.")
            except Exception as exc:
                print(f"✗  Could not load bundle: {exc}", file=sys.stderr)
                sys.exit(1)
        else:
            print(
                "  ⚠  load_bundle_json not available on this PlannerRuntime.\n"
                "     Provide --ifc + --excel to run the full pipeline instead.",
                file=sys.stderr,
            )
            sys.exit(1)

        print("  Rendering figures …")
        if args.stage:
            try:
                fig  = render_stage(args.stage, runtime)
                path = _save_html(fig, output_dir / f"{args.stage}.html")
                saved = [path]
            except Exception as exc:
                print(f"✗  Stage '{args.stage}' failed: {exc}", file=sys.stderr)
                sys.exit(1)
        else:
            saved = generate_pipeline_figures(runtime, output_dir=output_dir)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n  ✓  {len(saved)} figure(s) saved to: {output_dir}\n")
    for p in saved:
        print(f"     {p.name}")

    if args.open and saved:
        print("\n  Opening in browser …")
        for p in saved:
            webbrowser.open(p.as_uri())

    print()