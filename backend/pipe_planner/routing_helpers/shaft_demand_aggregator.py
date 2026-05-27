"""shaft_demand_aggregator.py
==============================
Compute per-service aggregated demands for shaft → Technikraum pipe segments.

Background
----------
Upper-floor rooms route to vertical shafts (A42, B42, C42, …).  At the
Technikraum floor a different set of IFC spaces represents the same physical
shafts (U42, U43, …) — same XY centroid, different Z band.

``compute_shaft_aggregated_demands`` matches each UG shaft to all upper-floor
shafts that share its XY centroid (within XY_MATCH_TOLERANCE), sums every
demand that was routed through those upper-floor shafts, and produces one
``DemandRecord`` per (UG-shaft, service) so ``SectionSizer`` can correctly
dimension the horizontal UG-floor pipe runs.

Public API
----------
    per_service, per_service_sel = compute_shaft_aggregated_demands(
        demands, selections, rooms_by_guid, shafts_by_guid,
        technical_rooms, shaft_placeholder_demands,
    )
"""
from __future__ import annotations

from collections import defaultdict

from pipe_planner.models import DemandRecord, SpaceRecord

# Two shaft spaces are considered co-located when their XY centroids are
# within this distance (metres).  Exact match expected; 0.5 m is generous.
XY_MATCH_TOLERANCE: float = 0.5


def _xy_centroid(space: SpaceRecord) -> tuple[float, float]:
    """Return the XY centroid of a space bbox."""
    return (
        (space.bbox.min_x + space.bbox.max_x) / 2.0,
        (space.bbox.min_y + space.bbox.max_y) / 2.0,
    )


def _xy_dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _build_upper_to_ug_shaft_map(
    ug_shafts: list[SpaceRecord],
    all_shafts: list[SpaceRecord],
) -> dict[str, str]:
    """Map every upper-floor shaft GUID to its matching UG-shaft GUID.

    For each upper-floor shaft the nearest UG-shaft (by XY centroid) within
    XY_MATCH_TOLERANCE is used.  Shafts with no match are ignored.

    Args:
        ug_shafts: Shafts that appear as route origins on the Technikraum floor
            (i.e. shafts that have a SHAFT_FEED placeholder demand).
        all_shafts: Every shaft SpaceRecord in the building.

    Returns:
        Mapping of upper_shaft_guid → ug_shaft_guid.
    """
    ug_centroids = {s.guid: _xy_centroid(s) for s in ug_shafts}
    mapping: dict[str, str] = {}

    for shaft in all_shafts:
        if shaft.guid in ug_centroids:
            # This IS a UG shaft — maps to itself.
            mapping[shaft.guid] = shaft.guid
            continue

        sc = _xy_centroid(shaft)
        best_guid: str | None = None
        best_dist = float("inf")
        for ug_guid, ug_c in ug_centroids.items():
            d = _xy_dist(sc, ug_c)
            if d < best_dist and d <= XY_MATCH_TOLERANCE:
                best_dist = d
                best_guid = ug_guid

        if best_guid is not None:
            mapping[shaft.guid] = best_guid

    return mapping




def _pick_service_strategy(
    ug_guid: str,
    service: str,
    strategy_weights: dict[tuple[str, str, str], float],
    fallback: str,
) -> str:
    """Pick the dominant selected strategy for one UG-shaft/service pair.

    Args:
        ug_guid: Technikraum-floor shaft GUID.
        service: Service key, e.g. HEI, LUE or SAN.
        strategy_weights: Weighted selected strategy counters.
        fallback: Strategy from the SHAFT_FEED placeholder.

    Returns:
        Strategy name to use for the per-service shaft→Technikraum route.
    """
    candidates: list[tuple[float, str]] = []
    for (candidate_ug, candidate_service, strategy), weight in strategy_weights.items():
        if candidate_ug == ug_guid and candidate_service == service:
            candidates.append((float(weight), strategy))

    if not candidates:
        return fallback or "Balanced"

    # Highest accumulated demand wins; strategy name is used as deterministic
    # tie-breaker so repeated rebuilds stay stable.
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1]

def compute_shaft_aggregated_demands(
    demands: list[DemandRecord],
    selections: dict[str, dict[str, str]],
    rooms_by_guid: dict[str, SpaceRecord],
    shafts_by_guid: dict[str, SpaceRecord],
    technical_rooms: list[SpaceRecord],
    shaft_placeholder_demands: list[DemandRecord],
) -> tuple[list[DemandRecord], dict[str, dict[str, str]]]:
    """Compute per-service aggregated demands for every UG shaft.

    Matches upper-floor shafts to UG shafts by XY centroid, sums all real
    room demands routed through each upper-floor shaft, and creates one
    ``DemandRecord`` per (UG shaft, service).

    Args:
        demands: All demands in the bundle (real + SHAFT_FEED placeholders).
        selections: Current selections dict (demand_id → {shaft_guid, strategy}).
        rooms_by_guid: Room lookup by GUID.
        shafts_by_guid: Shaft lookup by GUID.
        technical_rooms: List of Technikraum SpaceRecords.
        shaft_placeholder_demands: The SHAFT_FEED placeholder DemandRecords
            returned by ``build_unique_route_tasks``.

    Returns:
        Tuple of (per_service_demands, per_service_selections).
    """
    if not technical_rooms or not shaft_placeholder_demands:
        return [], {}

    technik_floor_indices: set[int] = {tr.floor_index for tr in technical_rooms}

    # ── UG shafts: shafts that appear as SHAFT_FEED route origins ────────────
    ug_shaft_guids: set[str] = {p.room_guid for p in shaft_placeholder_demands}
    ug_shafts: list[SpaceRecord] = [
        shafts_by_guid[g] for g in ug_shaft_guids if g in shafts_by_guid
    ]

    # ── Match every shaft in the building to its UG counterpart ──────────────
    upper_to_ug = _build_upper_to_ug_shaft_map(ug_shafts, list(shafts_by_guid.values()))

    # ── Build UG shaft → chosen technikraum + strategy from SHAFT_FEED ───────
    ug_to_tr: dict[str, str] = {}
    ug_to_strategy: dict[str, str] = {}
    for placeholder in shaft_placeholder_demands:
        sel = selections.get(placeholder.demand_id, {})
        tr_guid = sel.get("shaft_guid", "")
        strategy = sel.get("strategy", "Balanced")
        if tr_guid:
            ug_to_tr[placeholder.room_guid] = tr_guid
            ug_to_strategy[placeholder.room_guid] = strategy

    # ── Aggregate real room demands through the upper-floor shafts ────────────
    # key: (ug_shaft_guid, service)  value: accumulated value
    agg_value: dict[tuple[str, str], float] = defaultdict(float)
    agg_meta: dict[tuple[str, str], tuple[str, str, str]] = {}  # unit, media, hvac

    # A shaft→Technikraum route exists once per service in the visible/export
    # system.  The target Technikraum comes from the SHAFT_FEED placeholder,
    # but the route strategy should follow the selected room routes of the
    # same service.  This allows a service-filtered strategy change, e.g. HEI
    # only, without forcing LUE/SAN shaft-feed routes to the same strategy.
    agg_strategy_weight: dict[tuple[str, str, str], float] = defaultdict(float)

    for demand in demands:
        if demand.kind == "aggregated_shaft":
            continue  # skip synthetic demands

        room = rooms_by_guid.get(demand.room_guid)
        if room is None:
            continue
        if room.floor_index in technik_floor_indices:
            continue  # technikraum-floor rooms route directly, not through shafts

        sel = selections.get(demand.demand_id, {})
        chosen_shaft_guid = sel.get("shaft_guid", "")
        if not chosen_shaft_guid:
            continue

        ug_guid = upper_to_ug.get(chosen_shaft_guid)
        if ug_guid is None:
            continue  # no matching UG shaft
        if ug_guid not in ug_to_tr:
            continue  # UG shaft has no technikraum route selected

        key = (ug_guid, demand.service)
        agg_value[key] += demand.value

        selected_strategy = str(sel.get("strategy", "") or "").strip()
        if selected_strategy:
            # Use demand magnitude as weight.  If a demand has a zero value,
            # still count it so a selected strategy is not ignored entirely.
            agg_strategy_weight[(ug_guid, demand.service, selected_strategy)] += max(abs(float(demand.value)), 1.0)

        if key not in agg_meta:
            agg_meta[key] = (demand.unit, demand.media_type, demand.hvac_system_type)

    # ── Create per-service DemandRecords and matching selections ──────────────
    per_service_demands: list[DemandRecord] = []
    per_service_selections: dict[str, dict[str, str]] = {}

    for (ug_guid, service), value in agg_value.items():
        if value <= 0:
            continue

        tr_guid = ug_to_tr[ug_guid]
        strategy = _pick_service_strategy(
            ug_guid=ug_guid,
            service=service,
            strategy_weights=agg_strategy_weight,
            fallback=ug_to_strategy.get(ug_guid, "Balanced"),
        )
        unit, media_type, hvac = agg_meta[(ug_guid, service)]
        demand_id = f"__shaft__{ug_guid}__{tr_guid}__svc_{service}"

        per_service_demands.append(DemandRecord(
            demand_id=demand_id,
            room_guid=ug_guid,
            room_name=shafts_by_guid[ug_guid].label(),
            service=service,
            media_type=media_type,
            hvac_system_type=hvac,
            kind="aggregated_shaft",
            value=value,
            unit=unit,
        ))

        per_service_selections[demand_id] = {
            "shaft_guid": tr_guid,
            "strategy": strategy,
        }

    return per_service_demands, per_service_selections
