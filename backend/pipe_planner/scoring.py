from __future__ import annotations

from collections import Counter

from pipe_planner.models import RouteResult
from pipe_planner.voxel_grid import VoxelGrid


DIRECTION_VECTORS = {
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (0, 0, 1),
    (0, 0, -1),
}


def compute_route_metrics(
    path_indices: list[tuple[int, int, int]],
    grid: VoxelGrid,
    existing_edges: set[tuple[tuple[int, int, int], tuple[int, int, int]]] | None = None,
) -> dict[str, float]:
    """Compute KPIs for one voxel path.

    Args:
        path_indices: Route path in voxel indices.
        grid: Voxel grid.
        existing_edges: Optional existing network edges.

    Returns:
        Metric dictionary.
    """
    if not path_indices:
        return {
            "length_m": 0.0,
            "horizontal_length_m": 0.0,
            "vertical_length_m": 0.0,
            "bend_count": 0,
            "wall_crossings": 0,
            "slab_crossings": 0,
            "shared_length_m": 0.0,
            "corridor_steps": 0,
            "shaft_steps": 0,
            "room_steps": 0,
            "mean_ceiling_score": 0.0,
            "mean_wall_distance": 0.0,
            "mean_corridor_distance": 0.0,
        }

    horizontal_steps = 0
    vertical_steps = 0
    bend_count = 0
    wall_crossings = 0
    slab_crossings = 0
    shared_steps = 0
    corridor_steps = 0
    shaft_steps = 0
    room_steps = 0
    last_direction = None

    ceiling_scores: list[float] = []
    wall_distances: list[float] = []
    corridor_distances: list[float] = []

    for index, cell in enumerate(path_indices):
        ix, iy, iz = cell
        if grid.corridor_mask[ix, iy, iz]:
            corridor_steps += 1
        if grid.shaft_mask[ix, iy, iz]:
            shaft_steps += 1
        if grid.room_mask[ix, iy, iz]:
            room_steps += 1

        ceiling_scores.append(float(grid.ceiling_score[ix, iy, iz]))
        wall_distances.append(float(grid.wall_distance[ix, iy, iz]))
        corridor_distances.append(float(grid.corridor_distance[ix, iy, iz]))

        if grid.wall_mask[ix, iy, iz]:
            wall_crossings += 1
        if grid.slab_mask[ix, iy, iz]:
            slab_crossings += 1

        if index == 0:
            continue

        prev = path_indices[index - 1]
        direction = (cell[0] - prev[0], cell[1] - prev[1], cell[2] - prev[2])

        if direction[2] != 0:
            vertical_steps += 1
        else:
            horizontal_steps += 1

        if last_direction is not None and direction != last_direction:
            bend_count += 1
        last_direction = direction

        if existing_edges is not None:
            edge = tuple(sorted((prev, cell)))
            if edge in existing_edges:
                shared_steps += 1

    total_steps = max(0, len(path_indices) - 1)
    return {
        "length_m": total_steps * grid.voxel_size,
        "horizontal_length_m": horizontal_steps * grid.voxel_size,
        "vertical_length_m": vertical_steps * grid.voxel_size,
        "bend_count": bend_count,
        "wall_crossings": wall_crossings,
        "slab_crossings": slab_crossings,
        "shared_length_m": shared_steps * grid.voxel_size,
        "corridor_steps": corridor_steps,
        "shaft_steps": shaft_steps,
        "room_steps": room_steps,
        "mean_ceiling_score": _safe_mean(ceiling_scores),
        "mean_wall_distance": _safe_mean(wall_distances),
        "mean_corridor_distance": _safe_mean(corridor_distances),
    }


def compute_system_metrics(routes: list[RouteResult], grid: VoxelGrid) -> dict[str, float]:
    """Compute system-wide KPIs from selected routes.

    Args:
        routes: Route list.
        grid: Voxel grid.

    Returns:
        KPI dictionary.
    """
    successful_routes = [route for route in routes if route.success]
    if not successful_routes:
        return {
            "route_count": 0,
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

    total_length = sum(float(route.metrics.get("length_m", 0.0)) for route in successful_routes)
    total_bends = sum(int(route.metrics.get("bend_count", 0)) for route in successful_routes)
    total_wall_crossings = sum(int(route.metrics.get("wall_crossings", 0)) for route in successful_routes)
    total_slab_crossings = sum(int(route.metrics.get("slab_crossings", 0)) for route in successful_routes)
    mean_route_score = sum(float(route.score) for route in successful_routes) / len(successful_routes)
    worst_route_score = max(float(route.score) for route in successful_routes)

    edge_counter: Counter[tuple[tuple[int, int, int], tuple[int, int, int]]] = Counter()
    for route in successful_routes:
        for index in range(1, len(route.path_indices)):
            edge = tuple(sorted((route.path_indices[index - 1], route.path_indices[index])))
            edge_counter[edge] += 1

    unique_length = len(edge_counter) * grid.voxel_size
    shared_length = sum(max(0, count - 1) for count in edge_counter.values()) * grid.voxel_size

    return {
        "route_count": len(routes),
        "successful_route_count": len(successful_routes),
        "total_length_m": total_length,
        "unique_length_m": unique_length,
        "shared_length_m": shared_length,
        "total_bends": total_bends,
        "total_wall_crossings": total_wall_crossings,
        "total_slab_crossings": total_slab_crossings,
        "mean_route_score": mean_route_score,
        "worst_route_score": worst_route_score,
    }


def _safe_mean(values: list[float]) -> float:
    """Return a safe mean.

    Args:
        values: Number list.

    Returns:
        Mean value.
    """
    if not values:
        return 0.0
    return float(sum(values) / len(values))
