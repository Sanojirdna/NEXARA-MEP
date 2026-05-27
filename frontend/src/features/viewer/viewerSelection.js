import * as THREE from "three";

export async function resetHiddenItems(viewer) {
  viewer.hiddenModelIdMaps = [];
  viewer.hiddenBrowserNodeMaps.clear();
  await viewer._applyVisibilityState();
}

export async function hideSelectedItem(viewer) {
  if (!viewer.selectedModelIdMap) {
    return;
  }

  viewer.hiddenModelIdMaps.push(viewer._cloneModelIdMap(viewer.selectedModelIdMap));
  await viewer._applyVisibilityState();
}

export function focusOnBBox(viewer, bbox) {
  const center = viewer._roomCenterFromBBox(bbox);
  if (!center) {
    return;
  }

  const sizeX = bbox.max_x - bbox.min_x;
  const sizeY = bbox.max_y - bbox.min_y;
  const sizeZ = bbox.max_z - bbox.min_z;
  const offset = Math.max(sizeX, sizeY, sizeZ, 10);

  viewer.world.camera.controls.setLookAt(
    center.x + offset,
    center.y + offset,
    center.z + offset,
    center.x,
    center.y,
    center.z,
    true,
  );
}

export async function focusOnModelIdMap(viewer, modelIdMap) {
  const box = await viewer._getBoundingBoxForModelIdMap(modelIdMap);
  if (!box || box.isEmpty()) {
    return;
  }

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const offset = Math.max(size.x, size.y, size.z, 10) * 1.2;

  await viewer.world.camera.controls.setLookAt(
    center.x + offset,
    center.y + offset,
    center.z + offset,
    center.x,
    center.y,
    center.z,
    true,
  );
}

export function isBrowserNodeVisible(viewer, nodeKey) {
  return !viewer.hiddenBrowserNodeMaps.has(nodeKey);
}

export async function toggleBrowserNodeVisibility(viewer, nodeKey, visible) {
  const nodeState = viewer.browserNodeState.get(nodeKey);
  if (!nodeState || !nodeState.visibilityMap) {
    return;
  }

  if (visible) {
    viewer.hiddenBrowserNodeMaps.delete(nodeKey);
  } else {
    viewer.hiddenBrowserNodeMaps.set(nodeKey, viewer._cloneModelIdMap(nodeState.visibilityMap));
  }

  await viewer._applyVisibilityState();
}

export async function focusBrowserNode(viewer, nodeKey) {
  const nodeState = viewer.browserNodeState.get(nodeKey);
  if (!nodeState?.visibilityMap) {
    return;
  }

  await viewer.focusOnModelIdMap(nodeState.visibilityMap);
}

export async function selectBrowserNode(viewer, nodeKey) {
  const nodeState = viewer.browserNodeState.get(nodeKey);
  if (!nodeState) {
    return;
  }

  if (nodeState.selectionMap) {
    await viewer.highlighter.highlightByID("select", nodeState.selectionMap, true, false, null, false);
    return;
  }

  if (nodeState.visibilityMap) {
    await viewer.focusOnModelIdMap(nodeState.visibilityMap);
  }
}

export async function selectByGuid(viewer, guid, focus = false) {
  if (!guid) {
    return;
  }

  const modelIdMap = await viewer.fragments.guidsToModelIdMap([guid]);
  if (!modelIdMap || !Object.keys(modelIdMap).length) {
    return;
  }

  await viewer.highlighter.highlightByID("select", modelIdMap, true, false, null, false);

  if (focus) {
    await viewer.focusOnModelIdMap(modelIdMap);
  }
}

export function getCurrentSelectionNodeKey(viewer) {
  if (!viewer.selectedItemRef) {
    return "";
  }

  return viewer.itemNodeKeyByRef.get(
    `${viewer.selectedItemRef.modelId}:${viewer.selectedItemRef.localId}`
  ) || "";
}

export async function _handleSelection(viewer, modelIdMap) {
  viewer.selectedModelIdMap = viewer._cloneModelIdMap(modelIdMap);

  const pickedItems = [];
  let selectedModelId = null;
  let selectedLocalId = null;

  for (const [modelId, localIds] of Object.entries(modelIdMap)) {
    const model = viewer.fragments.list.get(modelId);
    if (!model) {
      continue;
    }

    const localIdList = [...localIds];
    const data = await model.getItemsData(localIdList, { attributesDefault: true });
    pickedItems.push(...data);

    if (selectedLocalId === null && localIdList.length) {
      selectedModelId = modelId;
      selectedLocalId = localIdList[0];
    }
  }

  const roomLikeItem = pickedItems.find((item) => {
    const typeText = String(viewer._extractCategory(item) || item?.constructor?.name || "");
    return typeText.toUpperCase().includes("SPACE");
  });

  const selectedItem = roomLikeItem || pickedItems[0];
  if (selectedItem) {
    const localId = viewer._getLocalId(selectedItem);
    if (localId !== null) {
      selectedLocalId = localId;
    }
  }

  if (selectedModelId && selectedLocalId !== null) {
    viewer.selectedItemRef = {
      modelId: selectedModelId,
      localId: selectedLocalId,
    };
  }

  await viewer._refreshVisualStyles();

  const roomGuid =
    viewer._getAttributeValue(selectedItem, "GlobalId") ||
    viewer._getAttributeValue(selectedItem, "globalId") ||
    viewer._getAttributeValue(selectedItem, "guid") ||
    viewer._getAttributeValue(selectedItem, "_guid") ||
    null;

  if (roomGuid && viewer.callbacks.onRoomPicked) {
    viewer.callbacks.onRoomPicked(roomGuid, selectedItem);
  }

  if (selectedModelId && selectedLocalId !== null) {
    const selectionPayload = await viewer._buildSelectionPayload(selectedModelId, selectedLocalId);
    viewer._notifySelectionChanged(selectionPayload);
    return;
  }

  viewer._notifySelectionChanged(null);
}

export async function _buildSelectionPayload(viewer, modelId, localId) {
  const model = viewer.fragments.list.get(modelId);
  if (!model) {
    return null;
  }

  const detailItems = await model.getItemsData([localId], {
    attributesDefault: true,
    relationsDefault: {
      attributes: true,
      relations: true,
    },
  });

  const itemData = detailItems[0] || null;
  const nodeKey = viewer.itemNodeKeyByRef.get(`${modelId}:${localId}`) || "";
  const pathKeys = nodeKey ? [nodeKey] : [];

  const guid = viewer._firstDefined(
    viewer._getAttributeValue(itemData, "GlobalId"),
    viewer._getAttributeValue(itemData, "globalId"),
    viewer._getAttributeValue(itemData, "guid"),
    viewer._getAttributeValue(itemData, "_guid"),
  );
  const room = guid ? viewer.roomRecordByGuid.get(guid) || viewer.shaftRecordByGuid.get(guid) || null : null;

  return {
    modelId,
    localId,
    nodeKey,
    pathKeys,
    label: room?.label || viewer._getItemLabel(itemData, viewer._extractCategory(itemData), localId),
    category: viewer._extractCategory(itemData),
    guid,
    room,
    data: itemData,
  };
}

export function _notifySelectionChanged(viewer, payload) {
  if (typeof viewer.callbacks.onSelectionChanged === "function") {
    viewer.callbacks.onSelectionChanged(payload);
  }
}

export async function _getBoundingBoxForModelIdMap(viewer, modelIdMap) {
  if (!modelIdMap) {
    return null;
  }

  const result = new THREE.Box3();
  let hasBox = false;

  for (const [modelId, rawLocalIds] of Object.entries(modelIdMap)) {
    const model = viewer.fragments.list.get(modelId);
    const localIds = viewer._toLocalIdArray(rawLocalIds);

    if (!model || !localIds.length) {
      continue;
    }

    const modelBox = await model.getMergedBox(localIds);
    if (!modelBox) {
      continue;
    }

    if (!hasBox) {
      result.copy(modelBox);
      hasBox = true;
    } else {
      result.union(modelBox);
    }
  }

  return hasBox ? result : null;
}

export function _getSceneBoundingBox(viewer) {
  const result = new THREE.Box3();
  let hasBox = false;

  for (const [, model] of viewer.fragments.list) {
    const modelBox = new THREE.Box3().setFromObject(model.object);
    if (modelBox.isEmpty()) {
      continue;
    }

    if (!hasBox) {
      result.copy(modelBox);
      hasBox = true;
    } else {
      result.union(modelBox);
    }
  }

  return hasBox ? result : null;
}
