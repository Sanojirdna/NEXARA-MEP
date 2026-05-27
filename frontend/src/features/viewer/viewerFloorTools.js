import {
  ROOM_STYLE,
  SHAFT_STYLE,
  CORRIDOR_STYLE,
  SELECTED_STYLE,
} from "./viewerStyles.js";

export function setFloorDefinitions(viewer, floors = []) {
  viewer.floorDefinitions = [...(floors || [])].sort((left, right) => {
    return Number(left?.index ?? 0) - Number(right?.index ?? 0);
  });
  viewer.floorSpaceModelIdMapByName.clear();
  viewer.spatialFloorSpaceModelIdMapByName.clear();
  viewer._rebuildFloorLevelMap();
  viewer._updateRoomLabelVisibility();
  viewer._updateRoomCenterVisibility();
}

export async function showSpacesOnly(viewer) {
  viewer.currentVisibilityMode = "spaces";
  await viewer._applyVisibilityState();
}

export async function showFullIfc(viewer) {
  viewer.currentVisibilityMode = "full";
  await viewer._applyVisibilityState();
}

export async function isolateFloor(viewer, floorName) {
  viewer.currentFloorName = floorName || "__all__";
  await viewer._applyVisibilityState();
  viewer._updateRoomLabelVisibility();
  viewer._updateRoomCenterVisibility();
}

export async function resetVisibility(viewer) {
  viewer.currentFloorName = "__all__";
  viewer.hiddenModelIdMaps = [];
  viewer.hiddenBrowserNodeMaps.clear();
  viewer.currentVisibilityMode = "full";
  await viewer._applyVisibilityState();
  viewer._updateRoomLabelVisibility();
  viewer._updateRoomCenterVisibility();
}

export async function _applyVisibilityState(viewer) {
  await viewer.hider.set(true);

  let visibleMap = null;
  const hasFloorFilter = viewer.currentFloorName && viewer.currentFloorName !== "__all__";

  if (hasFloorFilter) {
    visibleMap = await viewer._getFloorSpaceModelIdMap(viewer.currentFloorName);
  } else if (viewer.currentVisibilityMode === "spaces") {
    visibleMap = viewer._cloneModelIdMap(viewer.spaceModelIdMap);
  }

  if (visibleMap) {
    await viewer.hider.isolate(visibleMap);
  }

  for (const hiddenMap of viewer.hiddenModelIdMaps) {
    await viewer.hider.set(false, hiddenMap);
  }

  for (const [, hiddenMap] of viewer.hiddenBrowserNodeMaps) {
    await viewer.hider.set(false, hiddenMap);
  }

  await viewer._refreshVisualStyles();
  viewer._updateRoomLabelVisibility();
}

export async function _refreshVisualStyles(viewer) {
  await viewer.fragments.resetHighlight();

  const visibleSpacesMap = await viewer._getVisibleSpaceModelIdMap();
  if (visibleSpacesMap) {
    const visibleRoomMap = viewer._intersectModelIdMaps(visibleSpacesMap, viewer.roomModelIdMap);
    const visibleShaftMap = viewer._intersectModelIdMaps(visibleSpacesMap, viewer.shaftModelIdMap);
    const visibleCorridorMap = viewer._intersectModelIdMaps(visibleSpacesMap, viewer.corridorModelIdMap);

    if (visibleCorridorMap) {
      await viewer.fragments.highlight(CORRIDOR_STYLE, visibleCorridorMap);
    }

    if (visibleRoomMap) {
      await viewer.fragments.highlight(ROOM_STYLE, visibleRoomMap);
    }

    if (visibleShaftMap) {
      await viewer.fragments.highlight(SHAFT_STYLE, visibleShaftMap);
    }

    if (!visibleRoomMap && !visibleShaftMap && !visibleCorridorMap) {
      await viewer.fragments.highlight(ROOM_STYLE, visibleSpacesMap);
    }
  }

  if (viewer.selectedModelIdMap) {
    await viewer.fragments.highlight(SELECTED_STYLE, viewer.selectedModelIdMap);
  }
}

export async function _getVisibleSpaceModelIdMap(viewer) {
  let visibleSpaces = viewer._cloneModelIdMap(viewer.spaceModelIdMap);

  if (!visibleSpaces) {
    return null;
  }

  if (viewer.currentFloorName && viewer.currentFloorName !== "__all__") {
    const floorMap = await viewer._getFloorSpaceModelIdMap(viewer.currentFloorName);
    visibleSpaces = viewer._intersectModelIdMaps(visibleSpaces, floorMap);
  }

  for (const hiddenMap of viewer.hiddenModelIdMaps) {
    visibleSpaces = viewer._subtractModelIdMap(visibleSpaces, hiddenMap);
  }

  for (const [, hiddenMap] of viewer.hiddenBrowserNodeMaps) {
    visibleSpaces = viewer._subtractModelIdMap(visibleSpaces, hiddenMap);
  }

  return visibleSpaces;
}

export async function _buildSpaceModelIdMap(viewer) {
  const modelIdMap = {};

  for (const [, model] of viewer.fragments.list) {
    const items = await model.getItemsOfCategories([/^IFCSPACE$/]);
    const localIds = Object.values(items || {}).flat();
    modelIdMap[model.modelId] = new Set(localIds);
  }

  viewer.spaceModelIdMap = modelIdMap;
  viewer.roomModelIdMap = null;
  viewer.shaftModelIdMap = null;
  viewer.corridorModelIdMap = viewer._cloneModelIdMap(modelIdMap);
}

export async function _syncSpaceModelIdMapFromRooms(viewer) {
  if (!viewer.fragments) {
    return;
  }

  const roomGuids = viewer.roomRecords
    .map((room) => room?.guid)
    .filter((guid) => Boolean(guid));

  const shaftGuids = viewer.shaftRecords
    .map((shaft) => shaft?.guid)
    .filter((guid) => Boolean(guid));

  viewer.roomModelIdMap = roomGuids.length
    ? await viewer.fragments.guidsToModelIdMap(roomGuids)
    : null;

  viewer.shaftModelIdMap = shaftGuids.length
    ? await viewer.fragments.guidsToModelIdMap(shaftGuids)
    : null;

  const knownSpaceMap = viewer._unionModelIdMaps(viewer.roomModelIdMap, viewer.shaftModelIdMap);
  if (knownSpaceMap) {
    viewer.spaceModelIdMap = viewer._unionModelIdMaps(viewer.spaceModelIdMap, knownSpaceMap);
    viewer.corridorModelIdMap = viewer._subtractModelIdMap(viewer.spaceModelIdMap, knownSpaceMap);
    return;
  }

  viewer.corridorModelIdMap = viewer._cloneModelIdMap(viewer.spaceModelIdMap);
}

export async function _getFloorSpaceModelIdMap(viewer, floorName) {
  if (!floorName || floorName === "__all__") {
    return viewer._cloneModelIdMap(viewer.spaceModelIdMap);
  }

  if (viewer.floorSpaceModelIdMapByName.has(floorName)) {
    return viewer._cloneModelIdMap(viewer.floorSpaceModelIdMapByName.get(floorName));
  }

  const spatialFloorMap = viewer.spatialFloorSpaceModelIdMapByName.has(floorName)
    ? viewer._cloneModelIdMap(viewer.spatialFloorSpaceModelIdMapByName.get(floorName))
    : null;

  const levelMap = await viewer._getFloorModelIdMap(floorName);
  const levelSpaceMap = viewer._intersectModelIdMaps(viewer.spaceModelIdMap, levelMap);

  let knownMap = null;
  const floorIndex = viewer._getFloorIndexForName(floorName);
  if (floorIndex !== null) {
    const roomGuids = viewer.roomRecords
      .filter((room) => Number(room?.floor_index) === Number(floorIndex))
      .map((room) => room?.guid)
      .filter((guid) => Boolean(guid));

    const shaftGuids = viewer.shaftRecords
      .filter((shaft) => Number(shaft?.floor_index) === Number(floorIndex))
      .map((shaft) => shaft?.guid)
      .filter((guid) => Boolean(guid));

    const knownGuids = [...roomGuids, ...shaftGuids];
    if (knownGuids.length) {
      const floorKnownMap = await viewer.fragments.guidsToModelIdMap(knownGuids);
      if (floorKnownMap && Object.keys(floorKnownMap).length) {
        knownMap = floorKnownMap;
      }
    }
  }

  let mergedFloorMap = viewer._unionModelIdMaps(spatialFloorMap, levelSpaceMap);
  mergedFloorMap = viewer._unionModelIdMaps(mergedFloorMap, knownMap) || mergedFloorMap || knownMap || null;

  if (mergedFloorMap) {
    viewer.floorSpaceModelIdMapByName.set(floorName, viewer._cloneModelIdMap(mergedFloorMap));
    return viewer._cloneModelIdMap(mergedFloorMap);
  }

  return null;
}

export async function _buildSpatialFloorSpaceModelIdMaps(viewer) {
  viewer.spatialFloorSpaceModelIdMapByName.clear();

  for (const [, model] of viewer.fragments.list) {
    const spatialTree = await model.getSpatialStructure();
    if (!spatialTree) {
      continue;
    }

    const spatialIds = [];
    viewer._collectSpatialIds(spatialTree, spatialIds);

    const itemDataList = spatialIds.length
      ? await model.getItemsData(spatialIds, { attributesDefault: true })
      : [];
    const itemDataMap = new Map();

    for (const item of itemDataList) {
      const localId = viewer._getLocalId(item);
      if (localId !== null) {
        itemDataMap.set(localId, item);
      }
    }

    viewer._collectStoreySpaceIds(model.modelId, spatialTree, itemDataMap, "");
  }
}

export function _collectStoreySpaceIds(viewer, modelId, spatialNode, itemDataMap, activeFloorName) {
  if (!spatialNode) {
    return;
  }

  const localId = Number.isInteger(spatialNode?.localId) ? spatialNode.localId : null;
  const itemData = localId === null ? null : itemDataMap.get(localId) || null;
  const category = String(viewer._extractCategory(itemData) || spatialNode?.category || "").toUpperCase();

  let nextFloorName = activeFloorName;
  if (category.includes("BUILDINGSTOREY")) {
    const storeyName = viewer._getSpatialNodeName(itemData, localId);
    nextFloorName = viewer._resolveFloorNameFromStoreyName(storeyName);
  }

  if (nextFloorName && category.includes("SPACE") && localId !== null) {
    const floorMap = viewer.spatialFloorSpaceModelIdMapByName.get(nextFloorName) || {};
    if (!floorMap[modelId]) {
      floorMap[modelId] = new Set();
    }
    floorMap[modelId].add(localId);
    viewer.spatialFloorSpaceModelIdMapByName.set(nextFloorName, floorMap);
  }

  for (const child of spatialNode.children || []) {
    viewer._collectStoreySpaceIds(modelId, child, itemDataMap, nextFloorName);
  }
}

export function _resolveFloorNameFromStoreyName(viewer, storeyName) {
  const normalizedStoreyName = viewer._normalizeFloorName(storeyName);
  if (!normalizedStoreyName) {
    return "";
  }

  for (const floor of viewer.floorDefinitions) {
    const floorName = String(floor?.name || "");
    if (!floorName) {
      continue;
    }

    if (viewer._normalizeFloorName(floorName) === normalizedStoreyName) {
      return floorName;
    }
  }

  for (const [floorName, levelName] of viewer.levelNameByFloorKey.entries()) {
    if (viewer._normalizeFloorName(levelName) === normalizedStoreyName) {
      return floorName;
    }
  }

  return "";
}

export async function _getFloorModelIdMap(viewer, floorName) {
  const levelClassification = viewer.classifier.list.get("Levels");
  if (!levelClassification) {
    return null;
  }

  const resolvedLevelName = viewer._resolveLevelNameForFloor(floorName);
  const groupData = levelClassification.get(resolvedLevelName);

  if (!groupData) {
    return null;
  }

  return viewer._cloneModelIdMap(await groupData.get());
}

export function _captureLevelNames(viewer) {
  const levelClassification = viewer.classifier?.list?.get("Levels");
  if (!levelClassification || typeof levelClassification.keys !== "function") {
    viewer.levelNamesInOrder = [];
    return;
  }

  viewer.levelNamesInOrder = Array.from(levelClassification.keys());
}

export function _rebuildFloorLevelMap(viewer) {
  viewer.levelNameByFloorKey.clear();

  if (!viewer.floorDefinitions.length || !viewer.levelNamesInOrder.length) {
    return;
  }

  const usedLevelNames = new Set();
  const normalizedLevelNames = viewer.levelNamesInOrder.map((levelName) => ({
    levelName,
    normalized: viewer._normalizeFloorName(levelName),
  }));

  for (const floor of viewer.floorDefinitions) {
    const floorKey = String(floor?.name || "");
    const normalizedFloorName = viewer._normalizeFloorName(floorKey);
    const exactMatch = normalizedLevelNames.find((entry) => {
      return entry.normalized && entry.normalized === normalizedFloorName;
    });

    if (!exactMatch) {
      continue;
    }

    viewer.levelNameByFloorKey.set(floorKey, exactMatch.levelName);
    usedLevelNames.add(exactMatch.levelName);
  }

  viewer.floorDefinitions.forEach((floor, index) => {
    const floorKey = String(floor?.name || "");
    if (viewer.levelNameByFloorKey.has(floorKey)) {
      return;
    }

    const levelNameAtSameIndex = viewer.levelNamesInOrder[index];
    if (levelNameAtSameIndex && !usedLevelNames.has(levelNameAtSameIndex)) {
      viewer.levelNameByFloorKey.set(floorKey, levelNameAtSameIndex);
      usedLevelNames.add(levelNameAtSameIndex);
      return;
    }

    const nextUnusedLevelName = viewer.levelNamesInOrder.find((levelName) => {
      return !usedLevelNames.has(levelName);
    });

    if (nextUnusedLevelName) {
      viewer.levelNameByFloorKey.set(floorKey, nextUnusedLevelName);
      usedLevelNames.add(nextUnusedLevelName);
    }
  });
}

export function _resolveLevelNameForFloor(viewer, floorName) {
  if (!floorName) {
    return floorName;
  }

  if (viewer.levelNameByFloorKey.has(floorName)) {
    return viewer.levelNameByFloorKey.get(floorName);
  }

  const normalizedFloorName = viewer._normalizeFloorName(floorName);
  for (const levelName of viewer.levelNamesInOrder) {
    if (viewer._normalizeFloorName(levelName) === normalizedFloorName) {
      return levelName;
    }
  }

  return floorName;
}

export function _normalizeFloorName(viewer, value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
}

export function _getFloorIndexForName(viewer, floorName) {
  const floor = viewer.floorDefinitions.find((candidate) => {
    return viewer._normalizeFloorName(candidate?.name) === viewer._normalizeFloorName(floorName);
  });

  if (!floor) {
    return null;
  }

  return Number.isFinite(Number(floor.index)) ? Number(floor.index) : null;
}
