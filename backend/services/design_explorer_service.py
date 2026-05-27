from __future__ import annotations

import csv
import io
from typing import Any

import pandas as pd

from pipe_planner.routing_helpers.route_result_serializer import float_or_empty, int_or_empty


class DesignExplorerService:
    """Build Design Explorer rows and CSV exports.

    Args:
        None.

    Returns:
        DesignExplorerService object.
    """

    def build_csv(
        self,
        matrix_df: pd.DataFrame,
        demand_id: str,
        selections: dict[str, dict[str, str]] | None = None,
    ) -> str:
        """Build a Design Explorer compatible CSV for one demand.

        Args:
            matrix_df: Route matrix dataframe.
            demand_id: Demand identifier.
            selections: Current demand selections by demand id.

        Returns:
            CSV text.

        Raises:
            ValueError: If the demand has no successful variants.
        """
        rows = self.get_rows(matrix_df, demand_id, selections or {})
        if not rows:
            raise ValueError("No successful variants found for this demand.")

        fieldnames = list(rows[0].keys())
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()

    def get_rows(
        self,
        matrix_df: pd.DataFrame,
        demand_id: str,
        selections: dict[str, dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Prepare flat Design Explorer rows for one demand.

        Args:
            matrix_df: Route matrix dataframe.
            demand_id: Demand identifier.
            selections: Current demand selections by demand id.

        Returns:
            List of CSV-safe dictionaries.
        """
        if matrix_df.empty:
            return []

        filtered = matrix_df.loc[
            (matrix_df["demand_id"] == demand_id)
            & (matrix_df["success"] == True)
        ].copy()

        if filtered.empty:
            return []

        filtered = filtered.sort_values(by=["score", "shaft_name", "strategy"]).reset_index(drop=True)
        selected = (selections or {}).get(demand_id, {})
        rows: list[dict[str, Any]] = []

        for index, row in enumerate(filtered.to_dict(orient="records"), start=1):
            is_selected = (
                str(row.get("shaft_guid", "")) == str(selected.get("shaft_guid", ""))
                and str(row.get("strategy", "")) == str(selected.get("strategy", ""))
            )
            metrics = row.get("metrics") or {}
            rows.append(
                {
                    "VariantIndex": index,
                    "VariantLabel": f"{row.get('shaft_name', '-') } | {row.get('strategy', '-')}",
                    "DemandId": str(row.get("demand_id", "")),
                    "RoomName": str(row.get("room_name", "")),
                    "RoomGuid": str(row.get("room_guid", "")),
                    "Service": str(row.get("service", "")),
                    "ShaftName": str(row.get("shaft_name", "")),
                    "ShaftGuid": str(row.get("shaft_guid", "")),
                    "Strategy": str(row.get("strategy", "")),
                    "Selected": 1 if is_selected else 0,
                    "Score": float_or_empty(row.get("score")),
                    "LengthM": float_or_empty(row.get("length_m", metrics.get("length_m"))),
                    "HorizontalLengthM": float_or_empty(row.get("horizontal_length_m", metrics.get("horizontal_length_m"))),
                    "VerticalLengthM": float_or_empty(row.get("vertical_length_m", metrics.get("vertical_length_m"))),
                    "BendCount": int_or_empty(row.get("bend_count", metrics.get("bend_count"))),
                    "WallCrossings": int_or_empty(row.get("wall_crossings", metrics.get("wall_crossings"))),
                    "SlabCrossings": int_or_empty(row.get("slab_crossings", metrics.get("slab_crossings"))),
                    "SharedLengthM": float_or_empty(row.get("shared_length_m", metrics.get("shared_length_m"))),
                    "CorridorSteps": int_or_empty(row.get("corridor_steps", metrics.get("corridor_steps"))),
                    "ShaftSteps": int_or_empty(row.get("shaft_steps", metrics.get("shaft_steps"))),
                    "RoomSteps": int_or_empty(row.get("room_steps", metrics.get("room_steps"))),
                    "MeanCeilingScore": float_or_empty(row.get("mean_ceiling_score", metrics.get("mean_ceiling_score"))),
                    "MeanWallDistance": float_or_empty(row.get("mean_wall_distance", metrics.get("mean_wall_distance"))),
                    "MeanCorridorDistance": float_or_empty(row.get("mean_corridor_distance", metrics.get("mean_corridor_distance"))),
                    "Message": str(row.get("message", "")),
                }
            )

        return rows
