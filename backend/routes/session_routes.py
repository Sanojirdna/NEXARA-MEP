from __future__ import annotations

from pathlib import Path

from flask import jsonify, request, send_file
from werkzeug.utils import secure_filename

from planner_runtime import RUNTIME
from studie_service import STUDIE

from . import api


def ensure_upload_dir() -> Path:
    """Create the upload directory if needed.

    Args:
        None.

    Returns:
        Upload directory path.
    """
    upload_dir = Path(__file__).resolve().parents[2] / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@api.get("/health")
def health() -> tuple[dict, int]:
    """Return a simple health check response.

    Args:
        None.

    Returns:
        Health response and HTTP status code.
    """
    return {"ok": True}, 200


@api.post("/session/build")
def build_session():
    """Build a new planning session from uploaded files.

    Args:
        None.

    Returns:
        JSON response with the project summary.
    """
    ifc_file = request.files.get("ifc_file")
    excel_file = request.files.get("excel_file")
    config_file = request.files.get("config_file")
    workers = int(request.form.get("workers", "4"))

    if ifc_file is None or excel_file is None:
        return jsonify({"built": False, "message": "Both IFC and Excel files are required."}), 400

    upload_dir = ensure_upload_dir()

    safe_ifc_name = secure_filename(ifc_file.filename or "model.ifc")
    safe_excel_name = secure_filename(excel_file.filename or "room_book.xlsx")

    ifc_path = upload_dir / safe_ifc_name
    excel_path = upload_dir / safe_excel_name

    ifc_file.save(ifc_path)
    excel_file.save(excel_path)

    config = None
    config_name = None
    config_source = None
    if config_file is not None and config_file.filename:
        safe_config_name = secure_filename(config_file.filename or "planner_config.json")
        config_path = upload_dir / safe_config_name
        config_file.save(config_path)
        loaded = RUNTIME.load_config_json(str(config_path))
        config = RUNTIME.current_config
        config_name = loaded.get("config_name")
        config_source = loaded.get("config_source")

    summary = RUNTIME.build_from_files(
        ifc_path=str(ifc_path),
        excel_path=str(excel_path),
        uploads_dir=str(upload_dir / "outputs"),
        workers=workers,
        config=config,
        config_name=config_name,
        config_source=config_source,
    )

    return jsonify({
        "built": True,
        "summary": summary,
    })


@api.post("/session/import")
def import_session():
    """Import a saved project bundle.

    Args:
        None.

    Returns:
        JSON response with the loaded project summary.
    """
    bundle_file = request.files.get("bundle_file")
    ifc_file = request.files.get("ifc_file")
    if bundle_file is None:
        return jsonify({"loaded": False, "message": "bundle_file is required."}), 400

    upload_dir = ensure_upload_dir()
    safe_name = secure_filename(bundle_file.filename or "project_bundle.json")
    bundle_path = upload_dir / safe_name
    bundle_file.save(bundle_path)

    ifc_path = None
    if ifc_file is not None and ifc_file.filename:
        safe_ifc_name = secure_filename(ifc_file.filename or "model.ifc")
        ifc_path = upload_dir / safe_ifc_name
        ifc_file.save(ifc_path)

    try:
        summary = RUNTIME.import_project_bundle(
            bundle_path=str(bundle_path),
            ifc_path=str(ifc_path) if ifc_path else None,
        )
    except ValueError as exc:
        return jsonify({"loaded": False, "message": str(exc)}), 400

    study_state = summary.get("study_state")
    if isinstance(study_state, dict):
        STUDIE.import_state_snapshot(study_state)

    return jsonify({
        "loaded": True,
        "summary": summary,
    })


@api.get("/session/export")
def export_session():
    """Export the current project bundle.

    Args:
        None.

    Returns:
        Download response for the project bundle.
    """
    if RUNTIME.bundle is None:
        return jsonify({"exported": False, "message": "No active project loaded."}), 400

    export_path = RUNTIME.export_project_bundle(
        study_state=STUDIE.get_state_snapshot(),
    )
    return send_file(export_path, download_name=export_path.name, as_attachment=True)


@api.get("/session/summary")
def session_summary():
    """Return the current planning session summary.

    Args:
        None.

    Returns:
        JSON session summary.
    """
    summary = RUNTIME.get_summary()
    summary["study_state"] = STUDIE.get_state_snapshot()
    return jsonify(summary)


@api.post("/session/reset")
def reset_session():
    """Reset runtime and study state.

    Args:
        None.

    Returns:
        JSON reset response.
    """
    STUDIE.reset()
    return jsonify(RUNTIME.reset_session())
