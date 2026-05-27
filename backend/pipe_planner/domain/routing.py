"""Routing domain data classes: strategies, route results, and system build outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ConstraintSet:
    """Soft routing constraints applied during path search.

    Args:
        bend_penalty: Extra cost added for each direction change.
        prefer_vertical_early: Incentive to climb early in the route.
        merge_fast_weight: Weight for shared-segment reward during fast-merge.
    """

    bend_penalty: float = 0.0
    prefer_vertical_early: float = 0.0
    merge_fast_weight: float = 0.0


@dataclass
class SegmentSize:
    """Cross-sectional size specification for one route segment.

    Args:
        shape: Cross-section shape, e.g. ``round``, ``rectangular``.
        diameter_mm: Outer diameter in millimetres (round cross-sections).
        width_mm: Width in millimetres (rectangular cross-sections).
        height_mm: Height in millimetres (rectangular cross-sections).
    """

    shape: str
    diameter_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0


@dataclass
class RouteSegment:
    """One straight segment within a solved route.

    Args:
        seq: Sequence index within the parent route.
        from_node: Start node identifier.
        to_node: End node identifier.
        length_m: Segment length in metres.
        bend: Whether this segment starts with a direction change.
        size: Cross-sectional size of the segment.
    """

    seq: int
    from_node: str
    to_node: str
    length_m: float
    bend: bool
    size: SegmentSize


@dataclass
class Route:
    """A complete solved route for one MEP demand.

    Args:
        id: Unique route identifier.
        route_set_id: Identifier of the parent route set.
        media_type: Transport medium, e.g. ``water``, ``air``.
        hvac_system_type: HVAC system type tag.
        segments: Ordered list of route segments.
    """

    id: str
    route_set_id: str
    media_type: str
    hvac_system_type: str
    segments: list[RouteSegment] = field(default_factory=list)

    def metrics(self) -> dict[str, Any]:
        """Return basic route metrics.

        Returns:
            Dictionary with ``segment_count``, ``length_m``, and ``bend_count``.
        """
        return {
            "segment_count": len(self.segments),
            "length_m": sum(segment.length_m for segment in self.segments),
            "bend_count": sum(1 for segment in self.segments if segment.bend),
        }


@dataclass
class Agent:
    """A routing agent that plans a path for one MEP demand.

    Args:
        id: Unique agent identifier.
        media_type: Transport medium.
        hvac_system_type: HVAC system type tag.
        flow: Required flow rate.
        current_node: Current position in the routing graph.
        route: Solved route (``None`` until the agent has finished).
    """

    id: str
    media_type: str
    hvac_system_type: str
    flow: float
    current_node: str
    route: Route | None = None

    def propose_step(self, env: Any, constraints: ConstraintSet) -> dict[str, Any]:
        """Return a step proposal for the current agent state.

        Args:
            env: Routing environment object.
            constraints: Active constraint set.

        Returns:
            Dictionary with proposal details.
        """
        return {
            "current_node": self.current_node,
            "bend_penalty": constraints.bend_penalty,
            "prefer_vertical_early": constraints.prefer_vertical_early,
        }

    def can_merge(self, other: "Agent") -> bool:
        """Return whether this agent can share a segment with *other*.

        Args:
            other: Candidate merge partner.

        Returns:
            ``True`` if both agents carry the same medium and system type.
        """
        return self.media_type == other.media_type and self.hvac_system_type == other.hvac_system_type

    def merge(self, other: "Agent") -> bool:
        """Attempt to merge this agent with *other*.

        Args:
            other: Agent to merge with.

        Returns:
            ``True`` if merging is possible.
        """
        return self.can_merge(other)


@dataclass
class StrategyProfile:
    """Weighted cost profile for one routing strategy.

    Args:
        name: Strategy identifier string.
        length_weight: Weight applied to total route length.
        bend_penalty: Additional cost per bend.
        vertical_penalty: Additional cost per vertical step.
        wall_cross_penalty: Additional cost per wall crossing.
        slab_cross_penalty: Additional cost per slab crossing.
        wall_distance_weight: Weight for closeness to walls.
        ceiling_weight: Weight for ceiling-level routing preference.
        corridor_center_weight: Weight for routing along corridor centres.
        merge_reward: Reward applied when segments can be shared.
        ignore_wall_penalty: If ``True``, wall-crossing costs are suppressed.
    """

    name: str
    length_weight: float
    bend_penalty: float
    vertical_penalty: float
    wall_cross_penalty: float
    slab_cross_penalty: float
    wall_distance_weight: float
    ceiling_weight: float
    corridor_center_weight: float
    merge_reward: float
    ignore_wall_penalty: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all strategy parameters.
        """
        return asdict(self)


@dataclass
class RouteResult:
    """Result for one solved routing demand.

    Args:
        demand_id: Demand identifier.
        room_guid: IFC GUID of the source room.
        room_name: Human-readable room label.
        service: Service code, e.g. ``HEI``.
        shaft_guid: IFC GUID of the target shaft.
        shaft_name: Human-readable shaft label.
        strategy: Strategy profile name used to solve this route.
        success: Whether a valid route was found.
        score: Weighted cost of the chosen route (lower is better).
        path_indices: Voxel index path as ``(ix, iy, iz)`` tuples.
        path_xyz: Continuous 3-D path as ``(x, y, z)`` tuples in metres.
        metrics: Detailed route metrics dictionary.
        message: Status or error message.
    """

    demand_id: str
    room_guid: str
    room_name: str
    service: str
    shaft_guid: str
    shaft_name: str
    strategy: str
    success: bool
    score: float
    path_indices: list[tuple[int, int, int]] = field(default_factory=list)
    path_xyz: list[tuple[float, float, float]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all route-result fields.
        """
        return asdict(self)


@dataclass
class SystemBuildResult:
    """Aggregated result for the full MEP routing system.

    Args:
        selections: Active shaft and strategy selection per demand ID.
        routes: List of all solved route results.
        system_metrics: Aggregated system-level metrics.
        success_count: Number of demands with a valid route.
        failed_count: Number of demands without a valid route.
    """

    selections: dict[str, dict[str, str]]
    routes: list[RouteResult]
    system_metrics: dict[str, Any]
    success_count: int
    failed_count: int

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all system-build-result fields.
        """
        return {
            "selections": self.selections,
            "routes": [route.to_dict() for route in self.routes],
            "system_metrics": self.system_metrics,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
        }

    def to_json(self) -> str:
        """Return a JSON string representation.

        Returns:
            Indented JSON string.
        """
        import json
        return json.dumps(self.to_dict(), indent=2)
