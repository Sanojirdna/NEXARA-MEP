from __future__ import annotations

import numpy as np

from pipe_planner.models import DemandRecord, RouteResult, SpaceRecord
from pipe_planner.routing import RouteTask
from pipe_planner.voxel_grid import VoxelGrid


def build_unique_route_tasks(
    demands: list[DemandRecord],
    rooms_by_guid: dict[str, SpaceRecord],
    shafts: list[SpaceRecord],
    strategy_names: list[str],
    shaft_allow_map: dict[str, list[str]],
    shaft_limit: int,
    grid: VoxelGrid,
    technical_rooms: list[SpaceRecord] | None = None,
) -> tuple[list[RouteTask], dict[tuple[str, str, str], list[DemandRecord]]]:
    """
    Build unique geometry tasks and remember which demands reuse them.

    On floors that contain a Technikraum, rooms on that floor route directly
    to the nearest Technikraum (up to *shaft_limit* candidates) instead of to
    a shaft.  On all other floors the existing shaft-candidate logic is used.

    Args:
        demands: Demand rows.
        rooms_by_guid: Rooms by GUID.
        shafts: Available shafts.
        strategy_names: Strategy names.
        shaft_allow_map: Optional shaft allow-list per service.
        shaft_limit: Number of nearest shafts / technikräume to test per room.
        grid: Voxel grid with per-floor shaft targets.
        technical_rooms: Optional list of Technikraum SpaceRecords.

    Returns:
        Tuple of unique tasks and mapping to original demand rows.
    """
    # ── Build floor → technikräume lookup ────────────────────────────────────
    technik_by_floor: dict[int, list[SpaceRecord]] = {}
    for tr in (technical_rooms or []):
        technik_by_floor.setdefault(tr.floor_index, []).append(tr)

    technik_floor_indices: set[int] = set(technik_by_floor.keys())

    # ── Main task-building loop ───────────────────────────────────────────────
    unique_tasks_by_key: dict[tuple[str, str, str], RouteTask] = {}
    geometry_to_demands: dict[tuple[str, str, str], list[DemandRecord]] = {}

    demand_groups_by_room: dict[str, list[DemandRecord]] = {}
    for demand in demands:
        demand_groups_by_room.setdefault(demand.room_guid, []).append(demand)

    for room_guid, room_demands in demand_groups_by_room.items():
        room = rooms_by_guid.get(room_guid)
        if room is None:
            continue

        service_to_demands: dict[str, list[DemandRecord]] = {}
        for demand in room_demands:
            service_to_demands.setdefault(demand.service, []).append(demand)

        on_technik_floor = room.floor_index in technik_floor_indices

        for service, service_demands in service_to_demands.items():
            representative = service_demands[0]

            if on_technik_floor:
                # ── Route to Technikraum, not to shafts ──────────────────────
                floor_technikraeume = technik_by_floor[room.floor_index]
                candidates = _select_nearest_targets(room, floor_technikraeume, shaft_limit, grid)

                for technikraum in candidates:
                    # Re-use shaft_targets key (guid, floor_index) which was
                    # populated by _build_technikraum_targets in voxel_grid.
                    if (technikraum.guid, room.floor_index) not in grid.shaft_targets:
                        continue

                    key = (room.guid, technikraum.guid, strategy_names[0] if strategy_names else "")
                    for strategy_name in strategy_names:
                        key = (room.guid, technikraum.guid, strategy_name)
                        if key not in unique_tasks_by_key:
                            unique_tasks_by_key[key] = RouteTask(
                                demand=representative,
                                room=room,
                                shaft=technikraum,
                                strategy_name=strategy_name,
                            )
                        geometry_to_demands.setdefault(key, [])
                        geometry_to_demands[key].extend(service_demands)

            else:
                # ── Original shaft-candidate logic ────────────────────────────
                allowed_guids = shaft_allow_map.get(service, [])
                same_story_shafts: list[SpaceRecord] = []
                for shaft in shafts:
                    if allowed_guids and shaft.guid not in allowed_guids:
                        continue
                    if (shaft.guid, room.floor_index) not in grid.shaft_targets:
                        continue
                    same_story_shafts.append(shaft)

                shortlisted_shafts = select_nearest_shafts_numpy(
                    room=room,
                    shafts=same_story_shafts,
                    limit=shaft_limit,
                )

                for shaft in shortlisted_shafts:
                    for strategy_name in strategy_names:
                        key = (room.guid, shaft.guid, strategy_name)
                        if key not in unique_tasks_by_key:
                            unique_tasks_by_key[key] = RouteTask(
                                demand=representative,
                                room=room,
                                shaft=shaft,
                                strategy_name=strategy_name,
                            )
                        geometry_to_demands.setdefault(key, [])
                        geometry_to_demands[key].extend(service_demands)

    # ── Shaft → Technikraum tasks ─────────────────────────────────────────────
    # ONE synthetic DemandRecord per shaft (shared across all technikraum
    # candidates).  The route matrix gets one row per (shaft, technikraum,
    # strategy) — all with the same demand_id — so _build_default_selections
    # picks exactly ONE technikraum per shaft.  This avoids duplicate routes
    # and ensures compute_shaft_aggregated_demands picks the right target.
    shaft_synthetic_demands: dict[str, DemandRecord] = {}  # shaft_guid → demand

    for floor_index, technikraeume in technik_by_floor.items():
        for shaft in shafts:
            shaft_voxel = grid.shaft_targets.get((shaft.guid, floor_index))
            if shaft_voxel is None:
                continue

            # One stable demand per shaft (not per shaft+technikraum).
            demand_id = f"__shaft__{shaft.guid}"
            if demand_id not in shaft_synthetic_demands:
                shaft_synthetic_demands[demand_id] = DemandRecord(
                    demand_id=demand_id,
                    room_guid=shaft.guid,
                    room_name=shaft.label(),
                    service="SHAFT_FEED",
                    media_type="mixed",
                    hvac_system_type="mixed",
                    kind="aggregated_shaft",
                    value=1.0,
                    unit="kW",
                )
            synthetic_demand = shaft_synthetic_demands[demand_id]

            tr_candidates = [
                tr for tr in technikraeume
                if (tr.guid, floor_index) in grid.shaft_targets
            ]
            tr_candidates = select_nearest_shafts_numpy(
                room=shaft, shafts=tr_candidates, limit=shaft_limit
            )

            for technikraum in tr_candidates:
                for strategy_name in strategy_names:
                    key = (shaft.guid, technikraum.guid, strategy_name)
                    if key not in unique_tasks_by_key:
                        unique_tasks_by_key[key] = RouteTask(
                            demand=synthetic_demand,
                            room=shaft,
                            shaft=technikraum,
                            strategy_name=strategy_name,
                            start_voxel=shaft_voxel,
                            floor_index_override=floor_index,
                        )
                    # All candidates share the same demand — multiple matrix
                    # rows, same demand_id, different shaft_guid in results.
                    geometry_to_demands.setdefault(key, [synthetic_demand])

    # ── Deduplicate demand lists ──────────────────────────────────────────────
    for key, demand_list in geometry_to_demands.items():
        seen_ids: set[str] = set()
        unique_demand_list: list[DemandRecord] = []
        for demand in demand_list:
            if demand.demand_id in seen_ids:
                continue
            seen_ids.add(demand.demand_id)
            unique_demand_list.append(demand)
        geometry_to_demands[key] = unique_demand_list

    return list(unique_tasks_by_key.values()), geometry_to_demands, list(shaft_synthetic_demands.values())


def _select_nearest_targets(
    room: SpaceRecord,
    candidates: list[SpaceRecord],
    limit: int,
    grid: VoxelGrid,
) -> list[SpaceRecord]:
    """Select up to *limit* nearest candidates (technikräume) for a room.

    Filters to candidates that have a valid voxel target registered in the
    grid before distance-ranking.

    Args:
        room: Source room.
        candidates: Candidate Technikraum SpaceRecords on the same floor.
        limit: Maximum number of candidates to return.
        grid: Voxel grid (used to verify target registration).

    Returns:
        Shortlisted candidates sorted by ascending XY distance.
    """
    reachable = [
        c for c in candidates
        if (c.guid, room.floor_index) in grid.shaft_targets
    ]
    return select_nearest_shafts_numpy(room=room, shafts=reachable, limit=limit)


def select_nearest_shafts_numpy(
    room: SpaceRecord,
    shafts: list[SpaceRecord],
    limit: int,
) -> list[SpaceRecord]:
    """
    Select the nearest shafts on plan view using NumPy.

    Args:
        room: Start room.
        shafts: Candidate shafts.
        limit: Maximum number of shafts to keep.

    Returns:
        Shortlist of nearest shafts.
    """
    if not shafts or limit <= 0:
        return []

    room_center_xy = np.array(room.bbox.center()[:2], dtype=float)
    shaft_centers_xy = np.array([shaft.bbox.center()[:2] for shaft in shafts], dtype=float)
    deltas = shaft_centers_xy - room_center_xy
    distances = np.sqrt(np.sum(deltas * deltas, axis=1))

    keep_count = min(limit, len(shafts))
    nearest_indices = np.argsort(distances)[:keep_count]

    return [shafts[int(index)] for index in nearest_indices]


def expand_unique_results(
    unique_results: list[RouteResult],
    geometry_to_demands: dict[tuple[str, str, str], list[DemandRecord]],
) -> list[RouteResult]:
    """
    Expand geometry-level results back to demand-level rows.

    Args:
        unique_results: One result per room-shaft-strategy geometry.
        geometry_to_demands: Mapping from geometry key to original demands.

    Returns:
        Full demand-level candidate matrix.
    """
    expanded_results: list[RouteResult] = []

    for result in unique_results:
        key = (result.room_guid, result.shaft_guid, result.strategy)
        linked_demands = geometry_to_demands.get(key, [])

        if not linked_demands:
            expanded_results.append(result)
            continue

        for demand in linked_demands:
            expanded_results.append(
                RouteResult(
                    demand_id=demand.demand_id,
                    room_guid=result.room_guid,
                    room_name=result.room_name,
                    service=demand.service,
                    shaft_guid=result.shaft_guid,
                    shaft_name=result.shaft_name,
                    strategy=result.strategy,
                    success=result.success,
                    score=result.score,
                    path_indices=list(result.path_indices),
                    path_xyz=list(result.path_xyz),
                    metrics=dict(result.metrics),
                    message=result.message,
                )
            )

    return expanded_results
