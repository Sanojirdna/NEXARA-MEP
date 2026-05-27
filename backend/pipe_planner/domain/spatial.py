"""Spatial domain data classes for IFC spaces, obstacles, and floor bands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .demand import Demand
from .geometry import BBox, Placement


@dataclass
class SpaceRecord:
    """An IFC space (room, shaft, corridor, or similar).

    Args:
        guid: IFC global unique identifier.
        name: Short space name from the IFC model.
        long_name: Long descriptive name from the IFC model.
        space_type: IFC space type classification string.
        bbox: Axis-aligned bounding box of the space.
        floor_index: Floor band index the space belongs to.
        source_type: IFC entity type, e.g. ``IfcSpace``.
        footprint: 2-D polygon vertices of the space footprint.
    """

    guid: str
    name: str
    long_name: str
    space_type: str
    bbox: BBox
    floor_index: int = -1
    source_type: str = "IfcSpace"
    footprint: list[tuple[float, float]] = field(default_factory=list)

    def label(self) -> str:
        """Return the display label for this space.

        Returns:
            Combined ``name | long_name`` string, or GUID if both are empty.
        """
        if self.long_name:
            return f"{self.name} | {self.long_name}"
        return self.name or self.guid

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all space fields, with the bounding box expanded.
        """
        data = asdict(self)
        data["bbox"] = self.bbox.to_dict()
        return data


@dataclass
class Room:
    """A simplified room record used for demand assignment.

    Args:
        id: Internal room identifier.
        ifc_guid: IFC global unique identifier.
        name: Room name.
        storey_id: Identifier of the parent building storey.
        z_min: Minimum Z coordinate of the room in metres.
        z_max: Maximum Z coordinate of the room in metres.
        footprint: 2-D polygon vertices of the room footprint.
        centroid: Geometric centre of the room.
        demands: List of MEP demands assigned to this room.
    """

    id: str
    ifc_guid: str
    name: str
    storey_id: str
    z_min: float
    z_max: float
    footprint: list[tuple[float, float]] = field(default_factory=list)
    centroid: Placement = field(default_factory=lambda: Placement(0.0, 0.0, 0.0))
    demands: list[Demand] = field(default_factory=list)

    def add_demand(self, demand: Demand) -> None:
        """Append a demand to the room's demand list.

        Args:
            demand: Demand to add.

        Returns:
            None.
        """
        self.demands.append(demand)


@dataclass
class MechanicalRoom:
    """A mechanical room placement record.

    Args:
        id: Internal mechanical room identifier.
        host_room_id: Identifier of the host room.
        required_area_m2: Required floor area in square metres.
        width_m: Room width in metres.
        depth_m: Room depth in metres.
        transform: Position of the mechanical room origin.
    """

    id: str
    host_room_id: str
    required_area_m2: float
    width_m: float
    depth_m: float
    transform: Placement


@dataclass
class ObstacleRecord:
    """An IFC element that the routing must avoid or penalise.

    Args:
        guid: IFC global unique identifier.
        name: Element name.
        category: IFC category, e.g. ``IfcWall``.
        bbox: Axis-aligned bounding box of the element.
        crossable: Whether routing is allowed to cross this element.
        penalty: Additional routing cost applied when crossing.
        source_type: IFC entity type string.
    """

    guid: str
    name: str
    category: str
    bbox: BBox
    crossable: bool
    penalty: float
    source_type: str

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all obstacle fields, with the bounding box expanded.
        """
        data = asdict(self)
        data["bbox"] = self.bbox.to_dict()
        return data


@dataclass
class FloorBand:
    """A horizontal slab band representing one building storey.

    Args:
        floor_index: Zero-based storey index.
        name: Storey name from the IFC model.
        z_min: Bottom Z coordinate of the band in metres.
        z_max: Top Z coordinate of the band in metres.
    """

    floor_index: int
    name: str
    z_min: float
    z_max: float

    def contains_z(self, z_value: float) -> bool:
        """Return whether *z_value* falls inside this floor band.

        Args:
            z_value: Elevation to test in metres.

        Returns:
            ``True`` if the elevation is within the band.
        """
        return self.z_min <= z_value <= self.z_max

    def overlap_ratio(self, bbox: BBox) -> float:
        """Return the vertical overlap fraction between this band and *bbox*.

        Args:
            bbox: Bounding box to compare against.

        Returns:
            Fraction in ``[0, 1]`` where 1 means the bounding box is fully inside
            the band.
        """
        overlap = max(0.0, min(self.z_max, bbox.max_z) - max(self.z_min, bbox.min_z))
        total = max(1e-6, bbox.max_z - bbox.min_z)
        return overlap / total

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all floor-band fields.
        """
        return asdict(self)
