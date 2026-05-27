
"""Compatibility exports for the structured domain package.

Existing imports can keep using pipe_planner.models while the actual
classes now live under pipe_planner.domain.
"""

from pipe_planner.domain import *  # noqa: F401,F403
