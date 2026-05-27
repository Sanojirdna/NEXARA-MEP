from __future__ import annotations

import heapq
import math
import multiprocessing
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

import numba as nb
import numpy as np

from pipe_planner.config import ProjectConfig
from pipe_planner.models import DemandRecord, RouteResult, SpaceRecord, StrategyProfile
from pipe_planner.scoring import compute_route_metrics
from pipe_planner.voxel_grid import VoxelGrid


@dataclass
class RouteTask:
    """Description of a route to evaluate.

    Args:
        demand: Demand record.
        room: Start room (or shaft SpaceRecord for shaft→technikraum tasks).
        shaft: Target shaft or technikraum SpaceRecord.
        strategy_name: Strategy preset name.
        start_voxel: Optional explicit start voxel override.
        floor_index_override: Optional floor restriction override for A*.

    Returns:
        RouteTask object.
    """

    demand: DemandRecord
    room: SpaceRecord
    shaft: SpaceRecord
    strategy_name: str
    start_voxel: tuple[int, int, int] | None = None
    floor_index_override: int | None = None


# Type alias for the payload stored in the route cache.
_CachedPath = tuple[
    list[tuple[int, int, int]],
    list[Any],
    dict[str, Any],
    float,
]

WORKER_CONTEXT: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Numba A* — pre-allocated buffers and compiled core
# ---------------------------------------------------------------------------

class _AStarBuffers:
    """Pre-allocated work arrays for the numba A* implementation.

    Created once per unique grid shape and reused across all A* calls on
    that grid shape.  In parallel mode each worker process maintains its
    own independent buffer set.

    State encoding used throughout the numba function:
        state = x * SYZ7 + y * SZ7 + z * 7 + dir
        dir ∈ [0..5] — one of the six cardinal movement directions
        dir = 6       — start state (no previous movement direction)

    This non-negative encoding lets all state indices fit in int32 and
    replaces the Python A*'s use of -1 for the start direction.
    """

    __slots__ = (
        "X", "Y", "Z", "SZ7", "SYZ7",
        "best_cost", "parent",
        "heap_f", "heap_g", "heap_s",
        "path_x", "path_y", "path_z",
        "zero_penalty",
    )

    def __init__(self, shape: tuple[int, int, int]) -> None:
        X, Y, Z = shape
        self.X    = np.int32(X)
        self.Y    = np.int32(Y)
        self.Z    = np.int32(Z)
        self.SZ7  = np.int32(Z * 7)
        self.SYZ7 = np.int32(Y * Z * 7)

        n_states = X * Y * Z * 7
        # Heap capacity: A* with a good heuristic rarely pushes more than
        # a fraction of all states.  2 M entries gives ample headroom for
        # buildings of any realistic size while staying under 100 MB.
        max_heap = min(2_000_000, n_states)
        max_path = X * Y * Z

        self.best_cost    = np.empty(n_states, dtype=np.float32)
        self.parent       = np.empty(n_states, dtype=np.int32)
        self.heap_f       = np.empty(max_heap, dtype=np.float32)
        self.heap_g       = np.empty(max_heap, dtype=np.float32)
        self.heap_s       = np.empty(max_heap, dtype=np.int32)
        self.path_x       = np.empty(max_path, dtype=np.int32)
        self.path_y       = np.empty(max_path, dtype=np.int32)
        self.path_z       = np.empty(max_path, dtype=np.int32)
        # Reusable zero-penalty array used when no replanning overlay exists.
        self.zero_penalty = np.zeros((X, Y, Z), dtype=np.float32)


_ASTAR_BUFFERS: dict[tuple[int, int, int], _AStarBuffers] = {}


def _get_astar_buffers(shape: tuple[int, int, int]) -> _AStarBuffers:
    """Return cached A* work buffers for ``shape``, creating them on first call.

    Args:
        shape: Grid dimensions (X, Y, Z).

    Returns:
        _AStarBuffers instance.
    """
    if shape not in _ASTAR_BUFFERS:
        _ASTAR_BUFFERS[shape] = _AStarBuffers(shape)
    return _ASTAR_BUFFERS[shape]


@nb.njit(cache=True)
def _a_star_numba(
    sx, sy, sz,
    tx, ty, tz,
    X, Y, Z, SYZ7, SZ7,
    traversable,
    shaft,
    room_mask,
    floor_labels,
    cell_cost,
    penalty,
    room_floor,
    bend_penalty,
    vertical_penalty,
    voxel_size,
    best_cost,
    parent,
    heap_f,
    heap_g,
    heap_s,
    path_x,
    path_y,
    path_z,
):
    """Numba-compiled A* core for 3-D voxel-grid routing.

    All Python overhead (dictionary lookups, heap object creation, tuple
    packing/unpacking) is eliminated.  The function operates entirely on
    pre-allocated NumPy arrays and compiles to native machine code via LLVM.

    State encoding
    --------------
    ``state = x * SYZ7 + y * SZ7 + z * 7 + dir``
    where ``dir`` ∈ [0, 5] for the six movement directions and 6 for the
    start state.  This keeps all indices non-negative (int32-safe).

    Returns the path length in cells, or 0 if no path was found.  The path
    is written into ``path_x``, ``path_y``, ``path_z`` in forward order.
    """
    # ── Constants ─────────────────────────────────────────────────────────
    DX = (1, -1,  0,  0, 0, 0)
    DY = (0,  0,  1, -1, 0, 0)
    DZ = (0,  0,  0,  0, 1, -1)
    START_DIR = np.int32(6)
    NO_PARENT = np.int32(-1)
    MAX_HEAP  = len(heap_f)
    INF       = np.float32(1.0e30)

    # ── Initialise ────────────────────────────────────────────────────────
    best_cost.fill(INF)
    parent.fill(NO_PARENT)

    start_state = np.int32(sx * SYZ7 + sy * SZ7 + sz * 7 + START_DIR)
    best_cost[start_state] = np.float32(0.0)

    ddx = np.float32(sx - tx)
    ddy = np.float32(sy - ty)
    ddz = np.float32(sz - tz)
    h0  = np.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) * np.float32(voxel_size)

    heap_f[0] = h0
    heap_g[0] = np.float32(0.0)
    heap_s[0] = start_state
    heap_size = np.int32(1)

    found             = False
    best_target_state = NO_PARENT

    # ── Main A* loop ──────────────────────────────────────────────────────
    while heap_size > 0:

        # ── Pop minimum-f entry (heap root) ───────────────────────────────
        g0 = heap_g[0]
        s0 = heap_s[0]
        heap_size -= np.int32(1)
        if heap_size > 0:
            heap_f[0] = heap_f[heap_size]
            heap_g[0] = heap_g[heap_size]
            heap_s[0] = heap_s[heap_size]
            # Sift down
            i = np.int32(0)
            while True:
                l = np.int32(2 * i + 1)
                r = np.int32(2 * i + 2)
                m = i
                if l < heap_size and heap_f[l] < heap_f[m]:
                    m = l
                if r < heap_size and heap_f[r] < heap_f[m]:
                    m = r
                if m == i:
                    break
                tf = heap_f[m]; tg = heap_g[m]; ts = heap_s[m]
                heap_f[m] = heap_f[i]; heap_g[m] = heap_g[i]; heap_s[m] = heap_s[i]
                heap_f[i] = tf;        heap_g[i] = tg;        heap_s[i] = ts
                i = m

        # ── Decode state ──────────────────────────────────────────────────
        prev_dir = np.int32(s0 % 7)
        tmp      = np.int32(s0 // 7)
        cz       = np.int32(tmp % Z)
        tmp      = np.int32(tmp // Z)
        cy       = np.int32(tmp % Y)
        cx       = np.int32(tmp // Y)

        # Lazy deletion: skip stale heap entries
        if g0 > best_cost[s0]:
            continue

        # Goal check
        if cx == tx and cy == ty and cz == tz:
            found             = True
            best_target_state = s0
            break

        # ── Expand six neighbours ─────────────────────────────────────────
        for di in range(6):
            nx = cx + DX[di]
            ny = cy + DY[di]
            nz = cz + DZ[di]

            if nx < 0 or nx >= X or ny < 0 or ny >= Y or nz < 0 or nz >= Z:
                continue
            if not traversable[nx, ny, nz]:
                continue

            # Floor restriction: non-shaft cells must share the room's floor
            if not shaft[nx, ny, nz]:
                if floor_labels[nx, ny, nz] != room_floor:
                    continue

            # Vertical movement only allowed through shafts or room exits
            if DZ[di] != 0:
                if (not shaft[cx, cy, cz]
                        and not shaft[nx, ny, nz]
                        and not room_mask[cx, cy, cz]):
                    continue

            # ── Step cost ─────────────────────────────────────────────────
            # cell_cost holds all position-dependent costs pre-baked by
            # build_cell_cost_array().  Only direction-dependent and
            # replanning costs are added here.
            step = cell_cost[nx, ny, nz] + penalty[nx, ny, nz]
            if di != prev_dir and prev_dir != START_DIR:
                step = step + np.float32(bend_penalty)
            if DZ[di] != 0:
                step = step + np.float32(vertical_penalty)

            next_g     = g0 + step
            next_state = np.int32(nx * SYZ7 + ny * SZ7 + nz * 7 + di)

            if next_g >= best_cost[next_state]:
                continue

            best_cost[next_state] = next_g
            parent[next_state]    = s0

            # Euclidean heuristic
            ddx2  = np.float32(nx - tx)
            ddy2  = np.float32(ny - ty)
            ddz2  = np.float32(nz - tz)
            h2    = np.sqrt(ddx2*ddx2 + ddy2*ddy2 + ddz2*ddz2) * np.float32(voxel_size)
            next_f = next_g + h2

            if heap_size >= MAX_HEAP:
                # Heap overflow guard — should not occur in practice.
                continue

            # ── Push (sift up) ────────────────────────────────────────────
            pos = heap_size
            heap_f[pos] = next_f
            heap_g[pos] = next_g
            heap_s[pos] = next_state
            heap_size  += np.int32(1)
            while pos > 0:
                p = np.int32((pos - 1) >> 1)
                if heap_f[p] > heap_f[pos]:
                    tf = heap_f[p]; tg = heap_g[p]; ts = heap_s[p]
                    heap_f[p]  = heap_f[pos]; heap_g[p]  = heap_g[pos]; heap_s[p]  = heap_s[pos]
                    heap_f[pos] = tf;         heap_g[pos] = tg;         heap_s[pos] = ts
                    pos = p
                else:
                    break

    if not found:
        return np.int32(0)

    # ── Reconstruct path (reversed, then flipped) ─────────────────────────
    path_len = np.int32(0)
    s = best_target_state
    while s != NO_PARENT:
        tmp = np.int32(s // 7)
        pz  = np.int32(tmp % Z)
        tmp = np.int32(tmp // Z)
        py  = np.int32(tmp % Y)
        px  = np.int32(tmp // Y)
        path_x[path_len] = px
        path_y[path_len] = py
        path_z[path_len] = pz
        path_len += np.int32(1)
        s = parent[s]

    lo = np.int32(0)
    hi = path_len - np.int32(1)
    while lo < hi:
        tx2 = path_x[lo]; path_x[lo] = path_x[hi]; path_x[hi] = tx2
        ty2 = path_y[lo]; path_y[lo] = path_y[hi]; path_y[hi] = ty2
        tz2 = path_z[lo]; path_z[lo] = path_z[hi]; path_z[hi] = tz2
        lo += np.int32(1)
        hi -= np.int32(1)

    return path_len


# ---------------------------------------------------------------------------
# NumPy cost-array pre-baking
# ---------------------------------------------------------------------------

def build_cell_cost_array(
    grid: VoxelGrid,
    strategy: StrategyProfile,
    existing_network_mask: np.ndarray | None,
) -> np.ndarray:
    """Pre-bake all position-dependent step costs into a single NumPy array.

    Every cell stores the full cost of entering that cell, covering length
    weight, wall and slab penalties, wall-distance weight, corridor-centre
    weight, ceiling weight, and the existing-network merge reward.

    Direction-dependent costs (bend_penalty, vertical_penalty) and the
    per-iteration replanning overlay are NOT baked in because they depend
    on movement direction or replanning iteration.

    Args:
        grid: Voxel grid with all spatial masks and distance fields.
        strategy: Strategy profile providing all weighting parameters.
        existing_network_mask: Boolean array for merge reward; None if absent.

    Returns:
        Float32 NumPy array of shape ``grid.shape``.
    """
    cost = np.full(grid.shape, strategy.length_weight * grid.voxel_size, dtype=np.float32)

    if not strategy.ignore_wall_penalty:
        cost += grid.wall_mask.astype(np.float32) * strategy.wall_cross_penalty

    slab_outside_shaft: np.ndarray = grid.slab_mask & ~grid.shaft_mask
    cost += slab_outside_shaft.astype(np.float32) * strategy.slab_cross_penalty

    cost += grid.wall_distance.astype(np.float32) * (strategy.wall_distance_weight * 0.2)

    corridor_penalty = np.where(
        grid.corridor_mask,
        np.maximum(0.0, 6.0 - grid.corridor_distance.astype(np.float32))
        * (strategy.corridor_center_weight * 0.2),
        0.0,
    ).astype(np.float32)
    cost += corridor_penalty

    cost += (1.0 - grid.ceiling_score.astype(np.float32)) * strategy.ceiling_weight

    if existing_network_mask is not None:
        cost -= existing_network_mask.astype(np.float32) * strategy.merge_reward

    cost[~grid.traversable_mask] = 1.0e9

    return cost


# ---------------------------------------------------------------------------
# Matrix evaluation — two-level cache + room-grouped workers
# ---------------------------------------------------------------------------

def evaluate_route_matrix(
    tasks: list[RouteTask],
    grid: VoxelGrid,
    config: ProjectConfig,
    workers: int = 1,
) -> list[RouteResult]:
    """Evaluate the independent full route matrix.

    **Sequential mode**: tasks are sorted by room so all services of the same
    room (HEI, SAN, LUE, …) are processed consecutively.  A two-level cache
    avoids redundant work.

    **Parallel mode**: tasks are grouped by room GUID and room groups are
    distributed across workers (largest group first, round-robin) so that
    the two-level cache achieves the same hit rate per worker as in
    sequential mode.  Results are reassembled into the original task order.

    Args:
        tasks: Route tasks.
        grid: Voxel grid.
        config: Project config.
        workers: Number of process workers.

    Returns:
        List of RouteResult objects in the same order as ``tasks``.
    """
    if workers <= 1 or len(tasks) < 4:
        return _evaluate_sequential(tasks, grid, config)

    worker_count = min(max(1, workers), max(1, multiprocessing.cpu_count() - 1))
    print(f"Actual worker_count: {worker_count}", flush=True)

    worker_batches, worker_indices = _group_and_distribute(tasks, worker_count)
    print(
        "Room groups per worker: " + ", ".join(str(len(b)) for b in worker_batches),
        flush=True,
    )

    context = {"grid": grid, "config": config}

    batch_results: list[list[RouteResult]] = []
    with ProcessPoolExecutor(
        max_workers=worker_count,
        initializer=_init_worker,
        initargs=(context,),
    ) as executor:
        for batch in executor.map(_evaluate_task_batch_worker, worker_batches):
            batch_results.append(batch)

    ordered: list[RouteResult | None] = [None] * len(tasks)
    for batch, orig_indices in zip(batch_results, worker_indices):
        for result, orig_idx in zip(batch, orig_indices):
            ordered[orig_idx] = result

    return ordered  # type: ignore[return-value]


def _group_and_distribute(
    tasks: list[RouteTask],
    worker_count: int,
) -> tuple[list[list[RouteTask]], list[list[int]]]:
    """Group tasks by room GUID and distribute groups across workers.

    Args:
        tasks: Flat task list in original order.
        worker_count: Number of workers.

    Returns:
        ``(worker_batches, worker_indices)`` where ``worker_indices[w][i]``
        is the original index of ``worker_batches[w][i]``.
    """
    room_groups: dict[str, list[tuple[int, RouteTask]]] = defaultdict(list)
    for i, task in enumerate(tasks):
        room_groups[task.room.guid].append((i, task))

    sorted_groups = sorted(room_groups.values(), key=len, reverse=True)

    worker_batches: list[list[RouteTask]] = [[] for _ in range(worker_count)]
    worker_indices: list[list[int]]       = [[] for _ in range(worker_count)]

    for j, group in enumerate(sorted_groups):
        w = j % worker_count
        for orig_idx, task in group:
            worker_batches[w].append(task)
            worker_indices[w].append(orig_idx)

    return worker_batches, worker_indices


def _evaluate_sequential(
    tasks: list[RouteTask],
    grid: VoxelGrid,
    config: ProjectConfig,
) -> list[RouteResult]:
    """Sequential evaluation: sort by room then run the shared batch core.

    Args:
        tasks: Route tasks in original order.
        grid: Voxel grid.
        config: Project config.

    Returns:
        RouteResult list in the same order as ``tasks``.
    """
    indexed = sorted(enumerate(tasks), key=lambda x: x[1].room.guid)
    sorted_tasks = [t for _, t in indexed]
    orig_indices  = [i for i, _ in indexed]

    batch_results = _evaluate_task_batch(sorted_tasks, grid, config, None)

    ordered: list[RouteResult | None] = [None] * len(tasks)
    for result, orig_idx in zip(batch_results, orig_indices):
        ordered[orig_idx] = result

    return ordered  # type: ignore[return-value]


def _evaluate_task_batch(
    tasks: list[RouteTask],
    grid: VoxelGrid,
    config: ProjectConfig,
    existing_network_mask: np.ndarray | None,
) -> list[RouteResult]:
    """Shared two-level cached evaluation core.

    Level 1 — cost-array cache: one NumPy array per (strategy, mask_id).
    Level 2 — route cache: one path payload per (start, target, strategy).

    Args:
        tasks: Tasks processed in given order (sort by room for best hit rate).
        grid: Voxel grid.
        config: Project config.
        existing_network_mask: Optional network reward mask.

    Returns:
        RouteResult list in the same order as ``tasks``.
    """
    cost_array_cache: dict[tuple[str, int], np.ndarray] = {}
    route_cache: dict[tuple[Any, Any, str], _CachedPath] = {}
    results: list[RouteResult] = []

    for task in tasks:
        strategy = config.strategies[task.strategy_name]

        floor_idx = (
            task.floor_index_override
            if task.floor_index_override is not None
            else task.room.floor_index
        )
        target = grid.shaft_targets.get((task.shaft.guid, floor_idx))

        if target is None:
            results.append(RouteResult(
                demand_id=task.demand.demand_id,
                room_guid=task.room.guid,
                room_name=task.room.label(),
                service=task.demand.service,
                shaft_guid=task.shaft.guid,
                shaft_name=task.shaft.label(),
                strategy=task.strategy_name,
                success=False,
                score=1_000_000.0,
                message="No shaft target found on the room floor.",
            ))
            continue

        start = (
            task.start_voxel
            if task.start_voxel is not None
            else grid.get_room_center_index(task.room)
        )

        # Level-1: cost array
        cost_key = (task.strategy_name, id(existing_network_mask))
        if cost_key not in cost_array_cache:
            cost_array_cache[cost_key] = build_cell_cost_array(grid, strategy, existing_network_mask)
        cell_cost = cost_array_cache[cost_key]

        # Level-2: route cache (service-agnostic)
        route_key = (start, target, task.strategy_name)

        if route_key in route_cache:
            cached_path, cached_xyz, cached_metrics, cached_score = route_cache[route_key]
            results.append(RouteResult(
                demand_id=task.demand.demand_id,
                room_guid=task.room.guid,
                room_name=task.room.label(),
                service=task.demand.service,
                shaft_guid=task.shaft.guid,
                shaft_name=task.shaft.label(),
                strategy=task.strategy_name,
                success=True,
                score=cached_score,
                path_indices=cached_path,
                path_xyz=cached_xyz,
                metrics=cached_metrics,
                message="ok",
            ))
            continue

        # Cache miss: scale k by shaft distance, then compute
        k = _adaptive_k(start, target, grid.voxel_size, config.k_routes_per_strategy)

        result = build_route_result(
            demand=task.demand,
            room=task.room,
            shaft=task.shaft,
            strategy=strategy,
            grid=grid,
            existing_network_mask=existing_network_mask,
            cell_cost=cell_cost,
            start_voxel=start,
            target_voxel=target,
            floor_index_override=task.floor_index_override,
            k_routes=k,
            penalty_factor=config.penalty_factor,
        )

        if result.success:
            route_cache[route_key] = (
                result.path_indices,
                result.path_xyz,
                result.metrics,
                result.score,
            )

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Route result builder
# ---------------------------------------------------------------------------

def build_route_result(
    demand: DemandRecord,
    room: SpaceRecord,
    shaft: SpaceRecord,
    strategy: StrategyProfile,
    grid: VoxelGrid,
    existing_network_mask: np.ndarray | None,
    cell_cost: np.ndarray | None = None,
    start_voxel: tuple[int, int, int] | None = None,
    target_voxel: tuple[int, int, int] | None = None,
    floor_index_override: int | None = None,
    k_routes: int = 1,
    penalty_factor: float = 3.0,
) -> RouteResult:
    """Build one route result, optionally picking the best of k penalty-replanned paths.

    Args:
        demand: Demand record.
        room: Start room.
        shaft: Target shaft or technikraum.
        strategy: Strategy profile.
        grid: Voxel grid.
        existing_network_mask: Existing network reward mask.
        cell_cost: Pre-baked cost array; built automatically if None.
        start_voxel: Optional explicit start voxel.
        target_voxel: Optional explicit target voxel.
        floor_index_override: Optional floor index for A* restriction.
        k_routes: Number of penalty-replan iterations (1 = single A* run).
        penalty_factor: Cost multiplier for penalised cells.

    Returns:
        RouteResult object.
    """
    if target_voxel is not None:
        target = target_voxel
    else:
        floor_idx_for_lookup = (
            floor_index_override if floor_index_override is not None else room.floor_index
        )
        target = grid.shaft_targets.get((shaft.guid, floor_idx_for_lookup))
        if target is None:
            return RouteResult(
                demand_id=demand.demand_id,
                room_guid=room.guid,
                room_name=room.label(),
                service=demand.service,
                shaft_guid=shaft.guid,
                shaft_name=shaft.label(),
                strategy=strategy.name,
                success=False,
                score=1_000_000.0,
                message="No shaft target found on the room floor.",
            )

    start = start_voxel if start_voxel is not None else grid.get_room_center_index(room)

    route_floor_index = (
        floor_index_override if floor_index_override is not None else room.floor_index
    )

    if cell_cost is None:
        cell_cost = build_cell_cost_array(grid, strategy, existing_network_mask)

    candidate_paths = penalty_replan_k_routes(
        start=start,
        target=target,
        room_floor_index=route_floor_index,
        grid=grid,
        strategy=strategy,
        cell_cost=cell_cost,
        k=k_routes,
        penalty_factor=penalty_factor,
    )

    if not candidate_paths:
        return RouteResult(
            demand_id=demand.demand_id,
            room_guid=room.guid,
            room_name=room.label(),
            service=demand.service,
            shaft_guid=shaft.guid,
            shaft_name=shaft.label(),
            strategy=strategy.name,
            success=False,
            score=1_000_000.0,
            message="No path found.",
        )

    best_result: RouteResult | None = None
    best_score = float("inf")

    for path in candidate_paths:
        path_xyz = [grid.index_to_world(cell) for cell in path]
        metrics  = compute_route_metrics(path, grid)

        score = (
            float(metrics["length_m"]) * strategy.length_weight
            + float(metrics["bend_count"]) * strategy.bend_penalty
            + float(metrics["vertical_length_m"]) * strategy.vertical_penalty
            + float(metrics["wall_crossings"])
            * (0.0 if strategy.ignore_wall_penalty else strategy.wall_cross_penalty)
            + float(metrics["slab_crossings"]) * strategy.slab_cross_penalty
            - float(metrics["shared_length_m"]) * strategy.merge_reward
        )

        if score < best_score:
            best_score = score
            best_result = RouteResult(
                demand_id=demand.demand_id,
                room_guid=room.guid,
                room_name=room.label(),
                service=demand.service,
                shaft_guid=shaft.guid,
                shaft_name=shaft.label(),
                strategy=strategy.name,
                success=True,
                score=score,
                path_indices=path,
                path_xyz=path_xyz,
                metrics=metrics,
                message="ok",
            )

    return best_result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Penalty-based replanning
# ---------------------------------------------------------------------------

def penalty_replan_k_routes(
    start: tuple[int, int, int],
    target: tuple[int, int, int],
    room_floor_index: int,
    grid: VoxelGrid,
    strategy: StrategyProfile,
    cell_cost: np.ndarray,
    k: int = 5,
    penalty_factor: float = 3.0,
) -> list[list[tuple[int, int, int]]]:
    """Find up to k spatially different paths via penalty-based replanning.

    After each A* run all intermediate cells are penalised in a float32
    overlay so the next run is pushed into different corridors.  The overlay
    is always passed to the numba A* core (zero-initialised on the first run,
    effectively a no-op).

    An early-exit threshold stops replanning once the candidate path length
    exceeds 3× the straight-line distance — such detours will never beat
    the first candidate on original costs.

    Args:
        start: Start voxel.
        target: Target voxel.
        room_floor_index: Floor restriction for A*.
        grid: Voxel grid (read-only).
        strategy: Strategy profile.
        cell_cost: Pre-baked cost array (read-only).
        k: Maximum replanning iterations.
        penalty_factor: Cost added per penalised cell per iteration.

    Returns:
        List of paths; may be shorter than k.
    """
    penalty_mask = np.zeros(grid.shape, dtype=np.float32)
    cell_penalty = float(penalty_factor) * float(grid.voxel_size)

    found_paths: list[list[tuple[int, int, int]]] = []

    for _ in range(max(k, 1)):
        path = a_star_route(
            start,
            target,
            room_floor_index,
            grid,
            strategy,
            cell_cost,
            extra_penalty=penalty_mask,
        )

        if not path:
            break

        found_paths.append(path)

        if k <= 1:
            break

        for cell in path[1:-1]:
            penalty_mask[cell] += cell_penalty

    return found_paths


# ---------------------------------------------------------------------------
# Core A* — Python wrapper around the numba kernel
# ---------------------------------------------------------------------------

def a_star_route(
    start: tuple[int, int, int],
    target: tuple[int, int, int],
    room_floor_index: int,
    grid: VoxelGrid,
    strategy: StrategyProfile,
    cell_cost: np.ndarray,
    extra_penalty: np.ndarray | None = None,
) -> list[tuple[int, int, int]]:
    """Route on the voxel grid using the numba-compiled A* kernel.

    On the first call numba compiles ``_a_star_numba`` to native machine
    code (typically 10–30 s).  The compiled code is cached to disk
    (``cache=True``) so subsequent runs — including after server restarts —
    skip compilation entirely.

    Expected speedup over the pure-Python implementation: 10–50×.

    Args:
        start: Start voxel.
        target: Target voxel.
        room_floor_index: Floor restriction for non-shaft cells.
        grid: Voxel grid.
        strategy: Strategy profile (direction-dependent costs).
        cell_cost: Pre-baked position-dependent cost array.
        extra_penalty: Optional replanning overlay (same shape as grid).

    Returns:
        List of voxel index tuples, or empty list if no path exists.
    """
    buf     = _get_astar_buffers(tuple(grid.shape))
    penalty = buf.zero_penalty if extra_penalty is None else extra_penalty

    # Ensure dtypes expected by the numba kernel.  These are no-ops when the
    # arrays already have the correct dtype, which is the common case.
    traversable = (
        grid.traversable_mask
        if grid.traversable_mask.dtype == np.bool_
        else grid.traversable_mask.astype(np.bool_)
    )
    shaft = (
        grid.shaft_mask
        if grid.shaft_mask.dtype == np.bool_
        else grid.shaft_mask.astype(np.bool_)
    )
    room = (
        grid.room_mask
        if grid.room_mask.dtype == np.bool_
        else grid.room_mask.astype(np.bool_)
    )
    floor_lbl = (
        grid.floor_labels
        if grid.floor_labels.dtype == np.int32
        else grid.floor_labels.astype(np.int32)
    )
    cc  = cell_cost if cell_cost.dtype == np.float32 else cell_cost.astype(np.float32)
    pen = penalty   if penalty.dtype   == np.float32 else penalty.astype(np.float32)

    path_len = _a_star_numba(
        np.int32(start[0]),  np.int32(start[1]),  np.int32(start[2]),
        np.int32(target[0]), np.int32(target[1]), np.int32(target[2]),
        buf.X, buf.Y, buf.Z, buf.SYZ7, buf.SZ7,
        traversable, shaft, room, floor_lbl,
        cc, pen,
        np.int32(room_floor_index),
        np.float32(strategy.bend_penalty),
        np.float32(strategy.vertical_penalty),
        np.float32(grid.voxel_size),
        buf.best_cost, buf.parent,
        buf.heap_f, buf.heap_g, buf.heap_s,
        buf.path_x, buf.path_y, buf.path_z,
    )

    if path_len == 0:
        return []

    return [
        (int(buf.path_x[i]), int(buf.path_y[i]), int(buf.path_z[i]))
        for i in range(int(path_len))
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adaptive_k(
    start: tuple[int, int, int],
    target: tuple[int, int, int],
    voxel_size: float,
    k_max: int,
) -> int:
    """Scale replanning iterations by straight-line shaft distance.

    A distant shaft is very unlikely to be selected — scoring always favours
    shorter paths.  Running k_max iterations for such a shaft wastes time.

    Args:
        start: Room centre voxel.
        target: Shaft entry voxel.
        voxel_size: Voxel edge length in metres.
        k_max: Maximum iterations from config.

    Returns:
        Adjusted k between 1 and k_max inclusive.
    """
    if k_max <= 1:
        return k_max

    dx = start[0] - target[0]
    dy = start[1] - target[1]
    dz = start[2] - target[2]
    dist_m = math.sqrt(dx * dx + dy * dy + dz * dz) * voxel_size

    near_m = 10.0
    far_m  = 30.0

    if dist_m <= near_m:
        return k_max
    if dist_m >= far_m:
        return 1

    ratio = (dist_m - near_m) / (far_m - near_m)
    return max(1, round(k_max * (1.0 - ratio * 0.8)))


def _init_worker(context: dict[str, Any]) -> None:
    """Set the worker global context.

    Args:
        context: Shared context (grid, config).

    Returns:
        None.
    """
    global WORKER_CONTEXT
    WORKER_CONTEXT = context


def _evaluate_task_batch_worker(tasks: list[RouteTask]) -> list[RouteResult]:
    """Worker-side batch evaluation using the shared two-level cache core.

    Args:
        tasks: Room-grouped route tasks for this worker.

    Returns:
        RouteResult list in the same order as ``tasks``.
    """
    grid   = WORKER_CONTEXT["grid"]
    config = WORKER_CONTEXT["config"]
    return _evaluate_task_batch(tasks, grid, config, None)