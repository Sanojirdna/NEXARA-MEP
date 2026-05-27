from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from pipe_planner.config import ProjectConfig
from pipe_planner.models import BBox, FloorBand, ObstacleRecord, SpaceRecord


@dataclass
class VoxelGrid:
    """Voxel representation of the building.

    Args:
        origin: World-space origin of the grid.
        voxel_size: Edge length of one voxel.
        shape: Grid size in X, Y, Z.
        traversable_mask: Cells that may be used by routing.
        room_mask: Cells inside rooms.
        corridor_mask: Cells inside corridors.
        shaft_mask: Cells inside shafts.
        wall_mask: Cells that belong to walls.
        slab_mask: Cells that belong to slabs.
        blocked_mask: Cells blocked by columns, beams, or proxies.
        room_labels: Integer label for room ownership.
        floor_labels: Integer floor label per cell.
        wall_distance: Distance to the nearest wall cell.
        corridor_distance: Distance to the corridor boundary.
        ceiling_score: Higher values mean closer to the floor ceiling.

    Returns:
        VoxelGrid object.
    """

    origin: np.ndarray
    voxel_size: float
    shape: tuple[int, int, int]
    traversable_mask: np.ndarray
    room_mask: np.ndarray
    corridor_mask: np.ndarray
    shaft_mask: np.ndarray
    wall_mask: np.ndarray
    slab_mask: np.ndarray
    blocked_mask: np.ndarray
    room_labels: np.ndarray
    floor_labels: np.ndarray
    wall_distance: np.ndarray
    corridor_distance: np.ndarray
    ceiling_score: np.ndarray
    room_index_to_guid: dict[int, str]
    room_guid_to_index: dict[str, int]
    shaft_targets: dict[tuple[str, int], tuple[int, int, int]]
    floor_bounds: dict[int, tuple[float, float]]

    def world_to_index(self, point: tuple[float, float, float]) -> tuple[int, int, int]:
        """Convert a world point to voxel indices.

        Args:
            point: XYZ world point.

        Returns:
            Grid indices.
        """
        coords = np.array(point, dtype=float)
        index = np.floor((coords - self.origin) / self.voxel_size).astype(int)
        index = np.clip(index, 0, np.array(self.shape) - 1)
        return int(index[0]), int(index[1]), int(index[2])

    def index_to_world(self, index: tuple[int, int, int]) -> tuple[float, float, float]:
        """Convert voxel indices to world coordinates at the cell center.

        Args:
            index: Grid indices.

        Returns:
            XYZ world point.
        """
        xyz = self.origin + (np.array(index, dtype=float) + 0.5) * self.voxel_size
        return float(xyz[0]), float(xyz[1]), float(xyz[2])

    def get_room_center_index(self, room: SpaceRecord) -> tuple[int, int, int]:
        """Find a good start cell for a room.

        Args:
            room: Room record.

        Returns:
            Grid indices.
        """
        target = self.world_to_index(room.bbox.center())
        if self.room_mask[target]:
            return target
        return self.find_nearest_valid_cell(target, required_room_guid=room.guid)

    def find_nearest_valid_cell(
        self,
        target: tuple[int, int, int],
        required_room_guid: str | None = None,
        required_floor_index: int | None = None,
    ) -> tuple[int, int, int]:
        """Search nearby cells for a valid traversable cell.

        Args:
            target: Starting grid index.
            required_room_guid: Optional room restriction.
            required_floor_index: Optional floor restriction.

        Returns:
            Grid index.
        """
        tx, ty, tz = target
        best_cell = target
        best_distance = 10**9

        for radius in range(0, 6):
            for ix in range(max(0, tx - radius), min(self.shape[0], tx + radius + 1)):
                for iy in range(max(0, ty - radius), min(self.shape[1], ty + radius + 1)):
                    for iz in range(max(0, tz - radius), min(self.shape[2], tz + radius + 1)):
                        if not self.traversable_mask[ix, iy, iz]:
                            continue
                        if required_floor_index is not None and self.floor_labels[ix, iy, iz] != required_floor_index:
                            continue
                        if required_room_guid is not None:
                            room_index = self.room_guid_to_index.get(required_room_guid, -1)
                            if self.room_labels[ix, iy, iz] != room_index:
                                continue
                        distance = abs(ix - tx) + abs(iy - ty) + abs(iz - tz)
                        if distance < best_distance:
                            best_distance = distance
                            best_cell = (ix, iy, iz)

            if best_distance < 10**9:
                return best_cell

        return best_cell



def _matches_no_route_space(space: SpaceRecord, config: ProjectConfig) -> bool:
    """Return True when a space should be blocked for routing.

    Args:
        space: IFC space record.
        config: Project configuration.

    Returns:
        True if routing must not pass through the space.
    """
    text = f"{space.name} {space.long_name}".strip().lower()
    for keyword in config.keyword_config.no_route_space_keywords:
        if str(keyword).strip().lower() in text:
            return True
    return False

def _footprint_mask_2d(
    footprint: list[tuple[float, float]],
    origin_x: float,
    origin_y: float,
    voxel_size: float,
    shape_x: int,
    shape_y: int,
) -> np.ndarray:
    """
    Boolean 2-D mask (shape_x, shape_y) where True = voxel centre is inside
    the polygon footprint.  Uses vectorised ray-casting (even-odd rule).
    Falls back gracefully to a full True block if the footprint has < 3 pts.
    """
    if len(footprint) < 3:
        return np.ones((shape_x, shape_y), dtype=bool)

    # Voxel centre world coordinates
    gx = origin_x + (np.arange(shape_x) + 0.5) * voxel_size
    gy = origin_y + (np.arange(shape_y) + 0.5) * voxel_size
    GX, GY = np.meshgrid(gx, gy, indexing="ij")   # (shape_x, shape_y)

    inside = np.zeros((shape_x, shape_y), dtype=bool)
    n = len(footprint)

    for k in range(n):
        x1, y1 = footprint[k]
        x2, y2 = footprint[(k + 1) % n]

        # Horizontal ray to the right: count crossings
        cross = ((y1 <= GY) & (GY < y2)) | ((y2 <= GY) & (GY < y1))
        with np.errstate(divide="ignore", invalid="ignore"):
            x_cross = np.where(
                cross,
                x1 + (x2 - x1) * (GY - y1) / (y2 - y1),
                np.inf,
            )
        inside ^= cross & (GX < x_cross)

    return inside


def _fill_space_mask(
    mask: np.ndarray,
    space: "SpaceRecord",
    origin: np.ndarray,
    voxel_size: float,
    shape: tuple[int, int, int],
) -> np.ndarray:
    """
    Return a 3-D boolean array for one space, using the real polygon footprint
    if available or the bounding box as a fallback.

    The returned array has the same shape as *mask* and can be used with
    ``mask |= filled`` or ``mask[filled] = value``.
    """
    slices = _bbox_to_slices(space.bbox, origin, voxel_size, shape)
    sx = slice(*slices[0].indices(shape[0]))
    sy = slice(*slices[1].indices(shape[1]))
    sz = slice(*slices[2].indices(shape[2]))

    nx = sx.stop - sx.start
    ny = sy.stop - sy.start
    nz = sz.stop - sz.start

    if nx <= 0 or ny <= 0 or nz <= 0:
        return np.zeros(shape, dtype=bool)

    fp = getattr(space, "footprint", [])
    if len(fp) >= 3:
        # Polygon mask in the sub-grid covered by the bbox
        sub_ox = float(origin[0]) + sx.start * voxel_size
        sub_oy = float(origin[1]) + sy.start * voxel_size
        poly_2d = _footprint_mask_2d(fp, sub_ox, sub_oy, voxel_size, nx, ny)
        # Extrude to 3-D
        sub_3d = poly_2d[:, :, np.newaxis] * np.ones((1, 1, nz), dtype=bool)
    else:
        # Fallback: entire bbox block
        sub_3d = np.ones((nx, ny, nz), dtype=bool)

    result = np.zeros(shape, dtype=bool)
    result[sx, sy, sz] = sub_3d
    return result


def build_voxel_grid(
    spaces: list[SpaceRecord],
    obstacles: list[ObstacleRecord],
    floors: list[FloorBand],
    config: ProjectConfig,
) -> VoxelGrid:
    """Build a voxel grid from spaces and obstacles.

    Args:
        spaces: IFC spaces.
        obstacles: IFC obstacles.
        floors: Floor bands.
        config: Project configuration.

    Returns:
        VoxelGrid object.
    """
    full_bbox = _compute_full_bbox(spaces, obstacles, config.penalty_config.voxel_margin)
    voxel_size = config.voxel_size

    size_x = int(np.ceil((full_bbox.max_x - full_bbox.min_x) / voxel_size)) + 1
    size_y = int(np.ceil((full_bbox.max_y - full_bbox.min_y) / voxel_size)) + 1
    size_z = int(np.ceil((full_bbox.max_z - full_bbox.min_z) / voxel_size)) + 1
    shape = (size_x, size_y, size_z)
    origin = np.array([full_bbox.min_x, full_bbox.min_y, full_bbox.min_z], dtype=float)

    room_mask = np.zeros(shape, dtype=bool)
    corridor_mask = np.zeros(shape, dtype=bool)
    shaft_mask = np.zeros(shape, dtype=bool)
    wall_mask = np.zeros(shape, dtype=bool)
    slab_mask = np.zeros(shape, dtype=bool)
    blocked_mask = np.zeros(shape, dtype=bool)
    no_route_space_mask = np.zeros(shape, dtype=bool)
    room_labels = np.full(shape, -1, dtype=np.int32)
    floor_labels = np.full(shape, -1, dtype=np.int32)

    room_index_to_guid: dict[int, str] = {}
    room_guid_to_index: dict[str, int] = {}

    room_counter = 0
    for space in spaces:
        # Use real polygon footprint where available; bbox fallback otherwise
        filled = _fill_space_mask(space, space, origin, voxel_size, shape)

        if _matches_no_route_space(space, config):
            no_route_space_mask |= filled

        if space.space_type in ("room", "technical_room"):
            room_mask |= filled
            room_index_to_guid[room_counter] = space.guid
            room_guid_to_index[space.guid] = room_counter
            room_labels[filled] = room_counter
            room_counter += 1
        elif space.space_type == "corridor":
            corridor_mask |= filled
        elif space.space_type == "shaft":
            shaft_mask |= filled

    for obstacle in obstacles:
        slices = _bbox_to_slices(obstacle.bbox, origin, voxel_size, shape)
        if obstacle.category == "wall":
            wall_mask[slices] = True
        elif obstacle.category == "slab":
            slab_mask[slices] = True
        else:
            blocked_mask[slices] = True

    for floor in floors:
        z0 = int(np.floor((floor.z_min - full_bbox.min_z) / voxel_size))
        z1 = int(np.ceil((floor.z_max - full_bbox.min_z) / voxel_size))
        z0 = max(0, min(shape[2] - 1, z0))
        z1 = max(0, min(shape[2], z1))
        if z1 <= z0:
            z1 = min(shape[2], z0 + 1)
        floor_labels[:, :, z0:z1] = floor.floor_index

    traversable_mask = room_mask | corridor_mask | shaft_mask | wall_mask
    traversable_mask &= ~blocked_mask
    traversable_mask &= ~(slab_mask & ~shaft_mask)
    traversable_mask &= ~no_route_space_mask

    wall_distance = np.zeros(shape, dtype=np.int16)
    corridor_distance = np.zeros(shape, dtype=np.int16)
    ceiling_score = np.zeros(shape, dtype=np.float32)

    floor_bounds = {floor.floor_index: (floor.z_min, floor.z_max) for floor in floors}
    for iz in range(shape[2]):
        z_world = origin[2] + (iz + 0.5) * voxel_size
        matched_floor = None
        for floor in floors:
            if floor.z_min <= z_world <= floor.z_max:
                matched_floor = floor
                break
        if matched_floor is None:
            continue
        floor_height = max(0.1, matched_floor.z_max - matched_floor.z_min)
        score = float((z_world - matched_floor.z_min) / floor_height)
        ceiling_score[:, :, iz] = score

    shaft_targets = _build_shaft_targets(spaces, floors, origin, voxel_size, shape, traversable_mask, shaft_mask)
    technikraum_targets = _build_technikraum_targets(spaces, origin, voxel_size, shape, traversable_mask, room_mask)
    shaft_targets.update(technikraum_targets)

    return VoxelGrid(
        origin=origin,
        voxel_size=voxel_size,
        shape=shape,
        traversable_mask=traversable_mask,
        room_mask=room_mask,
        corridor_mask=corridor_mask,
        shaft_mask=shaft_mask,
        wall_mask=wall_mask,
        slab_mask=slab_mask,
        blocked_mask=blocked_mask,
        room_labels=room_labels,
        floor_labels=floor_labels,
        wall_distance=wall_distance,
        corridor_distance=corridor_distance,
        ceiling_score=ceiling_score,
        room_index_to_guid=room_index_to_guid,
        room_guid_to_index=room_guid_to_index,
        shaft_targets=shaft_targets,
        floor_bounds=floor_bounds,
    )


def _compute_full_bbox(
    spaces: Iterable[SpaceRecord],
    obstacles: Iterable[ObstacleRecord],
    margin: float,
) -> BBox:
    """Build a single bbox around everything.

    Args:
        spaces: Space list.
        obstacles: Obstacle list.
        margin: Margin around result.

    Returns:
        BBox object.
    """
    boxes = [space.bbox for space in spaces] + [obstacle.bbox for obstacle in obstacles]
    if not boxes:
        return BBox(0.0, 0.0, 0.0, 10.0, 10.0, 3.0)

    full_bbox = boxes[0]
    for box in boxes[1:]:
        full_bbox = full_bbox.union(box)
    return full_bbox.expand(margin)


def _bbox_to_slices(
    bbox: BBox,
    origin: np.ndarray,
    voxel_size: float,
    shape: tuple[int, int, int],
) -> tuple[slice, slice, slice]:
    """Convert bbox to numpy slices.

    Args:
        bbox: Bounding box.
        origin: Grid origin.
        voxel_size: Voxel size.
        shape: Grid shape.

    Returns:
        Tuple of slices.
    """
    min_index = np.floor(
        (np.array([bbox.min_x, bbox.min_y, bbox.min_z]) - origin) / voxel_size
    ).astype(int)
    max_index = np.ceil(
        (np.array([bbox.max_x, bbox.max_y, bbox.max_z]) - origin) / voxel_size
    ).astype(int)

    min_index = np.clip(min_index, 0, np.array(shape) - 1)
    max_index = np.clip(max_index, 0, np.array(shape))
    max_index = np.maximum(max_index, min_index + 1)

    return (
        slice(int(min_index[0]), int(max_index[0])),
        slice(int(min_index[1]), int(max_index[1])),
        slice(int(min_index[2]), int(max_index[2])),
    )


def _build_shaft_targets(
    spaces: list[SpaceRecord],
    floors: list[FloorBand],
    origin: np.ndarray,
    voxel_size: float,
    shape: tuple[int, int, int],
    traversable_mask: np.ndarray,
    shaft_mask: np.ndarray,
) -> dict[tuple[str, int], tuple[int, int, int]]:
    """Create one target cell per shaft and floor.

    Args:
        spaces: Space list.
        floors: Floor list.
        origin: Grid origin.
        voxel_size: Voxel size.
        shape: Grid shape.
        traversable_mask: Traversable mask.
        shaft_mask: Shaft mask.

    Returns:
        Mapping of (shaft_guid, floor_index) to voxel index.
    """
    result: dict[tuple[str, int], tuple[int, int, int]] = {}

    for space in spaces:
        if space.space_type != "shaft":
            continue

        for floor in floors:
            z_min = max(space.bbox.min_z, floor.z_min)
            z_max = min(space.bbox.max_z, floor.z_max)
            if z_max <= z_min:
                continue

            center_point = (
                (space.bbox.min_x + space.bbox.max_x) / 2.0,
                (space.bbox.min_y + space.bbox.max_y) / 2.0,
                (z_min + z_max) / 2.0,
            )

            raw_index = np.floor((np.array(center_point) - origin) / voxel_size).astype(int)
            raw_index = np.clip(raw_index, 0, np.array(shape) - 1)
            target = (int(raw_index[0]), int(raw_index[1]), int(raw_index[2]))

            if not shaft_mask[target]:
                target = _search_nearest_shaft_cell(target, shaft_mask, traversable_mask)

            result[(space.guid, floor.floor_index)] = target

    return result


def _search_nearest_shaft_cell(
    target: tuple[int, int, int],
    shaft_mask: np.ndarray,
    traversable_mask: np.ndarray,
) -> tuple[int, int, int]:
    """Find the closest shaft voxel near a target.

    Args:
        target: Seed index.
        shaft_mask: Shaft mask.
        traversable_mask: Traversable cells.

    Returns:
        Best shaft voxel.
    """
    tx, ty, tz = target
    shape = shaft_mask.shape
    best = target
    best_distance = 10**9

    for radius in range(0, 6):
        for ix in range(max(0, tx - radius), min(shape[0], tx + radius + 1)):
            for iy in range(max(0, ty - radius), min(shape[1], ty + radius + 1)):
                for iz in range(max(0, tz - radius), min(shape[2], tz + radius + 1)):
                    if not shaft_mask[ix, iy, iz]:
                        continue
                    if not traversable_mask[ix, iy, iz]:
                        continue
                    distance = abs(ix - tx) + abs(iy - ty) + abs(iz - tz)
                    if distance < best_distance:
                        best_distance = distance
                        best = (ix, iy, iz)
        if best_distance < 10**9:
            return best

    return best

def _build_technikraum_targets(
    spaces: list,
    origin: "np.ndarray",
    voxel_size: float,
    shape: tuple,
    traversable_mask: "np.ndarray",
    room_mask: "np.ndarray",
) -> "dict[tuple[str, int], tuple[int, int, int]]":
    """Create one target voxel per Technikraum, keyed by (guid, floor_index).

    The result is merged into ``shaft_targets`` so that room-to-technikraum
    routing works through the existing ``build_route_result`` path without any
    extra special-casing.

    Args:
        spaces: Full space list (all types).
        origin: Grid origin.
        voxel_size: Voxel edge length.
        shape: Grid shape.
        traversable_mask: Traversable voxel mask.
        room_mask: Room voxel mask (technikraum cells are included here).

    Returns:
        Mapping of (technikraum_guid, floor_index) to voxel index.
    """
    result: dict[tuple[str, int], tuple[int, int, int]] = {}

    for space in spaces:
        if space.space_type != "technical_room":
            continue

        center_point = (
            (space.bbox.min_x + space.bbox.max_x) / 2.0,
            (space.bbox.min_y + space.bbox.max_y) / 2.0,
            (space.bbox.min_z + space.bbox.max_z) / 2.0,
        )
        raw_index = np.floor(
            (np.array(center_point) - origin) / voxel_size
        ).astype(int)
        raw_index = np.clip(raw_index, 0, np.array(shape) - 1)
        target = (int(raw_index[0]), int(raw_index[1]), int(raw_index[2]))

        if not (room_mask[target] and traversable_mask[target]):
            target = _search_nearest_room_cell(target, room_mask, traversable_mask, shape)

        result[(space.guid, space.floor_index)] = target

    return result


def _search_nearest_room_cell(
    target: tuple,
    room_mask: "np.ndarray",
    traversable_mask: "np.ndarray",
    shape: tuple,
) -> tuple:
    """Find the closest traversable room voxel near *target*.

    Args:
        target: Seed index.
        room_mask: Room voxel mask.
        traversable_mask: Traversable voxel mask.
        shape: Grid shape.

    Returns:
        Best room voxel near *target*.
    """
    tx, ty, tz = target
    best = target
    best_distance = 10**9

    for radius in range(0, 6):
        for ix in range(max(0, tx - radius), min(shape[0], tx + radius + 1)):
            for iy in range(max(0, ty - radius), min(shape[1], ty + radius + 1)):
                for iz in range(max(0, tz - radius), min(shape[2], tz + radius + 1)):
                    if not room_mask[ix, iy, iz]:
                        continue
                    if not traversable_mask[ix, iy, iz]:
                        continue
                    distance = abs(ix - tx) + abs(iy - ty) + abs(iz - tz)
                    if distance < best_distance:
                        best_distance = distance
                        best = (ix, iy, iz)
        if best_distance < 10**9:
            return best

    return best
