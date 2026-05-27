from __future__ import annotations

from typing import Any

from openpyxl import load_workbook

from services.technikraum.technikraum_vdi_service import TECHNIKRAUM_VDI

from .assessment_service import StudyAssessmentService
from .state_store import StudyStateStore
from .study_utils import SHEET_NAME, StudyUtilityMixin
from .workbook_service import StudyWorkbookService


class StudieService:
    """Public facade for the Studie page and workbook export."""

    def __init__(self) -> None:
        self.state_store = StudyStateStore()
        self.workbook_service = StudyWorkbookService()
        self.assessment_service = StudyAssessmentService()
        self.utils = StudyUtilityMixin()

    def get_payload(self, runtime: Any) -> dict[str, Any]:
        state = self.state_store.load()
        workbook_path = self.workbook_service.ensure_export_workbook(state)
        wb = load_workbook(workbook_path)
        ws = wb[SHEET_NAME]

        selected_coords = set(state.get("selected_coords", []))
        weights = self.state_store.normalize_weights(state.get("weights", {}))

        table_rows = self.workbook_service.build_table(ws, selected_coords, weights)
        ifc_metrics = self.assessment_service.build_ifc_metrics(runtime)
        selection_summary = self.workbook_service.build_selection_summary(ws, selected_coords, weights)
        assessment = self.assessment_service.build_assessment(ifc_metrics, selection_summary)

        technikraum = TECHNIKRAUM_VDI.build_payload(runtime, study_state=state)

        return {
            "loaded": True,
            "table_rows": table_rows,
            "state": {
                "selected_coords": sorted(selected_coords),
                "weights": weights,
            },
            "selection_summary": selection_summary,
            "ifc_metrics": ifc_metrics,
            "assessment": assessment,
            "technikraum": technikraum,
            "project": {
                "ifc_name": getattr(runtime, "current_ifc_name", None),
                "demands_name": getattr(runtime, "current_excel_name", None),
                "config_name": getattr(runtime, "current_config_name", None),
                "config_source": getattr(runtime, "current_config_source", None),
                "has_bundle": getattr(runtime, "bundle", None) is not None,
            },
        }

    def save_state(self, payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
        selected_coords = set(str(item) for item in (payload.get("selected_coords") or []))
        weights = self.state_store.normalize_weights(payload.get("weights") or {})

        validation = self.assessment_service.validate_state(selected_coords, weights)
        if not validation["valid"]:
            return validation

        state = {
            "selected_coords": sorted(selected_coords),
            "weights": weights,
        }
        self.state_store.save(state)
        self.workbook_service.ensure_export_workbook(state)
        return {
            "saved": True,
            "payload": self.get_payload(runtime),
        }

    def autofill_from_ifc(self, runtime: Any) -> dict[str, Any]:
        state = self.state_store.load()
        selected_coords = set(state.get("selected_coords", []))
        weights = self.state_store.normalize_weights(state.get("weights", {}))

        metrics = self.assessment_service.build_ifc_metrics(runtime)
        suggested_coords = []

        criterion4_coord = metrics.get("criterion4_coord")
        if criterion4_coord:
            selected_coords = {
                coord for coord in selected_coords
                if self.utils._criterion_from_coord(coord) != 4
            }
            selected_coords.add(criterion4_coord)
            suggested_coords.append(criterion4_coord)
            row_coord = f"F{self.utils._row_from_coord(criterion4_coord)}"
            if row_coord not in weights:
                weights[row_coord] = 2

        building_type = metrics.get("building_type_suggestion") or {}
        building_type_coord = building_type.get("coord")
        if building_type_coord:
            selected_coords = {
                coord for coord in selected_coords
                if self.utils._criterion_from_coord(coord) != 2
            }
            selected_coords.add(building_type_coord)
            suggested_coords.append(building_type_coord)

        footprint = metrics.get("footprint_suggestion") or {}
        footprint_coord = footprint.get("coord")
        if footprint_coord:
            selected_coords = {
                coord for coord in selected_coords
                if self.utils._criterion_from_coord(coord) != 3
            }
            selected_coords.add(footprint_coord)
            suggested_coords.append(footprint_coord)

        validation = self.assessment_service.validate_state(selected_coords, weights)
        if not validation["valid"]:
            return validation

        new_state = {
            "selected_coords": sorted(selected_coords),
            "weights": weights,
        }
        self.state_store.save(new_state)
        self.workbook_service.ensure_export_workbook(new_state)

        payload = self.get_payload(runtime)
        payload["autofill_applied"] = suggested_coords

        if suggested_coords:
            payload["autofill_message"] = f"Autofill applied: {', '.join(suggested_coords)}"
        else:
            payload["autofill_message"] = "Autofill ran, but no matching suggestions were found in the IFC."

        return {
            "saved": True,
            "payload": payload,
        }

    def export_workbook(self, runtime: Any):
        state = self.state_store.load()
        return self.workbook_service.export_workbook(runtime, state)

    def get_state_snapshot(self) -> dict[str, Any]:
        return self.state_store.get_state_snapshot()

    def import_state_snapshot(self, state: dict[str, Any]) -> None:
        self.state_store.import_state_snapshot(state)
        self.workbook_service.ensure_export_workbook(self.state_store.load())

    def reset(self) -> None:
        self.state_store.reset()


STUDIE = StudieService()
