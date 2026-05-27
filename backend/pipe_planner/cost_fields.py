from __future__ import annotations

from collections import deque

import numpy as np

from pipe_planner.config import ProjectConfig
from pipe_planner.voxel_grid import VoxelGrid


def build_cost_fields(grid: VoxelGrid, config: ProjectConfig) -> None:
    """Fill the wall and corridor distance fields in place.

    Args:
        grid: Voxel grid to update.
        config: Project configuration.

    Returns:
        None.
    """
    grid.wall_distance[:] = _multi_source_distance(
        source_mask=grid.wall_mask,
        allowed_mask=grid.traversable_mask,
        max_distance=config.penalty_config.wall_distance_clip,
    )

    corridor_boundary = _find_corridor_boundary(grid.corridor_mask)
    grid.corridor_distance[:] = _multi_source_distance(
        source_mask=corridor_boundary,
        allowed_mask=grid.corridor_mask,
        max_distance=config.penalty_config.corridor_distance_clip,
    )


def _find_corridor_boundary(corridor_mask: np.ndarray) -> np.ndarray:
    """Mark corridor cells that touch non-corridor cells.

    Args:
        corridor_mask: Corridor mask.

    Returns:
        Boundary mask.
    """
    boundary = np.zeros_like(corridor_mask, dtype=bool)
    shifts = [
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (0, 0, 1),
        (0, 0, -1),
    ]

    max_x, max_y, max_z = corridor_mask.shape
    indices = np.argwhere(corridor_mask)
    for ix, iy, iz in indices:
        for dx, dy, dz in shifts:
            nx = ix + dx
            ny = iy + dy
            nz = iz + dz
            if nx < 0 or ny < 0 or nz < 0 or nx >= max_x or ny >= max_y or nz >= max_z:
                boundary[ix, iy, iz] = True
                break
            if not corridor_mask[nx, ny, nz]:
                boundary[ix, iy, iz] = True
                break

    return boundary


def _multi_source_distance(
    source_mask: np.ndarray,
    allowed_mask: np.ndarray,
    max_distance: int,
) -> np.ndarray:
    """Compute a small Manhattan distance field with BFS.

    Args:
        source_mask: Starting cells.
        allowed_mask: Cells where BFS may spread.
        max_distance: Maximum stored distance.

    Returns:
        Integer distance array.
    """
    shape = source_mask.shape
    distances = np.full(shape, max_distance, dtype=np.int16)

    queue: deque[tuple[int, int, int]] = deque()
    for ix, iy, iz in np.argwhere(source_mask):
        distances[ix, iy, iz] = 0
        queue.append((int(ix), int(iy), int(iz)))

    shifts = [
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (0, 0, 1),
        (0, 0, -1),
    ]

    max_x, max_y, max_z = shape
    while queue:
        ix, iy, iz = queue.popleft()
        base_distance = distances[ix, iy, iz]
        if base_distance >= max_distance:
            continue

        for dx, dy, dz in shifts:
            nx = ix + dx
            ny = iy + dy
            nz = iz + dz
            if nx < 0 or ny < 0 or nz < 0 or nx >= max_x or ny >= max_y or nz >= max_z:
                continue
            if not allowed_mask[nx, ny, nz]:
                continue

            next_distance = base_distance + 1
            if next_distance < distances[nx, ny, nz]:
                distances[nx, ny, nz] = next_distance
                queue.append((nx, ny, nz))

    return distances
