from __future__ import annotations

import json
import shutil
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from pipe_planner.config import ProjectConfig, build_default_config
from pipe_planner.cost_fields import build_cost_fields
from pipe_planner.demand_loader import load_demands, write_demands_json
from pipe_planner.ifc_reader import load_ifc_model_data
from pipe_planner.models import DemandRecord, SpaceRecord, SystemBuildResult
from pipe_planner.routing import evaluate_route_matrix
from pipe_planner.timing import TimingRecorder
from pipe_planner.voxel_grid import build_voxel_grid
from project_io import (
    build_system_from_saved_variants,
    _visible_system_demands,
    export_project_bundle,
    import_project_bundle,
    load_config_json,
    save_config_json,
)

from pipe_planner.routing_helpers.route_result_serializer import (
    float_or_empty,
    int_or_empty,
    space_to_frontend,
)
from pipe_planner.routing_helpers.shaft_demand_aggregator import (
    compute_shaft_aggregated_demands,
)
from pipe_planner.routing_helpers.route_task_builder import (
    build_unique_route_tasks,
    expand_unique_results,
)
from services.design_explorer_service import DesignExplorerService


class PlannerRuntime:
    """
    Keep the current uploaded model, route matrix, selections, and config in memory.

    Args:
        None.

    Returns:
        PlannerRuntime object.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.bundle: dict[str, Any] | None = None
        self.current_ifc_path: str | None = None
        self.current_excel_path: str | None = None
        self.current_system: SystemBuildResult | None = None
        self.current_ifc_name: str | None = None
        self.current_excel_name: str | None = None
        self.current_config: ProjectConfig = build_default_config()
        self.current_config_name: str = "default.json"
        self.current_config_source: str = "default"
        self.design_explorer = DesignExplorerService()

    def reset_session(self) -> dict[str, Any]:
        """
        Clear the current in-memory session and generated helper files.

        Args:
            None.

        Returns:
            Simple reset result dictionary.
        """
        with self._lock:
            uploads_dir = Path(__file__).resolve().parents[1] / "uploads" / "outputs"
            if uploads_dir.exists():
                shutil.rmtree(uploads_dir, ignore_errors=True)

            self.bundle = None
            self.current_ifc_path = None
            self.current_excel_path = None
            self.current_system = None
            self.current_ifc_name = None
            self.current_excel_name = None
            self.current_config = build_default_config()
            self.current_config_name = "default.json"
            self.current_config_source = "default"

        return {
            "reset": True,
            "message": "Session cleared.",
        }

    def load_config_json(self, config_path: str) -> dict[str, Any]:
        """
        Load one uploaded config JSON file and make it the active config.

        Args:
            config_path: Path to the config file.

        Returns:
            Frontend-friendly config summary.
        """
        with self._lock:
            config, payload = load_config_json(config_path)
            self.current_config = config
            self.current_config_name = Path(config_path).name
            self.current_config_source = "uploaded_json"

            return {
                "loaded": True,
                "config_name": self.current_config_name,
                "config_source": self.current_config_source,
                "config": payload,
                "strategy_count": len(config.strategies),
                "voxel_size": config.voxel_size,
                "candidate_shaft_limit": config.candidate_shaft_limit,
            }

    def export_config_json(self, output_path: str | None = None) -> Path:
        """
        Export the current active config to JSON.

        Args:
            output_path: Optional target path.

        Returns:
            Saved file path.
        """
        with self._lock:
            upload_dir = Path(__file__).resolve().parents[1] / "uploads" / "outputs"
            upload_dir.mkdir(parents=True, exist_ok=True)
            target = Path(output_path) if output_path else upload_dir / "planner_config.json"
            return save_config_json(
                config=self.current_config,
                output_path=target,
                name=self.current_config_name.replace(".json", ""),
            )

    def export_project_bundle(self, output_path: str | None = None, study_state: dict[str, Any] | None = None) -> Path:
        """
        Export the full calculated project bundle to JSON.

        Args:
            output_path: Optional target path.
            study_state: Optional Studie state.

        Returns:
            Saved file path.
        """
        with self._lock:
            upload_dir = Path(__file__).resolve().parents[1] / "uploads" / "outputs"
            upload_dir.mkdir(parents=True, exist_ok=True)
            target = Path(output_path) if output_path else upload_dir / "project_bundle.json"
            return export_project_bundle(self, target, study_state=study_state)

    def import_project_bundle(
        self,
        bundle_path: str,
        ifc_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Import a previously exported project bundle JSON.

        Args:
            bundle_path: Path to the bundle file.
            ifc_path: Optional IFC path uploaded only for bundle restore.

        Returns:
            Summary dictionary for the frontend.
        """
        with self._lock:
            return import_project_bundle(self, bundle_path, ifc_path=ifc_path)

    def build_from_files(
        self,
        ifc_path: str,
        excel_path: str,
        uploads_dir: str,
        workers: int,
        config: ProjectConfig | None = None,
        config_name: str | None = None,
        config_source: str | None = None,
    ) -> dict[str, Any]:
        """
        Build a fresh in-memory routing bundle from IFC and Excel files.

        Args:
            ifc_path: Path to the IFC file.
            excel_path: Path to the Excel room book.
            uploads_dir: Directory for helper JSON and CSV exports.
            workers: Number of worker processes.
            config: Optional config object. Uses the active config if None.
            config_name: Optional display name for the config.
            config_source: Optional source label for the config.

        Returns:
            Summary dictionary for the frontend.
        """
        with self._lock:
            uploads_path = Path(uploads_dir)
            uploads_path.mkdir(parents=True, exist_ok=True)

            active_config = config or self.current_config or build_default_config()
            active_config.default_workers = workers
            timer = TimingRecorder()

            with timer.stage("IFC parse"):
                ifc_data = load_ifc_model_data(ifc_path, active_config)

            rooms = ifc_data["rooms"]
            shafts = ifc_data["shafts"]
            corridors = ifc_data["corridors"]
            technical_rooms = ifc_data.get("technical_rooms", [])
            spaces_by_guid = ifc_data["spaces_by_guid"]
            spaces_by_name = ifc_data["spaces_by_name"]

            with timer.stage("Excel demands"):
                demands = load_demands(excel_path, spaces_by_guid, spaces_by_name)
                write_demands_json(demands, uploads_path / "demands.json")

            with timer.stage("Voxel grid"):
                grid = build_voxel_grid(
                    spaces=ifc_data["spaces"],
                    obstacles=ifc_data["obstacles"],
                    floors=ifc_data["floors"],
                    config=active_config,
                )

            with timer.stage("Cost fields"):
                build_cost_fields(grid, active_config)

            rooms_by_guid = {room.guid: room for room in rooms}
            shafts_by_guid = {shaft.guid: shaft for shaft in shafts}
            corridors_by_guid = {corridor.guid: corridor for corridor in corridors}

            with timer.stage("Task build"):
                unique_tasks, geometry_to_demands, shaft_synthetic_demands = build_unique_route_tasks(
                    demands=demands,
                    rooms_by_guid=rooms_by_guid,
                    shafts=shafts,
                    strategy_names=list(active_config.strategies.keys()),
                    shaft_allow_map=active_config.shaft_allow_map,
                    shaft_limit=active_config.candidate_shaft_limit,
                    grid=grid,
                    technical_rooms=technical_rooms,
                )

            timer.log(f"Demand rows: {len(demands)}")
            timer.log(f"Technical rooms found: {len(technical_rooms)} {[tr.label() for tr in technical_rooms]}")
            timer.log(f"Unique geometry tasks: {len(unique_tasks)}")
            timer.log(f"Shaft feed demands: {len(shaft_synthetic_demands)}")
            all_demands = list(demands) + shaft_synthetic_demands
            timer.log(f"Nearest shafts per room: {active_config.candidate_shaft_limit}")
            timer.log(f"Requested workers: {workers}")

            with timer.stage("Candidate routing matrix"):
                unique_results = evaluate_route_matrix(
                    tasks=unique_tasks,
                    grid=grid,
                    config=active_config,
                    workers=workers,
                )

            with timer.stage("Matrix expand"):
                matrix_results = expand_unique_results(unique_results, geometry_to_demands)

            route_rows: list[dict[str, Any]] = []
            for result in matrix_results:
                row = result.to_dict()
                metrics = row.pop("metrics", {})
                for key, value in metrics.items():
                    row[key] = value
                row["metrics"] = metrics
                route_rows.append(row)

            matrix_df = pd.DataFrame(route_rows)
            if not matrix_df.empty:
                matrix_df.to_csv(uploads_path / "route_matrix.csv", index=False)
                (uploads_path / "route_matrix.json").write_text(
                    json.dumps(route_rows, indent=2),
                    encoding="utf-8",
                )

            selections = self._build_default_selections(matrix_df)

            # Compute per-service aggregated demands for shaft→technikraum
            # sizing. These are kept separate from bundle["demands"] so they
            # do not appear as extra entries in the variant panel.
            shaft_per_service, shaft_per_service_sel = compute_shaft_aggregated_demands(
                demands=list(demands) + shaft_synthetic_demands,
                selections=selections,
                rooms_by_guid=rooms_by_guid,
                shafts_by_guid=shafts_by_guid,
                technical_rooms=technical_rooms,
                shaft_placeholder_demands=shaft_synthetic_demands,
            )
            selections.update(shaft_per_service_sel)
            timer.log(f"Shaft per-service sizing demands: {len(shaft_per_service)}")

            with timer.stage("Default system build from saved variants"):
                default_system = build_system_from_saved_variants(
                    demands=_visible_system_demands(all_demands, shaft_per_service),
                    route_rows=route_rows,
                    selections=selections,
                    shafts_by_guid=shafts_by_guid,
                    voxel_size=active_config.voxel_size,
                )

            (uploads_path / "system_defaults.json").write_text(
                default_system.to_json(),
                encoding="utf-8",
            )
            timer.write_json(uploads_path / "timings.json")

            self.bundle = {
                "config": active_config,
                "grid": grid,
                "rooms_by_guid": rooms_by_guid,
                "shafts_by_guid": shafts_by_guid,
                "corridors_by_guid": corridors_by_guid,
                "technical_rooms": technical_rooms,
                "floors": ifc_data["floors"],
                "demands": all_demands,
                "shaft_per_service_demands": shaft_per_service,
                "route_matrix_rows": route_rows,
                "route_matrix_df": matrix_df,
                "timings": timer.to_dict(),
                "selections": selections,
                "loaded_from_bundle": False,
            }
            self.current_ifc_path = ifc_path
            self.current_excel_path = excel_path
            self.current_ifc_name = Path(ifc_path).name
            self.current_excel_name = Path(excel_path).name
            self.current_system = default_system
            self.current_config = active_config
            self.current_config_name = config_name or self.current_config_name or "default.json"
            self.current_config_source = config_source or self.current_config_source or "default"

            # ── Auto-generate pipeline visualisation figures ──────────────
            # Runs after every successful build_from_files() call.
            # Figures are saved as interactive HTML files in the uploads dir.
            try:
                from pipe_planner.pipeline_visualizer import generate_pipeline_figures

                fig_dir = uploads_path / "pipeline_figures"
                timer.log("Pipeline visualizer: starting …")
                generate_pipeline_figures(self, output_dir=fig_dir)
                timer.log(f"Pipeline visualizer: figures saved to {fig_dir}")
            except Exception as _viz_exc:
                import traceback as _tb
                print(
                    f"[pipeline_visualizer] WARNING: figure generation failed: {_viz_exc}",
                    flush=True,
                )
                _tb.print_exc()

            return self.get_summary()

    def get_summary(self) -> dict[str, Any]:
        """
        Return a frontend-friendly summary of the current state.

        Args:
            None.

        Returns:
            Summary dictionary.
        """
        if self.bundle is None:
            return {
                "loaded": False,
                "message": "No model has been built yet.",
                "config_name": self.current_config_name,
                "config_source": self.current_config_source,
            }

        rooms = [space_to_frontend(room) for room in self.bundle["rooms_by_guid"].values()]
        rooms.sort(key=lambda item: (item["floor_index"], item["label"]))

        shafts = [space_to_frontend(shaft) for shaft in self.bundle["shafts_by_guid"].values()]
        shafts.sort(key=lambda item: (item["floor_index"], item["label"]))

        floors = []
        for floor in self.bundle["floors"]:
            floors.append(
                {
                    "index": floor.floor_index,
                    "name": floor.name,
                    "z_min": floor.z_min,
                    "z_max": floor.z_max,
                }
            )

        demand_rows = [demand.to_dict() for demand in self.bundle["demands"]]
        strategies = [asdict(strategy) for strategy in self.bundle["config"].strategies.values()]

        return {
            "loaded": True,
            "ifc_url": "/api/files/current-ifc" if self.current_ifc_path else None,
            "has_ifc_file": self.current_ifc_path is not None,
            "excel_name": self.current_excel_name,
            "ifc_name": self.current_ifc_name,
            "workers": self.bundle["config"].default_workers,
            "config_name": self.current_config_name,
            "config_source": self.current_config_source,
            "config": {
                "voxel_size": self.bundle["config"].voxel_size,
                "candidate_shaft_limit": self.bundle["config"].candidate_shaft_limit,
                "strategy_count": len(self.bundle["config"].strategies),
            },
            "rooms": rooms,
            "shafts": shafts,
            "floors": floors,
            "demands": demand_rows,
            "strategies": strategies,
            "selections": self.bundle["selections"],
            "system": self.current_system.to_dict() if self.current_system else None,
            "timings": self.bundle["timings"],
            "loaded_from_bundle": bool(self.bundle.get("loaded_from_bundle")),
        }

    def get_room_detail(self, room_guid: str) -> dict[str, Any]:
        """
        Return one room and its room-service demands.

        Args:
            room_guid: Room GUID.

        Returns:
            Room detail dictionary.
        """
        if self.bundle is None:
            return {"found": False, "message": "No active bundle."}

        room = self.bundle["rooms_by_guid"].get(room_guid)
        if room is None:
            # Fall back to shafts — shaft GUIDs are valid sources for
            # shaft→technikraum demands on the Technikraum floor.
            room = self.bundle["shafts_by_guid"].get(room_guid)
        if room is None:
            return {"found": False, "message": "Room not found."}

        demand_rows = []
        for demand in self.bundle["demands"]:
            if demand.room_guid == room_guid:
                demand_rows.append(demand.to_dict())

        return {
            "found": True,
            "room": space_to_frontend(room),
            "demands": demand_rows,
        }

    def get_variants_for_room_service(self, room_guid: str, service: str) -> dict[str, Any]:
        """
        Return candidate variants for one room and one service.

        Args:
            room_guid: Room GUID.
            service: Service key.

        Returns:
            Variant dictionary with rows and selected row.
        """
        if self.bundle is None:
            return {"found": False, "message": "No active bundle."}

        matrix_df: pd.DataFrame = self.bundle["route_matrix_df"]
        if matrix_df.empty:
            return {"found": True, "rows": [], "selected": None}

        filtered = matrix_df.loc[
            (matrix_df["room_guid"] == room_guid)
            & (matrix_df["service"] == service)
        ].copy()

        if filtered.empty:
            return {"found": True, "rows": [], "selected": None}

        filtered = filtered.sort_values(by=["success", "score"], ascending=[False, True])
        rows = filtered.to_dict(orient="records")

        selected = None
        current_system = self.current_system
        if current_system is not None:
            demand_id = None
            for demand in self.bundle["demands"]:
                if demand.room_guid == room_guid and demand.service == service:
                    demand_id = demand.demand_id
                    break

            if demand_id:
                selection = current_system.selections.get(demand_id)
                if selection:
                    for row in rows:
                        if (
                            row["shaft_guid"] == selection.get("shaft_guid")
                            and row["strategy"] == selection.get("strategy")
                        ):
                            selected = row
                            break

        return {
            "found": True,
            "rows": rows,
            "selected": selected,
        }


    def get_system_strategy_overview(self) -> dict[str, Any]:
        """Aggregate system metrics per strategy from saved route variants only.

        For each strategy, the same saved-row reconstruction path is used as
        for ``/selection/strategy-all``.  This means the overview includes the
        export-relevant per-service shaft→Technikraum routes instead of only
        the synthetic SHAFT_FEED placeholder geometry.

        Returns:
            Dict with ``found`` flag and ``rows`` list (one row per strategy).
        """
        if self.bundle is None:
            return {"found": False, "message": "No active bundle."}

        matrix_df: pd.DataFrame = self.bundle["route_matrix_df"]
        if matrix_df.empty:
            return {"found": True, "rows": []}

        success_mask = matrix_df["success"].astype(str).str.lower().isin(["true", "1", "yes"])
        rows: list[dict[str, Any]] = []

        for strategy_name in self.bundle["config"].strategies.keys():
            selections: dict[str, dict[str, str]] = {}

            for demand in self.bundle["demands"]:
                filtered = matrix_df.loc[
                    (matrix_df["demand_id"] == demand.demand_id)
                    & (matrix_df["strategy"] == strategy_name)
                    & success_mask
                ].copy()
                if filtered.empty:
                    continue

                filtered = filtered.sort_values(by=["score"])
                best = filtered.iloc[0]
                selections[demand.demand_id] = {
                    "shaft_guid": str(best["shaft_guid"]),
                    "strategy": str(best["strategy"]),
                }

            system = self._preview_system_from_saved_variants(selections)
            metrics = system.system_metrics
            route_count = int(metrics.get("route_count", len(system.routes)) or 0)
            coverage = (system.success_count / route_count * 100) if route_count else 0.0

            rows.append({
                "strategy": strategy_name,
                "shaft_guid": "__system__",
                "shaft_name": "System",
                "success": system.failed_count == 0,
                "demand_count": route_count,
                "success_count": system.success_count,
                "failed_count": system.failed_count,
                "demand_coverage_pct": round(coverage, 1),
                "avg_score": round(float(metrics.get("mean_route_score", 0.0)), 3),
                "total_length_m": round(float(metrics.get("total_length_m", 0.0)), 1),
                "total_horizontal_m": round(float(metrics.get("total_horizontal_m", 0.0)), 1),
                "total_vertical_m": round(float(metrics.get("total_vertical_m", 0.0)), 1),
                "total_bends": int(metrics.get("total_bends", 0) or 0),
                "total_wall_cross": int(metrics.get("total_wall_crossings", 0) or 0),
                "total_slab_cross": int(metrics.get("total_slab_crossings", 0) or 0),
                "total_shared_m": round(float(metrics.get("shared_length_m", 0.0)), 1),
            })

        rows.sort(key=lambda r: r.get("avg_score", 0))
        return {"found": True, "rows": rows}

    def get_all_variants(self) -> dict[str, Any]:
        """Return all route variants across all rooms and services.

        Heavy geometry columns (path_indices, path_xyz) are excluded so the
        payload stays small enough to send to the browser.

        Returns:
            Dict with ``found`` flag and ``rows`` list.
        """
        if self.bundle is None:
            return {"found": False, "message": "No active bundle."}

        matrix_df: pd.DataFrame = self.bundle["route_matrix_df"]
        if matrix_df.empty:
            return {"found": True, "rows": []}

        drop_cols = [c for c in ["path_indices", "path_xyz"] if c in matrix_df.columns]
        slim = matrix_df.drop(columns=drop_cols).copy()
        slim = slim.sort_values(by=["success", "score"], ascending=[False, True])

        # Mark selections from current system
        current_system = self.current_system
        selections = current_system.selections if current_system else {}
        rows = slim.to_dict(orient="records")
        for row in rows:
            sel = selections.get(row.get("demand_id", ""))
            row["is_selected"] = bool(
                sel
                and sel.get("shaft_guid") == row.get("shaft_guid")
                and sel.get("strategy") == row.get("strategy")
            )

        return {"found": True, "rows": rows}

    def update_selection(
        self,
        demand_id: str,
        shaft_guid: str,
        strategy: str,
    ) -> dict[str, Any]:
        """
        Update one demand selection and rebuild the merged system from saved rows.

        Args:
            demand_id: Demand id.
            shaft_guid: Target shaft GUID.
            strategy: Strategy name.

        Returns:
            Updated frontend payload.
        """
        with self._lock:
            if self.bundle is None:
                return {"updated": False, "message": "No active bundle."}

            selections = dict(self.bundle["selections"])
            selections[demand_id] = {
                "shaft_guid": shaft_guid,
                "strategy": strategy,
            }

            current_system = self._rebuild_system_from_saved_variants(selections)

            selected_route = None
            for route in current_system.routes:
                if route.demand_id == demand_id:
                    selected_route = route.to_dict()
                    break

            return {
                "updated": True,
                "selection": self.bundle["selections"].get(demand_id, selections[demand_id]),
                "route": selected_route,
                "system": current_system.to_dict(),
            }

    def apply_strategy_to_system(
        self,
        strategy: str,
        service: str | None = None,
    ) -> dict[str, Any]:
        """
        Apply one strategy to all matching demands using saved route variants only.

        Args:
            strategy: Strategy name to apply.
            service: Optional service filter like HEI, LUE, or SAN.

        Returns:
            Updated frontend payload.
        """
        with self._lock:
            if self.bundle is None:
                return {"updated": False, "message": "No active bundle."}

            config = self.bundle["config"]
            if strategy not in config.strategies:
                return {"updated": False, "message": f"Unknown strategy: {strategy}"}

            matrix_df: pd.DataFrame = self.bundle["route_matrix_df"]
            if matrix_df.empty:
                return {"updated": False, "message": "No route matrix available."}

            normalized_service = str(service or "").strip().upper()
            selections = dict(self.bundle["selections"])
            changed_count = 0

            target_demands = []
            for demand in self.bundle["demands"]:
                demand_service = str(demand.service or "").strip().upper()
                if normalized_service and demand_service != normalized_service:
                    continue
                target_demands.append(demand)

            success_mask = matrix_df["success"].astype(str).str.lower().isin(["true", "1", "yes"])
            for demand in target_demands:
                filtered = matrix_df.loc[
                    (matrix_df["demand_id"] == demand.demand_id)
                    & (matrix_df["strategy"] == strategy)
                    & success_mask
                ].copy()

                if filtered.empty:
                    continue

                filtered = filtered.sort_values(by=["score"])
                row = filtered.iloc[0]
                new_selection = {
                    "shaft_guid": str(row["shaft_guid"]),
                    "strategy": str(row["strategy"]),
                }

                if selections.get(demand.demand_id) != new_selection:
                    changed_count += 1

                selections[demand.demand_id] = new_selection

            current_system = self._rebuild_system_from_saved_variants(selections)

            return {
                "updated": True,
                "strategy": strategy,
                "service": normalized_service or None,
                "changed_count": changed_count,
                "system": current_system.to_dict(),
            }

    def _preview_system_from_saved_variants(
        self,
        selections: dict[str, dict[str, str]],
    ) -> SystemBuildResult:
        """Build a saved-variant system without mutating runtime state."""
        if self.bundle is None:
            raise ValueError("No active bundle.")

        clean_selections = {
            key: value
            for key, value in selections.items()
            if "__svc_" not in str(key)
        }
        shaft_per_service, shaft_per_service_sel = self._build_shaft_per_service(clean_selections)
        clean_selections.update(shaft_per_service_sel)

        return build_system_from_saved_variants(
            demands=_visible_system_demands(self.bundle["demands"], shaft_per_service),
            route_rows=self.bundle["route_matrix_rows"],
            selections=clean_selections,
            shafts_by_guid=self.bundle["shafts_by_guid"],
            voxel_size=self.bundle["config"].voxel_size,
        )

    def _rebuild_system_from_saved_variants(
        self,
        selections: dict[str, dict[str, str]],
    ) -> SystemBuildResult:
        """Recompute and store system state without running the A*/Numba router."""
        if self.bundle is None:
            raise ValueError("No active bundle.")

        clean_selections = {
            key: value
            for key, value in selections.items()
            if "__svc_" not in str(key)
        }
        shaft_per_service, shaft_per_service_sel = self._build_shaft_per_service(clean_selections)
        clean_selections.update(shaft_per_service_sel)
        self.bundle["shaft_per_service_demands"] = shaft_per_service

        current_system = build_system_from_saved_variants(
            demands=_visible_system_demands(self.bundle["demands"], shaft_per_service),
            route_rows=self.bundle["route_matrix_rows"],
            selections=clean_selections,
            shafts_by_guid=self.bundle["shafts_by_guid"],
            voxel_size=self.bundle["config"].voxel_size,
        )

        self.bundle["selections"] = clean_selections
        self.current_system = current_system
        return current_system

    def get_demand_id(self, room_guid: str, service: str) -> str | None:
        """
        Find the demand id for one room-service pair.

        Args:
            room_guid: Room GUID.
            service: Service key.

        Returns:
            Demand id or None.
        """
        if self.bundle is None:
            return None

        for demand in self.bundle["demands"]:
            if demand.room_guid == room_guid and demand.service == service:
                return demand.demand_id
        return None

    def build_design_explorer_csv(self, demand_id: str) -> str:
        """Build a Design Explorer compatible CSV for one demand.

        Args:
            demand_id: Demand identifier.

        Returns:
            CSV text.

        Raises:
            ValueError: If there is no active bundle or the demand has no rows.
        """
        if self.bundle is None:
            raise ValueError("No active bundle.")

        matrix_df: pd.DataFrame = self.bundle["route_matrix_df"]
        selections = self.bundle.get("selections", {})
        return self.design_explorer.build_csv(matrix_df, demand_id, selections)









    def _build_shaft_per_service(
        self, selections: dict[str, dict[str, str]]
    ) -> tuple[list, dict]:
        """Recompute per-service shaft demands from current selections.

        Called after any selection change so sizing stays accurate.

        Args:
            selections: Current selections dict.

        Returns:
            Tuple of (per_service_demands, per_service_selections).
        """
        bundle = self.bundle
        if bundle is None:
            return [], {}

        shaft_placeholders = [
            d for d in bundle["demands"]
            if d.kind == "aggregated_shaft" and d.service == "SHAFT_FEED"
        ]

        return compute_shaft_aggregated_demands(
            demands=bundle["demands"],
            selections=selections,
            rooms_by_guid=bundle["rooms_by_guid"],
            shafts_by_guid=bundle["shafts_by_guid"],
            technical_rooms=bundle.get("technical_rooms", []),
            shaft_placeholder_demands=shaft_placeholders,
        )

    def _build_default_selections(self, matrix_df: pd.DataFrame) -> dict[str, dict[str, str]]:
        """
        Pick the best successful row per demand as the default selection.

        Args:
            matrix_df: Candidate dataframe.

        Returns:
            Selection mapping.
        """
        selections: dict[str, dict[str, str]] = {}
        if matrix_df.empty:
            return selections

        valid_df = matrix_df.loc[matrix_df["success"] == True].copy()
        if valid_df.empty:
            return selections

        valid_df = valid_df.sort_values(by=["demand_id", "score"])
        for demand_id, group in valid_df.groupby("demand_id"):
            row = group.iloc[0]
            selections[str(demand_id)] = {
                "shaft_guid": str(row["shaft_guid"]),
                "strategy": str(row["strategy"]),
            }
        return selections

    def export_routing_ifc(
        self,
        output_path: str | None = None,
        sizer_config: Any | None = None,
    ) -> Path:
        """
        Export all selected routing segments as IFC extruded volumes.

        Each service (HEI / LUE / SAN) is sized independently from the
        accumulated demand at every shared voxel.  Where services share a
        voxel their rectangles are stacked side-by-side into one combined
        bounding-box, enlarged by 5 % for clearance.

        Args:
            output_path:  Target .ifc path.  Defaults to uploads dir.
            sizer_config: Optional ``SizerConfig`` override.

        Returns:
            Path to the written IFC file.

        Raises:
            ValueError: If no system routes are available.
        """
        from pipe_planner.ifc_exporter import export_routing_ifc as _do_export

        if self.current_system is None or not self.current_system.routes:
            raise ValueError("No routing system available.  Load or build a project first.")

        if self.bundle is None:
            raise ValueError("No bundle loaded.")

        upload_dir = Path(__file__).resolve().parents[1] / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        ifc_name = (self.current_ifc_name or "routing_volumes").replace(".ifc", "")
        default_out = upload_dir / f"{ifc_name}_routing_volumes.ifc"
        target = Path(output_path) if output_path else default_out

        # ── Filter routes for export ──────────────────────────────────────
        # Exclude SHAFT_FEED placeholder routes — per-service routes (HEI,
        # LUE, SAN) carry the same geometry with correct aggregated sizing.
        export_routes = [
            r for r in self.current_system.routes
            if r.service != "SHAFT_FEED"
        ]

        # ── Full demand list for correct SectionSizer lookup ─────────────
        export_demands = (
            list(self.bundle["demands"])
            + list(self.bundle.get("shaft_per_service_demands", []))
        )

        # ── Extend rooms_by_guid with shafts mapped to their technikraum
        #    floor so IFC storey placement is correct ──────────────────────
        import dataclasses
        technical_rooms = self.bundle.get("technical_rooms", [])
        tr_floor_by_guid = {tr.guid: tr.floor_index for tr in technical_rooms}
        selections = self.current_system.selections
        rooms_for_export = dict(self.bundle["rooms_by_guid"])
        for demand in self.bundle["demands"]:
            if demand.kind != "aggregated_shaft" or demand.service != "SHAFT_FEED":
                continue
            shaft = self.bundle["shafts_by_guid"].get(demand.room_guid)
            if shaft is None:
                continue
            sel = selections.get(demand.demand_id, {})
            tr_floor = tr_floor_by_guid.get(sel.get("shaft_guid", ""))
            if tr_floor is not None:
                rooms_for_export[shaft.guid] = dataclasses.replace(
                    shaft, floor_index=tr_floor
                )

        return _do_export(
            routes=export_routes,
            demands=export_demands,
            floors=self.bundle["floors"],
            rooms_by_guid=rooms_for_export,
            output_path=target,
            sizer_config=sizer_config,
            project_name=self.current_ifc_name or "HLKS Routing Volumes",
        )













RUNTIME = PlannerRuntime()
