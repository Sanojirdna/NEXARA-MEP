from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipe_planner.models import DemandRecord, SpaceRecord


SERVICE_ALIASES = {
    "SAN": "SAN",
    "WATER": "SAN",
    "SANITARY": "SAN",
    "DOMESTIC_WATER": "SAN",
    "LUE": "LUE",
    "AIR": "LUE",
    "SUPPLY_AIR": "LUE",
    "EXHAUST_AIR": "LUE",
    "VENTILATION": "LUE",
    "HEI": "HEI",
    "HEATING": "HEI",
    "HOT_WATER": "HEI",
    "HEAT": "HEI",
}


def normalize_service(media_type: str, hvac_system_type: str) -> str:
    """Map Excel text to SAN, LUE, or HEI.

    Args:
        media_type: Raw media type text.
        hvac_system_type: Raw HVAC system type text.

    Returns:
        Simplified service key.
    """
    for raw_value in [media_type, hvac_system_type]:
        key = str(raw_value or "").strip().upper()
        if key in SERVICE_ALIASES:
            return SERVICE_ALIASES[key]

        for alias, service in SERVICE_ALIASES.items():
            if alias in key:
                return service
    return "OTHER"


def load_demands(
    excel_path: str | Path,
    spaces_by_guid: dict[str, SpaceRecord],
    spaces_by_name: dict[str, SpaceRecord],
) -> list[DemandRecord]:
    """Load Excel demands and attach them to rooms.

    Args:
        excel_path: Excel file path.
        spaces_by_guid: IFC spaces by guid.
        spaces_by_name: IFC spaces by normalized room name.

    Returns:
        List of DemandRecord objects.
    """
    dataframe = pd.read_excel(excel_path)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]

    demands: list[DemandRecord] = []
    demand_index = 0

    for _, row in dataframe.iterrows():
        room_guid = str(row.get("ifc_guid", "") or "").strip()
        room_name = str(row.get("room_name", "") or "").strip()
        media_type = str(row.get("media_type", "") or "").strip()
        hvac_system_type = str(row.get("hvac_system_type", "") or "").strip()
        kind = str(row.get("kind", "") or "").strip()
        value = row.get("value", 0.0)
        unit = str(row.get("unit", "") or "").strip()

        space = None
        if room_guid and room_guid in spaces_by_guid:
            space = spaces_by_guid[room_guid]
        elif room_name:
            space = spaces_by_name.get(normalize_room_name(room_name))

        if space is None:
            continue

        if space.space_type != "room":
            continue

        demand_index += 1
        demands.append(
            DemandRecord(
                demand_id=f"demand_{demand_index:04d}",
                room_guid=space.guid,
                room_name=space.label(),
                service=normalize_service(media_type, hvac_system_type),
                media_type=media_type,
                hvac_system_type=hvac_system_type,
                kind=kind,
                value=float(value) if pd.notna(value) else 0.0,
                unit=unit,
            )
        )

    return demands


def normalize_room_name(text: str) -> str:
    """Normalize room names for matching.

    Args:
        text: Room name text.

    Returns:
        Normalized text.
    """
    return " ".join(str(text or "").strip().lower().split())


def write_demands_json(demands: list[DemandRecord], output_path: str | Path) -> None:
    """Write demands to JSON.

    Args:
        demands: Demand list.
        output_path: Output file path.

    Returns:
        None.
    """
    payload = [demand.to_dict() for demand in demands]
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
