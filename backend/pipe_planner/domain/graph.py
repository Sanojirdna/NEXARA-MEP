"""Graph data classes for the spatial routing environment."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Node:
    """A node in the routing graph.

    Args:
        id: Unique node identifier.
        x: X coordinate in metres.
        y: Y coordinate in metres.
        z: Z coordinate in metres.
        kind: Node classification, e.g. ``room``, ``shaft``, ``corridor``.
        room_id: Identifier of the containing room (empty if not inside a room).
    """

    id: str
    x: float
    y: float
    z: float
    kind: str
    room_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all node fields.
        """
        return asdict(self)


@dataclass
class Edge:
    """A directed edge connecting two nodes in the routing graph.

    Args:
        from_id: Source node identifier.
        to_id: Target node identifier.
        kind: Edge classification, e.g. ``horizontal``, ``vertical``.
        length_m: Edge length in metres.
    """

    from_id: str
    to_id: str
    kind: str
    length_m: float

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all edge fields.
        """
        return asdict(self)


@dataclass
class EnvironmentGraph:
    """Spatial graph connecting rooms, shafts, and corridors.

    Args:
        nodes: Node registry keyed by node identifier.
        edges: Directed edge list.
    """

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def neighbors(self, node_id: str) -> list[Node]:
        """Return all nodes directly reachable from *node_id*.

        Args:
            node_id: Source node identifier.

        Returns:
            List of adjacent :class:`Node` objects.
        """
        neighbor_ids = [edge.to_id for edge in self.edges if edge.from_id == node_id]
        return [self.nodes[n_id] for n_id in neighbor_ids if n_id in self.nodes]
