"""Geometric primitive data classes used throughout the pipe-planner domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Placement:
    """A point in 3-D space that describes the position of an object.

    Args:
        x: X coordinate in metres.
        y: Y coordinate in metres.
        z: Z coordinate in metres.
    """

    x: float
    y: float
    z: float

    def to_dict(self) -> dict[str, float]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with keys ``x``, ``y``, ``z``.
        """
        return asdict(self)


@dataclass
class BBox:
    """Axis-aligned bounding box in 3-D space.

    Args:
        min_x: Minimum X coordinate in metres.
        min_y: Minimum Y coordinate in metres.
        min_z: Minimum Z coordinate in metres.
        max_x: Maximum X coordinate in metres.
        max_y: Maximum Y coordinate in metres.
        max_z: Maximum Z coordinate in metres.
    """

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def center(self) -> tuple[float, float, float]:
        """Return the geometric centre of the bounding box.

        Returns:
            Tuple ``(cx, cy, cz)`` in metres.
        """
        return (
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
            (self.min_z + self.max_z) / 2.0,
        )

    def placement(self) -> Placement:
        """Return the centre as a :class:`Placement` object.

        Returns:
            Placement at the bounding-box centre.
        """
        x, y, z = self.center()
        return Placement(x=x, y=y, z=z)

    def size(self) -> tuple[float, float, float]:
        """Return the width, depth and height of the bounding box.

        Returns:
            Tuple ``(width, depth, height)`` in metres.
        """
        return (
            self.max_x - self.min_x,
            self.max_y - self.min_y,
            self.max_z - self.min_z,
        )

    def area_xy(self) -> float:
        """Return the horizontal footprint area.

        Returns:
            Area in square metres (width times depth).
        """
        width, depth, _ = self.size()
        return max(0.0, width) * max(0.0, depth)

    def expand(self, amount: float) -> "BBox":
        """Return a new bounding box padded by *amount* on every side.

        Args:
            amount: Padding distance in metres.

        Returns:
            Expanded bounding box.
        """
        return BBox(
            self.min_x - amount,
            self.min_y - amount,
            self.min_z - amount,
            self.max_x + amount,
            self.max_y + amount,
            self.max_z + amount,
        )

    def union(self, other: "BBox") -> "BBox":
        """Return the smallest bounding box that contains both boxes.

        Args:
            other: Second bounding box.

        Returns:
            Union bounding box.
        """
        return BBox(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            min(self.min_z, other.min_z),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
            max(self.max_z, other.max_z),
        )

    def contains_point(self, point: tuple[float, float, float]) -> bool:
        """Return whether *point* is inside or on the surface of the box.

        Args:
            point: Tuple ``(x, y, z)`` in metres.

        Returns:
            ``True`` if the point is contained.
        """
        x, y, z = point
        return (
            self.min_x <= x <= self.max_x
            and self.min_y <= y <= self.max_y
            and self.min_z <= z <= self.max_z
        )

    def z_overlap(self, other: "BBox") -> float:
        """Return the vertical overlap between this and another bounding box.

        Args:
            other: Second bounding box.

        Returns:
            Overlap distance in metres (0 if boxes do not overlap vertically).
        """
        return max(0.0, min(self.max_z, other.max_z) - max(self.min_z, other.min_z))

    def to_dict(self) -> dict[str, float]:
        """Return a plain dictionary representation.

        Returns:
            Dictionary with all six coordinate keys.
        """
        return asdict(self)
