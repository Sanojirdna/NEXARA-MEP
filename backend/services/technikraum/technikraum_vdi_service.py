from __future__ import annotations

from typing import Any

from .chart_builder import TechnikraumChartBuilder
from .diagram_repository import DiagramRepository
from .scenario_builder import TechnikraumScenarioBuilder
from .technical_room_detector import TechnicalRoomDetector


class TechnikraumVDIService:
    """Public facade for VDI 2050 technical-room evaluation."""

    def __init__(self) -> None:
        self.diagram_repository = DiagramRepository()
        self.chart_builder = TechnikraumChartBuilder(
            diagram_repository=self.diagram_repository,
        )
        self.room_detector = TechnicalRoomDetector()
        self.scenario_builder = TechnikraumScenarioBuilder(
            diagram_repository=self.diagram_repository,
            chart_builder=self.chart_builder,
        )

    def build_payload(self, runtime: Any, study_state: dict[str, Any] | None = None) -> dict[str, Any]:
        bundle = getattr(runtime, "bundle", None)
        if bundle is None:
            return {
                "available": False,
                "message": "Load an IFC on the landing page first.",
            }

        rooms = list(bundle.get("rooms_by_guid", {}).values())
        shafts = list(bundle.get("shafts_by_guid", {}).values())
        corridors = list(bundle.get("corridors_by_guid", {}).values())
        # The IFC reader stores spaces that matched a technical-room keyword separately
        # so that they do not interfere with routing.  They must be included here so
        # the VDI service can find them again.
        ifc_classified_technical = list(bundle.get("technical_rooms", []))
        floors = list(bundle.get("floors", []))

        # BGF approximation uses all non-technical spaces (rooms + corridors + shafts)
        bgf_spaces = rooms + corridors + shafts
        floor_areas = self.scenario_builder.approx_floor_areas(bgf_spaces)
        approx_bgf_m2 = sum(item["area_m2"] for item in floor_areas)
        building_height_m = self.scenario_builder.building_height_m(floors)
        bgf_axis_value = approx_bgf_m2 / 1000.0 if approx_bgf_m2 > 0 else None

        # Pass every space type to the detector so no technical room is missed:
        # - rooms_by_guid / shafts_by_guid / corridors_by_guid may contain rooms
        #   whose name did not match the technical-room keyword list exactly.
        # - technical_rooms contains rooms the IFC reader already classified, but the
        #   VDI detector must still inspect them to assign a discipline (sanitary,
        #   heating, ventilation, …).
        all_spaces = rooms + shafts + corridors + ifc_classified_technical

        technical_room_keywords = self.room_detector.technical_room_keywords(runtime)
        technical_rooms = self.room_detector.find_technical_rooms(
            rooms=all_spaces,
            floors=floors,
            runtime=runtime,
            technical_room_keywords=technical_room_keywords,
        )
        actual_area_m2 = round(sum(item["area_m2"] for item in technical_rooms), 2)
        actual_share_pct = round(actual_area_m2 / approx_bgf_m2 * 100.0, 2) if approx_bgf_m2 > 0 else None

        # Use all spaces so room-name fallback detection covers the full building,
        # not just rooms that were not classified as shafts or corridors.
        use_family = self.scenario_builder.detect_use_family(
            runtime=runtime,
            rooms=all_spaces,
            study_state=study_state or {},
        )

        required_discipline_status = self.room_detector.build_required_discipline_status(technical_rooms)
        ventilation_detected = required_discipline_status["ventilation"]["found"]
        study_rlt_central_selected = self.scenario_builder.study_rlt_central_selected(study_state or {})
        cooling_detected = any(item["discipline_key"] == "cooling" for item in technical_rooms)
        sprinkler_detected = any(item["discipline_key"] == "sprinkler" for item in technical_rooms)

        scenario_rows = self.scenario_builder.build_scenarios(
            use_family_key=use_family["key"],
            approx_bgf_m2=approx_bgf_m2,
            building_height_m=building_height_m,
            study_rlt_central_selected=study_rlt_central_selected,
            cooling_detected=cooling_detected,
            sprinkler_detected=sprinkler_detected,
            actual_area_m2=actual_area_m2,
        )
        best_match = self.scenario_builder.pick_best_match(scenario_rows)

        notes = [
            "Only rooms whose names contain one of the configured Technikraum keywords are counted as technical rooms.",
            "The default keywords are Technikzentrale, Zentrale and Technik. They can now be changed in the planner config JSON.",
            "The discipline scan now checks the technical rooms mainly for Sanitär, Heizung and Lüftung. IT, GA and Lift are no longer treated as technical rooms.",
            "If Studie Kriterium 8.3 'RLT zentral' is selected, the Verwaltung diagrams V2 and V3 are used so the user can compare 6 and 9 m³/(h·m²).",
            "The building type for the VDI scenario is now taken from Studie -> Steigzonen -> Kriterium 2 Gebäudetyp whenever that selection exists.",
            "VDI 2050 Blatt 1 uses Bruttogrundfläche (BGF). Here it is approximated from IFC space bounding boxes per floor, so it is only a rough project check.",
        ]
        if use_family.get("is_analog"):
            notes.append("The selected Gebäudetyp has no direct diagram in the current digitized VDI set. The app therefore uses the Verwaltung family analogously.")
        if not use_family.get("from_study"):
            notes.append("No Gebäudetyp was selected in Studie criterion 2, so a fallback family detection was used.")

        return {
            "available": True,
            "message": None,
            "approx_bgf_m2": round(approx_bgf_m2, 2),
            "bgf_axis_value": round(bgf_axis_value, 3) if bgf_axis_value is not None else None,
            "building_height_m": round(building_height_m, 2) if building_height_m is not None else None,
            "actual_technical_room_area_m2": actual_area_m2,
            "actual_technical_room_share_pct": actual_share_pct,
            "technical_room_keywords_used": technical_room_keywords,
            "floor_areas": floor_areas,
            "use_family": use_family,
            "required_disciplines": required_discipline_status,
            "ventilation_detected": ventilation_detected,
            "study_rlt_central_selected": study_rlt_central_selected,
            "cooling_detected": cooling_detected,
            "sprinkler_detected": sprinkler_detected,
            "technical_room_count": len(technical_rooms),
            "technical_rooms": technical_rooms,
            "scenario_rows": scenario_rows,
            "best_match": best_match,
            "notes": notes,
        }

    def write_workbook_sheet(
        self,
        wb: Any,
        runtime: Any,
        study_state: dict[str, Any] | None = None,
    ) -> None:
        payload = self.build_payload(runtime, study_state=study_state)
        if "Technikraeume_VDI2050" in wb.sheetnames:
            wb.remove(wb["Technikraeume_VDI2050"])
        ws = wb.create_sheet("Technikraeume_VDI2050")

        if not payload.get("available"):
            ws["A1"] = "Status"
            ws["B1"] = payload.get("message", "No data.")
            return

        required = payload.get("required_disciplines", {})
        info_rows = [
            ("Approx. BGF [m2]", payload.get("approx_bgf_m2")),
            ("Building height [m]", payload.get("building_height_m")),
            ("Detected building family", (payload.get("use_family") or {}).get("label")),
            ("Detection source", (payload.get("use_family") or {}).get("source")),
            ("Study building type", (payload.get("use_family") or {}).get("study_label")),
            ("Technical room keywords", ", ".join(payload.get("technical_room_keywords_used", []))),
            ("Actual technical room area [m2]", payload.get("actual_technical_room_area_m2")),
            ("Actual technical room share [%]", payload.get("actual_technical_room_share_pct")),
            ("Sanitary detected", required.get("sanitary", {}).get("found")),
            ("Heating detected", required.get("heating", {}).get("found")),
            ("Ventilation detected", required.get("ventilation", {}).get("found")),
            ("Study RLT zentral selected", payload.get("study_rlt_central_selected")),
            ("Cooling add-on detected", payload.get("cooling_detected")),
            ("Sprinkler add-on detected", payload.get("sprinkler_detected")),
            ("Best VDI scenario", (payload.get("best_match") or {}).get("label")),
            ("Best scenario status", (payload.get("best_match") or {}).get("status_label")),
        ]
        for row_index, (label, value) in enumerate(info_rows, start=1):
            ws[f"A{row_index}"] = label
            ws[f"B{row_index}"] = value

        start_row = len(info_rows) + 3
        ws[f"A{start_row}"] = "Scenario"
        ws[f"B{start_row}"] = "Expected lower [m2]"
        ws[f"C{start_row}"] = "Expected upper [m2]"
        ws[f"D{start_row}"] = "Status"
        ws[f"E{start_row}"] = "Gap [m2]"
        ws[f"F{start_row}"] = "Notes"
        for offset, item in enumerate(payload.get("scenario_rows", []), start=1):
            row_index = start_row + offset
            ws[f"A{row_index}"] = item.get("label")
            ws[f"B{row_index}"] = item.get("expected_lower_m2")
            ws[f"C{row_index}"] = item.get("expected_upper_m2")
            ws[f"D{row_index}"] = item.get("status_label")
            ws[f"E{row_index}"] = item.get("gap_to_range_m2")
            ws[f"F{row_index}"] = "; ".join(item.get("notes", []))

        room_row = start_row + len(payload.get("scenario_rows", [])) + 3
        ws[f"A{room_row}"] = "Detected technical room"
        ws[f"B{room_row}"] = "Floor"
        ws[f"C{room_row}"] = "Approx. area [m2]"
        ws[f"D{room_row}"] = "Discipline"
        ws[f"E{room_row}"] = "Room keyword"
        ws[f"F{room_row}"] = "Discipline tokens"
        for offset, item in enumerate(payload.get("technical_rooms", []), start=1):
            row_index = room_row + offset
            ws[f"A{row_index}"] = item.get("label")
            ws[f"B{row_index}"] = item.get("floor_name")
            ws[f"C{row_index}"] = item.get("area_m2")
            ws[f"D{row_index}"] = item.get("discipline_label")
            ws[f"E{row_index}"] = ", ".join(item.get("room_keyword_matches", []))
            ws[f"F{row_index}"] = ", ".join(item.get("discipline_tokens", []))

TECHNIKRAUM_VDI = TechnikraumVDIService()
