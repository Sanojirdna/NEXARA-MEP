from __future__ import annotations

import math
from typing import Any


class TechnikraumChartBuilder:
    """Prepare VDI chart payloads for the frontend."""

    def __init__(self, diagram_repository: Any) -> None:
        self.diagram_repository = diagram_repository

    def build_chart_payload(
        self,
        scenario: dict[str, str],
        x_value: float,
        actual_area_m2: float,
        expected_lower: float,
        expected_upper: float,
        cooling_addon_applied: bool,
        sprinkler_addon: float,
    ) -> dict[str, Any]:
        """Return a chart payload for one VDI scenario."""
        return self._build_chart_payload(
            scenario=scenario,
            x_value=x_value,
            actual_area_m2=actual_area_m2,
            expected_lower=expected_lower,
            expected_upper=expected_upper,
            cooling_addon_applied=cooling_addon_applied,
            sprinkler_addon=sprinkler_addon,
        )

    def _build_chart_payload(
        self,
        scenario: dict[str, str],
        x_value: float,
        actual_area_m2: float,
        expected_lower: float,
        expected_upper: float,
        cooling_addon_applied: bool,
        sprinkler_addon: float,
    ) -> dict[str, Any]:
        data = self.diagram_repository.load_diagram(scenario["diagram_key"])
        x_values = [float(value) for value in data["x"]]
        lower_values = [float(value) for value in data["series"][scenario["lower"]]]
        upper_values = [float(value) for value in data["series"][scenario["upper"]]]

        if cooling_addon_applied:
            adjusted_lower: list[float] = []
            adjusted_upper: list[float] = []
            for base_x, base_lower, base_upper in zip(x_values, lower_values, upper_values):
                cooling_curve = self.diagram_repository.interpolate("v1", base_x)
                adjusted_lower.append(base_lower + float(cooling_curve.get("TBA_KD_lower_m2", 0.0)))
                adjusted_upper.append(base_upper + float(cooling_curve.get("TBA_KD_upper_m2", 0.0)))
            lower_values = adjusted_lower
            upper_values = adjusted_upper

        if sprinkler_addon:
            lower_values = [value + sprinkler_addon for value in lower_values]
            upper_values = [value + sprinkler_addon for value in upper_values]

        x_min = min(x_values) if x_values else x_value
        x_max = max(x_values) if x_values else x_value
        plotted_x_value = min(max(x_value, x_min), x_max)
        y_candidates = lower_values + upper_values + [actual_area_m2, expected_lower, expected_upper]
        y_min = min(y_candidates) if y_candidates else 0.0
        y_max = max(y_candidates) if y_candidates else max(actual_area_m2, 1.0)
        padding = max((y_max - y_min) * 0.08, 4.0)

        return {
            "x_label": "BGF [1000 m²]",
            "y_label": "Technikfläche [m²]",
            "x_values": [round(value, 3) for value in x_values],
            "lower_values": [round(value, 2) for value in lower_values],
            "upper_values": [round(value, 2) for value in upper_values],
            "x_min": round(x_min, 3),
            "x_max": round(x_max, 3),
            "y_min": round(max(0.0, y_min - padding), 2),
            "y_max": round(y_max + padding, 2),
            "project_x_value": round(x_value, 3),
            "project_x_plot": round(plotted_x_value, 3),
            "project_y_value": round(actual_area_m2, 2),
            "expected_lower_m2": round(expected_lower, 2),
            "expected_upper_m2": round(expected_upper, 2),
            "x_was_clamped": not math.isclose(plotted_x_value, x_value, rel_tol=1e-9, abs_tol=1e-9),
        }
