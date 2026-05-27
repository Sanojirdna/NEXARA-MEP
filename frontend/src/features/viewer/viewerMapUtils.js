

export function _cloneModelIdMap(viewer, modelIdMap) {
  if (!modelIdMap) {
    return null;
  }

  const result = {};

  for (const [modelId, localIds] of Object.entries(modelIdMap)) {
    result[modelId] = new Set(viewer._toLocalIdArray(localIds));
  }

  return result;
}

export function _intersectModelIdMaps(viewer, mapA, mapB) {
  if (!mapA || !mapB) {
    return mapA || mapB;
  }

  const result = {};
  const modelIds = new Set([...Object.keys(mapA), ...Object.keys(mapB)]);

  for (const modelId of modelIds) {
    const setA = new Set(viewer._toLocalIdArray(mapA[modelId]));
    const setB = new Set(viewer._toLocalIdArray(mapB[modelId]));
    const intersection = new Set();

    for (const value of setA) {
      if (setB.has(value)) {
        intersection.add(value);
      }
    }

    if (intersection.size) {
      result[modelId] = intersection;
    }
  }

  return Object.keys(result).length ? result : null;
}

export function _unionModelIdMaps(viewer, mapA, mapB) {
  if (!mapA && !mapB) {
    return null;
  }

  const result = {};
  const modelIds = new Set([...Object.keys(mapA || {}), ...Object.keys(mapB || {})]);

  for (const modelId of modelIds) {
    const merged = new Set([
      ...viewer._toLocalIdArray(mapA?.[modelId]),
      ...viewer._toLocalIdArray(mapB?.[modelId]),
    ]);

    if (merged.size) {
      result[modelId] = merged;
    }
  }

  return Object.keys(result).length ? result : null;
}

export function _subtractModelIdMap(viewer, sourceMap, subtractMap) {
  if (!sourceMap || !subtractMap) {
    return sourceMap;
  }

  const result = {};
  for (const [modelId, sourceIds] of Object.entries(sourceMap)) {
    const subtractIds = new Set(viewer._toLocalIdArray(subtractMap[modelId]));
    const remaining = new Set();

    for (const localId of viewer._toLocalIdArray(sourceIds)) {
      if (!subtractIds.has(localId)) {
        remaining.add(localId);
      }
    }

    if (remaining.size) {
      result[modelId] = remaining;
    }
  }

  return Object.keys(result).length ? result : null;
}
