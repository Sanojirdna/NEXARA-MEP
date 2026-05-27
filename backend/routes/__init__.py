from __future__ import annotations

from flask import Blueprint

api = Blueprint("api", __name__)

from . import session_routes  # noqa: E402,F401
from . import config_routes  # noqa: E402,F401
from . import study_routes  # noqa: E402,F401
from . import routing_routes  # noqa: E402,F401
from . import file_routes  # noqa: E402,F401
