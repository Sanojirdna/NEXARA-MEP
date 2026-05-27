from __future__ import annotations

import csv
import math
from typing import Any

from .constants import DATA_DIR, DIAGRAM_FILES


class DiagramRepository:
    """Load and interpolate digitized VDI diagram CSV data."""

    def __init__(self) -> None:
        self._diagram_cache: dict[str, dict[str, Any]] = {}

    def load_diagram(self, diagram_key: str) -> dict[str, Any]:
        """Return one VDI diagram data table."""
        return self._load_diagram(diagram_key)

    def interpolate(self, diagram_key: str, x_value: float) -> dict[str, float]:
        """Return interpolated diagram values for one x value."""
        return self._interpolate_diagram(diagram_key, x_value)

    def _interpolate_diagram(self, diagram_key: str, x_query: float) -> dict[str, float]:
        data = self._load_diagram(diagram_key)
        x_values = data["x"]
        result: dict[str, float] = {}
        clamped = False
        for column_name, y_values in data["series"].items():
            value, was_clamped = self._interpolate_series(x_values, y_values, x_query)
            result[column_name] = value
            clamped = clamped or was_clamped
        result["_clamped"] = clamped  # type: ignore[assignment]
        return result

    def _load_diagram(self, diagram_key: str) -> dict[str, Any]:
        if diagram_key in self._diagram_cache:
            return self._diagram_cache[diagram_key]

        filename = DIAGRAM_FILES[diagram_key]
        path = DATA_DIR / filename
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            x_values: list[float] = []
            series: dict[str, list[float]] = {}
            first_key = reader.fieldnames[0] if reader.fieldnames else None
            if first_key is None:
                payload = {"x": [], "series": {}}
                self._diagram_cache[diagram_key] = payload
                return payload

            for row in reader:
                if not row:
                    continue
                x_values.append(float(row[first_key]))
                for key, raw_value in row.items():
                    if key == first_key or raw_value in (None, ""):
                        continue
                    series.setdefault(key, []).append(float(raw_value))

        payload = {"x": x_values, "series": series}
        self._diagram_cache[diagram_key] = payload
        return payload

    def _interpolate_series(
        self,
        x_values: list[float],
        y_values: list[float],
        x_query: float,
    ) -> tuple[float, bool]:
        if not x_values:
            return 0.0, False
        if x_query <= x_values[0]:
            return float(y_values[0]), True
        if x_query >= x_values[-1]:
            return float(y_values[-1]), True

        for index in range(1, len(x_values)):
            x0 = x_values[index - 1]
            x1 = x_values[index]
            if x0 <= x_query <= x1:
                y0 = y_values[index - 1]
                y1 = y_values[index]
                if math.isclose(x0, x1):
                    return float(y0), False
                fraction = (x_query - x0) / (x1 - x0)
                return float(y0 + (y1 - y0) * fraction), False
        return float(y_values[-1]), True
