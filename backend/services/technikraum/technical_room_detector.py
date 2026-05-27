from __future__ import annotations

from typing import Any

from .constants import DISCIPLINE_LABELS


class TechnicalRoomDetector:
    """Find and classify technical rooms from IFC spaces."""

    def find_technical_rooms(
        self,
        rooms: list[Any],
        floors: list[Any],
        runtime: Any,
        technical_room_keywords: list[str],
    ) -> list[dict[str, Any]]:
        """Return technical rooms detected by name keywords."""
        return self._find_technical_rooms(rooms, floors, runtime, technical_room_keywords)

    def build_required_discipline_status(
        self,
        technical_rooms: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Return sanitary, heating, and ventilation detection status."""
        return self._build_required_discipline_status(technical_rooms)

    def technical_room_keywords(self, runtime: Any) -> list[str]:
        """Return configured technical-room keywords or safe defaults."""
        return self._technical_room_keywords(runtime)

    def _technical_room_keywords(self, runtime: Any) -> list[str]:
        config = getattr(runtime, "current_config", None)
        keyword_config = getattr(config, "keyword_config", None)
        values = list(getattr(keyword_config, "technical_room_keywords", []) or [])
        clean_values = [str(item).strip().lower() for item in values if str(item).strip()]
        if clean_values:
            return clean_values
        return ["technikzentrale", "zentrale", "technik"]

    def _discipline_token_map(self, runtime: Any) -> dict[str, list[str]]:
        config = getattr(runtime, "current_config", None)
        keyword_config = getattr(config, "keyword_config", None)

        def clean(name: str, fallback: list[str]) -> list[str]:
            values = list(getattr(keyword_config, name, []) or [])
            clean_values = [str(item).strip().lower() for item in values if str(item).strip()]
            if clean_values:
                return clean_values
            return fallback

        return {
            "sanitary": clean(
                "technical_room_sanitary_keywords",
                ["sanit", "trinkwasser", "abwasser", "wasser", "fettabscheider"],
            ),
            "heating": clean(
                "technical_room_heating_keywords",
                ["heiz", "wärme", "waerme", "fernwärme", "fernwaerme"],
            ),
            "ventilation": clean(
                "technical_room_ventilation_keywords",
                ["rlt", "lüft", "lueft", "vent", "klima", "ahu"],
            ),
            "cooling": clean(
                "technical_room_cooling_keywords",
                ["kälte", "kaelte", "kühl", "kuehl", "cool", "chiller"],
            ),
            "sprinkler": clean(
                "technical_room_sprinkler_keywords",
                ["sprinkler", "lösch", "loesch", "feuerlösch"],
            ),
        }

    def _build_required_discipline_status(self, technical_rooms: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = {}
        for discipline_key in ["sanitary", "heating", "ventilation"]:
            matching_rooms = [item for item in technical_rooms if item.get("discipline_key") == discipline_key]
            summary[discipline_key] = {
                "label": DISCIPLINE_LABELS[discipline_key],
                "found": bool(matching_rooms),
                "room_count": len(matching_rooms),
                "area_m2": round(sum(float(item.get("area_m2") or 0.0) for item in matching_rooms), 2),
            }
        return summary

    def _find_technical_rooms(
        self,
        rooms: list[Any],
        floors: list[Any],
        runtime: Any,
        technical_room_keywords: list[str],
    ) -> list[dict[str, Any]]:
        floor_name_by_index = {
            getattr(floor, "floor_index", -1): str(getattr(floor, "name", "") or "")
            for floor in floors
        }
        discipline_token_map = self._discipline_token_map(runtime)
        discipline_order = ["sanitary", "heating", "ventilation", "cooling", "sprinkler"]

        items: list[dict[str, Any]] = []
        for room in rooms:
            room_text = f"{getattr(room, 'name', '')} {getattr(room, 'long_name', '')}".lower()
            room_keyword_matches = [token for token in technical_room_keywords if token in room_text]
            if not room_keyword_matches:
                continue

            discipline_key = "unknown"
            discipline_tokens: list[str] = []
            for key in discipline_order:
                local_matches = [token for token in discipline_token_map[key] if token in room_text]
                if local_matches:
                    discipline_key = key
                    discipline_tokens = local_matches
                    break

            items.append(
                {
                    "guid": str(getattr(room, "guid", "") or ""),
                    "label": self._space_label(room),
                    "floor_index": getattr(room, "floor_index", -1),
                    "floor_name": floor_name_by_index.get(
                        getattr(room, "floor_index", -1),
                        f"Floor {getattr(room, 'floor_index', -1)}",
                    ),
                    "area_m2": round(self._bbox_area(room), 2),
                    "discipline_key": discipline_key,
                    "discipline_label": DISCIPLINE_LABELS.get(discipline_key, discipline_key),
                    "room_keyword_matches": sorted(set(room_keyword_matches)),
                    "discipline_tokens": sorted(set(discipline_tokens)),
                }
            )

        items.sort(key=lambda item: (item["floor_index"], item["label"]))
        return items

    def _space_label(self, space: Any) -> str:
        name = str(getattr(space, "name", "") or "").strip()
        long_name = str(getattr(space, "long_name", "") or "").strip()
        if long_name:
            return f"{name} | {long_name}"
        return name or str(getattr(space, "guid", "") or "-")

    def _bbox_area(self, space: Any) -> float:
        bbox = getattr(space, "bbox", None)
        if bbox is None:
            return 0.0
        width = max(0.0, float(bbox.max_x) - float(bbox.min_x))
        depth = max(0.0, float(bbox.max_y) - float(bbox.min_y))
        return width * depth