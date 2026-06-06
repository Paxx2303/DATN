/**
 * FishEye8K Layout Component
 * Caches global DOM references and exposes core UI shell helper functions.
 */

export const elements = {
  uploadZone: document.getElementById("upload-zone"),
  fileInput: document.getElementById("file-input"),
  sourceLayout: document.getElementById("source-layout"),
  fisheyeEnabled: document.getElementById("fisheye-enabled"),
  modelKey: document.getElementById("model-key"),
  confidence: document.getElementById("confidence"),
  confidenceValue: document.getElementById("confidence-value"),
  iou: document.getElementById("iou"),
  iouValue: document.getElementById("iou-value"),
  fisheyeStrength: document.getElementById("fisheye-strength"),
  fisheyeStrengthValue: document.getElementById("fisheye-strength-value"),
  fisheyeRadius: document.getElementById("fisheye-radius"),
  fisheyeRadiusValue: document.getElementById("fisheye-radius-value"),
  fisheyeEffect: document.getElementById("fisheye-effect"),
  videoDetectFpsWrap: document.getElementById("video-detect-fps-wrap"),
  videoDetectFps: document.getElementById("video-detect-fps"),
  detectBtn: document.getElementById("detect-btn"),
  convertBtn: document.getElementById("convert-btn"),
  clearBtn: document.getElementById("clear-btn"),
  refreshHistory: document.getElementById("refresh-history"),
  externalCameraFrame: document.getElementById("external-camera-frame"),
  externalCameraUrl: document.getElementById("external-camera-url"),
  externalCameraComputeMode: document.getElementById("external-camera-compute-mode"),
  externalCameraLiveInterval: document.getElementById("external-camera-live-interval"),
  externalCameraLoad: document.getElementById("external-camera-load"),
  externalCameraDetect: document.getElementById("external-camera-detect"),
  externalCameraLiveStart: document.getElementById("external-camera-live-start"),
  externalCameraLiveStop: document.getElementById("external-camera-live-stop"),
  externalCameraLiveRefresh: document.getElementById("external-camera-live-refresh"),
  externalCameraLiveStatus: document.getElementById("external-camera-live-status"),
  externalCameraOpen: document.getElementById("external-camera-open"),
  externalCameraResults: document.getElementById("external-camera-results"),
  congestionPanel: document.getElementById("congestion-panel"),
  congestionBadge: document.getElementById("congestion-badge"),
  congestionDetail: document.getElementById("congestion-detail"),
  alertList: document.getElementById("alert-list"),
  exampleStrip: document.getElementById("example-strip"),
  downloadPrimary: document.getElementById("download-primary"),
  downloadJson: document.getElementById("download-json"),
  originalMedia: document.getElementById("original-media"),
  preprocessedMedia: document.getElementById("preprocessed-media"),
  resultMedia: document.getElementById("result-media"),
  originalMeta: document.getElementById("original-meta"),
  preprocessedMeta: document.getElementById("preprocessed-meta"),
  resultMeta: document.getElementById("result-meta"),
  statsGrid: document.getElementById("stats-grid"),
  summaryRow: document.getElementById("summary-row"),
  detectionList: document.getElementById("detection-list"),
  historyList: document.getElementById("history-list"),
  statsRefreshBtn: document.getElementById("stats-refresh-btn"),
  statTotal: document.getElementById("stat-total"),
  statDetect: document.getElementById("stat-detect"),
  statConvert: document.getElementById("stat-convert"),
  statInference: document.getElementById("stat-inference"),
  classChart: document.getElementById("class-chart"),
  chartEmpty: document.getElementById("chart-empty"),
  legend: document.getElementById("legend"),
  overlay: document.getElementById("overlay"),
  toast: document.getElementById("toast"),
  selectedFile: document.getElementById("selected-file"),
  selectedType: document.getElementById("selected-type"),
  selectedSize: document.getElementById("selected-size"),
  requestId: document.getElementById("request-id"),
  savedResult: document.getElementById("saved-result"),
  statusModel: document.getElementById("status-model"),
  statusPath: document.getElementById("status-path"),
  statusDevice: document.getElementById("status-device"),
  statusResults: document.getElementById("status-results"),
  topDevice: document.getElementById("top-device"),
  topConf: document.getElementById("top-conf"),
  topIou: document.getElementById("top-iou"),
  classCount: document.getElementById("class-count"),
  recentRunCount: document.getElementById("recent-run-count"),
  modelSource: document.getElementById("model-source"),
};

/**
 * Shows a toast message on the bottom right.
 */
export function setToast(message, isSuccess = false) {
  if (!elements.toast) return;
  elements.toast.textContent = message;
  elements.toast.className = isSuccess ? "toast success show" : "toast show";
  window.setTimeout(() => {
    elements.toast.className = isSuccess ? "toast success" : "toast";
  }, 3200);
}

/**
 * Triggers loading state across the application.
 */
export function setLoading(isLoading, appState) {
  if (elements.overlay) {
    elements.overlay.classList.toggle("show", isLoading);
  }
  const canOperate = !isLoading && !!appState.currentFile;
  if (elements.detectBtn) elements.detectBtn.disabled = !canOperate;
  if (elements.convertBtn) elements.convertBtn.disabled = !canOperate;
  if (elements.refreshHistory) elements.refreshHistory.disabled = isLoading;
}

/**
 * Syncs confidence, iou, and fisheye inputs to display labels.
 */
export function updateControlLabels() {
  if (elements.confidence && elements.confidenceValue) {
    elements.confidenceValue.textContent = Number(elements.confidence.value).toFixed(2);
  }
  if (elements.iou && elements.iouValue) {
    elements.iouValue.textContent = Number(elements.iou.value).toFixed(2);
  }
  if (elements.fisheyeStrength && elements.fisheyeStrengthValue) {
    elements.fisheyeStrengthValue.textContent = `${(Number(elements.fisheyeStrength.value) * 100).toFixed(0)}%`;
  }
  if (elements.fisheyeRadius && elements.fisheyeRadiusValue) {
    elements.fisheyeRadiusValue.textContent = `${(Number(elements.fisheyeRadius.value) * 100).toFixed(0)}%`;
  }
  if (elements.topConf && elements.confidence) {
    elements.topConf.textContent = Number(elements.confidence.value).toFixed(2);
  }
  if (elements.topIou && elements.iou) {
    elements.topIou.textContent = Number(elements.iou.value).toFixed(2);
  }
}
