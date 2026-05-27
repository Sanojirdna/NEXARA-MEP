from __future__ import annotations

import json
from typing import Any

from .study_utils import STUDY_EXPORT_PATH, STUDY_STATE_PATH, StudyUtilityMixin


class StudyStateStore(StudyUtilityMixin):
    """Load, save, import, export, and reset the Studie state."""

    def load(self) -> dict[str, Any]:
        """Return the saved Studie state."""
        return self._load_state()

    def save(self, state: dict[str, Any]) -> None:
        """Save the Studie state to disk."""
        self._save_state_to_disk(state)

    def normalize_weights(self, weights: dict[str, Any]) -> dict[str, int]:
        """Return normalized Studie weight values."""
        return self._normalized_weights(weights)

    def get_snapshot(self) -> dict[str, Any]:
        """Return a serializable Studie state snapshot."""
        return self.get_state_snapshot()

    def import_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Import a serializable Studie state snapshot."""
        self.import_state_snapshot(snapshot)

    def get_state_snapshot(self) -> dict[str, Any]:
        return self._load_state()

    def import_state_snapshot(self, state: dict[str, Any]) -> None:
        clean_state = {
            "selected_coords": list((state or {}).get("selected_coords", [])),
            "weights": self._normalized_weights((state or {}).get("weights", {})),
        }
        self._save_state_to_disk(clean_state)

    def reset(self) -> None:
        if STUDY_STATE_PATH.exists():
            STUDY_STATE_PATH.unlink()
        if STUDY_EXPORT_PATH.exists():
            STUDY_EXPORT_PATH.unlink()

    def _load_state(self) -> dict[str, Any]:
        if not STUDY_STATE_PATH.exists():
            return {"selected_coords": [], "weights": {}}
        try:
            data = json.loads(STUDY_STATE_PATH.read_text(encoding="utf-8"))
            return {
                "selected_coords": list(data.get("selected_coords", [])),
                "weights": self._normalized_weights(data.get("weights", {})),
            }
        except Exception:
            return {"selected_coords": [], "weights": {}}

    def _save_state_to_disk(self, state: dict[str, Any]) -> None:
        STUDY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STUDY_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _normalized_weights(self, raw_weights: dict[str, Any]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for key, value in (raw_weights or {}).items():
            coord = str(key or "").strip().upper()
            if not coord.startswith("F"):
                continue
            if value in (None, ""):
                continue
            try:
                parsed = int(value)
            except Exception:
                continue
            if parsed in (1, 2, 3):
                normalized[coord] = parsed
        return normalized
