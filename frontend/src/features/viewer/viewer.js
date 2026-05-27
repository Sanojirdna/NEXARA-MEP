import * as THREE from "three";
import * as OBC from "@thatopen/components";
import * as OBF from "@thatopen/components-front";
import {
  ROOM_STYLE,
  SHAFT_STYLE,
  CORRIDOR_STYLE,
  SELECTED_STYLE,
  DEFAULT_ROUTE_COLOR,
} from "./viewerStyles.js";
import {
  drawVariantRoutes,
  drawSystemNetwork,
  drawSystemRoute,
  clearAllRoutes,
  _transformPathPoint,
  _getServiceRouteColor,
  _buildLineFromXYZ,
  _buildPipeFromXYZ,
  _buildRoutePoints,
  _clipPathXYZToCurrentFloor,
  _getCurrentFloorZBounds,
  _clipSegmentToZBand,
  _pushUniqueXYZ,
  _clearGroup,
} from "./routeRenderer.js";
import {
  setRoomCenters,
  setRoomCentersVisible,
  setRoomLabelsVisible,
  _roomCenterFromBBox,
  _centerFromBox,
  _rebuildSpaceLabels,
  _buildSpaceFloorIndexLookup,
  _buildCorridorLabelSprites,
  _getSpaceLabelText,
  _createLabelSprite,
  _createRoomLabelSprite,
  _drawRoundedRect,
  _updateRoomLabelVisibility,
  _updateRoomCenterVisibility,
  _floorIndexMatchesCurrentFilter,
} from "./roomMarkers.js";
import {
  resetHiddenItems,
  hideSelectedItem,
  focusOnBBox,
  focusOnModelIdMap,
  isBrowserNodeVisible,
  toggleBrowserNodeVisibility,
  focusBrowserNode,
  selectBrowserNode,
  selectByGuid,
  getCurrentSelectionNodeKey,
  _handleSelection,
  _buildSelectionPayload,
  _notifySelectionChanged,
  _getBoundingBoxForModelIdMap,
  _getSceneBoundingBox,
} from "./viewerSelection.js";
import {
  getBrowserData,
  _buildBrowserData,
  _buildStructureNode,
  _collectSpatialIds,
  _getSpatialNodeName,
  _getLocalId,
  _extractCategory,
  _getItemLabel,
  _getAttributeValue,
  _regexFromExactText,
  _firstDefined,
  _toLocalIdArray,
} from "./viewerBrowserData.js";
import {
  setFloorDefinitions,
  showSpacesOnly,
  showFullIfc,
  isolateFloor,
  resetVisibility,
  _applyVisibilityState,
  _refreshVisualStyles,
  _getVisibleSpaceModelIdMap,
  _buildSpaceModelIdMap,
  _syncSpaceModelIdMapFromRooms,
  _getFloorSpaceModelIdMap,
  _buildSpatialFloorSpaceModelIdMaps,
  _collectStoreySpaceIds,
  _resolveFloorNameFromStoreyName,
  _getFloorModelIdMap,
  _captureLevelNames,
  _rebuildFloorLevelMap,
  _resolveLevelNameForFloor,
  _normalizeFloorName,
  _getFloorIndexForName,
} from "./viewerFloorTools.js";
import {
  _cloneModelIdMap,
  _intersectModelIdMaps,
  _unionModelIdMaps,
  _subtractModelIdMap,
} from "./viewerMapUtils.js";

export class PipePlannerViewer {
  constructor(container, callbacks = {}) {
    this.container = container;
    this.callbacks = callbacks;

    this.components = null;
    this.world = null;
    this.fragments = null;
    this.ifcLoader = null;
    this.classifier = null;
    this.hider = null;
    this.highlighter = null;
    this.clipper = null;

    this.spaceModelIdMap = null;
    this.selectedModelIdMap = null;
    this.selectedItemRef = null;
    this.hiddenModelIdMaps = [];
    this.hiddenBrowserNodeMaps = new Map();

    this.currentFloorName = "__all__";
    this.currentVisibilityMode = "spaces";

    this.variantGroup = new THREE.Group();
    this.systemGroup = new THREE.Group();
    this.activeRouteGroup = new THREE.Group();
    this.roomCenterGroup = new THREE.Group();
    this.roomLabelGroup = new THREE.Group();

    this.roomCentersVisible = true;
    this.roomLabelsVisible = false;
    this.roomRecords = [];
    this.shaftRecords = [];
    this.roomCenterEntries = [];
    this.roomRecordByGuid = new Map();
    this.shaftRecordByGuid = new Map();
    this.roomModelIdMap = null;
    this.shaftModelIdMap = null;
    this.corridorModelIdMap = null;
    this.floorSpaceModelIdMapByName = new Map();
    this.spatialFloorSpaceModelIdMapByName = new Map();
    this.browserData = { structure: [], categories: [] };
    this.browserNodeState = new Map();
    this.browserPathMap = new Map();
    this.itemNodeKeyByRef = new Map();

    this.routeTransformMode = "x_z_neg_y";
    this.floorDefinitions = [];
    this.levelNamesInOrder = [];
    this.levelNameByFloorKey = new Map();
  }

  async init() {
    this.components = new OBC.Components();

    const worlds = this.components.get(OBC.Worlds);
    this.world = worlds.create();

    this.world.scene = new OBC.SimpleScene(this.components);
    this.world.scene.setup();
    this.world.scene.three.background = new THREE.Color("#ffffff");

    this.world.renderer = new OBC.SimpleRenderer(this.components, this.container);
    this.world.camera = new OBC.OrthoPerspectiveCamera(this.components);
    await this.world.camera.controls.setLookAt(25, 25, 25, 0, 0, 0);

    this.components.init();

    const grids = this.components.get(OBC.Grids);
    const grid = grids.create(this.world);
    if (grid) {
      grid.visible = false;
    }

    const githubUrl = "https://thatopen.github.io/engine_fragment/resources/worker.mjs";
    const fetchedUrl = await fetch(githubUrl);
    const workerBlob = await fetchedUrl.blob();
    const workerFile = new File([workerBlob], "worker.mjs", {
      type: "text/javascript",
    });
    const workerUrl = URL.createObjectURL(workerFile);

    this.fragments = this.components.get(OBC.FragmentsManager);
    this.fragments.init(workerUrl);

    this.world.camera.controls.addEventListener("update", () => {
      this.fragments.core.update();
    });

    this.world.onCameraChanged.add((camera) => {
      for (const [, model] of this.fragments.list) {
        model.useCamera(camera.three);
      }
      this.fragments.core.update(true);
    });

    this.fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(this.world.camera.three);
      this.world.scene.three.add(model.object);
      this.fragments.core.update(true);
    });

    this.fragments.core.models.materials.list.onItemSet.add(({ value: material }) => {
      if (!("isLodMaterial" in material && material.isLodMaterial)) {
        material.polygonOffset = true;
        material.polygonOffsetUnits = 1;
        material.polygonOffsetFactor = Math.random();
      }
    });

    this.ifcLoader = this.components.get(OBC.IfcLoader);
    await this.ifcLoader.setup({
      autoSetWasm: false,
      wasm: {
        path: "https://unpkg.com/web-ifc@0.0.77/",
        absolute: true,
      },
      webIfc: {
        COORDINATE_TO_ORIGIN: false,
      },
    });

    this.components.get(OBC.Raycasters).get(this.world);

    this.clipper = this.components.get(OBC.Clipper);
    this.clipper.setup({
      color: new THREE.Color("#0D47A1"),
      opacity: 0.2,
      size: 18,
    });
    this.clipper.enabled = true;
    this.clipper.visible = true;

    this.highlighter = this.components.get(OBF.Highlighter);
    this.highlighter.setup({
      world: this.world,
      selectMaterialDefinition: SELECTED_STYLE,
    });
    this.highlighter.zoomToSelection = false;

    this.highlighter.events.select.onHighlight.add(async (modelIdMap) => {
      await this._handleSelection(modelIdMap);
    });

    this.highlighter.events.select.onClear.add(async () => {
      this.selectedModelIdMap = null;
      this.selectedItemRef = null;
      await this._refreshVisualStyles();
      this._notifySelectionChanged(null);
    });

    this.classifier = this.components.get(OBC.Classifier);
    this.hider = this.components.get(OBC.Hider);

    this.world.scene.three.add(this.variantGroup);
    this.world.scene.three.add(this.systemGroup);
    this.world.scene.three.add(this.activeRouteGroup);
    this.world.scene.three.add(this.roomCenterGroup);
    this.world.scene.three.add(this.roomLabelGroup);


  }

  async loadIfcFromUrl(url, modelId = "active-model") {
    for (const [, model] of this.fragments.list) {
      this.world.scene.three.remove(model.object);
    }

    this.clearAllRoutes();
    this._clearGroup(this.roomCenterGroup);
    this._clearGroup(this.roomLabelGroup);
    this.roomCenterEntries = [];
    this.floorSpaceModelIdMapByName.clear();
    this.spatialFloorSpaceModelIdMapByName.clear();

    this.spaceModelIdMap = null;
    this.roomModelIdMap = null;
    this.shaftModelIdMap = null;
    this.corridorModelIdMap = null;
    this.selectedModelIdMap = null;
    this.selectedItemRef = null;
    this.hiddenModelIdMaps = [];
    this.hiddenBrowserNodeMaps.clear();
    this.browserData = { structure: [], categories: [] };
    this.browserNodeState.clear();
    this.browserPathMap.clear();
    this.itemNodeKeyByRef.clear();
    this.levelNamesInOrder = [];
    this.levelNameByFloorKey.clear();
    this.currentFloorName = "__all__";
    this.currentVisibilityMode = "spaces";

    const file = await fetch(url);
    const data = await file.arrayBuffer();
    const buffer = new Uint8Array(data);

    await this.ifcLoader.load(buffer, false, modelId, {
      processData: {
        progressCallback: (progress) => {
          console.log("IFC load progress", progress);
        },
      },
    });

    await this.classifier.byIfcBuildingStorey({ classificationName: "Levels" });
    this._captureLevelNames();
    this._rebuildFloorLevelMap();
    await this._buildSpaceModelIdMap();
    await this._buildSpatialFloorSpaceModelIdMaps();

    if (this.roomRecords.length || this.shaftRecords.length) {
      await this._syncSpaceModelIdMapFromRooms();
      await this._rebuildSpaceLabels();
    }

    await this._buildBrowserData();
    await this._applyVisibilityState();
    await this.setView("iso");
  }

  setFloorDefinitions(...args) {
    return setFloorDefinitions(this, ...args);
  }

  async setRoomCenters(...args) {
    return setRoomCenters(this, ...args);
  }

  setRoomCentersVisible(...args) {
    return setRoomCentersVisible(this, ...args);
  }

  setRoomLabelsVisible(...args) {
    return setRoomLabelsVisible(this, ...args);
  }

  async showSpacesOnly(...args) {
    return showSpacesOnly(this, ...args);
  }

  async showFullIfc(...args) {
    return showFullIfc(this, ...args);
  }

  async isolateFloor(...args) {
    return isolateFloor(this, ...args);
  }

  async resetVisibility(...args) {
    return resetVisibility(this, ...args);
  }

  async resetHiddenItems(...args) {
    return resetHiddenItems(this, ...args);
  }

  async hideSelectedItem(...args) {
    return hideSelectedItem(this, ...args);
  }

  focusOnBBox(...args) {
    return focusOnBBox(this, ...args);
  }

  async focusOnModelIdMap(...args) {
    return focusOnModelIdMap(this, ...args);
  }

  async setView(viewName) {
    const box = this._getSceneBoundingBox();
    if (!box || box.isEmpty()) {
      return;
    }

    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const offset = Math.max(size.x, size.y, size.z, 10) * 1.4;

    if (viewName === "iso") {
      await this.world.camera.projection.set("Perspective");
      await this.world.camera.controls.setLookAt(
        center.x + offset,
        center.y + offset,
        center.z + offset,
        center.x,
        center.y,
        center.z,
        true,
      );
      return;
    }

    await this.world.camera.projection.set("Orthographic");

    const positions = {
      top: new THREE.Vector3(center.x, center.y + offset, center.z),
      bottom: new THREE.Vector3(center.x, center.y - offset, center.z),
      front: new THREE.Vector3(center.x, center.y, center.z + offset),
      back: new THREE.Vector3(center.x, center.y, center.z - offset),
      left: new THREE.Vector3(center.x - offset, center.y, center.z),
      right: new THREE.Vector3(center.x + offset, center.y, center.z),
    };

    const position = positions[viewName];
    if (!position) {
      return;
    }

    await this.world.camera.controls.setLookAt(
      position.x,
      position.y,
      position.z,
      center.x,
      center.y,
      center.z,
      true,
    );
  }

  async addSectionCut(mode = "pick") {
    if (!this.clipper) {
      return;
    }

    if (mode === "pick") {
      await this.clipper.create(this.world);
      return;
    }

    const box = this._getSceneBoundingBox();
    if (!box || box.isEmpty()) {
      return;
    }

    const center = box.getCenter(new THREE.Vector3());

    const normals = {
      horizontal: new THREE.Vector3(0, -1, 0),
      front: new THREE.Vector3(0, 0, -1),
      right: new THREE.Vector3(-1, 0, 0),
    };

    const normal = normals[mode];
    if (!normal) {
      return;
    }

    this.clipper.createFromNormalAndCoplanarPoint(this.world, normal, center);
  }

  async deleteLastSectionCut() {
    if (!this.clipper || !this.clipper.list.size) {
      return;
    }

    const planeIds = [];
    for (const [planeId] of this.clipper.list) {
      planeIds.push(planeId);
    }

    const lastPlaneId = planeIds[planeIds.length - 1];
    if (!lastPlaneId) {
      return;
    }

    await this.clipper.delete(this.world, lastPlaneId);
  }

  clearSectionCuts() {
    if (!this.clipper) {
      return;
    }
    this.clipper.deleteAll();
  }

  getSectionCount() {
    if (!this.clipper) {
      return 0;
    }
    return this.clipper.list.size;
  }

  getBrowserData(...args) {
    return getBrowserData(this, ...args);
  }

  isBrowserNodeVisible(...args) {
    return isBrowserNodeVisible(this, ...args);
  }

  async toggleBrowserNodeVisibility(...args) {
    return toggleBrowserNodeVisibility(this, ...args);
  }

  async focusBrowserNode(...args) {
    return focusBrowserNode(this, ...args);
  }

  async selectBrowserNode(...args) {
    return selectBrowserNode(this, ...args);
  }

  async selectByGuid(...args) {
    return selectByGuid(this, ...args);
  }

  getCurrentSelectionNodeKey(...args) {
    return getCurrentSelectionNodeKey(this, ...args);
  }

  drawVariantRoutes(...args) {
    return drawVariantRoutes(this, ...args);
  }

  drawSystemNetwork(...args) {
    return drawSystemNetwork(this, ...args);
  }

  drawSystemRoute(...args) {
    return drawSystemRoute(this, ...args);
  }

  clearAllRoutes(...args) {
    return clearAllRoutes(this, ...args);
  }

  _transformPathPoint(...args) {
    return _transformPathPoint(this, ...args);
  }

  _getServiceRouteColor(...args) {
    return _getServiceRouteColor(this, ...args);
  }

  _buildLineFromXYZ(...args) {
    return _buildLineFromXYZ(this, ...args);
  }

  _buildPipeFromXYZ(...args) {
    return _buildPipeFromXYZ(this, ...args);
  }

  _buildRoutePoints(...args) {
    return _buildRoutePoints(this, ...args);
  }

  _clipPathXYZToCurrentFloor(...args) {
    return _clipPathXYZToCurrentFloor(this, ...args);
  }

  _getCurrentFloorZBounds(...args) {
    return _getCurrentFloorZBounds(this, ...args);
  }

  _clipSegmentToZBand(...args) {
    return _clipSegmentToZBand(this, ...args);
  }

  _pushUniqueXYZ(...args) {
    return _pushUniqueXYZ(this, ...args);
  }

  _clearGroup(...args) {
    return _clearGroup(this, ...args);
  }

  async _applyVisibilityState(...args) {
    return _applyVisibilityState(this, ...args);
  }

  async _refreshVisualStyles(...args) {
    return _refreshVisualStyles(this, ...args);
  }

  async _getVisibleSpaceModelIdMap(...args) {
    return _getVisibleSpaceModelIdMap(this, ...args);
  }

  async _buildSpaceModelIdMap(...args) {
    return _buildSpaceModelIdMap(this, ...args);
  }

  async _syncSpaceModelIdMapFromRooms(...args) {
    return _syncSpaceModelIdMapFromRooms(this, ...args);
  }

  async _getFloorSpaceModelIdMap(...args) {
    return _getFloorSpaceModelIdMap(this, ...args);
  }


  async _buildSpatialFloorSpaceModelIdMaps(...args) {
    return _buildSpatialFloorSpaceModelIdMaps(this, ...args);
  }

  _collectStoreySpaceIds(...args) {
    return _collectStoreySpaceIds(this, ...args);
  }

  _getSpatialNodeName(...args) {
    return _getSpatialNodeName(this, ...args);
  }

  _resolveFloorNameFromStoreyName(...args) {
    return _resolveFloorNameFromStoreyName(this, ...args);
  }

  async _getFloorModelIdMap(...args) {
    return _getFloorModelIdMap(this, ...args);
  }

  _captureLevelNames(...args) {
    return _captureLevelNames(this, ...args);
  }

  _rebuildFloorLevelMap(...args) {
    return _rebuildFloorLevelMap(this, ...args);
  }

  _resolveLevelNameForFloor(...args) {
    return _resolveLevelNameForFloor(this, ...args);
  }

  _normalizeFloorName(...args) {
    return _normalizeFloorName(this, ...args);
  }

  _getFloorIndexForName(...args) {
    return _getFloorIndexForName(this, ...args);
  }

  async _buildBrowserData(...args) {
    return _buildBrowserData(this, ...args);
  }

  _buildStructureNode(...args) {
    return _buildStructureNode(this, ...args);
  }

  async _handleSelection(...args) {
    return _handleSelection(this, ...args);
  }

  async _buildSelectionPayload(...args) {
    return _buildSelectionPayload(this, ...args);
  }

  _notifySelectionChanged(...args) {
    return _notifySelectionChanged(this, ...args);
  }

  async _getBoundingBoxForModelIdMap(...args) {
    return _getBoundingBoxForModelIdMap(this, ...args);
  }

  _getSceneBoundingBox(...args) {
    return _getSceneBoundingBox(this, ...args);
  }

  _collectSpatialIds(...args) {
    return _collectSpatialIds(this, ...args);
  }

  _roomCenterFromBBox(...args) {
    return _roomCenterFromBBox(this, ...args);
  }

  _centerFromBox(...args) {
    return _centerFromBox(this, ...args);
  }

  async _rebuildSpaceLabels(...args) {
    return _rebuildSpaceLabels(this, ...args);
  }

  async _buildSpaceFloorIndexLookup(...args) {
    return _buildSpaceFloorIndexLookup(this, ...args);
  }

  async _buildCorridorLabelSprites(...args) {
    return _buildCorridorLabelSprites(this, ...args);
  }

  _getSpaceLabelText(...args) {
    return _getSpaceLabelText(this, ...args);
  }

  _createLabelSprite(...args) {
    return _createLabelSprite(this, ...args);
  }

  _createRoomLabelSprite(...args) {
    return _createRoomLabelSprite(this, ...args);
  }

  _drawRoundedRect(...args) {
    return _drawRoundedRect(this, ...args);
  }

  _updateRoomLabelVisibility(...args) {
    return _updateRoomLabelVisibility(this, ...args);
  }

  _updateRoomCenterVisibility(...args) {
    return _updateRoomCenterVisibility(this, ...args);
  }

  _floorIndexMatchesCurrentFilter(...args) {
    return _floorIndexMatchesCurrentFilter(this, ...args);
  }

  _getLocalId(...args) {
    return _getLocalId(this, ...args);
  }

  _extractCategory(...args) {
    return _extractCategory(this, ...args);
  }

  _getItemLabel(...args) {
    return _getItemLabel(this, ...args);
  }

  _getAttributeValue(...args) {
    return _getAttributeValue(this, ...args);
  }

  _regexFromExactText(...args) {
    return _regexFromExactText(this, ...args);
  }


  _firstDefined(...args) {
    return _firstDefined(this, ...args);
  }

  _toLocalIdArray(...args) {
    return _toLocalIdArray(this, ...args);
  }

  _cloneModelIdMap(...args) {
    return _cloneModelIdMap(this, ...args);
  }

  _intersectModelIdMaps(...args) {
    return _intersectModelIdMaps(this, ...args);
  }

  _unionModelIdMaps(...args) {
    return _unionModelIdMaps(this, ...args);
  }

  _subtractModelIdMap(...args) {
    return _subtractModelIdMap(this, ...args);
  }
}