from __future__ import annotations

from dataclasses import dataclass, field

from pipe_planner.models import StrategyProfile


@dataclass
class KeywordConfig:
    """Keyword lists used to classify spaces.

    Args:
        corridor_keywords: Name fragments for corridors.
        shaft_keywords: Name fragments for shafts.
        no_route_space_keywords: Name fragments for spaces that routing must not pass through.
        technical_room_keywords: Name fragments that mark one room as a technical room.
        technical_room_sanitary_keywords: Tokens for sanitary technical rooms.
        technical_room_heating_keywords: Tokens for heating technical rooms.
        technical_room_ventilation_keywords: Tokens for ventilation technical rooms.
        technical_room_cooling_keywords: Tokens for cooling technical rooms.
        technical_room_sprinkler_keywords: Tokens for sprinkler technical rooms.

    Returns:
        KeywordConfig object.
    """

    corridor_keywords: list[str] = field(
        default_factory=lambda: ["korridor", "corridor", "flur", "gang"]
    )
    shaft_keywords: list[str] = field(
        default_factory=lambda: ["schacht", "shaft", "riser"]
    )
    no_route_space_keywords: list[str] = field(
        default_factory=lambda: [
            "treppenhaus",
            "stair",
            "stairs",
            "staircase",
            "lift",
            "elevator",
            "aufzug",
        ]
    )
    technical_room_keywords: list[str] = field(
        default_factory=lambda: ["technikzentrale", "zentrale", "technik"]
    )
    technical_room_sanitary_keywords: list[str] = field(
        default_factory=lambda: ["sanit", "trinkwasser", "abwasser", "wasser", "fettabscheider"]
    )
    technical_room_heating_keywords: list[str] = field(
        default_factory=lambda: ["heiz", "wärme", "waerme", "fernwärme", "fernwaerme"]
    )
    technical_room_ventilation_keywords: list[str] = field(
        default_factory=lambda: ["rlt", "lüft", "lueft", "vent", "klima", "ahu"]
    )
    technical_room_cooling_keywords: list[str] = field(
        default_factory=lambda: ["kälte", "kaelte", "kühl", "kuehl", "cool", "chiller"]
    )
    technical_room_sprinkler_keywords: list[str] = field(
        default_factory=lambda: ["sprinkler", "lösch", "loesch", "feuerlösch"]
    )


@dataclass
class PenaltyConfig:
    """Routing penalties and geometric margins.

    Args:
        wall_cross_penalty: Penalty for crossing a wall cell.
        slab_cross_penalty: Penalty for crossing a slab outside shafts.
        blocked_penalty: Very large value for blocked cells.
        wall_distance_clip: Maximum wall distance used in cost field.
        corridor_distance_clip: Maximum corridor center distance used in cost field.
        route_clearance_margin: Small bbox padding for route zones.
        voxel_margin: Margin added around the full model bbox.

    Returns:
        PenaltyConfig object.
    """

    wall_cross_penalty: float = 8.0
    slab_cross_penalty: float = 1000.0
    blocked_penalty: float = 1_000_000.0
    wall_distance_clip: int = 6
    corridor_distance_clip: int = 10
    route_clearance_margin: float = 0.1
    voxel_margin: float = 1.0


@dataclass
class ProjectConfig:
    """Top-level project configuration.

    Args:
        voxel_size: Edge length of one voxel in meters.
        default_workers: Number of parallel workers.
        keyword_config: Name filters.
        penalty_config: Penalties and margins.
        strategies: Strategy presets.
        shaft_allow_map: Optional shaft allow-list per service.
        candidate_shaft_limit: Number of nearest shafts to test per room.
        k_routes_per_strategy: Number of alternative routes computed per strategy via
            penalty replanning.  Each round penalises all cells of the previously
            found path so that A* is pushed into spatially different corridors.
            The candidate with the best score on the unmodified grid is returned.
            Set to 1 to disable replanning (single A* run, original behaviour).
        penalty_factor: Multiplier applied to the base voxel step cost when a cell
            is penalised after a replanning round.  Higher values force subsequent
            routes further away from earlier paths.  Typical range: 2.0–6.0.

    Returns:
        ProjectConfig object.
    """

    voxel_size: float = 0.5
    default_workers: int = 4
    keyword_config: KeywordConfig = field(default_factory=KeywordConfig)
    penalty_config: PenaltyConfig = field(default_factory=PenaltyConfig)
    strategies: dict[str, StrategyProfile] = field(default_factory=dict)
    shaft_allow_map: dict[str, list[str]] = field(default_factory=dict)
    candidate_shaft_limit: int = 4
    k_routes_per_strategy: int = 100
    penalty_factor: float = 3.0

    def __post_init__(self) -> None:
        """Fill strategy presets.

        Args:
            None.

        Returns:
            None.
        """
        if self.strategies:
            return

        self.strategies = {
            "Shortest": StrategyProfile(
                name="Shortest",
                length_weight=1.0,
                bend_penalty=0.3,
                vertical_penalty=0.8,
                wall_cross_penalty=8.0,
                slab_cross_penalty=1000.0,
                wall_distance_weight=0.1,
                ceiling_weight=0.1,
                corridor_center_weight=0.1,
                merge_reward=0.3,
            ),
            "WallCeiling": StrategyProfile(
                name="WallCeiling",
                length_weight=1.0,
                bend_penalty=0.4,
                vertical_penalty=0.8,
                wall_cross_penalty=8.0,
                slab_cross_penalty=1000.0,
                wall_distance_weight=0.8,
                ceiling_weight=0.6,
                corridor_center_weight=0.2,
                merge_reward=0.4,
            ),
            "CorridorMerge": StrategyProfile(
                name="CorridorMerge",
                length_weight=1.1,
                bend_penalty=0.5,
                vertical_penalty=1.0,
                wall_cross_penalty=8.0,
                slab_cross_penalty=1000.0,
                wall_distance_weight=0.4,
                ceiling_weight=0.4,
                corridor_center_weight=1.1,
                merge_reward=1.8,
            ),
            "LowPenetration": StrategyProfile(
                name="LowPenetration",
                length_weight=1.0,
                bend_penalty=0.7,
                vertical_penalty=0.9,
                wall_cross_penalty=20.0,
                slab_cross_penalty=1000.0,
                wall_distance_weight=0.6,
                ceiling_weight=0.4,
                corridor_center_weight=0.4,
                merge_reward=0.4,
            ),
            "Balanced": StrategyProfile(
                name="Balanced",
                length_weight=1.0,
                bend_penalty=0.5,
                vertical_penalty=0.9,
                wall_cross_penalty=10.0,
                slab_cross_penalty=1000.0,
                wall_distance_weight=0.5,
                ceiling_weight=0.5,
                corridor_center_weight=0.5,
                merge_reward=0.8,
            ),
            "IgnoreWallPenalty": StrategyProfile(
                name="IgnoreWallPenalty",
                length_weight=1.0,
                bend_penalty=0.4,
                vertical_penalty=0.8,
                wall_cross_penalty=0.0,
                slab_cross_penalty=1000.0,
                wall_distance_weight=0.2,
                ceiling_weight=0.3,
                corridor_center_weight=0.3,
                merge_reward=0.6,
                ignore_wall_penalty=True,
            ),
        }


def build_default_config() -> ProjectConfig:
    """Return the default project config.

    Args:
        None.

    Returns:
        ProjectConfig object.
    """
    return ProjectConfig()
