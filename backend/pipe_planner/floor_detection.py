from __future__ import annotations

from typing import Iterable

from pipe_planner.models import FloorBand, SpaceRecord


def build_floor_bands_from_storeys(
    storey_data: list[tuple[str, float]],
    fallback_spaces: Iterable[SpaceRecord],
) -> list[FloorBand]:
    """Build floor bands from IFC storey elevations.

    Args:
        storey_data: List of (storey_name, elevation_z).
        fallback_spaces: Space list used to estimate thickness.

    Returns:
        List of FloorBand objects.
    """
    if not storey_data:
        return []

    sorted_storeys = sorted(storey_data, key=lambda item: item[1])

    estimated_height = _estimate_floor_height(fallback_spaces)
    bands: list[FloorBand] = []

    for index, (name, elevation) in enumerate(sorted_storeys):
        next_elevation = (
            sorted_storeys[index + 1][1]
            if index + 1 < len(sorted_storeys)
            else elevation + estimated_height
        )
        z_min = elevation - 0.25
        z_max = next_elevation - 0.25
        if z_max <= z_min:
            z_max = z_min + estimated_height

        bands.append(
            FloorBand(
                floor_index=index,
                name=name or f"Floor {index}",
                z_min=z_min,
                z_max=z_max,
            )
        )

    return bands


def build_floor_bands_from_space_ranges(spaces: Iterable[SpaceRecord]) -> list[FloorBand]:
    """Infer floors from the min and max Z ranges of spaces.

    Args:
        spaces: IFC spaces.

    Returns:
        List of FloorBand objects.
    """
    working_spaces = [
        space
        for space in spaces
        if space.space_type in {"room", "corridor", "shaft"}
    ]
    if not working_spaces:
        return []

    sorted_spaces = sorted(working_spaces, key=lambda space: (space.bbox.min_z, space.bbox.max_z))
    bands: list[FloorBand] = []

    current_min = sorted_spaces[0].bbox.min_z
    current_max = sorted_spaces[0].bbox.max_z
    band_spaces = [sorted_spaces[0]]

    tolerance = 0.35

    for space in sorted_spaces[1:]:
        if space.bbox.min_z <= current_max + tolerance:
            current_min = min(current_min, space.bbox.min_z)
            current_max = max(current_max, space.bbox.max_z)
            band_spaces.append(space)
        else:
            floor_index = len(bands)
            bands.append(
                FloorBand(
                    floor_index=floor_index,
                    name=f"Floor {floor_index}",
                    z_min=current_min,
                    z_max=current_max,
                )
            )
            current_min = space.bbox.min_z
            current_max = space.bbox.max_z
            band_spaces = [space]

    floor_index = len(bands)
    bands.append(
        FloorBand(
            floor_index=floor_index,
            name=f"Floor {floor_index}",
            z_min=current_min,
            z_max=current_max,
        )
    )

    return bands


def assign_spaces_to_floors(spaces: list[SpaceRecord], floors: list[FloorBand]) -> None:
    """Assign every space to the best floor band.

    Args:
        spaces: Space list to update in place.
        floors: Floor bands.

    Returns:
        None.
    """
    if not floors:
        return

    for space in spaces:
        best_index = 0
        best_score = -1.0

        for floor in floors:
            score = floor.overlap_ratio(space.bbox)
            if score > best_score:
                best_index = floor.floor_index
                best_score = score

        space.floor_index = best_index


def _estimate_floor_height(spaces: Iterable[SpaceRecord]) -> float:
    """Estimate a reasonable floor height from spaces.

    Args:
        spaces: Space list.

    Returns:
        Estimated floor height.
    """
    heights = [space.bbox.max_z - space.bbox.min_z for space in spaces]
    if not heights:
        return 3.0
    heights.sort()
    return max(2.8, heights[len(heights) // 2] + 0.5)
