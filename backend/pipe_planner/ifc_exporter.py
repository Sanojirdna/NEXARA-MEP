"""
ifc_exporter.py
===============
Export all selected routing segments as extruded-area-solid IFC volumes.

Logic
-----
1.  ``SectionSizer`` sizes each service (HEI / LUE / SAN) individually from
    accumulated demand at every voxel.
2.  Where multiple services share a voxel their individual rectangles are
    stacked side-by-side; the combined bounding-box is enlarged by 5 %.
3.  Collinear sub-segments are deduplicated: two routes sharing the same
    voxel run produce exactly ONE IFC element.
4.  Each element is an ``IfcVirtualElement`` placed on the correct
    ``IfcBuildingStorey``.  Property sets carry per-service demands and
    individual sizes.

Entry point
-----------
    from pipe_planner.ifc_exporter import export_routing_ifc

    path = export_routing_ifc(runtime, output_path)
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ifcopenshell
import ifcopenshell.guid

from pipe_planner.domain import DemandRecord, FloorBand, RouteResult, SpaceRecord
from pipe_planner.section_sizing import (
    CollinearSegment, JunctionPoint, SectionSizer, SizerConfig, build_junction_points
)

# ---------------------------------------------------------------------------
# Colour palette per service combination
# ---------------------------------------------------------------------------
_COLOURS: Dict[str, Tuple[float, float, float]] = {
    "HEI":          (0.90, 0.45, 0.10),   # orange
    "LUE":          (0.20, 0.50, 0.85),   # blue
    "SAN":          (0.15, 0.70, 0.25),   # green
    "HEI+LUE":      (0.85, 0.70, 0.10),   # amber
    "HEI+SAN":      (0.60, 0.38, 0.18),   # brown
    "LUE+SAN":      (0.10, 0.60, 0.60),   # teal
    "HEI+LUE+SAN":  (0.50, 0.50, 0.58),   # neutral grey
}


def _colour_for(services: List[str]) -> Tuple[float, float, float]:
    key = "+".join(sorted(services))
    return _COLOURS.get(key, (0.55, 0.55, 0.55))


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _normalize(v: Tuple[float, ...]) -> Tuple[float, ...]:
    L = math.sqrt(sum(x * x for x in v))
    if L < 1e-9:
        return v
    return tuple(x / L for x in v)


def _ref_dir_for_axis(axis: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    Local X direction (RefDirection) for an IfcAxis2Placement3D whose
    local Z equals *axis* (the extrusion / pipe direction).

    Convention (keeps vertical ducts oriented sensibly in IFC viewers):
    - Horizontal pipes  →  RefDirection ≈ world Z (0,0,1)
      then  XDim = height (vertical), YDim = width (horizontal-perp).
    - Vertical pipes    →  RefDirection = world X (1,0,0).
    """
    world_z = (0.0, 0.0, 1.0)
    dot = sum(axis[i] * world_z[i] for i in range(3))
    if abs(dot) > 0.99:                   # pipe is nearly vertical
        return (1.0, 0.0, 0.0)
    # Project world Z onto the plane perpendicular to axis
    proj = tuple(world_z[i] - dot * axis[i] for i in range(3))
    return _normalize(proj)


# ---------------------------------------------------------------------------
# Low-level IFC helpers
# ---------------------------------------------------------------------------

def _pt3(f: ifcopenshell.file, xyz: Tuple[float, float, float]):
    return f.createIfcCartesianPoint(list(xyz))


def _dir3(f: ifcopenshell.file, xyz: Tuple[float, float, float]):
    return f.createIfcDirection(list(xyz))


def _ax2p3d(
    f: ifcopenshell.file,
    origin: Tuple[float, float, float],
    axis: Tuple[float, float, float],
    ref_dir: Tuple[float, float, float],
):
    """IfcAxis2Placement3D: axis = local Z, ref_dir = local X."""
    return f.createIfcAxis2Placement3D(_pt3(f, origin), _dir3(f, axis), _dir3(f, ref_dir))


def _local_placement(
    f: ifcopenshell.file,
    parent,
    origin: Tuple[float, float, float],
    axis: Tuple[float, float, float],
    ref_dir: Tuple[float, float, float],
):
    return f.createIfcLocalPlacement(parent, _ax2p3d(f, origin, axis, ref_dir))


def _identity_placement(f: ifcopenshell.file, parent=None, z: float = 0.0):
    return f.createIfcLocalPlacement(
        parent,
        f.createIfcAxis2Placement3D(
            _pt3(f, (0.0, 0.0, z)), None, None
        ),
    )


def _extruded_solid(
    f: ifcopenshell.file,
    width_m: float,
    height_m: float,
    origin: Tuple[float, float, float],
    axis: Tuple[float, float, float],
    ref_dir: Tuple[float, float, float],
    depth_m: float,
):
    """
    IfcExtrudedAreaSolid for a rectangle width_m × height_m extruded along
    *axis* for *depth_m*.

    Coordinate convention (axis = local Z, ref_dir = local X):
    - XDim  →  along local X  ≈ world Z for horizontal pipes  →  height
    - YDim  →  along local Y  =  axis × ref_dir               →  width
    So pass XDim=height_m, YDim=width_m.
    """
    profile_origin = f.createIfcCartesianPoint([0.0, 0.0])
    profile_place  = f.createIfcAxis2Placement2D(profile_origin, None)
    profile = f.createIfcRectangleProfileDef(
        "AREA", None, profile_place,
        float(height_m),   # XDim  (local X ≈ vertical for horizontal runs)
        float(width_m),    # YDim  (local Y ≈ horizontal-perp for horizontal runs)
    )
    position = _ax2p3d(f, origin, axis, ref_dir)
    extrude_dir = _dir3(f, (0.0, 0.0, 1.0))   # local Z direction
    return f.createIfcExtrudedAreaSolid(profile, position, extrude_dir, float(depth_m))


def _styled_item(
    f: ifcopenshell.file,
    solid,
    rgb: Tuple[float, float, float],
    transparency: float = 0.35,
):
    colour  = f.createIfcColourRgb(None, *rgb)
    surface = f.createIfcSurfaceStyleRendering(
        colour, transparency, None, None, None, None, None, None, "FLAT"
    )
    style      = f.createIfcSurfaceStyle(None, "BOTH", [surface])
    style_asgn = f.createIfcPresentationStyleAssignment([style])
    return f.createIfcStyledItem(solid, [style_asgn], None)


def _corner_box_solid(
    f: ifcopenshell.file,
    center: Tuple[float, float, float],
    box_x_m: float,
    box_y_m: float,
    box_z_m: float,
):
    """
    IfcExtrudedAreaSolid — a rectangular box centred on *center*.

    Dimensions:
      box_x_m  →  world X  (width of segment running in Y)
      box_y_m  →  world Y  (width of segment running in X)
      box_z_m  →  world Z  (duct height — same for both legs)

    The profile is a rectangle in the XY plane extruded along world Z,
    placed so the box is centred on center in all three axes.
    """
    # The IfcRectangleProfileDef is already centered at [0, 0] in profile
    # space (it extends ±XDim/2 and ±YDim/2 around its origin).  So the
    # Axis2Placement3D must be placed AT (center_x, center_y) — not offset
    # by -box/2 — otherwise the box is shifted a full half-width in both X
    # and Y.  Z is offset by -box_z/2 because the extrusion goes upward and
    # we want the box centred vertically on center[2].
    origin = (
        center[0],
        center[1],
        center[2] - box_z_m / 2.0,
    )
    profile_origin = f.createIfcCartesianPoint([0.0, 0.0])
    profile_place  = f.createIfcAxis2Placement2D(profile_origin, None)
    profile = f.createIfcRectangleProfileDef(
        "AREA", None, profile_place,
        float(box_x_m),   # XDim  → world X
        float(box_y_m),   # YDim  → world Y
    )
    position = f.createIfcAxis2Placement3D(_pt3(f, origin), None, None)
    extrude_dir = _dir3(f, (0.0, 0.0, 1.0))
    return f.createIfcExtrudedAreaSolid(profile, position, extrude_dir, float(box_z_m))


def _add_pset(
    f: ifcopenshell.file,
    owner_hist,
    element,
    pset_name: str,
    props: Dict[str, Any],
) -> None:
    """Attach a simple IfcPropertySet to *element*."""
    ifc_props = []
    for name, value in props.items():
        if isinstance(value, bool):
            ifc_val = f.createIfcBoolean(value)
        elif isinstance(value, (int, float)):
            ifc_val = f.createIfcReal(float(value))
        else:
            ifc_val = f.createIfcLabel(str(value))
        ifc_props.append(
            f.createIfcPropertySingleValue(name, None, ifc_val, None)
        )
    pset = f.createIfcPropertySet(
        ifcopenshell.guid.new(), owner_hist, pset_name, None, ifc_props
    )
    f.createIfcRelDefinesByProperties(
        ifcopenshell.guid.new(), owner_hist, None, None, [element], pset
    )


# ---------------------------------------------------------------------------
# IFC model builder
# ---------------------------------------------------------------------------

def _build_ifc_model(
    segments: List[CollinearSegment],
    floors: List[FloorBand],
    junctions: Optional[List[JunctionPoint]] = None,
    project_name: str = "HLKS Routing Volumes",
) -> ifcopenshell.file:
    f = ifcopenshell.file(schema="IFC4")

    # -- Owner history -------------------------------------------------
    person   = f.createIfcPerson(None, "HLKS", "App", None, None, None, None, None)
    org      = f.createIfcOrganization(None, "HLKS Routing", None, None, None)
    p_org    = f.createIfcPersonAndOrganization(person, org, None)
    app      = f.createIfcApplication(org, "1.0", "HLKS Routing Exporter", "HLKSRouting")
    ts       = int(time.time())
    oh       = f.createIfcOwnerHistory(p_org, app, None, "ADDED", None, p_org, app, ts)

    # -- Units ---------------------------------------------------------
    ua = f.createIfcUnitAssignment([
        f.createIfcSIUnit(None, "LENGTHUNIT",  None, "METRE"),
        f.createIfcSIUnit(None, "AREAUNIT",    None, "SQUARE_METRE"),
        f.createIfcSIUnit(None, "VOLUMEUNIT",  None, "CUBIC_METRE"),
    ])

    # -- Geometric contexts --------------------------------------------
    world_ax2 = f.createIfcAxis2Placement3D(_pt3(f, (0., 0., 0.)), None, None)
    ctx = f.createIfcGeometricRepresentationContext(
        None, "Model", 3, 1.0e-5, world_ax2, None
    )
    body_ctx = f.createIfcGeometricRepresentationSubContext(
        "Body", "Model", None, None, None, None, ctx, None, "MODEL_VIEW", None
    )

    # -- IFC hierarchy -------------------------------------------------
    project = f.createIfcProject(
        ifcopenshell.guid.new(), oh, project_name, None,
        None, None, None, [ctx], ua,
    )

    site_pl   = _identity_placement(f)
    site      = f.createIfcSite(
        ifcopenshell.guid.new(), oh, "Site", None, None,
        site_pl, None, None, "ELEMENT", None, None, None, None, None,
    )

    bldg_pl   = _identity_placement(f, site_pl)
    building  = f.createIfcBuilding(
        ifcopenshell.guid.new(), oh, "Building", None, None,
        bldg_pl, None, None, "ELEMENT", None, None, None,
    )

    f.createIfcRelAggregates(ifcopenshell.guid.new(), oh, None, None, project,  [site])
    f.createIfcRelAggregates(ifcopenshell.guid.new(), oh, None, None, site,     [building])

    # One storey per floor
    sorted_floors = sorted(floors, key=lambda fl: fl.floor_index)
    storey_map: Dict[int, Any] = {}
    for fl in sorted_floors:
        st_pl = _identity_placement(f, bldg_pl, fl.z_min)
        storey = f.createIfcBuildingStorey(
            ifcopenshell.guid.new(), oh, fl.name, None, None,
            st_pl, None, None, "ELEMENT", fl.z_min,
        )
        storey_map[fl.floor_index] = storey

    f.createIfcRelAggregates(
        ifcopenshell.guid.new(), oh, None, None,
        building, list(storey_map.values()),
    )

    # -- IfcSystem per service ----------------------------------------
    systems: Dict[str, Any] = {}
    for svc, label in [("HEI", "Heating"), ("LUE", "Ventilation"), ("SAN", "Sanitation")]:
        sys_obj = f.createIfcDistributionSystem(
            ifcopenshell.guid.new(), oh, f"{svc} – {label}", None, None, svc
        )
        systems[svc] = sys_obj

    # -- Elements per segment -----------------------------------------
    elements_by_storey: Dict[int, List[Any]] = {fi: [] for fi in storey_map}
    elements_by_service: Dict[str, List[Any]] = {svc: [] for svc in systems}

    for seg in segments:
        if seg.length_m < 1e-4:
            continue

        d   = seg.direction
        rd  = _ref_dir_for_axis(d)
        rgb = _colour_for(seg.services)

        # Geometry
        solid = _extruded_solid(
            f,
            seg.combined_w_m,
            seg.combined_h_m,
            seg.start_xyz,
            d,
            rd,
            seg.length_m,
        )
        _styled_item(f, solid, rgb)

        shape_rep = f.createIfcShapeRepresentation(
            body_ctx, "Body", "SweptSolid", [solid]
        )
        prod_shape = f.createIfcProductDefinitionShape(None, None, [shape_rep])

        # Placement (identity – geometry is already in world coordinates)
        el_pl = _identity_placement(f)

        label = "HLKS Bundle [{}]".format("+".join(seg.services))
        element = f.createIfcVirtualElement(
            ifcopenshell.guid.new(), oh, label, None, None,
            el_pl, prod_shape, None,
        )

        # --- Property sets ---
        # 1.  Combined bundle dimensions
        _add_pset(f, oh, element, "Pset_RoutingBundle", {
            "Services":          "+".join(seg.services),
            "CombinedWidth_mm":  round(seg.combined_w_m * 1000, 1),
            "CombinedHeight_mm": round(seg.combined_h_m * 1000, 1),
            "Length_m":          round(seg.length_m, 3),
            "FloorIndex":        seg.floor_index,
            "ClearanceFactor":   1.05,
        })

        # 2.  Per-service breakdown
        for svc, (w, h, demand, unit) in seg.service_breakdown.items():
            _add_pset(f, oh, element, f"Pset_Service_{svc}", {
                "Service":             svc,
                "AccumulatedDemand":   round(demand, 3),
                "DemandUnit":          unit,
                "SectionWidth_mm":     round(w * 1000, 1),
                "SectionHeight_mm":    round(h * 1000, 1),
            })

        # Assign to storey
        fi = seg.floor_index
        if fi not in storey_map:
            # fallback to first/last storey
            fi = sorted_floors[0].floor_index if sorted_floors else fi
        elements_by_storey.setdefault(fi, []).append(element)

        # Assign to service systems
        for svc in seg.services:
            elements_by_service.setdefault(svc, []).append(element)

    # -- Corner boxes at every bend point ------------------------------
    for junc in (junctions or []):
        if junc.box_z_m < 1e-4:
            continue

        rgb = _colour_for(junc.services)
        solid = _corner_box_solid(
            f, junc.xyz, junc.box_x_m, junc.box_y_m, junc.box_z_m
        )
        _styled_item(f, solid, rgb)

        shape_rep  = f.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
        prod_shape = f.createIfcProductDefinitionShape(None, None, [shape_rep])
        el_pl      = _identity_placement(f)

        corner_el = f.createIfcVirtualElement(
            ifcopenshell.guid.new(), oh,
            "HLKS Corner [{}]".format("+".join(junc.services)),
            None, None, el_pl, prod_shape, None,
        )

        fi = junc.floor_index
        if fi not in storey_map and sorted_floors:
            fi = sorted_floors[0].floor_index
        elements_by_storey.setdefault(fi, []).append(corner_el)

        for svc in junc.services:
            elements_by_service.setdefault(svc, []).append(corner_el)

    # -- Spatial containment per storey --------------------------------
    for fi, storey in storey_map.items():
        elems = elements_by_storey.get(fi, [])
        if elems:
            f.createIfcRelContainedInSpatialStructure(
                ifcopenshell.guid.new(), oh, None, None, elems, storey
            )

    # -- System assignment per service ---------------------------------
    for svc, sys_obj in systems.items():
        elems = [e for e in elements_by_service.get(svc, [])]
        if elems:
            f.createIfcRelAssignsToGroup(
                ifcopenshell.guid.new(), oh, None, None,
                elems, None, sys_obj,
            )

    return f


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def export_routing_ifc(
    routes: List[RouteResult],
    demands: List[DemandRecord],
    floors: List[FloorBand],
    rooms_by_guid: Dict[str, SpaceRecord],
    output_path: str | Path,
    sizer_config: Optional[SizerConfig] = None,
    project_name: str = "HLKS Routing Volumes",
) -> Path:
    """
    Generate an IFC file with one extruded volume per unique routing segment.

    Parameters
    ----------
    routes        : list[RouteResult]  from runtime.current_system.routes
    demands       : list[DemandRecord] from runtime.bundle["demands"]
    floors        : list[FloorBand]    from runtime.bundle["floors"]
    rooms_by_guid : dict               from runtime.bundle["rooms_by_guid"]
    output_path   : destination .ifc file
    sizer_config  : optional override for velocity / insulation / grid params
    project_name  : IFC project name string

    Returns
    -------
    Path to the written IFC file.
    """
    floor_by_room = {
        guid: space.floor_index for guid, space in rooms_by_guid.items()
    }

    sizer    = SectionSizer(routes, demands, config=sizer_config)
    segments = sizer.build_all_unique_segments(floor_by_room)
    junctions = build_junction_points(routes, sizer, floor_by_room, segments=segments)

    ifc_model = _build_ifc_model(
        segments, floors,
        junctions=junctions,
        project_name=project_name,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ifc_model.write(str(out))
    return out
