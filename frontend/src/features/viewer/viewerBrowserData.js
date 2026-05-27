

export function getBrowserData(viewer) {
  return viewer.browserData;
}

export async function _buildBrowserData(viewer) {
  const structure = [];
  const categories = [];

  viewer.browserNodeState.clear();
  viewer.browserPathMap.clear();
  viewer.itemNodeKeyByRef.clear();

  for (const [, model] of viewer.fragments.list) {
    const spatialTree = await model.getSpatialStructure();
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

    const rootResult = viewer._buildStructureNode(model.modelId, spatialTree, itemDataMap, []);
    if (rootResult?.node) {
      structure.push(rootResult.node);
    }

    const categoryNames = (await model.getCategories()).filter((name) => Boolean(name));
    const categoryExpressions = categoryNames.map((name) => viewer._regexFromExactText(name));
    const categoryMap = categoryExpressions.length
      ? await model.getItemsOfCategories(categoryExpressions)
      : {};

    for (const categoryName of categoryNames) {
      const localIds = categoryMap[categoryName] || [];
      const key = `category:${model.modelId}:${categoryName}`;
      const label = categoryName.replace(/^IFC/, "");

      viewer.browserNodeState.set(key, {
        key,
        label,
        category: categoryName,
        localId: null,
        modelId: model.modelId,
        selectionMap: null,
        visibilityMap: localIds.length ? { [model.modelId]: new Set(localIds) } : null,
      });
      viewer.browserPathMap.set(key, [key]);

      categories.push({
        key,
        label,
        category: categoryName,
        itemCount: localIds.length,
        children: [],
      });
    }
  }

  viewer.browserData = { structure, categories };
}

export function _buildStructureNode(viewer, modelId, spatialNode, itemDataMap, parentPath) {
  const localId = Number.isInteger(spatialNode?.localId) ? spatialNode.localId : null;
  const itemData = localId === null ? null : itemDataMap.get(localId) || null;
  const label = viewer._getItemLabel(itemData, spatialNode?.category, localId);
  const childResults = [];
  const currentPath = [...parentPath];

  const children = spatialNode?.children || [];
  for (let index = 0; index < children.length; index += 1) {
    const childResult = viewer._buildStructureNode(
      modelId,
      children[index],
      itemDataMap,
      [...currentPath, index],
    );
    if (childResult?.node) {
      childResults.push(childResult);
    }
  }

  const descendantIds = [];
  if (localId !== null) {
    descendantIds.push(localId);
  }

  for (const childResult of childResults) {
    descendantIds.push(...childResult.descendantIds);
  }

  const keySeed = localId === null ? `root-${currentPath.join("-") || "0"}` : String(localId);
  const key = `structure:${modelId}:${keySeed}:${currentPath.join(".") || "0"}`;
  const pathKeys = [key];

  for (const childResult of childResults) {
    for (const childPathKey of childResult.pathKeys) {
      pathKeys.push(childPathKey);
    }
  }

  const node = {
    key,
    label,
    category: spatialNode?.category || "Item",
    localId,
    itemCount: descendantIds.length,
    children: childResults.map((childResult) => childResult.node),
  };

  const visibilityMap = descendantIds.length ? { [modelId]: new Set(descendantIds) } : null;
  const selectionMap = localId !== null ? { [modelId]: new Set([localId]) } : null;

  viewer.browserNodeState.set(key, {
    key,
    label,
    category: spatialNode?.category || "Item",
    localId,
    modelId,
    selectionMap,
    visibilityMap,
  });

  viewer.browserPathMap.set(key, [key]);
  if (localId !== null) {
    viewer.itemNodeKeyByRef.set(`${modelId}:${localId}`, key);
  }

  return {
    node,
    descendantIds,
    pathKeys,
  };
}

export function _collectSpatialIds(viewer, spatialNode, target) {
  if (!spatialNode) {
    return;
  }

  if (Number.isInteger(spatialNode.localId)) {
    target.push(spatialNode.localId);
  }

  for (const child of spatialNode.children || []) {
    viewer._collectSpatialIds(child, target);
  }
}

export function _getSpatialNodeName(viewer, itemData, localId = null) {
  const name = viewer._firstDefined(
    viewer._getAttributeValue(itemData, "Name"),
    viewer._getAttributeValue(itemData, "LongName"),
    viewer._getAttributeValue(itemData, "_name"),
    viewer._getAttributeValue(itemData, "name"),
  );

  if (name) {
    return String(name);
  }

  if (localId !== null && localId !== undefined) {
    return `Storey #${localId}`;
  }

  return "";
}

export function _getLocalId(viewer, itemData) {
  const localIdValue = viewer._firstDefined(
    viewer._getAttributeValue(itemData, "_localId"),
    viewer._getAttributeValue(itemData, "localId"),
    viewer._getAttributeValue(itemData, "expressID"),
    viewer._getAttributeValue(itemData, "id"),
  );

  if (!Number.isInteger(Number(localIdValue))) {
    return null;
  }

  return Number(localIdValue);
}

export function _extractCategory(viewer, itemData) {
  return (
    viewer._getAttributeValue(itemData, "_category") ||
    viewer._getAttributeValue(itemData, "type") ||
    viewer._getAttributeValue(itemData, "ifcClass") ||
    viewer._getAttributeValue(itemData, "category") ||
    "Item"
  );
}

export function _getItemLabel(viewer, itemData, fallbackCategory, localId) {
  const name =
    viewer._getAttributeValue(itemData, "Name") ||
    viewer._getAttributeValue(itemData, "LongName") ||
    viewer._getAttributeValue(itemData, "ObjectType") ||
    viewer._getAttributeValue(itemData, "_name") ||
    viewer._getAttributeValue(itemData, "name");

  const category = viewer._extractCategory(itemData) || fallbackCategory || "Item";
  const shortCategory = String(category).replace(/^IFC/, "");

  if (name) {
    return `${name}`;
  }

  if (localId !== null && localId !== undefined) {
    return `${shortCategory} #${localId}`;
  }

  return shortCategory;
}

export function _getAttributeValue(viewer, source, key) {
  if (!source || typeof source !== "object") {
    return null;
  }

  const candidateKeys = [
    key,
    String(key),
    String(key).replace(/^_+/, ""),
    `_${String(key).replace(/^_+/, "")}`,
    String(key).toLowerCase(),
    `_${String(key).replace(/^_+/, "").toLowerCase()}`,
  ];

  for (const candidateKey of candidateKeys) {
    if (!(candidateKey in source)) {
      continue;
    }

    const value = source[candidateKey];
    if (value && typeof value === "object" && "value" in value) {
      return value.value;
    }

    return value;
  }

  return null;
}

export function _regexFromExactText(viewer, text) {
  const escaped = String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${escaped}$`);
}

export function _firstDefined(viewer, ...values) {
  for (const value of values) {
    if (value !== undefined && value !== null) {
      return value;
    }
  }
  return null;
}

export function _toLocalIdArray(viewer, localIds) {
  if (!localIds) {
    return [];
  }

  if (Array.isArray(localIds)) {
    return [...localIds];
  }

  if (localIds instanceof Set) {
    return [...localIds];
  }

  return Array.from(localIds);
}
