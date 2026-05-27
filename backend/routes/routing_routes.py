from __future__ import annotations

from flask import Response, jsonify, request

from planner_runtime import RUNTIME

from . import api


@api.get("/room/<room_guid>")
def room_detail(room_guid: str):
    """Return frontend details for one room.

    Args:
        room_guid: IFC room GUID.

    Returns:
        JSON room detail payload.
    """
    return jsonify(RUNTIME.get_room_detail(room_guid))


@api.get("/variants/system-overview")
def system_strategy_overview():
    """Return one aggregated row per strategy for the global Design Explorer.

    Args:
        None.

    Returns:
        JSON system overview payload.
    """
    payload = RUNTIME.get_system_strategy_overview()
    return jsonify(payload)


@api.get("/variants/all")
def all_variants():
    """Return all route variants for the Design Explorer overview.

    Args:
        None.

    Returns:
        JSON variant payload.
    """
    payload = RUNTIME.get_all_variants()
    return jsonify(payload)


@api.get("/variants")
def room_variants():
    """Return route variants for one room and service.

    Args:
        None.

    Returns:
        JSON room/service variant payload.
    """
    room_guid = str(request.args.get("room_guid", ""))
    service = str(request.args.get("service", ""))

    if not room_guid or not service:
        return jsonify({"found": False, "message": "room_guid and service are required."}), 400

    payload = RUNTIME.get_variants_for_room_service(room_guid, service)
    return jsonify(payload)


@api.get("/design-explorer/datasets/<demand_id>/data.csv")
def design_explorer_dataset(demand_id: str):
    """Return a Design Explorer compatible CSV for one room-service demand.

    Args:
        demand_id: Demand identifier.

    Returns:
        CSV response.
    """
    try:
        csv_text = RUNTIME.build_design_explorer_csv(demand_id)
    except ValueError as exc:
        return jsonify({"found": False, "message": str(exc)}), 404

    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


@api.post("/selection")
def update_selection():
    """Update the selected route variant for one demand.

    Args:
        None.

    Returns:
        JSON update result.
    """
    payload = request.get_json(silent=True) or {}
    demand_id = str(payload.get("demand_id", ""))
    shaft_guid = str(payload.get("shaft_guid", ""))
    strategy = str(payload.get("strategy", ""))

    if not demand_id or not shaft_guid or not strategy:
        return jsonify({"updated": False, "message": "demand_id, shaft_guid and strategy are required."}), 400

    result = RUNTIME.update_selection(demand_id=demand_id, shaft_guid=shaft_guid, strategy=strategy)
    return jsonify(result)


@api.post("/selection/strategy-all")
def apply_strategy_to_all():
    """Apply one routing strategy to all matching selected demands.

    Args:
        None.

    Returns:
        JSON update result.
    """
    payload = request.get_json(silent=True) or {}
    strategy = str(payload.get("strategy", ""))
    service = str(payload.get("service", ""))

    if not strategy:
        return jsonify({"updated": False, "message": "strategy is required."}), 400

    result = RUNTIME.apply_strategy_to_system(
        strategy=strategy,
        service=service or None,
    )
    return jsonify(result)


@api.get("/demand-id")
def get_demand_id():
    """Find the demand id for a room and service.

    Args:
        None.

    Returns:
        JSON demand id lookup result.
    """
    room_guid = str(request.args.get("room_guid", ""))
    service = str(request.args.get("service", ""))

    if not room_guid or not service:
        return jsonify({"found": False, "message": "room_guid and service are required."}), 400

    demand_id = RUNTIME.get_demand_id(room_guid=room_guid, service=service)
    return jsonify({"found": demand_id is not None, "demand_id": demand_id})
