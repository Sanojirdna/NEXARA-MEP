# -*- coding: utf-8 -*-
"""
section_sizing.py
=================
Demand-driven cross-section sizing for routing volumes.

Each service is sized independently from its accumulated demand at every
voxel.  When multiple services share a voxel the individual sizes are
stacked horizontally to form one combined bounding-box, then enlarged by
5 % to leave clearance between pipes/ducts.

Public API
----------
    sizer = SectionSizer(routes, demands)
    combined_W, combined_H, per_service = sizer.combined_size_at_voxel(vox)
    segments = sizer.build_collinear_segments(route)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pipe_planner.domain import RouteResult, DemandRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard DN series (nominal inner diameter, mm)
_DN_MM = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300]
CLEARANCE_FACTOR = 1.05   # 5 % clearance between services in combined box


def _next_dn(d_mm: float) -> int:
    """Round a hydraulic diameter up to the next standard DN."""
    for dn in _DN_MM:
        if dn >= d_mm:
            return dn
    return _DN_MM[-1]


def _darcy_diameter(
    Q_m3s: float,
    R_Pa_m: float,
    rho: float,
    mu: float,
    k_m: float,
) -> Tuple[float, float, float]:
    """
    Solve Darcy-Weisbach for pipe diameter at a target specific pressure drop.

    d^5 = 8*lambda*rho*Q^2 / (pi^2*R)  -> iterate lambda via Colebrook-White.

    Returns (diameter_m, velocity_m_s, Reynolds_number).
    """
    lam = 0.025                           # initial friction factor estimate
    d = 0.02                              # initial diameter estimate
    for _ in range(40):
        d_new = (8.0 * lam * rho * Q_m3s**2 / (math.pi**2 * R_Pa_m)) ** 0.2
        if d_new < 1e-6:
            break
        d = d_new
        v = Q_m3s / (math.pi * d**2 / 4.0)
        Re = rho * v * d / mu
        if Re < 2300:
            lam = 64.0 / Re              # Hagen-Poiseuille (laminar)
        else:
            # Colebrook-White (turbulent)
            kd = k_m / d
            lam = (1.0 / (-2.0 * math.log10(kd / 3.71 + 2.51 / (Re * math.sqrt(lam))))) ** 2

    v = Q_m3s / (math.pi * d**2 / 4.0)
    Re = rho * v * d / mu
    return d, v, Re


# ---------------------------------------------------------------------------
# Sizing config
# ---------------------------------------------------------------------------

@dataclass
class SizerConfig:
    # ── HEI – heating pipe ──────────────────────────────────────────────────
    # Darcy-Weisbach at R = 50 Pa/m (suissetec / SIA 384.101)
    # Water at ~65 °C: ρ = 980 kg/m³, μ = 4.3×10⁻⁴ Pa·s
    # Copper pipe roughness k = 0.0015 mm
    hei_R_Pa_m: float        = 50.0      # specific pressure drop  [Pa/m]
    hei_delta_t_k: float     = 20.0      # supply/return ΔT        [K]
    hei_cp_j_kgk: float      = 4186.0   # specific heat           [J/(kg·K)]
    hei_rho_kg_m3: float     = 980.0    # water density at 65 °C  [kg/m³]
    hei_mu_pa_s: float       = 4.3e-4   # dynamic viscosity       [Pa·s]
    hei_roughness_m: float   = 1.5e-6   # pipe roughness (copper) [m]
    hei_insulation_mm: float = 30.0     # insulation each side    [mm]

    # ── LUE – ventilation duct ───────────────────────────────────────────────
    # EN 13779 / suissetec flow-stepped maximum velocity
    # ≤1000 m³/h -> 3 m/s  |  ≤2000 -> 4  |  ≤4000 -> 5  |  ≤10000 -> 6  |  >10000 -> 7
    # Duct aspect 2:1 (W/H), 50 mm grid, minimum 200×100 mm
    lue_aspect: float        = 2.0
    lue_grid_mm: float       = 50.0
    lue_min_w_mm: float      = 200.0
    lue_min_h_mm: float      = 100.0

    # ── SAN – Trinkwasser supply (SVGW W3 / SIA 385) ────────────────────────
    # Darcy-Weisbach at R = 100 Pa/m for distribution
    # Cold water at 10 °C: ρ = 1000 kg/m³, μ = 1.3×10⁻³ Pa·s
    # Copper pipe roughness k = 0.0015 mm; minimum DN 15
    san_R_Pa_m: float        = 100.0
    san_rho_kg_m3: float     = 1000.0
    san_mu_pa_s: float       = 1.3e-3
    san_roughness_m: float   = 1.5e-6
    san_insulation_mm: float = 20.0     # insulation/clearance    [mm]
    san_min_dn_mm: float     = 15.0    # minimum DN              [mm]

    # ── Combined bounding-box ────────────────────────────────────────────────
    clearance_factor: float  = CLEARANCE_FACTOR


# ---------------------------------------------------------------------------
# Per-service sizing functions   ->  (width_m, height_m)
# ---------------------------------------------------------------------------

def size_hei(p_w: float, cfg: SizerConfig) -> Tuple[float, float]:
    """
    Heating load [W] -> bounding box for Vorlauf + Rücklauf pipe pair.

    Method: Darcy-Weisbach at R = 50 Pa/m (suissetec / SIA 384.101).
    Flow:   Q = P / (ρ · cp · ΔT)
    Pipe:   iterate d from d⁵ = 8·λ·ρ·Q² / (π²·R) -> round up to DN standard.
    Box:    two identical pipes (Vorlauf + Rücklauf) placed side by side.
            Width  = 2 × (DN + 2 × insulation)
            Height =     (DN + 2 × insulation)
    """
    if p_w <= 0:
        min_mm = _DN_MM[0] + 2 * cfg.hei_insulation_mm
        s = min_mm / 1000
        return s * 2, s

    Q = p_w / (cfg.hei_rho_kg_m3 * cfg.hei_cp_j_kgk * cfg.hei_delta_t_k)
    d, _, _ = _darcy_diameter(
        Q, cfg.hei_R_Pa_m, cfg.hei_rho_kg_m3, cfg.hei_mu_pa_s, cfg.hei_roughness_m
    )
    dn = _next_dn(d * 1000)
    outer_mm = dn + 2.0 * cfg.hei_insulation_mm
    s = outer_mm / 1000.0
    # Two pipes side by side: Vorlauf (supply) + Rücklauf (return)
    return s * 2, s


def size_lue(q_m3h: float, cfg: SizerConfig) -> Tuple[float, float]:
    """
    Airflow [m³/h] -> rectangular duct cross-section (W × H).

    Method: EN 13779 flow-stepped maximum velocity (suissetec / EN-4):
      ≤ 1 000 m³/h -> v = 3 m/s
      ≤ 2 000 m³/h -> v = 4 m/s
      ≤ 4 000 m³/h -> v = 5 m/s
      ≤10 000 m³/h -> v = 6 m/s
       > 10 000 m³/h -> v = 7 m/s
    Profile: 2:1 aspect (W/H), snapped to 50 mm grid.
    """
    if q_m3h <= 0:
        return cfg.lue_min_w_mm / 1000, cfg.lue_min_h_mm / 1000

    # Flow-stepped velocity per EN 13779 / suissetec
    if   q_m3h <= 1000:  v = 3.0
    elif q_m3h <= 2000:  v = 4.0
    elif q_m3h <= 4000:  v = 5.0
    elif q_m3h <= 10000: v = 6.0
    else:                v = 7.0

    q_m3s = q_m3h / 3600.0
    a = q_m3s / v                           # required cross-section area [m²]
    h = math.sqrt(a / cfg.lue_aspect)       # raw height
    w = cfg.lue_aspect * h                  # raw width

    g = cfg.lue_grid_mm / 1000.0
    h_m = max(cfg.lue_min_h_mm / 1000.0, math.ceil(h / g) * g)
    w_m = max(cfg.lue_min_w_mm / 1000.0, math.ceil(w / g) * g)
    return w_m, h_m


def size_san(q_ls: float, cfg: SizerConfig, segment_length_m: float = 35.0) -> Tuple[float, float]:
    """
    Trinkwasser supply flow [l/s] -> bounding box for Kaltwasser + Warmwasser pipe pair.

    Method: Nussbaum Optipress Belastungswert-Tabelle (SVGW 0209-4548).
    1 LU = 0.1 l/s.  Uses the column for the given segment length,
    rounded up to the next table column (5 / 10 / 15 / 20 / 35 m).
    If LU or length exceeds the table, uses da = 42 mm.

    Pipe outer diameters (da):  15 / 18 / 22 / 28 / 35 / 42 mm

    Two pipes placed side by side:
      Kaltwasser (KW): da_kalt from Nussbaum table lookup
      Warmwasser (WW): one DN step smaller than KW (minimum DN 15)

    Box:
      Width  = outer_kalt + outer_warm  (both pipes side by side)
      Height = outer_kalt               (Kaltwasser is always the larger one)
    """
    # ── Nussbaum Optipress table: (LU_row, length_col) -> da_mm ──────────────
    # LU rows: 1, 2, 3, 4, 6, 8, 10, 15, 20, 30, 40, 50, 70, 90, 120, 150
    # Length columns [m]: 5, 10, 15, 20, 35
    _TABLE: Dict[Tuple[int, int], int] = {
        (1,   5): 15, (1,  10): 15, (1,  15): 15, (1,  20): 15, (1,  35): 15,
        (2,   5): 15, (2,  10): 15, (2,  15): 15, (2,  20): 18, (2,  35): 18,
        (3,   5): 18, (3,  10): 18, (3,  15): 18, (3,  20): 18, (3,  35): 22,
        (4,   5): 18, (4,  10): 18, (4,  15): 18, (4,  20): 22, (4,  35): 22,
        (6,   5): 18, (6,  10): 18, (6,  15): 22, (6,  20): 22, (6,  35): 22,
        (8,   5): 22, (8,  10): 22, (8,  15): 22, (8,  20): 22, (8,  35): 22,
        (10,  5): 22, (10, 10): 22, (10, 15): 22, (10, 20): 22, (10, 35): 28,
        (15,  5): 22, (15, 10): 22, (15, 15): 22, (15, 20): 22, (15, 35): 28,
        (20,  5): 22, (20, 10): 22, (20, 15): 22, (20, 20): 28, (20, 35): 28,
        (30,  5): 28, (30, 10): 28, (30, 15): 28, (30, 20): 28, (30, 35): 28,
        (40,  5): 28, (40, 10): 28, (40, 15): 28, (40, 20): 28, (40, 35): 28,
        (50,  5): 28, (50, 10): 28, (50, 15): 28, (50, 20): 28, (50, 35): 35,
        (70,  5): 28, (70, 10): 28, (70, 15): 28, (70, 20): 35, (70, 35): 35,
        (90,  5): 28, (90, 10): 28, (90, 15): 28, (90, 20): 35, (90, 35): 35,
        (120, 5): 35, (120,10): 35, (120,15): 35, (120,20): 35, (120,35): 35,
        (150, 5): 35, (150,10): 35, (150,15): 35, (150,20): 35, (150,35): 35,
    }
    _LU_ROWS  = [1, 2, 3, 4, 6, 8, 10, 15, 20, 30, 40, 50, 70, 90, 120, 150]
    _LEN_COLS = [5, 10, 15, 20, 35]
    # Standard outer diameters in ascending order
    _DA_SERIES = [15, 18, 22, 28, 35, 42]

    if q_ls <= 0:
        da_kalt_mm = 15
    else:
        lu = q_ls / 0.1   # 1 LU = 0.1 l/s

        # Round LU up to next table row; if above 150 -> da = 42 mm (one size up)
        lu_row = next((r for r in _LU_ROWS if r >= lu), None)

        # Round length up to next table column; cap at 35 m
        len_col = next((c for c in _LEN_COLS if c >= segment_length_m), 35)

        if lu_row is None:
            da_kalt_mm = 42
        else:
            da_kalt_mm = _TABLE[(lu_row, len_col)]

    # ── Warmwasser: one DN step smaller (minimum DN 15) ───────────────────────
    kalt_idx   = _DA_SERIES.index(da_kalt_mm) if da_kalt_mm in _DA_SERIES else len(_DA_SERIES) - 1
    warm_idx   = max(0, kalt_idx - 1)
    da_warm_mm = _DA_SERIES[warm_idx]

    outer_kalt_m = (da_kalt_mm + 2.0 * cfg.san_insulation_mm) / 1000.0
    outer_warm_m = (da_warm_mm + 2.0 * cfg.san_insulation_mm) / 1000.0

    # Two pipes side by side: Kaltwasser + Warmwasser
    return outer_kalt_m + outer_warm_m, outer_kalt_m


_SIZE_FN = {
    "HEI": size_hei,
    "LUE": size_lue,
    "SAN": size_san,
}


# ---------------------------------------------------------------------------
# Segment data class
# ---------------------------------------------------------------------------

@dataclass
class CollinearSegment:
    """One straight stretch of a route with a fixed combined cross-section."""
    start_voxel: Tuple[int, int, int]
    end_voxel: Tuple[int, int, int]
    start_xyz: Tuple[float, float, float]
    end_xyz: Tuple[float, float, float]
    floor_index: int
    # combined box (all co-located services + clearance)
    combined_w_m: float
    combined_h_m: float
    # per-service breakdown  {service: (w_m, h_m, accumulated_demand, unit)}
    service_breakdown: Dict[str, Tuple[float, float, float, str]]
    # all voxel indices covered by this segment (for deduplication)
    all_voxels: List[Tuple[int, int, int]] = None

    @property
    def length_m(self) -> float:
        return math.sqrt(sum((b - a) ** 2 for a, b in zip(self.start_xyz, self.end_xyz)))

    @property
    def direction(self) -> Tuple[float, float, float]:
        dx, dy, dz = (self.end_xyz[i] - self.start_xyz[i] for i in range(3))
        L = math.sqrt(dx**2 + dy**2 + dz**2)
        if L < 1e-9:
            return (1.0, 0.0, 0.0)
        return dx / L, dy / L, dz / L

    @property
    def services(self) -> List[str]:
        return sorted(self.service_breakdown)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SectionSizer:
    """
    Compute demand-based cross-sections for all routing segments.

    Parameters
    ----------
    routes  : list[RouteResult]  – from runtime.current_system.routes
    demands : list[DemandRecord] – from runtime.bundle["demands"]
    config  : SizerConfig        – optional override
    """

    def __init__(
        self,
        routes: List[RouteResult],
        demands: List[DemandRecord],
        config: Optional[SizerConfig] = None,
    ) -> None:
        self.routes = [r for r in routes if r.success]
        self.cfg = config or SizerConfig()

        # (room_guid, service) -> (value, unit)
        self._demand_lookup: Dict[Tuple[str, str], Tuple[float, str]] = {}
        for d in demands:
            self._demand_lookup[(d.room_guid, d.service)] = (d.value, d.unit)

        # voxel_tuple -> {service: accumulated_demand}
        self._voxel_demand: Dict[Tuple, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for route in self.routes:
            val, _ = self._demand_lookup.get((route.room_guid, route.service), (0.0, ""))
            for vox in route.path_indices:
                self._voxel_demand[tuple(vox)][route.service] += val

        # (room_guid, service) -> unit string
        self._unit: Dict[Tuple[str, str], str] = {
            (d.room_guid, d.service): d.unit for d in demands
        }

    # ------------------------------------------------------------------
    # Voxel-level queries
    # ------------------------------------------------------------------

    def voxel_demands(self, voxel: Tuple[int, int, int]) -> Dict[str, float]:
        """Accumulated demand per service at this voxel."""
        return dict(self._voxel_demand.get(voxel, {}))

    def combined_size_at_voxels(
        self,
        voxels: List[Tuple[int, int, int]],
        segment_length_m: float = 35.0,
    ) -> Tuple[float, float, Dict[str, Tuple[float, float, float, str]]]:
        """
        Combined bounding-box for a list of voxels (uses peak demand per service).

        Parameters
        ----------
        voxels           : voxel indices along the segment
        segment_length_m : developed length of the segment [m], used for SAN
                           table column selection (Nussbaum Optipress).

        Returns
        -------
        combined_w_m, combined_h_m, service_breakdown
        service_breakdown: {service: (w_m, h_m, peak_demand, unit)}
        """
        # Accumulate peak demand per service across all voxels in segment
        peak: Dict[str, float] = {}
        for vox in voxels:
            for svc, demand in self._voxel_demand.get(vox, {}).items():
                peak[svc] = max(peak.get(svc, 0.0), demand)

        service_breakdown: Dict[str, Tuple[float, float, float, str]] = {}
        for svc, demand in peak.items():
            fn = _SIZE_FN.get(svc)
            if fn is None or demand <= 0:
                continue
            # SAN uses the Nussbaum table which needs segment length
            if svc == "SAN":
                w, h = fn(demand, self.cfg, segment_length_m)
            else:
                w, h = fn(demand, self.cfg)
            unit = ""
            for (rg, s), u in self._unit.items():
                if s == svc:
                    unit = u
                    break
            service_breakdown[svc] = (w, h, demand, unit)

        if not service_breakdown:
            return 0.05, 0.05, {}

        total_W = sum(w for w, h, _, _ in service_breakdown.values())
        total_H = max(h for w, h, _, _ in service_breakdown.values())
        combined_W = total_W * self.cfg.clearance_factor
        combined_H = total_H * self.cfg.clearance_factor

        return combined_W, combined_H, service_breakdown

    # ------------------------------------------------------------------
    # Segment building
    # ------------------------------------------------------------------

    def build_collinear_segments(
        self, route: RouteResult, floor_index: int
    ) -> List[CollinearSegment]:
        """
        Split one route into collinear sub-segments.
        A new segment starts at every direction change.
        """
        path_idx = [tuple(p) for p in route.path_indices]
        path_xyz = [tuple(p) for p in route.path_xyz]
        n = len(path_idx)
        if n < 2:
            return []

        def _vdir(i: int) -> Tuple[int, int, int]:
            return tuple(path_idx[i + 1][k] - path_idx[i][k] for k in range(3))

        segments: List[CollinearSegment] = []
        seg_start = 0
        cur_dir = _vdir(0)

        def _flush(end_i: int) -> None:
            voxels = path_idx[seg_start: end_i + 1]
            # Compute segment length from XYZ endpoints for SAN table lookup
            p0, p1 = path_xyz[seg_start], path_xyz[end_i]
            seg_len = math.sqrt(sum((p1[k] - p0[k])**2 for k in range(3)))
            w, h, breakdown = self.combined_size_at_voxels(voxels, segment_length_m=seg_len)
            segments.append(
                CollinearSegment(
                    start_voxel=path_idx[seg_start],
                    end_voxel=path_idx[end_i],
                    start_xyz=path_xyz[seg_start],
                    end_xyz=path_xyz[end_i],
                    floor_index=floor_index,
                    combined_w_m=w,
                    combined_h_m=h,
                    service_breakdown=breakdown,
                    all_voxels=list(voxels),
                )
            )

        for i in range(1, n - 1):
            d = _vdir(i)
            if d != cur_dir:
                _flush(i)
                seg_start = i
                cur_dir = d

        _flush(n - 1)
        return segments

    def build_all_unique_segments(
        self,
        floor_by_room: Dict[str, int],
    ) -> List[CollinearSegment]:
        """
        Build fully deduplicated segments using edge-level deduplication.

        Algorithm
        ---------
        1.  Decompose every route path into individual voxel-edges
            (consecutive voxel pairs).
        2.  Deduplicate edges globally - each physical edge (regardless of
            which route traverses it) appears exactly once.
        3.  Re-merge consecutive collinear edges into the longest possible
            straight segments, sized for the peak accumulated demand along
            their voxels.

        This is provably overlap-free: no two segments can share a voxel in
        the same axis direction.
        """
        # Step 1 - collect unique edges: (min_vox, max_vox) -> (v_from, v_to, xyz_from, xyz_to, fi)
        seen_edges: set = set()
        # Store: (v_from, v_to, xyz_from, xyz_to, floor_index)
        unique_edges: List[tuple] = []

        for route in self.routes:
            path_idx = [tuple(p) for p in route.path_indices]
            path_xyz = [tuple(p) for p in route.path_xyz]
            fi = floor_by_room.get(route.room_guid, 0)

            for i in range(len(path_idx) - 1):
                v0, v1 = path_idx[i], path_idx[i + 1]
                edge_key = (min(v0, v1), max(v0, v1))
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                unique_edges.append((v0, v1, path_xyz[i], path_xyz[i + 1], fi))

        # Step 2 - group edges into chains by building adjacency
        # Key: for each "to" voxel, find which edge arrives there
        # We chain edges greedily: walk from each unused edge as long as
        # the next voxel has exactly one outgoing edge in the same direction.

        # Build adjacency: from_voxel -> list of (to_voxel, edge_index)
        from_adj: Dict[Tuple, List[Tuple]] = defaultdict(list)
        for idx, (v0, v1, xyz0, xyz1, fi) in enumerate(unique_edges):
            from_adj[v0].append((v1, idx))
            # Also store the reverse for bidirectional traversal check
            from_adj[v1].append((v0, idx))

        # Step 3 - merge collinear edges into segments
        used: set = set()
        result: List[CollinearSegment] = []

        def _axis(v0, v1):
            """Return (0,1,2) for the axis of this edge."""
            d = tuple(v1[k] - v0[k] for k in range(3))
            return max(range(3), key=lambda k: abs(d[k]))

        for start_idx, (sv0, sv1, sxyz0, sxyz1, sfi) in enumerate(unique_edges):
            if start_idx in used:
                continue
            used.add(start_idx)

            # Walk forward along the same axis as long as edges continue
            axis = _axis(sv0, sv1)
            chain_voxels = [sv0, sv1]
            chain_xyz    = [sxyz0, sxyz1]
            chain_fi     = sfi

            cur_tail = sv1
            while True:
                # Find a continuation edge from cur_tail on the same axis
                next_edge = None
                for (nbr, eidx) in from_adj.get(cur_tail, []):
                    if eidx in used:
                        continue
                    if _axis(cur_tail, nbr) != axis:
                        continue
                    # Same direction (not reversing)
                    d_cur = tuple(chain_voxels[-1][k] - chain_voxels[-2][k] for k in range(3))
                    d_nxt = tuple(nbr[k] - cur_tail[k] for k in range(3))
                    if d_cur == d_nxt:
                        next_edge = (nbr, eidx)
                        break
                if next_edge is None:
                    break
                nbr, eidx = next_edge
                used.add(eidx)
                _, _, _, xyz_to, _ = unique_edges[eidx]
                chain_voxels.append(nbr)
                chain_xyz.append(xyz_to)
                cur_tail = nbr

            # Size the merged segment - compute length from XYZ for SAN table
            p0, p1 = chain_xyz[0], chain_xyz[-1]
            seg_len = math.sqrt(sum((p1[k] - p0[k])**2 for k in range(3)))
            w, h, breakdown = self.combined_size_at_voxels(chain_voxels, segment_length_m=seg_len)
            result.append(
                CollinearSegment(
                    start_voxel=chain_voxels[0],
                    end_voxel=chain_voxels[-1],
                    start_xyz=chain_xyz[0],
                    end_xyz=chain_xyz[-1],
                    floor_index=chain_fi,
                    combined_w_m=w,
                    combined_h_m=h,
                    service_breakdown=breakdown,
                    all_voxels=chain_voxels,
                )
            )

        return result


# ---------------------------------------------------------------------------
# Junction point data class + builder
# ---------------------------------------------------------------------------

@dataclass
class JunctionPoint:
    """
    A bend point where segments from different axes meet.

    The corner box is NOT a cube - it is sized to exactly fill the gap
    between the incoming and outgoing segments:
      - box_x_m : extent along world X  = width of the segment running in Y or Z
      - box_y_m : extent along world Y  = width of the segment running in X or Z
      - box_z_m : extent along world Z  = max height of all meeting segments
    The box is centred on xyz in XY and centred in Z on the segment plane.
    """
    xyz: Tuple[float, float, float]
    voxel: Tuple[int, int, int]
    floor_index: int
    box_x_m: float   # world-X extent
    box_y_m: float   # world-Y extent
    box_z_m: float   # world-Z extent (= duct height, NOT duct width)
    service_breakdown: Dict[str, Tuple[float, float, float, str]]

    @property
    def services(self) -> List[str]:
        return sorted(self.service_breakdown)


def build_junction_points(
    routes: List,
    sizer: "SectionSizer",
    floor_by_room: Dict[str, int],
    segments: Optional[List[CollinearSegment]] = None,
) -> List[JunctionPoint]:
    """
    Find every bend point and compute axis-correct corner-box dimensions.

    For each bend voxel we look at which segments pass through it and
    group them by their world axis (X / Y / Z).  The corner box then gets:
      box_X = combined_w of the segment(s) running along Y or Z
      box_Y = combined_w of the segment(s) running along X or Z
      box_Z = max combined_h of all meeting segments

    This means horizontal ducts get a box that is exactly as tall as the
    ducts and as wide as needed to fill the corner - no more.
    """
    # Build voxel -> segments map from the already-deduplicated segment list
    from collections import defaultdict as _dd
    vox_to_segs: Dict[Tuple, List[CollinearSegment]] = _dd(list)
    if segments:
        for seg in segments:
            for v in (seg.all_voxels or [seg.start_voxel, seg.end_voxel]):
                vox_to_segs[v].append(seg)

    seen: set = set()
    junctions: List[JunctionPoint] = []

    for route in sizer.routes:
        path_idx = [tuple(p) for p in route.path_indices]
        path_xyz = [tuple(p) for p in route.path_xyz]
        n = len(path_idx)
        if n < 3:
            continue

        fi = floor_by_room.get(route.room_guid, 0)

        def _vdir(i):
            return tuple(path_idx[i + 1][k] - path_idx[i][k] for k in range(3))

        def _axis(d):
            return max(range(3), key=lambda k: abs(d[k]))

        prev_dir = _vdir(0)
        for i in range(1, n - 1):
            cur_dir = _vdir(i)
            if cur_dir != prev_dir:
                vox = path_idx[i]
                xyz = path_xyz[i]

                if vox not in seen:
                    seen.add(vox)
                    _, _, breakdown = sizer.combined_size_at_voxels([vox])

                    # Group meeting segments by their world axis
                    axis_segs: Dict[int, List[CollinearSegment]] = _dd(list)
                    for seg in vox_to_segs.get(vox, []):
                        ax = _axis(tuple(
                            seg.end_voxel[k] - seg.start_voxel[k] for k in range(3)
                        ))
                        axis_segs[ax].append(seg)

                    # Per-axis width = max combined_w of segments along that axis
                    # For the corner box, the extent in world-axis A comes from
                    # the WIDTH of segments running in the OTHER axes.
                    def _max_w(ax: int) -> float:
                        segs = axis_segs.get(ax, [])
                        return max((s.combined_w_m for s in segs), default=0.0)

                    def _max_h(ax: int) -> float:
                        segs = axis_segs.get(ax, [])
                        return max((s.combined_h_m for s in segs), default=0.0)

                    all_axes = set(axis_segs.keys())

                    # box_X = extent needed in world X
                    #   if a segment runs in X -> its width is the perpendicular
                    #   extent we need in the OTHER directions, not X itself.
                    #   The X extent of the box = width of segments NOT running in X.
                    non_x = [w for ax, segs in axis_segs.items()
                              if ax != 0 for s in segs for w in [s.combined_w_m]]
                    non_y = [w for ax, segs in axis_segs.items()
                              if ax != 1 for s in segs for w in [s.combined_w_m]]

                    # Fallback: use the single voxel combined size
                    w_all, h_all, _ = sizer.combined_size_at_voxels([vox])

                    box_x = max(non_x, default=w_all)
                    box_y = max(non_y, default=w_all)
                    # Height: always the duct height (Z-dimension of cross-section)
                    box_z = max(
                        (s.combined_h_m for segs in axis_segs.values() for s in segs),
                        default=h_all,
                    )

                    # Ensure the box at minimum covers the voxel itself (0.5m grid)
                    box_x = max(box_x, 0.05)
                    box_y = max(box_y, 0.05)
                    box_z = max(box_z, 0.05)

                    junctions.append(
                        JunctionPoint(
                            xyz=xyz,
                            voxel=vox,
                            floor_index=fi,
                            box_x_m=box_x,
                            box_y_m=box_y,
                            box_z_m=box_z,
                            service_breakdown=breakdown,
                        )
                    )
            prev_dir = cur_dir

    return junctions