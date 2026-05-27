import * as THREE from "three";
import { DEFAULT_ROUTE_COLOR } from "./viewerStyles.js";

export function drawVariantRoutes(viewer, rows, activeKey, options = {}) {
  viewer._clearGroup(viewer.variantGroup);

  const successfulRows = (rows || []).filter((row) => {
    return row.success && Array.isArray(row.path_xyz) && row.path_xyz.length > 1;
  });

  const optionColor = options.optionColor || DEFAULT_ROUTE_COLOR;

  for (const row of successfulRows) {
    const key = `${row.shaft_guid}|${row.strategy}`;
    if (key === activeKey) {
      continue;
    }

    const line = viewer._buildLineFromXYZ(row.path_xyz, optionColor, 0.5);
    line.userData = { key };
    line.renderOrder = 996;
    viewer.variantGroup.add(line);
  }
}

export function drawSystemNetwork(viewer, routes, options = {}) {
  viewer._clearGroup(viewer.systemGroup);

  const serviceFilter = String(options.serviceFilter || "__all__").toUpperCase();
  const hiddenDemandIds = new Set(options.hiddenDemandIds || []);

  for (const route of routes || []) {
    const routeService = String(route?.service || "").toUpperCase();
    const shouldShowService = serviceFilter === "__ALL__" || serviceFilter === "__all__".toUpperCase() || !serviceFilter || routeService === serviceFilter;
    const pathXYZ = route?.path_xyz;

    if (!route?.success || !shouldShowService || hiddenDemandIds.has(route?.demand_id)) {
      continue;
    }

    if (!Array.isArray(pathXYZ) || pathXYZ.length < 2) {
      continue;
    }

    const line = viewer._buildLineFromXYZ(pathXYZ, viewer._getServiceRouteColor(routeService), 0.82);
    line.renderOrder = 995;
    line.userData = {
      demandId: route.demand_id || "",
      service: routeService,
    };
    viewer.systemGroup.add(line);
  }
}

export function drawSystemRoute(viewer, pathXYZ, color = "#00E676") {
  viewer._clearGroup(viewer.activeRouteGroup);

  if (!Array.isArray(pathXYZ) || pathXYZ.length < 2) {
    return;
  }

  const pipe = viewer._buildPipeFromXYZ(pathXYZ, color, 0.96, 0.12);
  pipe.renderOrder = 999;
  viewer.activeRouteGroup.add(pipe);
}

export function clearAllRoutes(viewer) {
  viewer._clearGroup(viewer.variantGroup);
  viewer._clearGroup(viewer.systemGroup);
  viewer._clearGroup(viewer.activeRouteGroup);
}

export function _transformPathPoint(viewer, xyz) {
  const x = xyz[0];
  const y = xyz[1];
  const z = xyz[2];

  if (viewer.routeTransformMode === "x_neg_z_y") {
    return new THREE.Vector3(x, -z, y);
  }

  if (viewer.routeTransformMode === "x_z_neg_y") {
    return new THREE.Vector3(x, z, -y);
  }

  if (viewer.routeTransformMode === "x_z_y") {
    return new THREE.Vector3(x, z, y);
  }

  if (viewer.routeTransformMode === "neg_x_z_neg_y") {
    return new THREE.Vector3(-x, z, -y);
  }

  return new THREE.Vector3(x, y, z);
}

export function _getServiceRouteColor(viewer, service) {
  const serviceKey = String(service || "").trim().toUpperCase();

  if (serviceKey === "HEI") {
    return "#FF9800";
  }

  if (serviceKey === "LUE") {
    return "#00BCD4";
  }

  if (serviceKey === "SAN") {
    return "#E91E63";
  }

  return "#0D47A1";
}

export function _buildLineFromXYZ(viewer, pathXYZ, color, opacity) {
  const points = viewer._buildRoutePoints(pathXYZ);

  if (points.length < 2) {
    return new THREE.Group();
  }

  const geometry = new THREE.BufferGeometry().setFromPoints(points);

  const material = new THREE.LineBasicMaterial({
    color,
    transparent: opacity < 1,
    opacity,
    depthTest: false,
  });

  return new THREE.Line(geometry, material);
}

export function _buildPipeFromXYZ(viewer, pathXYZ, color, opacity, radius = 0.12) {
  const points = viewer._buildRoutePoints(pathXYZ);

  if (points.length < 2) {
    return new THREE.Group();
  }

  const curve = new THREE.CatmullRomCurve3(points);
  const tubularSegments = Math.max(points.length * 10, 32);
  const geometry = new THREE.TubeGeometry(curve, tubularSegments, radius, 14, false);

  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: opacity < 1,
    opacity,
    depthWrite: false,
    depthTest: false,
  });

  return new THREE.Mesh(geometry, material);
}

export function _buildRoutePoints(viewer, pathXYZ) {
  const clippedPathXYZ = viewer._clipPathXYZToCurrentFloor(pathXYZ);
  const transformedPoints = [];

  for (const xyz of clippedPathXYZ || []) {
    const point = viewer._transformPathPoint(xyz);
    const previousPoint = transformedPoints[transformedPoints.length - 1];

    if (!previousPoint || previousPoint.distanceToSquared(point) > 0.000001) {
      transformedPoints.push(point);
    }
  }

  return transformedPoints;
}

export function _clipPathXYZToCurrentFloor(viewer, pathXYZ) {
  if (!Array.isArray(pathXYZ) || pathXYZ.length < 2) {
    return Array.isArray(pathXYZ) ? [...pathXYZ] : [];
  }

  const floorBounds = viewer._getCurrentFloorZBounds();
  if (!floorBounds) {
    return [...pathXYZ];
  }

  const epsilon = 0.01;
  const minZ = floorBounds.minZ - epsilon;
  const maxZ = floorBounds.maxZ + epsilon;
  const clipped = [];

  for (let index = 0; index < pathXYZ.length - 1; index += 1) {
    const startPoint = pathXYZ[index];
    const endPoint = pathXYZ[index + 1];
    const clippedSegment = viewer._clipSegmentToZBand(startPoint, endPoint, minZ, maxZ);

    if (!clippedSegment) {
      continue;
    }

    const [segmentStart, segmentEnd] = clippedSegment;
    viewer._pushUniqueXYZ(clipped, segmentStart);
    viewer._pushUniqueXYZ(clipped, segmentEnd);
  }

  return clipped;
}

export function _getCurrentFloorZBounds(viewer) {
  const hasFloorFilter = viewer.currentFloorName && viewer.currentFloorName !== "__all__";
  if (!hasFloorFilter) {
    return null;
  }

  const floor = viewer.floorDefinitions.find((candidate) => {
    return viewer._normalizeFloorName(candidate?.name) === viewer._normalizeFloorName(viewer.currentFloorName);
  });

  if (!floor) {
    return null;
  }

  const minZ = Number(floor?.z_min);
  const maxZ = Number(floor?.z_max);
  if (!Number.isFinite(minZ) || !Number.isFinite(maxZ)) {
    return null;
  }

  return {
    minZ: Math.min(minZ, maxZ),
    maxZ: Math.max(minZ, maxZ),
  };
}

export function _clipSegmentToZBand(viewer, startPoint, endPoint, minZ, maxZ) {
  const z0 = Number(startPoint?.[2]);
  const z1 = Number(endPoint?.[2]);

  if (!Number.isFinite(z0) || !Number.isFinite(z1)) {
    return null;
  }

  const isInside0 = z0 >= minZ && z0 <= maxZ;
  const isInside1 = z1 >= minZ && z1 <= maxZ;

  if (isInside0 && isInside1) {
    return [startPoint, endPoint];
  }

  if (z0 === z1) {
    return null;
  }

  const intersections = [];

  const addIntersectionAtZ = (targetZ) => {
    const t = (targetZ - z0) / (z1 - z0);
    if (t < 0 || t > 1) {
      return;
    }

    intersections.push({
      t,
      point: [
        startPoint[0] + (endPoint[0] - startPoint[0]) * t,
        startPoint[1] + (endPoint[1] - startPoint[1]) * t,
        targetZ,
      ],
    });
  };

  addIntersectionAtZ(minZ);
  addIntersectionAtZ(maxZ);
  intersections.sort((left, right) => left.t - right.t);

  if (isInside0 && intersections.length) {
    return [startPoint, intersections[0].point];
  }

  if (isInside1 && intersections.length) {
    return [intersections[intersections.length - 1].point, endPoint];
  }

  if (intersections.length >= 2) {
    return [intersections[0].point, intersections[intersections.length - 1].point];
  }

  return null;
}

export function _pushUniqueXYZ(viewer, target, xyz) {
  if (!Array.isArray(xyz) || xyz.length < 3) {
    return;
  }

  const previous = target[target.length - 1];
  if (
    previous
    && Math.abs(previous[0] - xyz[0]) < 0.000001
    && Math.abs(previous[1] - xyz[1]) < 0.000001
    && Math.abs(previous[2] - xyz[2]) < 0.000001
  ) {
    return;
  }

  target.push([xyz[0], xyz[1], xyz[2]]);
}

export function _clearGroup(viewer, group) {
  const children = [...group.children];

  for (const child of children) {
    group.remove(child);

    if (child.geometry) {
      child.geometry.dispose();
    }

    if (child.material) {
      if (Array.isArray(child.material)) {
        for (const material of child.material) {
          material.dispose();
        }
      } else {
        child.material.dispose();
      }
    }
  }
}
