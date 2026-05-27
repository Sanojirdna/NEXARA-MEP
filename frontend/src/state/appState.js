export function getDefaultDesignExplorerState() {
  return {
    categoryKeys: ["performance", "geometry", "crossings"],
    xMetricKey: "score",
    yMetricKey: "length_m",
    colorBy: "strategy",
    strategyFilter: "__all__",
    shaftFilter: "__all__",
  };
}

export const state = {
  summary: null,
  selectedRoomGuid: "",
  selectedService: "",
  selectedDemandId: "",
  selectedShaftGuid: "",
  selectedStrategy: "",
  selectedVariantRows: [],
  selectedVariantKey: "",
  allVariantRows: [],
  systemOverviewRows: [],
  selectedSystemRow: null,
  deViewMode: "all",
  systemServiceFilter: "__all__",
  systemStrategy: "",
  viewer: null,
  browserData: { structure: [], categories: [] },
  browserTab: "structure",
  browserSearch: "",
  browserOpenKeys: new Set(),
  selectedBrowserKey: "",
  selectedIfcSelection: null,
  roomCentersVisible: true,
  roomLabelsVisible: false,
  viewerMode: "spaces",
  ignoreNextViewerRoomPicked: false,
  designExplorer: getDefaultDesignExplorerState(),
};
