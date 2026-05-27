from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, render_template, send_from_directory
from flask_cors import CORS

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_SRC_DIR = PROJECT_ROOT / "frontend" / "src"
FRONTEND_NODE_MODULES_DIR = PROJECT_ROOT / "frontend" / "node_modules"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from routes import api
from pipe_planner.config import build_default_config


def create_app() -> Flask:
    """Create the Flask application with 3 main pages."""
    app = Flask(
        __name__,
        template_folder=str(CURRENT_DIR / "templates"),
    )
    CORS(app)
    app.register_blueprint(api, url_prefix="/api")

    @app.get("/")
    def landing_page():
        cfg = build_default_config()
        return render_template("landing.html", default_workers=cfg.default_workers)

    @app.get("/studie")
    def studie_page():
        return render_template("studie.html")

    @app.get("/vorprojekt")
    def vorprojekt_page():
        return render_template("vorprojekt_source.html")

    @app.get("/vorprojekt_src/<path:path>")
    def vorprojekt_source_asset(path: str):
        return send_from_directory(FRONTEND_SRC_DIR, path)

    @app.get("/vorprojekt_modules/<path:path>")
    def vorprojekt_module_asset(path: str):
        return send_from_directory(FRONTEND_NODE_MODULES_DIR, path)

    @app.get("/vorprojekt_dist/<path:path>")
    def vorprojekt_dist_asset(path: str):
        if FRONTEND_DIST_DIR.exists():
            return send_from_directory(FRONTEND_DIST_DIR, path)
        return ("Not found", 404)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
