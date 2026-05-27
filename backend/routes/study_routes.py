from __future__ import annotations

from flask import jsonify, send_file, request

from planner_runtime import RUNTIME
from studie_service import STUDIE

from . import api


@api.get("/studie/data")
def studie_data():
    """Return the Studie page payload.

    Args:
        None.

    Returns:
        JSON Studie payload.
    """
    return jsonify(STUDIE.get_payload(RUNTIME))


@api.post("/studie/save")
def studie_save():
    """Save Studie page state.

    Args:
        None.

    Returns:
        JSON save result.
    """
    payload = request.get_json(silent=True) or {}
    result = STUDIE.save_state(payload, RUNTIME)
    status = 200 if result.get("saved") else 400
    return jsonify(result), status


@api.post("/studie/autofill")
def studie_autofill():
    """Autofill Studie values from the current IFC runtime.

    Args:
        None.

    Returns:
        JSON autofill result.
    """
    result = STUDIE.autofill_from_ifc(RUNTIME)
    payload = result.get("payload", {})
    return jsonify({
        "saved": result.get("saved", False),
        "message": payload.get("autofill_message"),
        "applied": payload.get("autofill_applied", []),
        "payload": payload,
    }), 200


@api.get("/studie/export")
def studie_export():
    """Export the Studie workbook.

    Args:
        None.

    Returns:
        Download response for the workbook.
    """
    export_path = STUDIE.export_workbook(RUNTIME)
    return send_file(export_path, download_name=export_path.name, as_attachment=True)
