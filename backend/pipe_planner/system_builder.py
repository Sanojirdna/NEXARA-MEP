from __future__ import annotations

import numpy as np

from pipe_planner.config import ProjectConfig
from pipe_planner.models import DemandRecord, RouteResult, SpaceRecord, SystemBuildResult
from pipe_planner.routing import build_route_result
from pipe_planner.scoring import compute_route_metrics, compute_system_metrics
from pipe_planner.voxel_grid import VoxelGrid


def build_selected_system(
    demands: list[DemandRecord],
    rooms_by_guid: dict[str, SpaceRecord],
    shafts_by_guid: dict[str, SpaceRecord],
    selections: dict[str, dict[str, str]],
    grid: VoxelGrid,
    config: ProjectConfig,
    technical_rooms: list[SpaceRecord] | None = None,
) -> SystemBuildResult:
    """Build a merged system from user selections.

    When *technical_rooms* are provided, shaft → Technikraum routes are
    automatically appended after the per-demand routes are built.  These extra
    routes carry the aggregated demand of all rooms (from any floor) that were
    assigned to each shaft and are sized accordingly by ``SectionSizer``.

    Args:
        demands: Demand list.
        rooms_by_guid: Rooms by guid.
        shafts_by_guid: Shafts by guid.
        selections: Mapping from demand_id to chosen shaft and strategy.
        grid: Voxel grid.
        config: Project config.
        technical_rooms: Optional list of Technikraum SpaceRecords.  When
            supplied, shaft → Technikraum routes are added automatically.

    Returns:
        SystemBuildResult object.
    """
    # Build a combined target lookup: shafts + technikräume.
    # On Technikraum floors, the selection's shaft_guid is the technikraum guid,
    # so we must be able to resolve it here alongside real shafts.
    target_by_guid: dict[str, SpaceRecord] = dict(shafts_by_guid)
    for tr in (technical_rooms or []):
        target_by_guid[tr.guid] = tr

    # all_spaces_by_guid covers rooms, technikräume AND shafts (which act as
    # route origins for shaft→technikraum synthetic demands).
    all_spaces_by_guid: dict[str, SpaceRecord] = dict(rooms_by_guid)
    for tr in (technical_rooms or []):
        all_spaces_by_guid[tr.guid] = tr
    for shaft in shafts_by_guid.values():
        all_spaces_by_guid[shaft.guid] = shaft

    routeable_demands = [d for d in demands if d.room_guid in all_spaces_by_guid]

    demand_order = sorted(
        routeable_demands,
        key=lambda demand: (
            all_spaces_by_guid[demand.room_guid].floor_index,
            all_spaces_by_guid[demand.room_guid].label(),
            demand.service,
        ),
    )

    existing_network_mask = np.zeros(grid.shape, dtype=bool)
    existing_edges: set[tuple[tuple[int, int, int], tuple[int, int, int]]] = set()
    built_routes: list[RouteResult] = []

    for demand in demand_order:
        selection = selections.get(demand.demand_id, {})
        shaft_guid = selection.get("shaft_guid", "")
        strategy_name = selection.get("strategy", "Balanced")

        room = all_spaces_by_guid[demand.room_guid]
        shaft = target_by_guid.get(shaft_guid)
        if shaft is None:
            built_routes.append(
                RouteResult(
                    demand_id=demand.demand_id,
                    room_guid=room.guid,
                    room_name=room.label(),
                    service=demand.service,
                    shaft_guid=shaft_guid,
                    shaft_name="unknown",
                    strategy=strategy_name,
                    success=False,
                    score=1_000_000.0,
                    message="Selected shaft does not exist.",
                )
            )
            continue

        strategy = config.strategies[strategy_name]

        # Shaft-origin demands (room_guid is a shaft) need the shaft's floor
        # entry voxel and the technikraum's floor_index as overrides so A*
        # routes correctly on the Technikraum floor.
        is_shaft_origin = demand.room_guid in shafts_by_guid
        if is_shaft_origin:
            technikraum_floor_index = shaft.floor_index
            shaft_start_voxel = grid.shaft_targets.get(
                (room.guid, technikraum_floor_index)
            )
            technikraum_target_voxel = grid.shaft_targets.get(
                (shaft.guid, technikraum_floor_index)
            )
            route = build_route_result(
                demand=demand,
                room=room,
                shaft=shaft,
                strategy=strategy,
                grid=grid,
                existing_network_mask=existing_network_mask,
                start_voxel=shaft_start_voxel,
                target_voxel=technikraum_target_voxel,
                floor_index_override=technikraum_floor_index,
            )
        else:
            route = build_route_result(
                demand=demand,
                room=room,
                shaft=shaft,
                strategy=strategy,
                grid=grid,
                existing_network_mask=existing_network_mask,
            )

        if route.success:
            for cell in route.path_indices:
                existing_network_mask[cell] = True

            for index in range(1, len(route.path_indices)):
                edge = tuple(sorted((route.path_indices[index - 1], route.path_indices[index])))
                existing_edges.add(edge)

            route.metrics = compute_route_metrics(
                route.path_indices,
                grid,
                existing_edges=existing_edges,
            )
            route.score = (
                float(route.metrics["length_m"]) * strategy.length_weight
                + float(route.metrics["bend_count"]) * strategy.bend_penalty
                + float(route.metrics["vertical_length_m"]) * strategy.vertical_penalty
                + float(route.metrics["wall_crossings"]) * (0.0 if strategy.ignore_wall_penalty else strategy.wall_cross_penalty)
                + float(route.metrics["slab_crossings"]) * strategy.slab_cross_penalty
                - float(route.metrics["shared_length_m"]) * strategy.merge_reward
            )

        built_routes.append(route)

    system_metrics = compute_system_metrics(built_routes, grid)
    success_count = sum(1 for route in built_routes if route.success)
    failed_count = len(built_routes) - success_count

    return SystemBuildResult(
        selections=selections,
        routes=built_routes,
        system_metrics=system_metrics,
        success_count=success_count,
        failed_count=failed_count,
    )
