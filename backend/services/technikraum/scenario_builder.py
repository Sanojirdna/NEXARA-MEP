from __future__ import annotations

import math
from collections import defaultdict
from typing import Any
from .constants import (
    ADMIN_SCENARIOS,
    FALLBACK_USE_FAMILY_TOKENS,
    KITCHEN_SCENARIOS,
    RETAIL_SCENARIOS,
    STUDY_BUILDING_TYPE_RULES,
    USE_FAMILY_LABELS,
)


class TechnikraumScenarioBuilder:
    """Build VDI comparison scenarios for the current building."""

    def __init__(self, diagram_repository: Any, chart_builder: Any) -> None:
        self.diagram_repository = diagram_repository
        self.chart_builder = chart_builder

    def build_scenarios(
        self,
        use_family_key: str,
        approx_bgf_m2: float,
        building_height_m: float | None,
        study_rlt_central_selected: bool,
        cooling_detected: bool,
        sprinkler_detected: bool,
        actual_area_m2: float,
    ) -> list[dict[str, Any]]:
        """Return VDI scenario rows for the current project."""
        return self._build_scenarios(
            use_family_key=use_family_key,
            approx_bgf_m2=approx_bgf_m2,
            building_height_m=building_height_m,
            study_rlt_central_selected=study_rlt_central_selected,
            cooling_detected=cooling_detected,
            sprinkler_detected=sprinkler_detected,
            actual_area_m2=actual_area_m2,
        )

    def pick_best_match(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Return the best matching VDI scenario row."""
        return self._pick_best_match(rows)

    def detect_use_family(
        self,
        runtime: Any,
        rooms: list[Any],
        study_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the detected VDI use family for the project."""
        return self._detect_use_family(runtime, rooms, study_state)

    def approx_floor_areas(self, spaces: list[Any]) -> list[dict[str, Any]]:
        """Return approximate floor areas from IFC space bounding boxes."""
        return self._approx_floor_areas(spaces)

    def building_height_m(self, floors: list[Any]) -> float | None:
        """Return approximate building height in meters."""
        return self._building_height_m(floors)

    def study_rlt_central_selected(self, study_state: dict[str, Any]) -> bool:
        """Return whether Studie criterion 8.3 RLT zentral is selected."""
        return self._study_rlt_central_selected(study_state)

    def _detect_use_family(
        self,
        runtime: Any,
        rooms: list[Any],
        study_state: dict[str, Any],
    ) -> dict[str, Any]:
        selected_coords = [str(item) for item in (study_state.get("selected_coords") or [])]
        selected_rows = sorted(self._row_from_coord(item) for item in selected_coords)
        for row_index in selected_rows:
            if row_index in STUDY_BUILDING_TYPE_RULES:
                rule = STUDY_BUILDING_TYPE_RULES[row_index]
                return {
                    "key": rule["use_family_key"],
                    "label": rule["use_family_label"],
                    "study_label": rule["study_label"],
                    "source": rule["source"],
                    "from_study": True,
                    "is_analog": rule["is_analog"],
                }

        fallback_scores: dict[str, float] = defaultdict(float)
        for room in rooms:
            label = f"{getattr(room, 'name', '')} {getattr(room, 'long_name', '')}".lower()
            area = self._bbox_area(room)
            for family_key, tokens in FALLBACK_USE_FAMILY_TOKENS.items():
                if any(token in label for token in tokens):
                    fallback_scores[family_key] += max(area, 1.0)

        file_text = str(getattr(runtime, "current_ifc_name", "") or "").lower()
        for family_key, tokens in FALLBACK_USE_FAMILY_TOKENS.items():
            if any(token in file_text for token in tokens):
                fallback_scores[family_key] += 1000.0

        if fallback_scores:
            family_key = max(fallback_scores.items(), key=lambda item: item[1])[0]
        else:
            family_key = "administration"

        return {
            "key": family_key,
            "label": USE_FAMILY_LABELS.get(family_key, family_key),
            "study_label": None,
            "source": "fallback room names / IFC file name",
            "from_study": False,
            "is_analog": family_key != "retail",
            "scores": {key: round(value, 2) for key, value in sorted(fallback_scores.items())},
        }

    def _build_scenarios(
        self,
        use_family_key: str,
        approx_bgf_m2: float,
        building_height_m: float | None,
        study_rlt_central_selected: bool,
        cooling_detected: bool,
        sprinkler_detected: bool,
        actual_area_m2: float,
    ) -> list[dict[str, Any]]:
        if approx_bgf_m2 <= 0:
            return []

        x_value = approx_bgf_m2 / 1000.0
        if use_family_key == "retail":
            base_scenarios = RETAIL_SCENARIOS
        elif use_family_key == "kitchen":
            base_scenarios = KITCHEN_SCENARIOS
        else:
            if study_rlt_central_selected:
                base_scenarios = [scenario for scenario in ADMIN_SCENARIOS if scenario["key"] in {"v2", "v3"}]
            else:
                base_scenarios = [scenario for scenario in ADMIN_SCENARIOS if scenario["key"] == "v1"]

        rows: list[dict[str, Any]] = []
        for scenario in base_scenarios:
            interpolated = self.diagram_repository.interpolate(scenario["diagram_key"], x_value)
            lower = interpolated.get(scenario["lower"])
            upper = interpolated.get(scenario["upper"])
            if lower is None or upper is None:
                continue

            notes: list[str] = []
            if study_rlt_central_selected and use_family_key == "administration":
                notes.append("Studie Kriterium 8.3 'RLT zentral' is selected, so the Verwaltung diagrams V2 and V3 are shown for 6 and 9 m³/(h·m²).")
            if interpolated.get("_clamped"):
                notes.append("BGF lies outside the digitized diagram range. End value was used.")

            expected_lower = float(lower)
            expected_upper = float(upper)
            cooling_addon_applied = False
            sprinkler_addon = 0.0

            if use_family_key == "administration" and cooling_detected:
                cooling_curve = self.diagram_repository.interpolate("v1", x_value)
                addon_lower = cooling_curve.get("TBA_KD_lower_m2")
                addon_upper = cooling_curve.get("TBA_KD_upper_m2")
                if addon_lower is not None and addon_upper is not None:
                    expected_lower += float(addon_lower)
                    expected_upper += float(addon_upper)
                    cooling_addon_applied = True
                    notes.append(
                        "Cooling add-on from V1 (TBA/KD) was added because cooling-related technical rooms were detected in the IFC."
                    )

            if sprinkler_detected:
                sprinkler_addon_value = self._sprinkler_addon(building_height_m)
                if sprinkler_addon_value is not None:
                    sprinkler_addon = float(sprinkler_addon_value)
                    expected_lower += sprinkler_addon
                    expected_upper += sprinkler_addon
                    notes.append(
                        f"Sprinkler add-on of {sprinkler_addon:.0f} m² was added because a sprinkler-related technical room was detected in the IFC."
                    )

            status_key, gap_to_range_m2 = self._compare_to_range(
                value=actual_area_m2,
                lower=expected_lower,
                upper=expected_upper,
            )

            share_lower = expected_lower / approx_bgf_m2 * 100.0
            share_upper = expected_upper / approx_bgf_m2 * 100.0
            chart = self.chart_builder.build_chart_payload(
                scenario=scenario,
                x_value=x_value,
                actual_area_m2=actual_area_m2,
                expected_lower=expected_lower,
                expected_upper=expected_upper,
                cooling_addon_applied=cooling_addon_applied,
                sprinkler_addon=sprinkler_addon,
            )

            rows.append(
                {
                    "key": scenario["key"],
                    "label": scenario["label"],
                    "diagram_key": scenario["diagram_key"],
                    "expected_lower_m2": round(expected_lower, 2),
                    "expected_upper_m2": round(expected_upper, 2),
                    "expected_mid_m2": round((expected_lower + expected_upper) / 2.0, 2),
                    "expected_share_lower_pct": round(share_lower, 2),
                    "expected_share_upper_pct": round(share_upper, 2),
                    "status_key": status_key,
                    "status_label": self._status_label(status_key),
                    "gap_to_range_m2": round(gap_to_range_m2, 2),
                    "raumvorschlag": _raumvorschlag(gap_to_range_m2) if status_key == "below" else None,
                    "notes": notes,
                    "chart": chart,
                }
            )
        return rows

    def _pick_best_match(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None

        ranked = sorted(
            rows,
            key=lambda item: (
                0 if item.get("status_key") == "within" else 1,
                float(item.get("gap_to_range_m2") or 0.0),
            ),
        )
        return ranked[0]

    def _compare_to_range(self, value: float, lower: float, upper: float) -> tuple[str, float]:
        if value < lower:
            return "below", lower - value
        if value > upper:
            return "above", value - upper
        return "within", 0.0

    def _status_label(self, status_key: str) -> str:
        mapping = {
            "below": "unter VDI-Band",
            "within": "im VDI-Band",
            "above": "über VDI-Band",
        }
        return mapping.get(status_key, "-")

    def _sprinkler_addon(self, building_height_m: float | None) -> float | None:
        if building_height_m is None:
            return 110.0
        return 150.0 if building_height_m >= 45.0 else 110.0

    def _row_from_coord(self, coord: str) -> int:
        digits = "".join(character for character in str(coord) if character.isdigit())
        return int(digits) if digits else -1

    def _study_rlt_central_selected(self, study_state: dict[str, Any]) -> bool:
        selected_coords = [str(item) for item in (study_state.get("selected_coords") or [])]
        selected_rows = {self._row_from_coord(item) for item in selected_coords}
        return 57 in selected_rows

    def _approx_floor_areas(self, spaces: list[Any]) -> list[dict[str, Any]]:
        rects_by_floor: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
        for space in spaces:
            floor_index = getattr(space, "floor_index", -1)
            bbox = getattr(space, "bbox", None)
            if bbox is None:
                continue
            rects_by_floor[floor_index].append(
                (float(bbox.min_x), float(bbox.min_y), float(bbox.max_x), float(bbox.max_y))
            )

        floor_rows: list[dict[str, Any]] = []
        for floor_index, rects in sorted(rects_by_floor.items()):
            floor_rows.append(
                {
                    "floor_index": floor_index,
                    "area_m2": round(self._union_area(rects), 2),
                }
            )
        return floor_rows

    def _building_height_m(self, floors: list[Any]) -> float | None:
        if not floors:
            return None
        z_min = min(float(getattr(floor, "z_min", 0.0)) for floor in floors)
        z_max = max(float(getattr(floor, "z_max", 0.0)) for floor in floors)
        return max(0.0, z_max - z_min)

    def _bbox_area(self, space: Any) -> float:
        bbox = getattr(space, "bbox", None)
        if bbox is None:
            return 0.0
        width = max(0.0, float(getattr(bbox, "max_x", 0.0)) - float(getattr(bbox, "min_x", 0.0)))
        depth = max(0.0, float(getattr(bbox, "max_y", 0.0)) - float(getattr(bbox, "min_y", 0.0)))
        return width * depth

    def _union_area(self, rects: list[tuple[float, float, float, float]]) -> float:
        if not rects:
            return 0.0

        x_coords = sorted({x0 for x0, _, x1, _ in rects} | {x1 for _, _, x1, _ in rects})
        total = 0.0
        for index in range(len(x_coords) - 1):
            x_left = x_coords[index]
            x_right = x_coords[index + 1]
            if x_right <= x_left:
                continue

            y_intervals: list[tuple[float, float]] = []
            for rx0, ry0, rx1, ry1 in rects:
                if rx0 <= x_left and rx1 >= x_right:
                    y_intervals.append((ry0, ry1))
            if not y_intervals:
                continue

            y_intervals.sort()
            merged: list[tuple[float, float]] = []
            current_start, current_end = y_intervals[0]
            for start, end in y_intervals[1:]:
                if start <= current_end:
                    current_end = max(current_end, end)
                else:
                    merged.append((current_start, current_end))
                    current_start, current_end = start, end
            merged.append((current_start, current_end))

            height = sum(max(0.0, end - start) for start, end in merged)
            total += (x_right - x_left) * height
        return total


def _raumvorschlag(fehlende_flaeche_m2: float) -> str:
    """Suggest a room size (2:1 ratio) for a given missing area.

    Computes length and width so that length = 2 × width and
    length × width = fehlende_flaeche_m2.  Both values are rounded
    to one decimal place and formatted as a human-readable string.

    Args:
        fehlende_flaeche_m2: The missing Technikraum area in m².

    Returns:
        Formatted string, e.g. "6.3 m × 3.2 m".
    """
    if fehlende_flaeche_m2 <= 0:
        return "-"
    breite = math.sqrt(fehlende_flaeche_m2 / 2.0)
    laenge = breite * 2.0
    return f"{laenge:.1f} m × {breite:.1f} m"
