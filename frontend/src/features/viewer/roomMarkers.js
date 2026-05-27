import * as THREE from "three";

export async function setRoomCenters(viewer, rooms = [], shafts = []) {
  viewer.roomRecords = [...(rooms || [])];
  viewer.shaftRecords = [...(shafts || [])];
  viewer.roomCenterEntries = [];

  viewer.roomRecordByGuid = new Map();
  for (const room of viewer.roomRecords) {
    if (room?.guid) {
      viewer.roomRecordByGuid.set(room.guid, room);
    }
  }

  viewer.shaftRecordByGuid = new Map();
  for (const shaft of viewer.shaftRecords) {
    if (shaft?.guid) {
      viewer.shaftRecordByGuid.set(shaft.guid, shaft);
    }
  }

  viewer.floorSpaceModelIdMapByName.clear();
  viewer._clearGroup(viewer.roomCenterGroup);

  for (const room of viewer.roomRecords) {
    const point = viewer._roomCenterFromBBox(room?.bbox);
    if (point) {
      viewer.roomCenterEntries.push({
        point,
        floorIndex: Number.isFinite(Number(room?.floor_index)) ? Number(room.floor_index) : null,
      });
    }
  }

  viewer._updateRoomCenterVisibility();

  if (viewer.fragments) {
    await viewer._syncSpaceModelIdMapFromRooms();
    await viewer._rebuildSpaceLabels();
    await viewer._applyVisibilityState();
    return;
  }

  await viewer._rebuildSpaceLabels();
}

export function setRoomCentersVisible(viewer, visible) {
  viewer.roomCentersVisible = Boolean(visible);
  viewer._updateRoomCenterVisibility();
}

export function setRoomLabelsVisible(viewer, visible) {
  viewer.roomLabelsVisible = Boolean(visible);
  viewer._updateRoomLabelVisibility();
}

export function _roomCenterFromBBox(viewer, bbox) {
  if (!bbox) {
    return null;
  }

  const hasAllValues = [
    bbox.min_x,
    bbox.max_x,
    bbox.min_y,
    bbox.max_y,
    bbox.min_z,
    bbox.max_z,
  ].every((value) => Number.isFinite(Number(value)));

  if (!hasAllValues) {
    return null;
  }

  const centerXYZ = [
    (bbox.min_x + bbox.max_x) / 2,
    (bbox.min_y + bbox.max_y) / 2,
    (bbox.min_z + bbox.max_z) / 2,
  ];

  return viewer._transformPathPoint(centerXYZ);
}

export function _centerFromBox(viewer, box) {
  if (!box || typeof box.isEmpty !== "function" || box.isEmpty()) {
    return null;
  }

  return box.getCenter(new THREE.Vector3());
}

export async function _rebuildSpaceLabels(viewer) {
  viewer._clearGroup(viewer.roomLabelGroup);

  for (const room of viewer.roomRecords) {
    const labelSprite = viewer._createRoomLabelSprite(room);
    if (labelSprite) {
      viewer.roomLabelGroup.add(labelSprite);
    }
  }

  for (const shaft of viewer.shaftRecords) {
    const labelSprite = viewer._createRoomLabelSprite(shaft);
    if (labelSprite) {
      viewer.roomLabelGroup.add(labelSprite);
    }
  }

  if (viewer.fragments && viewer.corridorModelIdMap) {
    const floorIndexLookup = await viewer._buildSpaceFloorIndexLookup();
    const corridorSprites = await viewer._buildCorridorLabelSprites(floorIndexLookup);
    for (const sprite of corridorSprites) {
      viewer.roomLabelGroup.add(sprite);
    }
  }

  viewer._updateRoomLabelVisibility();
}

export async function _buildSpaceFloorIndexLookup(viewer) {
  const lookup = new Map();

  for (const floor of viewer.floorDefinitions) {
    const floorName = String(floor?.name || "").trim();
    if (!floorName) {
      continue;
    }

    const floorIndex = Number.isFinite(Number(floor?.index)) ? Number(floor.index) : null;
    const floorMap = await viewer._getFloorSpaceModelIdMap(floorName);
    if (!floorMap || floorIndex === null) {
      continue;
    }

    for (const [modelId, localIds] of Object.entries(floorMap)) {
      for (const localId of viewer._toLocalIdArray(localIds)) {
        lookup.set(`${modelId}:${localId}`, floorIndex);
      }
    }
  }

  return lookup;
}

export async function _buildCorridorLabelSprites(viewer, floorIndexLookup = new Map()) {
  const sprites = [];

  for (const [modelId, localIds] of Object.entries(viewer.corridorModelIdMap || {})) {
    const model = viewer.fragments.list.get(modelId);
    const localIdList = viewer._toLocalIdArray(localIds);

    if (!model || !localIdList.length) {
      continue;
    }

    const itemDataList = await model.getItemsData(localIdList, { attributesDefault: true });
    const itemDataByLocalId = new Map();

    for (const itemData of itemDataList) {
      const localId = viewer._getLocalId(itemData);
      if (localId !== null) {
        itemDataByLocalId.set(localId, itemData);
      }
    }

    for (const localId of localIdList) {
      const itemData = itemDataByLocalId.get(localId) || null;
      const labelText = viewer._getSpaceLabelText(itemData, localId);
      if (!labelText) {
        continue;
      }

      const itemBox = await model.getMergedBox([localId]);
      const center = viewer._centerFromBox(itemBox);
      if (!center) {
        continue;
      }

      const floorIndex = floorIndexLookup.get(`${modelId}:${localId}`) ?? null;
      const guid = viewer._firstDefined(
        viewer._getAttributeValue(itemData, "GlobalId"),
        viewer._getAttributeValue(itemData, "globalId"),
        viewer._getAttributeValue(itemData, "guid"),
        viewer._getAttributeValue(itemData, "_guid"),
      );

      const labelSprite = viewer._createLabelSprite(center, labelText, {
        guid: guid || "",
        floorIndex,
      });

      if (labelSprite) {
        sprites.push(labelSprite);
      }
    }
  }

  return sprites;
}

export function _getSpaceLabelText(viewer, spaceLikeData, localId = null) {
  if (!spaceLikeData) {
    return localId !== null ? `Space #${localId}` : "";
  }

  const label = String(
    spaceLikeData?.label ||
    spaceLikeData?.name ||
    viewer._getAttributeValue(spaceLikeData, "LongName") ||
    viewer._getAttributeValue(spaceLikeData, "Name") ||
    viewer._getAttributeValue(spaceLikeData, "Tag") ||
    viewer._getAttributeValue(spaceLikeData, "ObjectType") ||
    spaceLikeData?.guid ||
    ""
  ).trim();

  if (label) {
    return label;
  }

  return localId !== null ? `Space #${localId}` : "";
}

export function _createLabelSprite(viewer, center, labelText, userData = {}) {
  if (!center) {
    return null;
  }

  const cleanLabelText = String(labelText || "").trim();
  if (!cleanLabelText) {
    return null;
  }

  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  const fontSize = 18;
  context.font = `600 ${fontSize}px Arial`;

  const paddingX = 12;
  const paddingY = 8;
  const textWidth = Math.ceil(context.measureText(cleanLabelText).width);
  canvas.width = textWidth + paddingX * 2;
  canvas.height = fontSize + paddingY * 2;

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.font = `600 ${fontSize}px Arial`;
  context.textAlign = "center";
  context.textBaseline = "middle";

  context.fillStyle = "rgba(0, 0, 0, 0.68)";
  context.strokeStyle = "rgba(13, 71, 161, 0.8)";
  context.lineWidth = 2;

  const radius = 10;
  viewer._drawRoundedRect(context, 1, 1, canvas.width - 2, canvas.height - 2, radius);
  context.fill();
  context.stroke();

  context.fillStyle = "#E3F2FD";
  context.fillText(cleanLabelText, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    depthTest: false,
  });

  const sprite = new THREE.Sprite(material);
  sprite.position.copy(center);
  sprite.scale.set(canvas.width / 36, canvas.height / 36, 1);
  sprite.renderOrder = 997;
  sprite.userData = {
    guid: userData?.guid || "",
    floorIndex: Number.isFinite(Number(userData?.floorIndex)) ? Number(userData.floorIndex) : null,
  };
  return sprite;
}

export function _createRoomLabelSprite(viewer, room) {
  const center = viewer._roomCenterFromBBox(room?.bbox);
  const labelText = viewer._getSpaceLabelText(room);
  return viewer._createLabelSprite(center, labelText, {
    guid: room?.guid || "",
    floorIndex: Number.isFinite(Number(room?.floor_index)) ? Number(room.floor_index) : null,
  });
}

export function _drawRoundedRect(viewer, context, x, y, width, height, radius) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
}

export function _updateRoomLabelVisibility(viewer) {
  viewer.roomLabelGroup.visible = viewer.roomLabelsVisible;

  for (const child of viewer.roomLabelGroup.children) {
    const childFloorIndex = child.userData?.floorIndex;
    child.visible = viewer.roomLabelsVisible && viewer._floorIndexMatchesCurrentFilter(childFloorIndex);
  }
}

export function _updateRoomCenterVisibility(viewer) {
  viewer._clearGroup(viewer.roomCenterGroup);
  viewer.roomCenterGroup.visible = viewer.roomCentersVisible;

  if (!viewer.roomCentersVisible) {
    return;
  }

  const visiblePoints = viewer.roomCenterEntries
    .filter((entry) => viewer._floorIndexMatchesCurrentFilter(entry.floorIndex))
    .map((entry) => entry.point);

  if (!visiblePoints.length) {
    return;
  }

  const geometry = new THREE.BufferGeometry().setFromPoints(visiblePoints);
  const material = new THREE.PointsMaterial({
    color: "#00C853",
    size: 0.6,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.8,
    depthWrite: false,
  });

  const pointCloud = new THREE.Points(geometry, material);
  pointCloud.renderOrder = 998;
  pointCloud.visible = true;
  viewer.roomCenterGroup.add(pointCloud);
}

export function _floorIndexMatchesCurrentFilter(viewer, floorIndex) {
  const hasFloorFilter = viewer.currentFloorName && viewer.currentFloorName !== "__all__";
  if (!hasFloorFilter) {
    return true;
  }

  const visibleFloorIndex = viewer._getFloorIndexForName(viewer.currentFloorName);
  if (visibleFloorIndex === null || floorIndex === null || floorIndex === undefined) {
    return true;
  }

  return Number(floorIndex) === Number(visibleFloorIndex);
}
