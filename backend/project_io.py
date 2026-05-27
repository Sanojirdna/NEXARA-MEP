from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from pipe_planner.config import KeywordConfig, PenaltyConfig, ProjectConfig, build_default_config
from pipe_planner.models import BBox, DemandRecord, FloorBand, RouteResult, SpaceRecord, StrategyProfile, SystemBuildResult


CONFIG_VERSION = 1
BUNDLE_VERSION = 1
ROUTE_METRIC_KEYS = [
    "length_m",
    "horizontal_length_m",
    "vertical_length_m",
    "bend_count",
    "wall_crossings",
    "slab_crossings",
    "shared_length_m",
    "corridor_steps",
    "shaft_steps",
    "room_steps",
    "mean_ceiling_score",
    "mean_wall_distance",
    "mean_corridor_distance",
]


def config_to_dict(config: ProjectConfig, name: str = "default") -> dict[str, Any]:
    """
    Convert a ProjectConfig to one JSON-safe dictionary.

    Args:
        config: Project configuration object.
        name: Display name for the config.

    Returns:
        JSON-safe config dictionary.
    """
    strategies: dict[str, dict[str, Any]] = {}
    for strategy_name, strategy in config.strategies.items():
        strategies[strategy_name] = strategy.to_dict()

    return {
        "config_version": CONFIG_VERSION,
        "name": name,
        "voxel_grid": {
            "voxel_size": config.voxel_size,
            "voxel_margin": config.penalty_config.voxel_margin,
            "route_clearance_margin": config.penalty_config.route_clearance_margin,
        },
        "runtime": {
            "default_workers": config.default_workers,
            "candidate_shaft_limit": config.candidate_shaft_limit,
            "k_routes_per_strategy": config.k_routes_per_strategy,
            "penalty_factor": config.penalty_factor,
        },
        "keywords": {
            "corridor_keywords": list(config.keyword_config.corridor_keywords),
            "shaft_keywords": list(config.keyword_config.shaft_keywords),
            "no_route_space_keywords": list(config.keyword_config.no_route_space_keywords),
            "technical_room_keywords": list(config.keyword_config.technical_room_keywords),
            "technical_room_sanitary_keywords": list(config.keyword_config.technical_room_sanitary_keywords),
            "technical_room_heating_keywords": list(config.keyword_config.technical_room_heating_keywords),
            "technical_room_ventilation_keywords": list(config.keyword_config.technical_room_ventilation_keywords),
            "technical_room_cooling_keywords": list(config.keyword_config.technical_room_cooling_keywords),
            "technical_room_sprinkler_keywords": list(config.keyword_config.technical_room_sprinkler_keywords),
        },
        "penalties": {
            "wall_cross_penalty": config.penalty_config.wall_cross_penalty,
            "slab_cross_penalty": config.penalty_config.slab_cross_penalty,
            "blocked_penalty": config.penalty_config.blocked_penalty,
            "wall_distance_clip": config.penalty_config.wall_distance_clip,
            "corridor_distance_clip": config.penalty_config.corridor_distance_clip,
        },
        "shaft_allow_map": {
            str(service): [str(value) for value in values]
            for service, values in config.shaft_allow_map.items()
        },
        "strategies": strategies,
    }


def config_from_dict(raw: dict[str, Any]) -> ProjectConfig:
    """
    Build a ProjectConfig from uploaded JSON data.

    Missing values fall back to the current defaults.

    Args:
        raw: Parsed JSON object.

    Returns:
        ProjectConfig object.
    """
    base = build_default_config()

    voxel_grid = raw.get("voxel_grid", {}) or {}
    runtime = raw.get("runtime", {}) or {}
    keywords = raw.get("keywords", {}) or {}
    penalties = raw.get("penalties", {}) or {}
    shaft_allow_map = raw.get("shaft_allow_map", {}) or {}
    strategies = raw.get("strategies", {}) or {}

    base.voxel_size = float(voxel_grid.get("voxel_size", base.voxel_size))
    base.default_workers = int(runtime.get("default_workers", base.default_workers))
    base.candidate_shaft_limit = int(
        runtime.get("candidate_shaft_limit", base.candidate_shaft_limit)
    )
    base.k_routes_per_strategy = int(
        runtime.get("k_routes_per_strategy", base.k_routes_per_strategy)
    )
    base.penalty_factor = float(
        runtime.get("penalty_factor", base.penalty_factor)
    )

    base.keyword_config = KeywordConfig(
        corridor_keywords=[
            str(item)
            for item in keywords.get("corridor_keywords", base.keyword_config.corridor_keywords)
        ],
        shaft_keywords=[
            str(item)
            for item in keywords.get("shaft_keywords", base.keyword_config.shaft_keywords)
        ],
        no_route_space_keywords=[
            str(item)
            for item in keywords.get(
                "no_route_space_keywords",
                base.keyword_config.no_route_space_keywords,
            )
        ],
        technical_room_keywords=[
            str(item)
            for item in keywords.get(
                "technical_room_keywords",
                base.keyword_config.technical_room_keywords,
            )
        ],
        technical_room_sanitary_keywords=[
            str(item)
            for item in keywords.get(
                "technical_room_sanitary_keywords",
                base.keyword_config.technical_room_sanitary_keywords,
            )
        ],
        technical_room_heating_keywords=[
            str(item)
            for item in keywords.get(
                "technical_room_heating_keywords",
                base.keyword_config.technical_room_heating_keywords,
            )
        ],
        technical_room_ventilation_keywords=[
            str(item)
            for item in keywords.get(
                "technical_room_ventilation_keywords",
                base.keyword_config.technical_room_ventilation_keywords,
            )
        ],
        technical_room_cooling_keywords=[
            str(item)
            for item in keywords.get(
                "technical_room_cooling_keywords",
                base.keyword_config.technical_room_cooling_keywords,
            )
        ],
        technical_room_sprinkler_keywords=[
            str(item)
            for item in keywords.get(
                "technical_room_sprinkler_keywords",
                base.keyword_config.technical_room_sprinkler_keywords,
            )
        ],
    )

    base.penalty_config = PenaltyConfig(
        wall_cross_penalty=float(
            penalties.get("wall_cross_penalty", base.penalty_config.wall_cross_penalty)
        ),
        slab_cross_penalty=float(
            penalties.get("slab_cross_penalty", base.penalty_config.slab_cross_penalty)
        ),
        blocked_penalty=float(
            penalties.get("blocked_penalty", base.penalty_config.blocked_penalty)
        ),
        wall_distance_clip=int(
            penalties.get("wall_distance_clip", base.penalty_config.wall_distance_clip)
        ),
        corridor_distance_clip=int(
            penalties.get(
                "corridor_distance_clip",
                base.penalty_config.corridor_distance_clip,
            )
        ),
        route_clearance_margin=float(
            voxel_grid.get(
                "route_clearance_margin",
                base.penalty_config.route_clearance_margin,
            )
        ),
        voxel_margin=float(
            voxel_grid.get("voxel_margin", base.penalty_config.voxel_margin)
        ),
    )

    clean_allow_map: dict[str, list[str]] = {}
    for service, values in shaft_allow_map.items():
        if isinstance(values, list):
            clean_allow_map[str(service)] = [str(item) for item in values]
    base.shaft_allow_map = clean_allow_map

    if isinstance(strategies, dict) and strategies:
        clean_strategies: dict[str, StrategyProfile] = {}
        for strategy_name, values in strategies.items():
            if not isinstance(values, dict):
                continue
            name = str(values.get("name", strategy_name))
            clean_strategies[name] = StrategyProfile(
                name=name,
                length_weight=float(values.get("length_weight", 1.0)),
                bend_penalty=float(values.get("bend_penalty", 0.0)),
                vertical_penalty=float(values.get("vertical_penalty", 0.0)),
                wall_cross_penalty=float(values.get("wall_cross_penalty", 0.0)),
                slab_cross_penalty=float(values.get("slab_cross_penalty", 0.0)),
                wall_distance_weight=float(values.get("wall_distance_weight", 0.0)),
                ceiling_weight=float(values.get("ceiling_weight", 0.0)),
                corridor_center_weight=float(values.get("corridor_center_weight", 0.0)),
                merge_reward=float(values.get("merge_reward", 0.0)),
                ignore_wall_penalty=bool(values.get("ignore_wall_penalty", False)),
            )
        if clean_strategies:
            base.strategies = clean_strategies

    return base


def load_config_json(config_path: str | Path) -> tuple[ProjectConfig, dict[str, Any]]:
    """
    Load one planner config JSON file from disk.

    Args:
        config_path: Path to the uploaded JSON file.

    Returns:
        Tuple of config object and original JSON-safe dictionary.
    """
    raw_text = Path(config_path).read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("Config JSON must contain a top-level object.")
    return config_from_dict(payload), payload


def save_config_json(
    config: ProjectConfig,
    output_path: str | Path,
    name: str = "default",
) -> Path:
    """
    Write one planner config JSON file.

    Args:
        config: Project configuration object.
        output_path: Target path.
        name: Config display name.

    Returns:
        Final saved path.
    """
    payload = config_to_dict(config, name=name)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def export_project_bundle(
    runtime: Any,
    output_path: str | Path,
    study_state: dict[str, Any] | None = None,
) -> Path:
    """
    Export the full calculated project state to one JSON file.

    Args:
        runtime: PlannerRuntime object.
        output_path: Target path.
        study_state: Optional saved Studie state.

    Returns:
        Final saved path.
    """
    if runtime.bundle is None:
        raise ValueError("No active bundle available for export.")

    rooms = [room.to_dict() for room in runtime.bundle["rooms_by_guid"].values()]
    shafts = [shaft.to_dict() for shaft in runtime.bundle["shafts_by_guid"].values()]
    corridors = [corridor.to_dict() for corridor in runtime.bundle.get("corridors_by_guid", {}).values()]
    floors = [floor.to_dict() for floor in runtime.bundle["floors"]]
    demands = [demand.to_dict() for demand in runtime.bundle["demands"]]
    shaft_per_service_demands = [
        demand.to_dict()
        for demand in runtime.bundle.get("shaft_per_service_demands", [])
    ]

    variants: list[dict[str, Any]] = []
    for row in runtime.bundle["route_matrix_rows"]:
        clean_row = dict(row)
        clean_row["path_indices"] = _normalize_path_indices(clean_row.get("path_indices", []))
        clean_row["path_xyz"] = _normalize_path_xyz(clean_row.get("path_xyz", []))
        clean_row["metrics"] = _extract_metrics(clean_row)
        variants.append(clean_row)

    payload = {
        "bundle_version": BUNDLE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "ifc_name": runtime.current_ifc_name,
            "excel_name": runtime.current_excel_name,
            "config_name": runtime.current_config_name,
            "config_source": runtime.current_config_source,
        },
        "config": config_to_dict(runtime.bundle["config"], name=runtime.current_config_name),
        "model": {
            "rooms": rooms,
            "shafts": shafts,
            "corridors": corridors,
            "floors": floors,
        },
        "demands": demands,
        "shaft_per_service_demands": shaft_per_service_demands,
        "variants": variants,
        "selections": dict(runtime.bundle.get("selections", {})),
        "system": runtime.current_system.to_dict() if runtime.current_system else None,
        "timings": dict(runtime.bundle.get("timings", {})),
        "study_state": study_state or {},
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def import_project_bundle(
    runtime: Any,
    bundle_path: str | Path,
    ifc_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Import one previously exported project bundle JSON file.

    Args:
        runtime: PlannerRuntime object.
        bundle_path: Path to the bundle file.
        ifc_path: Optional IFC path uploaded only for bundle restore.

    Returns:
        Summary dictionary.
    """
    raw_text = Path(bundle_path).read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("Project bundle JSON must contain a top-level object.")
    return import_project_payload(runtime, payload, ifc_path=ifc_path)


def import_project_payload(
    runtime: Any,
    payload: dict[str, Any],
    ifc_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Load one parsed project bundle payload into the runtime.

    Args:
        runtime: PlannerRuntime object.
        payload: Parsed bundle JSON.
        ifc_path: Optional IFC path uploaded only for bundle restore.

    Returns:
        Summary dictionary.
    """
    config_dict = payload.get("config", {}) or {}
    config = config_from_dict(config_dict)

    rooms_by_guid: dict[str, SpaceRecord] = {}
    for item in payload.get("model", {}).get("rooms", []):
        room = _space_from_dict(item)
        rooms_by_guid[room.guid] = room

    shafts_by_guid: dict[str, SpaceRecord] = {}
    for item in payload.get("model", {}).get("shafts", []):
        shaft = _space_from_dict(item)
        shafts_by_guid[shaft.guid] = shaft

    corridors_by_guid: dict[str, SpaceRecord] = {}
    for item in payload.get("model", {}).get("corridors", []):
        corridor = _space_from_dict(item)
        corridors_by_guid[corridor.guid] = corridor

    floors: list[FloorBand] = []
    for item in payload.get("model", {}).get("floors", []):
        floors.append(_floor_from_dict(item))

    demands: list[DemandRecord] = []
    for item in payload.get("demands", []):
        demands.append(_demand_from_dict(item))

    shaft_per_service_demands: list[DemandRecord] = []
    for item in payload.get("shaft_per_service_demands", []):
        shaft_per_service_demands.append(_demand_from_dict(item))

    route_rows: list[dict[str, Any]] = []
    for item in payload.get("variants", []):
        route_rows.append(_normalize_route_row(item))

    route_matrix_df = pd.DataFrame(route_rows)
    selections = dict(payload.get("selections", {}) or {})
    current_system = build_system_from_saved_variants(
        demands=_visible_system_demands(demands, shaft_per_service_demands),
        route_rows=route_rows,
        selections=selections,
        shafts_by_guid=shafts_by_guid,
        voxel_size=config.voxel_size,
    )

    runtime.bundle = {
        "config": config,
        "grid": None,
        "rooms_by_guid": rooms_by_guid,
        "shafts_by_guid": shafts_by_guid,
        "corridors_by_guid": corridors_by_guid,
        "floors": floors,
        "demands": demands,
        "shaft_per_service_demands": shaft_per_service_demands,
        "route_matrix_rows": route_rows,
        "route_matrix_df": route_matrix_df,
        "timings": dict(payload.get("timings", {})),
        "selections": selections,
        "loaded_from_bundle": True,
    }
    runtime.current_system = current_system
    runtime.current_ifc_path = str(ifc_path) if ifc_path else None
    runtime.current_excel_path = None

    project_ifc_name = str(payload.get("project", {}).get("ifc_name") or "imported_bundle")
    uploaded_ifc_name = Path(ifc_path).name if ifc_path else None
    if uploaded_ifc_name:
        expected_ifc_name = Path(project_ifc_name).name
        normalized_uploaded_name = uploaded_ifc_name.casefold()
        normalized_expected_name = expected_ifc_name.casefold()
        if normalized_uploaded_name != normalized_expected_name:
            raise ValueError(
                "The uploaded IFC file name does not match the IFC name stored in the bundle. "
                f"Expected '{expected_ifc_name}', got '{uploaded_ifc_name}'."
            )

    runtime.current_ifc_name = uploaded_ifc_name or project_ifc_name
    runtime.current_excel_name = str(payload.get("project", {}).get("excel_name") or "imported_bundle")
    runtime.current_config_name = str(payload.get("project", {}).get("config_name") or config_dict.get("name") or "imported_config")
    runtime.current_config_source = str(payload.get("project", {}).get("config_source") or "project_bundle")
    runtime.current_config = config

    summary = runtime.get_summary()
    summary["study_state"] = payload.get("study_state", {})
    summary["bundle_ifc_expected_name"] = project_ifc_name
    summary["bundle_ifc_uploaded"] = bool(ifc_path)
    if uploaded_ifc_name:
        summary["bundle_ifc_message"] = (
            f"Imported bundle with matching IFC '{uploaded_ifc_name}' for viewing only."
        )
    else:
        summary["bundle_ifc_message"] = (
            "Imported bundle without an IFC file. Saved routes are available, but IFC viewing is disabled."
        )
    return summary


def build_system_from_saved_variants(
    demands: list[DemandRecord],
    route_rows: list[dict[str, Any]],
    selections: dict[str, dict[str, str]],
    shafts_by_guid: dict[str, SpaceRecord],
    voxel_size: float,
) -> SystemBuildResult:
    """
    Build the selected system from already saved route rows.

    Per-service shaft→Technikraum demands do not have their own route matrix
    rows.  Their geometry is reconstructed from the saved SHAFT_FEED route for
    the same UG shaft, Technikraum target and strategy, then emitted with the
    real service key (HEI/LUE/SAN) so visualisation and IFC export can size it
    correctly.

    Args:
        demands: Visible/export-relevant demand list.
        route_rows: Saved candidate routes.
        selections: Selection mapping.
        shafts_by_guid: Shaft lookup.
        voxel_size: Voxel size in meters.

    Returns:
        SystemBuildResult object.
    """
    route_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    route_lookup_by_geometry: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in route_rows:
        demand_id = str(row.get("demand_id", ""))
        room_guid = str(row.get("room_guid", ""))
        shaft_guid = str(row.get("shaft_guid", ""))
        strategy = str(row.get("strategy", ""))
        service = str(row.get("service", ""))

        route_lookup[(demand_id, shaft_guid, strategy)] = row
        route_lookup_by_geometry[(room_guid, shaft_guid, strategy, service)] = row

    built_routes: list[RouteResult] = []
    for demand in demands:
        selection = selections.get(demand.demand_id, {})
        shaft_guid = str(selection.get("shaft_guid", ""))
        strategy = str(selection.get("strategy", ""))

        saved_row = _find_saved_route_row(
            demand=demand,
            shaft_guid=shaft_guid,
            strategy=strategy,
            route_lookup=route_lookup,
            route_lookup_by_geometry=route_lookup_by_geometry,
        )
        shaft = shafts_by_guid.get(shaft_guid)

        if saved_row is None:
            built_routes.append(
                RouteResult(
                    demand_id=demand.demand_id,
                    room_guid=demand.room_guid,
                    room_name=demand.room_name,
                    service=demand.service,
                    shaft_guid=shaft_guid,
                    shaft_name=shaft.label() if shaft else "unknown",
                    strategy=strategy or "unknown",
                    success=False,
                    score=1_000_000.0,
                    message="Selected variant is missing in the saved route matrix.",
                )
            )
            continue

        built_routes.append(
            RouteResult(
                demand_id=demand.demand_id,
                room_guid=demand.room_guid,
                room_name=demand.room_name,
                service=demand.service,
                shaft_guid=str(saved_row.get("shaft_guid", shaft_guid)),
                shaft_name=str(saved_row.get("shaft_name", shaft.label() if shaft else "unknown")),
                strategy=str(saved_row.get("strategy", strategy)),
                success=_as_bool(saved_row.get("success", False)),
                score=float(saved_row.get("score", 0.0)),
                path_indices=_normalize_path_indices(saved_row.get("path_indices", [])),
                path_xyz=_normalize_path_xyz(saved_row.get("path_xyz", [])),
                metrics=_extract_metrics(saved_row),
                message=str(saved_row.get("message", "")),
            )
        )

    system_metrics = _compute_system_metrics(built_routes, voxel_size)

    success_count = 0
    for route in built_routes:
        if route.success:
            success_count += 1

    return SystemBuildResult(
        selections=selections,
        routes=built_routes,
        system_metrics=system_metrics,
        success_count=success_count,
        failed_count=len(built_routes) - success_count,
    )


def _find_saved_route_row(
    demand: DemandRecord,
    shaft_guid: str,
    strategy: str,
    route_lookup: dict[tuple[str, str, str], dict[str, Any]],
    route_lookup_by_geometry: dict[tuple[str, str, str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the saved matrix row that provides geometry for one demand."""
    exact = route_lookup.get((demand.demand_id, shaft_guid, strategy))
    if exact is not None:
        return exact

    if _is_per_service_shaft_demand(demand):
        placeholder_demand_id = f"__shaft__{demand.room_guid}"
        placeholder = route_lookup.get((placeholder_demand_id, shaft_guid, strategy))
        if placeholder is not None:
            return placeholder

        return route_lookup_by_geometry.get(
            (demand.room_guid, shaft_guid, strategy, "SHAFT_FEED")
        )

    return None


def _is_per_service_shaft_demand(demand: DemandRecord) -> bool:
    """Return whether a demand is an export-relevant shaft→Technikraum service."""
    return (
        demand.kind == "aggregated_shaft"
        and str(demand.service).upper() != "SHAFT_FEED"
        and "__svc_" in demand.demand_id
    )


def _is_shaft_feed_placeholder(demand: DemandRecord) -> bool:
    """Return whether a demand is only a geometry placeholder."""
    return demand.kind == "aggregated_shaft" and str(demand.service).upper() == "SHAFT_FEED"


def _visible_system_demands(
    demands: list[DemandRecord],
    shaft_per_service_demands: list[DemandRecord],
) -> list[DemandRecord]:
    """Return only routes that should be visible and export-relevant."""
    visible = [demand for demand in demands if not _is_shaft_feed_placeholder(demand)]
    visible.extend(shaft_per_service_demands)
    return visible


def _as_bool(value: Any) -> bool:
    """Convert bool-like route-row values from JSON/CSV/Pandas safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)

def _compute_system_metrics(routes: list[RouteResult], voxel_size: float) -> dict[str, Any]:
    """
    Compute system metrics from saved route paths only.

    Args:
        routes: Built routes.
        voxel_size: Voxel edge length in meters.

    Returns:
        Simple system metrics dictionary.
    """
    successful_routes = [route for route in routes if route.success]
    if not successful_routes:
        return {
            "route_count": len(routes),
            "successful_route_count": 0,
            "total_length_m": 0.0,
            "unique_length_m": 0.0,
            "shared_length_m": 0.0,
            "total_bends": 0,
            "total_wall_crossings": 0,
            "total_slab_crossings": 0,
            "mean_route_score": 0.0,
            "worst_route_score": 0.0,
        }

    edge_counts: dict[tuple[tuple[int, int, int], tuple[int, int, int]], int] = {}
    total_length_m = 0.0
    total_bends = 0
    total_wall_crossings = 0
    total_slab_crossings = 0
    total_score = 0.0
    worst_route_score = 0.0

    for route in successful_routes:
        total_length_m += float(route.metrics.get("length_m", 0.0))
        total_bends += int(route.metrics.get("bend_count", 0))
        total_wall_crossings += int(route.metrics.get("wall_crossings", 0))
        total_slab_crossings += int(route.metrics.get("slab_crossings", 0))
        total_score += float(route.score)
        if float(route.score) > worst_route_score:
            worst_route_score = float(route.score)

        for index in range(1, len(route.path_indices)):
            left = route.path_indices[index - 1]
            right = route.path_indices[index]
            edge = tuple(sorted((left, right)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    shared_edge_count = 0
    for count in edge_counts.values():
        if count > 1:
            shared_edge_count += count - 1

    return {
        "route_count": len(routes),
        "successful_route_count": len(successful_routes),
        "total_length_m": total_length_m,
        "unique_length_m": len(edge_counts) * voxel_size,
        "shared_length_m": shared_edge_count * voxel_size,
        "total_bends": total_bends,
        "total_wall_crossings": total_wall_crossings,
        "total_slab_crossings": total_slab_crossings,
        "mean_route_score": total_score / len(successful_routes),
        "worst_route_score": worst_route_score,
    }


def _normalize_route_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize one saved route row.

    Args:
        row: Raw route row.

    Returns:
        Cleaned route row.
    """
    clean_row = dict(row)
    clean_row["path_indices"] = _normalize_path_indices(clean_row.get("path_indices", []))
    clean_row["path_xyz"] = _normalize_path_xyz(clean_row.get("path_xyz", []))
    metrics = _extract_metrics(clean_row)
    clean_row["metrics"] = metrics
    for key, value in metrics.items():
        clean_row[key] = value
    return clean_row


def _extract_metrics(row: dict[str, Any]) -> dict[str, Any]:
    """
    Extract route metrics from nested or flat values.

    Args:
        row: Route row.

    Returns:
        Metrics dictionary.
    """
    metrics = row.get("metrics")
    if isinstance(metrics, dict):
        return dict(metrics)

    clean_metrics: dict[str, Any] = {}
    for key in ROUTE_METRIC_KEYS:
        if key in row:
            clean_metrics[key] = row[key]
    return clean_metrics


def _normalize_path_indices(values: list[Any]) -> list[tuple[int, int, int]]:
    """
    Convert JSON path index values to integer tuples.

    Args:
        values: Raw path index data.

    Returns:
        Clean list of path index tuples.
    """
    result: list[tuple[int, int, int]] = []
    for item in values:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            continue
        result.append((int(item[0]), int(item[1]), int(item[2])))
    return result


def _normalize_path_xyz(values: list[Any]) -> list[tuple[float, float, float]]:
    """
    Convert JSON world coordinate values to float tuples.

    Args:
        values: Raw xyz data.

    Returns:
        Clean list of xyz tuples.
    """
    result: list[tuple[float, float, float]] = []
    for item in values:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            continue
        result.append((float(item[0]), float(item[1]), float(item[2])))
    return result


def _bbox_from_dict(raw: dict[str, Any]) -> BBox:
    """
    Create one BBox object from JSON data.

    Args:
        raw: Raw bbox dictionary.

    Returns:
        BBox object.
    """
    return BBox(
        min_x=float(raw.get("min_x", 0.0)),
        min_y=float(raw.get("min_y", 0.0)),
        min_z=float(raw.get("min_z", 0.0)),
        max_x=float(raw.get("max_x", 0.0)),
        max_y=float(raw.get("max_y", 0.0)),
        max_z=float(raw.get("max_z", 0.0)),
    )


def _space_from_dict(raw: dict[str, Any]) -> SpaceRecord:
    """
    Create one SpaceRecord from JSON data.

    Args:
        raw: Raw space dictionary.

    Returns:
        SpaceRecord object.
    """
    return SpaceRecord(
        guid=str(raw.get("guid", "")),
        name=str(raw.get("name", "")),
        long_name=str(raw.get("long_name", "")),
        space_type=str(raw.get("space_type", "room")),
        bbox=_bbox_from_dict(raw.get("bbox", {}) or {}),
        floor_index=int(raw.get("floor_index", -1)),
        source_type=str(raw.get("source_type", "json")),
    )


def _floor_from_dict(raw: dict[str, Any]) -> FloorBand:
    """
    Create one FloorBand from JSON data.

    Args:
        raw: Raw floor dictionary.

    Returns:
        FloorBand object.
    """
    return FloorBand(
        floor_index=int(raw.get("floor_index", raw.get("index", -1))),
        name=str(raw.get("name", "")),
        z_min=float(raw.get("z_min", 0.0)),
        z_max=float(raw.get("z_max", 0.0)),
    )


def _demand_from_dict(raw: dict[str, Any]) -> DemandRecord:
    """
    Create one DemandRecord from JSON data.

    Args:
        raw: Raw demand dictionary.

    Returns:
        DemandRecord object.
    """
    return DemandRecord(
        demand_id=str(raw.get("demand_id", "")),
        room_guid=str(raw.get("room_guid", "")),
        room_name=str(raw.get("room_name", "")),
        service=str(raw.get("service", "")),
        media_type=str(raw.get("media_type", "")),
        hvac_system_type=str(raw.get("hvac_system_type", "")),
        kind=str(raw.get("kind", "")),
        value=float(raw.get("value", 0.0)),
        unit=str(raw.get("unit", "")),
    )
