from __future__ import annotations

from pathlib import Path

from flask import jsonify, send_file

from planner_runtime import RUNTIME

from . import api


@api.get("/session/export-routing-ifc")
def export_routing_ifc():
    """Export selected routing segments as IFC extruded volumes.

    Args:
        None.

    Returns:
        Download response for the routing IFC file.
    """
    if RUNTIME.bundle is None or RUNTIME.current_system is None:
        return jsonify({"exported": False, "message": "No active project loaded."}), 400
    try:
        ifc_path = RUNTIME.export_routing_ifc()
    except ValueError as exc:
        return jsonify({"exported": False, "message": str(exc)}), 400
    return send_file(ifc_path, download_name=ifc_path.name, as_attachment=True)


@api.get("/files/current-ifc")
def current_ifc():
    """Return the current IFC file.

    Args:
        None.

    Returns:
        Download response for the IFC file.
    """
    if RUNTIME.current_ifc_path is None:
        return jsonify({"found": False, "message": "No IFC file loaded in the current session."}), 404

    return send_file(RUNTIME.current_ifc_path, download_name=Path(RUNTIME.current_ifc_path).name)
