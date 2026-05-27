"""Demand data classes representing MEP supply requirements for a room."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DemandRecord:
    """A single MEP demand linked to an IFC room.

    Args:
        demand_id: Unique demand identifier.
        room_guid: IFC GUID of the source room.
        room_name: Human-readable room label.
        service: Service code, e.g. ``HEI``, ``LUE``, ``SAN``.
        media_type: Transport medium, e.g. ``water``, ``air``.
        hvac_system_type: HVAC system type tag.
        kind: Demand kind, e.g. ``supply`` or ``return``.
        value: Numeric demand value.
        unit: Physical unit of *value*.
    """

    demand_id: str
    room_guid: str
    room_name: str
    service: str
    media_type: str
    hvac_system_type: str
    kind: str
    value: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all demand fields.
        """
        return asdict(self)


@dataclass
class Demand:
    """A media-level demand without room context.

    Args:
        media_type: Transport medium.
        hvac_system_type: HVAC system type tag.
        kind: Demand kind.
        value: Numeric demand value.
        unit: Physical unit of *value*.
    """

    media_type: str
    hvac_system_type: str
    kind: str
    value: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all demand fields.
        """
        return asdict(self)
