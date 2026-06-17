/**
 * FishEye8K Front-end Application Bootstrapper
 * Integrates router, state, API wrappers, and page components.
 */
import { router } from './router.js';
import { appState } from './state/appState.js';
import { ApiService } from './services/api.js';
import { elements, setToast, setLoading, updateControlLabels } from './components/Layout.js';
import { initDashboard, renderLegend, loadStats, loadDashboardExtras } from './components/Dashboard.js';
import { initWorkspace, renderPlaceholder, loadExampleIntoWorkspace } from './components/Workspace.js';
import { initLiveStreams, loadExternalCamera, loadExternalCameraLiveStatus } from './components/LiveStreams.js';
import { initLogsTerminal, loadLogs } from './components/LogsTerminal.js';
import { initTOC, startTOCPolling, stopTOCPolling, loadTOCHeatmap } from './components/TOC.js';
import { initALPR, loadAlprHistory } from './components/ALPR.js';

// Expose navigation to the global scope for the inline onclick handlers in HTML
window.nav = function(pageId) {
  router.navigate(pageId);
};

/**
 * Renders the saved inference run history items.
 */
function renderHistory(items) {
  if (elements.recentRunCount) {
    elements.recentRunCount.textContent = String(items.length);
  }
  if (!elements.historyList) return;
  
  if (!items.length) {
    elements.historyList.innerHTML = '<div class="placeholder" style="max-width:none;">No saved runs yet. Execute detection or conversion once to populate history.</div>';
    return;
  }

  elements.historyList.innerHTML = items.map((item) => {
    const actionLinks = Object.entries(item.artifact_urls || {}).map(([key, url]) => `
      <a class="tiny-link" href="${url}" target="_blank" rel="noopener">${key.replaceAll("_", " ")}</a>
    `).join("");

    let summary = `${item.media_type} | ${item.summary.output_kind || "fisheye"}`;
    if (item.task === "detect" && item.media_type === "image") {
      summary = `${item.summary.total_objects} obj | ${item.summary.inference_ms} ms`;
    } else if (item.task === "detect" && item.media_type === "video") {
      summary = `${item.summary.total_frames} frames | ${item.summary.inference_ms_avg} ms/frame`;
    }

    return `
      <div class="history-item">
        <div class="history-main">
          <div>
            <strong>${item.filename || item.id}</strong>
            <div class="history-sub">${item.id}</div>
          </div>
          <div class="history-sub">${item.task} | ${summary}</div>
        </div>
        <div class="history-sub">${item.created_at}</div>
        <div class="history-actions">${actionLinks}</div>
      </div>
    `;
  }).join("");
}

/**
 * Renders backend health and storage locations into static settings.
 */
function renderHealth(health) {
  const model = health.model || {};
  if (elements.statusModel) elements.statusModel.textContent = model.loaded_from_name || model.source || "unloaded";
  if (elements.statusPath) elements.statusPath.textContent = model.loaded_from || model.candidate || "not resolved";
  if (elements.statusDevice) elements.statusDevice.textContent = health.device || model.device || "cpu";
  if (elements.statusResults) elements.statusResults.textContent = health.storage.results_dir || "unknown";
  if (elements.topDevice) elements.topDevice.textContent = health.device || model.device || "cpu";
  if (elements.modelSource) elements.modelSource.textContent = model.source || "unknown";
}

/**
 * Load system health data.
 */
async function loadHealth() {
  try {
    const data = await ApiService.fetchHealth();
    renderHealth(data);
  } catch (error) {
    console.error("Failed to load health status:", error);
  }
}

/**
 * Load run history items.
 */
async function loadHistory() {
  try {
    const data = await ApiService.fetchHistory();
    renderHistory(data.items || []);
  } catch (error) {
    console.error("Failed to load run history:", error);
  }
}

/**
 * Callback triggered whenever an inference detection or conversion job succeeds.
 * Refreshes dependent list displays synchronously.
 */
async function onJobCompleted() {
  await Promise.all([
    loadHistory(),
    loadHealth(),
    loadStats(window.APP_CONFIG.classColors)
  ]);
}

// Register router hooks
router.onNavigate((pageId) => {
  if (pageId === "logs") {
    loadLogs();
    window.setTimeout(() => {
      const terminal = document.getElementById("logs-terminal");
      if (terminal) terminal.scrollTop = terminal.scrollHeight;
    }, 100);
  }
  if (pageId === "streams") {
    loadExternalCameraLiveStatus(true);
  }
  if (pageId === "toc") {
    startTOCPolling();
    loadTOCHeatmap();
  } else {
    stopTOCPolling();
  }
  if (pageId === "dash") {
    loadDashboardExtras();
  }
  if (pageId === "alpr") {
    loadAlprHistory();
  }
});

/**
 * Core initialization loop.
 */
async function boot() {
  const config = window.APP_CONFIG;
  if (!config) {
    console.error("APP_CONFIG is missing from the global window object.");
    return;
  }

  // Render initial static legends and control values
  renderLegend(config.classNames, config.classColors);
  updateControlLabels();

  // Set placeholders
  renderPlaceholder(elements.originalMedia, "The uploaded image or video preview will appear here.");
  renderPlaceholder(elements.preprocessedMedia, "If preprocessing is enabled, the warped fisheye output will appear here.");
  renderPlaceholder(elements.resultMedia, "Detection annotations or converted fisheye video will appear here.");

  // Initialize page-level controllers (each wrapped so one failure doesn't block navigation)
  const _tryInit = (label, fn) => { try { fn(); } catch (e) { console.error(`[boot] init ${label} failed:`, e); } };
  _tryInit("Dashboard",      () => initDashboard(config.classColors));
  _tryInit("Workspace",      () => initWorkspace(config.classNames, config.classColors, onJobCompleted));
  _tryInit("LiveStreams",    () => initLiveStreams(config.classNames, config.classColors, onJobCompleted));
  _tryInit("LogsTerminal",   () => initLogsTerminal());
  _tryInit("TOC",            () => initTOC());
  _tryInit("ALPR",           () => initALPR());

  // Bind History refresh click
  if (elements.refreshHistory) {
    elements.refreshHistory.addEventListener("click", loadHistory);
  }

  // Load backend metadata
  try {
    await Promise.all([
      loadHealth(),
      loadHistory(),
      loadStats(config.classColors),
      loadExternalCameraLiveStatus(true)
    ]);
    
    // Auto-load default external camera source on startup
    await loadExternalCamera(config.externalCameraUrl);
    await loadDashboardExtras();
  } catch (error) {
    setToast(`Failed to load system metadata on boot: ${error.message}`);
  }

  // Navigate to default Dashboard page
  router.navigate("dash");
}

// Execute boot when DOM content is fully loaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
