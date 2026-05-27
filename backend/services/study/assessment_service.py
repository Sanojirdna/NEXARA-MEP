from __future__ import annotations

from collections import defaultdict
from typing import Any

from .study_utils import SELECTABLE_COLUMNS, StudyUtilityMixin


class StudyAssessmentService(StudyUtilityMixin):
    """Calculate IFC-derived Studie metrics and validate selections."""

    def build_ifc_metrics(self, runtime: Any) -> dict[str, Any]:
        """Return IFC metrics used by the Studie page."""
        return self._build_ifc_metrics(runtime)

    def build_assessment(
        self,
        ifc_metrics: dict[str, Any],
        selection_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the Studie assessment payload."""
        return self._build_assessment(ifc_metrics, selection_summary)

    def validate_state(self, selected_coords: set[str], weights: dict[str, int]) -> dict[str, Any]:
        """Validate selected Studie cells and weights."""
        return self._validate_state(selected_coords, weights)

    def _build_assessment(self, ifc_metrics: dict[str, Any], selection_summary: dict[str, Any]) -> dict[str, Any]:
        actual_share_pct = ifc_metrics.get("shaft_share_pct")
        score_band = selection_summary.get("score_band")

        band_match = None
        band_message = "Noch keine gewichtete Bewertung verfügbar."
        if actual_share_pct is not None and score_band:
            band_match = self._share_matches_band(actual_share_pct, score_band)
            if band_match:
                band_message = "Der Schachtflächenanteil liegt im geschätzten Bereich der gewichteten Studie."
            else:
                band_message = "Der Schachtflächenanteil liegt ausserhalb des geschätzten Bereichs der gewichteten Studie."

        return {
            "actual_share_pct": actual_share_pct,
            "score_band": score_band,
            "score_band_label": selection_summary.get("score_band_label"),
            "required_share_label": selection_summary.get("required_share_label"),
            "band_match": band_match,
            "band_message": band_message,
        }

    def _build_ifc_metrics(self, runtime: Any) -> dict[str, Any]:
        bundle = getattr(runtime, "bundle", None)
        if bundle is None:
            return {
                "available": False,
                "message": "Bitte zuerst IFC und Bedarfe auf der Startseite laden.",
            }

        rooms = list(bundle.get("rooms_by_guid", {}).values())
        shafts = list(bundle.get("shafts_by_guid", {}).values())
        corridors = list(bundle.get("corridors_by_guid", {}).values())
        floors = bundle.get("floors", [])
        if not floors:
            return {
                "available": False,
                "message": "Keine Geschossbänder aus dem IFC extrahiert.",
            }

        all_spaces = rooms + corridors + shafts
        reference_floor = self._pick_ground_floor(floors)
        if reference_floor is None:
            reference_floor = sorted(
                floors,
                key=lambda item: (getattr(item, "floor_index", 0), getattr(item, "z_min", 0.0)),
            )[0]

        floor_breakdown: list[dict[str, Any]] = []
        total_floor_area = 0.0
        total_shaft_area = 0.0

        for floor in sorted(
            floors,
            key=lambda item: (getattr(item, "floor_index", 0), getattr(item, "z_min", 0.0)),
        ):
            floor_index = getattr(floor, "floor_index", None)
            floor_spaces = [
                space
                for space in all_spaces
                if getattr(space, "floor_index", None) == floor_index
            ]
            floor_shafts = [
                shaft
                for shaft in shafts
                if getattr(shaft, "floor_index", None) == floor_index
            ]

            floor_rects = [
                (space.bbox.min_x, space.bbox.min_y, space.bbox.max_x, space.bbox.max_y)
                for space in floor_spaces
            ]
            shaft_rects = [
                (space.bbox.min_x, space.bbox.min_y, space.bbox.max_x, space.bbox.max_y)
                for space in floor_shafts
            ]

            floor_area = self._union_area(floor_rects) if floor_rects else 0.0
            shaft_area = self._union_area(shaft_rects) if shaft_rects else 0.0

            total_floor_area += floor_area
            total_shaft_area += shaft_area

            floor_breakdown.append(
                {
                    "index": floor_index,
                    "name": getattr(floor, "name", ""),
                    "z_min": getattr(floor, "z_min", None),
                    "z_max": getattr(floor, "z_max", None),
                    "floor_area_m2": round(floor_area, 2),
                    "shaft_area_m2": round(shaft_area, 2),
                    "shaft_count": len(floor_shafts),
                }
            )

        shaft_share_pct = None
        shafts_per_1000 = None
        if total_floor_area > 0:
            shaft_share_pct = total_shaft_area / total_floor_area * 100.0
            shafts_per_1000 = len(shafts) / total_floor_area * 1000.0

        criterion4 = self._criterion4_from_density(shafts_per_1000)
        building_type_suggestion = self._suggest_building_type(runtime.current_ifc_path)
        reference_spaces = [
            space
            for space in all_spaces
            if getattr(space, "floor_index", None) == getattr(reference_floor, "floor_index", None)
        ]
        footprint_suggestion = self._suggest_footprint(reference_spaces)

        return {
            "available": True,
            "message": None,
            "reference_floor": {
                "index": getattr(reference_floor, "floor_index", None),
                "name": getattr(reference_floor, "name", ""),
                "z_min": getattr(reference_floor, "z_min", None),
                "z_max": getattr(reference_floor, "z_max", None),
            },
            "floor_count": len(floor_breakdown),
            "floor_breakdown": floor_breakdown,
            "total_floor_area_m2": round(total_floor_area, 2),
            "shaft_area_m2": round(total_shaft_area, 2),
            "shaft_share_pct": round(shaft_share_pct, 2) if shaft_share_pct is not None else None,
            "shaft_count": len(shafts),
            "shafts_per_1000_m2": round(shafts_per_1000, 2) if shafts_per_1000 is not None else None,
            "criterion4_coord": criterion4.get("coord") if criterion4 else None,
            "criterion4_label": criterion4.get("label") if criterion4 else None,
            "building_type_suggestion": building_type_suggestion,
            "footprint_suggestion": footprint_suggestion,
            "notes": [
                "Die Gesamt-BGF wird als Summe aller Geschoss-Vereinigungsflächen aus IFC-Raum-Bounding-Boxes approximiert, nicht aus exakten DIN-277-Polygonen.",
                "Die Gesamtschachtfläche wird als Summe aller Schacht-Vereinigungsflächen über alle Geschosse approximiert.",
                "Criterion 4.2 is derived from total shaft count per 1000 m² across the full building. The footprint suggestion still uses the detected reference floor.",
            ],
        }

    def _pick_ground_floor(self, floors: list[Any]) -> Any | None:
        preferred_name_tokens = ("eg", "erdgeschoss", "ground", "gf")
        for floor in floors:
            name = str(getattr(floor, "name", "") or "").strip().lower()
            if any(token in name for token in preferred_name_tokens):
                return floor

        for floor in floors:
            if getattr(floor, "floor_index", None) == 0:
                return floor

        non_negative = [floor for floor in floors if getattr(floor, "floor_index", -9999) >= 0]
        if non_negative:
            return sorted(non_negative, key=lambda item: (item.floor_index, item.z_min))[0]

        return sorted(floors, key=lambda item: abs(getattr(item, "z_min", 0.0)))[0] if floors else None

    def _criterion4_from_density(self, shafts_per_1000: float | None) -> dict[str, str] | None:
        if shafts_per_1000 is None:
            return None
        if shafts_per_1000 <= 3.0:
            return {"coord": "C33", "label": "4.2 geringe Anzahl Schächte (≤ 3 / 1000 m²)"}
        if shafts_per_1000 < 6.0:
            return {"coord": "D33", "label": "4.2 mittlere Anzahl Schächte (4 bis 5 / 1000 m²)"}
        return {"coord": "E33", "label": "4.2 hohe Anzahl Schächte (≥ 6 / 1000 m²)"}

    def _suggest_building_type(self, ifc_path: str | None) -> dict[str, Any] | None:
        if not ifc_path:
            return None

        text_parts: list[str] = []
        try:
            import ifcopenshell  # type: ignore
        except Exception:
            return None

        try:
            model = ifcopenshell.open(ifc_path)
            for entity_type in ("IfcProject", "IfcSite", "IfcBuilding"):
                for entity in model.by_type(entity_type):
                    for attr in ("Name", "LongName", "Description", "ObjectType"):
                        value = getattr(entity, attr, None)
                        if value:
                            text_parts.append(str(value))
            for storey in model.by_type("IfcBuildingStorey")[:10]:
                for attr in ("Name", "LongName"):
                    value = getattr(storey, attr, None)
                    if value:
                        text_parts.append(str(value))
        except Exception:
            return None

        text = " ".join(text_parts).lower()
        candidates = [
            (("wohn", "residential", "apartment"), "C13", "2.1 Wohnhaus"),
            (("verkauf", "retail", "mall"), "C14", "2.2 Verkaufsstätte"),
            (("discount", "discounter"), "C15", "2.3 Discounter"),
            (("office", "büro", "buero", "verwaltung", "admin"), "D16", "2.4 Büro und Verwaltung"),
            (("assembly", "versammlung", "event", "hall"), "D17", "2.5 Versammlungsstätte"),
            (("kino", "cinema"), "D18", "2.6 Kino"),
            (("hotel", "beherberg"), "D19", "2.7 Beherbergungsstätte"),
            (("hospital", "krankenhaus", "clinic"), "D20", "2.8 Krankenhaus"),
            (("pflege", "care home", "nursing"), "D21", "2.9 Pflegeheim"),
            (("schule", "school", "campus"), "D22", "2.10 Schule"),
            (("hochhaus", "tower", "high-rise", "high rise"), "D23", "2.11 Hochhaus"),
            (("industrie", "industrial", "factory", "production"), "D24", "2.12 Industrie"),
        ]

        for tokens, coord, label in candidates:
            if any(token in text for token in tokens):
                return {
                    "coord": coord,
                    "label": label,
                    "reason": "Matched IFC project or building metadata.",
                }
        return None

    def _suggest_footprint(self, eg_spaces: list[Any]) -> dict[str, Any] | None:
        if not eg_spaces:
            return None

        min_x = min(space.bbox.min_x for space in eg_spaces)
        min_y = min(space.bbox.min_y for space in eg_spaces)
        max_x = max(space.bbox.max_x for space in eg_spaces)
        max_y = max(space.bbox.max_y for space in eg_spaces)
        width = max_x - min_x
        depth = max_y - min_y
        if width <= 0 or depth <= 0:
            return None

        ratio = max(width, depth) / max(0.001, min(width, depth))
        if ratio <= 1.25:
            return {
                "coord": "C26",
                "label": "3.1 quadratisch/rund",
                "reason": "The EG outer footprint is close to a square bounding box.",
            }
        if ratio <= 2.5:
            return {
                "coord": "C27",
                "label": "3.2 rechteckig",
                "reason": "The EG outer footprint has a clear long side and short side.",
            }
        return {
            "coord": "E30",
            "label": "3.5 Freiform",
            "reason": "The EG outer footprint aspect ratio is strongly elongated.",
        }

    def _share_matches_band(self, share_pct: float, score_band: str) -> bool:
        if score_band == "low":
            return share_pct <= 1.0
        if score_band == "medium":
            return 1.0 < share_pct <= 2.0
        return share_pct > 2.0

    def _score_band(self, total_score: int) -> str | None:
        if total_score <= 0:
            return None
        if total_score <= 11:
            return "low"
        if total_score <= 22:
            return "medium"
        return "high"

    def _score_band_label(self, score_band: str | None) -> str | None:
        mapping = {
            "low": "geringer Platzbedarf",
            "medium": "mittlerer Platzbedarf",
            "high": "hoher Platzbedarf",
        }
        return mapping.get(score_band)

    def _required_share_label(self, score_band: str | None) -> str | None:
        mapping = {
            "low": "bis maximal 1 % BGF",
            "medium": "über 1 % bis maximal 2 % BGF",
            "high": "über 2 % BGF",
        }
        return mapping.get(score_band)

    def _validate_state(self, selected_coords: set[str], weights: dict[str, int]) -> dict[str, Any]:
        coords_by_row: dict[int, list[str]] = defaultdict(list)
        coords_by_criterion: dict[int, list[str]] = defaultdict(list)

        for coord in selected_coords:
            row_idx = self._row_from_coord(coord)
            col_idx = self._col_from_coord(coord)
            if col_idx not in SELECTABLE_COLUMNS:
                return {"saved": False, "valid": False, "message": f"{coord} is not a selectable C/D/E cell."}
            criterion = self._criterion_from_coord(coord)
            if criterion is None:
                return {"saved": False, "valid": False, "message": f"{coord} does not belong to a valid criterion row."}
            coords_by_row[row_idx].append(coord)
            coords_by_criterion[criterion].append(coord)

        for row_idx, coords in coords_by_row.items():
            if len(coords) > 1:
                return {
                    "saved": False,
                    "valid": False,
                    "message": f"Only one option can be selected in row {row_idx}.",
                }

        for criterion, coords in coords_by_criterion.items():
            limit = 1 if criterion <= 5 else 3
            if len(coords) > limit:
                return {
                    "saved": False,
                    "valid": False,
                    "message": f"Criterion {criterion} allows at most {limit} selected option(s).",
                }

        used_weights_by_criterion: dict[int, list[int]] = defaultdict(list)
        for coord, value in weights.items():
            if not isinstance(value, int) or value not in (1, 2, 3):
                return {
                    "saved": False,
                    "valid": False,
                    "message": f"{coord} must be weighted with 1, 2, or 3.",
                }
            row_idx = self._row_from_coord(coord)
            row_selection_exists = any(self._row_from_coord(selected) == row_idx for selected in selected_coords)
            if not row_selection_exists:
                return {
                    "saved": False,
                    "valid": False,
                    "message": f"Weight {coord} can only be set for a selected row.",
                }
            criterion = self._criterion_from_row(row_idx)
            if criterion is None:
                continue
            used_weights_by_criterion[criterion].append(value)

        for criterion, values in used_weights_by_criterion.items():
            if criterion >= 6 and len(values) != len(set(values)):
                return {
                    "saved": False,
                    "valid": False,
                    "message": f"Within criterion {criterion}, the weights 1, 2, and 3 may only be used once each.",
                }

        return {"saved": False, "valid": True, "message": None}
