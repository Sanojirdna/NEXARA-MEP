from __future__ import annotations

from collections import defaultdict
from typing import Any

from pipe_planner.config import ProjectConfig
from pipe_planner.floor_detection import assign_spaces_to_floors, build_floor_bands_from_space_ranges, build_floor_bands_from_storeys
from pipe_planner.models import BBox, FloorBand, ObstacleRecord, SpaceRecord
import numpy as np


def load_ifc_model_data(ifc_path: str, config: ProjectConfig) -> dict[str, Any]:
    """Read spaces, floor bands, and obstacles from an IFC file.

    Args:
        ifc_path: IFC file path.
        config: Project configuration.

    Returns:
        Dictionary with spaces, floors, obstacles, and helper maps.
    """
    try:
        import ifcopenshell
        import ifcopenshell.geom
        import ifcopenshell.util.shape
        import ifcopenshell.util.unit
        import ifcopenshell.util.placement
    except ImportError as exc:
        raise RuntimeError(
            "IfcOpenShell is required. Install it with: pip install ifcopenshell"
        ) from exc

    model = ifcopenshell.open(ifc_path)
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)

    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("disable-opening-subtractions", True)
    settings.set("no-normals", True)

    spaces: list[SpaceRecord] = []
    obstacles: list[ObstacleRecord] = []
    storey_data: list[tuple[str, float]] = []

    for storey in model.by_type("IfcBuildingStorey"):
        try:
            elevation = ifcopenshell.util.placement.get_storey_elevation(storey) * unit_scale
        except Exception:
            elevation = 0.0
        storey_data.append((str(getattr(storey, "Name", "") or ""), float(elevation)))

    for space in model.by_type("IfcSpace"):
        bbox, footprint = _safe_bbox_and_footprint(space, settings, unit_scale)
        if bbox is None:
            continue

        name = str(getattr(space, "Name", "") or "")
        long_name = str(getattr(space, "LongName", "") or "")

        space_type = classify_space(name, long_name, config)
        spaces.append(
            SpaceRecord(
                guid=str(getattr(space, "GlobalId", "") or ""),
                name=name,
                long_name=long_name,
                space_type=space_type,
                bbox=bbox,
                source_type=space.is_a(),
                footprint=footprint,
            )
        )

    floors = build_floor_bands_from_storeys(storey_data, spaces)
    if not floors:
        floors = build_floor_bands_from_space_ranges(spaces)

    assign_spaces_to_floors(spaces, floors)

    obstacle_specs = [
        ("IfcWall", "wall", True, config.penalty_config.wall_cross_penalty),
        ("IfcWallStandardCase", "wall", True, config.penalty_config.wall_cross_penalty),
        ("IfcSlab", "slab", True, config.penalty_config.slab_cross_penalty),
        ("IfcColumn", "column", False, config.penalty_config.blocked_penalty),
        ("IfcBeam", "beam", False, config.penalty_config.blocked_penalty),
        ("IfcCurtainWall", "wall", True, config.penalty_config.wall_cross_penalty),
        ("IfcBuildingElementProxy", "proxy", False, config.penalty_config.blocked_penalty),
    ]

    seen_pairs: set[tuple[str, str]] = set()
    for ifc_type, category, crossable, penalty in obstacle_specs:
        for element in model.by_type(ifc_type):
            guid = str(getattr(element, "GlobalId", "") or "")
            pair = (guid, ifc_type)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            bbox = _safe_bbox_from_element(element, settings, unit_scale)
            if bbox is None:
                continue

            obstacles.append(
                ObstacleRecord(
                    guid=guid,
                    name=str(getattr(element, "Name", "") or ""),
                    category=category,
                    bbox=bbox,
                    crossable=crossable,
                    penalty=penalty,
                    source_type=ifc_type,
                )
            )

    spaces_by_guid = {space.guid: space for space in spaces if space.guid}
    spaces_by_name = {}
    for space in spaces:
        key = normalize_room_name(space.name or space.long_name)
        if key:
            spaces_by_name[key] = space
        long_key = normalize_room_name(space.long_name)
        if long_key:
            spaces_by_name[long_key] = space

    shafts = [space for space in spaces if space.space_type == "shaft"]
    rooms = [space for space in spaces if space.space_type == "room"]
    corridors = [space for space in spaces if space.space_type == "corridor"]
    technical_rooms = [space for space in spaces if space.space_type == "technical_room"]

    return {
        "spaces": spaces,
        "rooms": rooms,
        "corridors": corridors,
        "shafts": shafts,
        "technical_rooms": technical_rooms,
        "obstacles": obstacles,
        "floors": floors,
        "spaces_by_guid": spaces_by_guid,
        "spaces_by_name": spaces_by_name,
        "unit_scale": unit_scale,
    }


def classify_space(name: str, long_name: str, config: ProjectConfig) -> str:
    """Classify an IFC space by name.

    Args:
        name: IFC Name.
        long_name: IFC LongName.
        config: Project configuration.

    Returns:
        technical_room, shaft, corridor, or room.
    """
    text = f"{name} {long_name}".lower()

    # Shafts first — "Technik Schacht" is a shaft, not a technical room.
    for keyword in config.keyword_config.shaft_keywords:
        if keyword in text:
            return "shaft"

    # Technical rooms (Technikzentrale, Zentrale, Technik …) — checked before
    # corridor so "Technikraum" does not accidentally match a corridor keyword.
    for keyword in config.keyword_config.technical_room_keywords:
        if keyword in text:
            return "technical_room"

    for keyword in config.keyword_config.corridor_keywords:
        if keyword in text:
            return "corridor"

    return "room"


def normalize_room_name(text: str) -> str:
    """Normalize a name for lookups.

    Args:
        text: Input text.

    Returns:
        Normalized text.
    """
    return " ".join(str(text or "").strip().lower().split())


def _boundary_polygon_from_faces(
    verts_scaled: "np.ndarray",
    faces_flat: list[int],
    z_min: float,
) -> list[tuple[float, float]]:
    """
    Extract the true 2-D boundary polygon of a tessellated solid's bottom face.

    Algorithm
    ---------
    1. Select all triangles whose average Z is within 10 % of element height
       from z_min  (= bottom-face triangles).
    2. Find boundary edges: edges that appear in exactly ONE triangle
       (interior edges are shared by two triangles).
    3. Walk the boundary edges into an ordered polygon chain.
    4. Deduplicate 2-D vertices to 1 cm grid.
    5. Return the longest closed loop (outer boundary of the footprint).

    This correctly handles ANY shape: rectangles, L-shapes, U-shapes, etc.
    """
    import numpy as np

    if len(faces_flat) == 0 or len(verts_scaled) == 0:
        return []

    faces = np.array(faces_flat, dtype=np.int32).reshape(-1, 3)
    vz    = verts_scaled[:, 2]
    z_max = float(vz.max())

    height   = z_max - z_min
    tol      = max(height * 0.10, 0.05)

    # Bottom faces: all three vertices near z_min
    is_bot   = vz < (z_min + tol)
    bot_mask = is_bot[faces[:, 0]] & is_bot[faces[:, 1]] & is_bot[faces[:, 2]]
    bot_faces = faces[bot_mask]

    if len(bot_faces) == 0:
        return []

    # Count how many times each edge appears
    edge_count: dict[tuple[int, int], int] = {}
    for tri in bot_faces:
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            e = (min(a, b), max(a, b))
            edge_count[e] = edge_count.get(e, 0) + 1

    # Boundary edges appear exactly once
    boundary = [e for e, c in edge_count.items() if c == 1]
    if not boundary:
        return []

    # Build adjacency map for boundary vertices
    adj: dict[int, list[int]] = {}
    for a, b in boundary:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

    # Walk boundary edges into closed loops
    visited: set[tuple[int, int]] = set()
    loops: list[list[int]] = []

    for start_a, start_b in boundary:
        if (start_a, start_b) in visited:
            continue

        loop = [start_a]
        visited.add((start_a, start_b))
        visited.add((start_b, start_a))

        prev, cur = start_a, start_b
        while True:
            loop.append(cur)
            nxt = None
            for nb in adj.get(cur, []):
                if nb != prev and (cur, nb) not in visited:
                    nxt = nb
                    break
            if nxt is None or nxt == start_a:
                break
            visited.add((cur, nxt))
            visited.add((nxt, cur))
            prev, cur = cur, nxt

        if len(loop) >= 3:
            loops.append(loop)

    if not loops:
        return []

    # Take the longest loop (= outer boundary; inner holes are smaller)
    longest = max(loops, key=len)

    # Deduplicate 2-D positions to 1 cm grid and build polygon
    seen_xy: dict[tuple[int, int], tuple[float, float]] = {}
    result: list[tuple[float, float]] = []
    for vi in longest:
        x = float(verts_scaled[vi, 0])
        y = float(verts_scaled[vi, 1])
        key = (round(x, 2), round(y, 2))
        if key not in seen_xy:
            seen_xy[key] = (x, y)
            result.append((x, y))

    return result if len(result) >= 3 else []


def _safe_bbox_and_footprint(
    element: Any,
    settings: Any,
    unit_scale: float,
) -> tuple["BBox | None", list[tuple[float, float]]]:
    """
    Extract axis-aligned BBox AND the true 2-D footprint polygon from IFC geometry.

    The footprint is derived from the tessellated face topology: boundary edges
    of the bottom-face triangles are walked into a closed polygon chain.
    This correctly handles any room shape (rectangle, L, U, T, etc.).

    Returns (BBox, footprint) or (None, []) on failure.
    """
    try:
        import numpy as np
        import ifcopenshell.geom
        import ifcopenshell.util.shape

        shape    = ifcopenshell.geom.create_shape(settings, element)
        geometry = shape.geometry

        # Scaled vertices as (N, 3) array
        raw_verts = ifcopenshell.util.shape.get_shape_vertices(shape, geometry)
        if len(raw_verts) == 0:
            return None, []

        verts = raw_verts * unit_scale   # apply unit scale once

        vx, vy, vz = verts[:, 0], verts[:, 1], verts[:, 2]
        min_x, max_x = float(vx.min()), float(vx.max())
        min_y, max_y = float(vy.min()), float(vy.max())
        min_z, max_z = float(vz.min()), float(vz.max())
        bbox = BBox(min_x, min_y, min_z, max_x, max_y, max_z)

        # Face indices from geometry (flat list: v0,v1,v2, v0,v1,v2, …)
        try:
            faces_flat = list(geometry.faces)
        except AttributeError:
            faces_flat = []

        footprint = _boundary_polygon_from_faces(verts, faces_flat, min_z)

        return bbox, footprint

    except Exception:
        return None, []


def _safe_bbox_from_element(
    element: Any,
    settings: Any,
    unit_scale: float,
) -> BBox | None:
    """Kept for obstacle extraction (obstacles don't need footprints)."""
    bbox, _ = _safe_bbox_and_footprint(element, settings, unit_scale)
    return bbox