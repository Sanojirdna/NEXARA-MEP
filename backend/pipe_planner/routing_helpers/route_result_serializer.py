from __future__ import annotations

from typing import Any

from pipe_planner.models import SpaceRecord


def float_or_empty(value: Any) -> float | str:
    """Convert a value to a float when possible.

    Args:
        value: Any raw value.

    Returns:
        Float value or an empty string.
    """
    if value is None or value == "":
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return ""


def int_or_empty(value: Any) -> int | str:
    """Convert a value to an integer when possible.

    Args:
        value: Any raw value.

    Returns:
        Integer value or an empty string.
    """
    if value is None or value == "":
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return ""


def space_to_frontend(space: SpaceRecord) -> dict[str, Any]:
    """Convert a space record into a JSON-safe frontend dictionary.

    Args:
        space: Space record.

    Returns:
        Frontend dictionary.
    """
    return {
        "guid": space.guid,
        "name": space.name,
        "long_name": space.long_name,
        "label": space.label(),
        "space_type": space.space_type,
        "floor_index": space.floor_index,
        "bbox": space.bbox.to_dict(),
    }
