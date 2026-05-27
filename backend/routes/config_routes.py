from __future__ import annotations

from flask import jsonify, request, send_file
from werkzeug.utils import secure_filename

from planner_runtime import RUNTIME

from . import api
from .session_routes import ensure_upload_dir


@api.get("/config/export")
def export_config():
    """Export the active planner configuration.

    Args:
        None.

    Returns:
        Download response for the config JSON file.
    """
    export_path = RUNTIME.export_config_json()
    return send_file(export_path, download_name=export_path.name, as_attachment=True)


@api.post("/config/import")
def import_config():
    """Import a planner configuration JSON file.

    Args:
        None.

    Returns:
        JSON import result.
    """
    config_file = request.files.get("config_file")
    if config_file is None:
        return jsonify({"loaded": False, "message": "config_file is required."}), 400

    upload_dir = ensure_upload_dir()
    safe_name = secure_filename(config_file.filename or "planner_config.json")
    config_path = upload_dir / safe_name
    config_file.save(config_path)

    result = RUNTIME.load_config_json(str(config_path))
    return jsonify(result)


@api.get("/session/config")
def session_config():
    """Return the active session config summary.

    Args:
        None.

    Returns:
        JSON config summary.
    """
    return jsonify({
        "loaded": True,
        "config_name": RUNTIME.current_config_name,
        "config_source": RUNTIME.current_config_source,
        "config": {
            "voxel_size": RUNTIME.current_config.voxel_size,
            "default_workers": RUNTIME.current_config.default_workers,
            "candidate_shaft_limit": RUNTIME.current_config.candidate_shaft_limit,
            "k_routes_per_strategy": RUNTIME.current_config.k_routes_per_strategy,
            "penalty_factor": RUNTIME.current_config.penalty_factor,
            "strategy_count": len(RUNTIME.current_config.strategies),
        },
    })
