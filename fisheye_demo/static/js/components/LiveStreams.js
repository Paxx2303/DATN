/**
 * FishEye8K Live Streams Component
 */
import { elements, setToast, setLoading } from './Layout.js';
import { appState } from '../state/appState.js';
import { ApiService } from '../services/api.js';
import { escapeHtml, normalizeExternalCameraUrl } from '../utils/helpers.js';
import { renderMedia, setArtifactLinks } from './Workspace.js';

export function initLiveStreams(classNames, classColors, onJobCompleted) {
  elements.externalCameraLoad.addEventListener("click", () => loadExternalCamera());
  elements.externalCameraDetect.addEventListener("click",
    () => runExternalCameraDetection(classNames, classColors, onJobCompleted));
  elements.externalCameraLiveStart.addEventListener("click", startExternalCameraLive);
  elements.externalCameraLiveStop.addEventListener("click", stopExternalCameraLive);
  elements.externalCameraLiveRefresh.addEventListener("click",
    () => loadExternalCameraLiveStatus(false, { forceRedraw: true }));

  elements.externalCameraLiveUiFps.addEventListener("input", () => {
    if (appState.liveMonitorRunning) syncExternalCameraLivePolling();
  });
  elements.externalCameraUrl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); loadExternalCamera(); }
  });

  setExternalCameraLiveButtons(false);
}

function getLiveUiPollMs() {
  const raw = Number.parseFloat(elements.externalCameraLiveUiFps.value);
  const fps = Number.isFinite(raw) ? Math.min(60, Math.max(1, raw)) : 15;
  return Math.max(16, Math.round(1000 / fps));
}

export async function loadExternalCamera(urlOverride = null) {
  const normalizedUrl = normalizeExternalCameraUrl(urlOverride ?? "https://camera.0511.vn/camera.html");
  if (!normalizedUrl) { setToast("Nhập URL camera hợp lệ."); return; }
  if (elements.externalCameraUrl) elements.externalCameraUrl.value = normalizedUrl;
  elements.externalCameraOpen.href  = normalizedUrl;
  elements.externalCameraFrame.src  = "about:blank";

  try {
    const data = await ApiService.fetchExternalCameraSource(normalizedUrl);
    if (data.source_mode === "stream") {
      elements.externalCameraFrame.src = "about:blank";
      if (elements.externalCameraLiveStatus && !appState.liveMonitorRunning) {
        elements.externalCameraLiveStatus.innerHTML = `
          <strong>${escapeHtml(data.title || "External camera stream")}</strong>
          <span>Direct stream source configured for live GPU inference.</span>`;
      }
    } else {
      elements.externalCameraFrame.src = data.embed_url;
      if (elements.externalCameraLiveStatus && !appState.liveMonitorRunning) {
        elements.externalCameraLiveStatus.innerHTML = `
          <strong>${escapeHtml(data.title || "External camera video")}</strong>
          <span>YouTube ${escapeHtml(data.youtube_id || "")}</span>`;
      }
    }
  } catch (error) {
    if (elements.externalCameraLiveStatus && !appState.liveMonitorRunning) {
      elements.externalCameraLiveStatus.innerHTML = `
        <strong>Camera video unavailable</strong>
        <span>${escapeHtml(error.message || "Không tải được embed video.")}</span>`;
    }
    setToast(error.message || "Không tải được video camera.");
  }
}

// ── Camera grid (snapshot + live non-stream mode) ───────────────────────────

function renderExternalCameraGrid(data, cacheBustToken = null) {
  elements.externalCameraResults.replaceChildren();
  const cameras = data.cameras || [];

  if (!cameras.length) {
    const empty = document.createElement("div");
    empty.className = "placeholder";
    empty.style.cssText = "max-width:none; grid-column:1/-1;";
    empty.textContent = "Không có ảnh camera nào được detect.";
    elements.externalCameraResults.appendChild(empty);
    return;
  }

  for (const camera of cameras) {
    const article = document.createElement("article");
    article.className = "external-result-item";
    article.dataset.camIndex = String(camera.index ?? 0);

    // Image
    const img = document.createElement("img");
    let src = camera.annotated || "";
    if (cacheBustToken != null && src && !src.startsWith("data:")) {
      src = `${src}?_=${String(cacheBustToken).replace(/[^a-zA-Z0-9._-]/g, "")}`;
    } else if (cacheBustToken != null && src.startsWith("data:")) {
      src = `${src.split("#")[0]}#${String(cacheBustToken).replace(/[^a-zA-Z0-9._-]/g, "")}`;
    }
    img.src = src;
    img.alt = camera.title || camera.name || "";

    // Speed badge (top-right overlay)
    const speedEl = document.createElement("div");
    speedEl.className = "cam-speed-badge";
    speedEl.id = `cam-speed-${camera.index ?? 0}`;
    const spd = camera.avg_speed_kmh ?? 0;
    speedEl.innerHTML = `<span>${spd > 0 ? spd.toFixed(0) + " km/h" : "—"}</span>`;

    // Congestion badge (bottom-left overlay)
    const congEl = document.createElement("div");
    congEl.className = `cam-cong-badge ${(camera.congestion?.level || "low")}`;
    congEl.id = `cam-cong-${camera.index ?? 0}`;
    congEl.textContent = (camera.congestion?.level || "LOW").toUpperCase();

    // Caption
    const copy = document.createElement("div");
    copy.className = "external-result-copy";
    const titleEl = document.createElement("strong");
    titleEl.textContent = camera.title || camera.name || "";
    const meta = document.createElement("span");
    meta.id = `cam-meta-${camera.index ?? 0}`;
    meta.textContent = `${camera.total_objects ?? camera.count ?? 0} objects`;

    copy.append(titleEl, meta);
    article.append(img, speedEl, congEl, copy);
    elements.externalCameraResults.appendChild(article);
  }
}

/** Update speed/congestion overlays on existing camera items from live status data */
function updateCameraOverlays(cameras) {
  if (!cameras || !cameras.length) return;
  for (const cam of cameras) {
    const idx = cam.index ?? 0;
    const speedEl = document.getElementById(`cam-speed-${idx}`);
    const congEl  = document.getElementById(`cam-cong-${idx}`);
    const metaEl  = document.getElementById(`cam-meta-${idx}`);

    if (speedEl) {
      const spd = cam.avg_speed_kmh ?? 0;
      speedEl.innerHTML = `<span>${spd > 0 ? spd.toFixed(0) + " km/h" : "—"}</span>`;
    }
    if (congEl) {
      const lvl = cam.congestion?.level || "low";
      congEl.className = `cam-cong-badge ${lvl}`;
      congEl.textContent = lvl.toUpperCase();
    }
    if (metaEl) {
      metaEl.textContent = `${cam.count ?? 0} objects`;
    }
  }
}

// ── Congestion panel ─────────────────────────────────────────────────────────

function updateCongestionPanel(liveResult) {
  if (!elements.congestionPanel) return;
  const cs = liveResult?.congestion_summary || { level: "low", avg_score: 0 };
  const cameras = liveResult?.cameras || [];
  const lvl = (cs.level || "low").toLowerCase();

  elements.congestionPanel.className = `card congestion-bar cong-${lvl}`;
  if (elements.congestionBadge) {
    const colors = { low: "b-green", moderate: "b-amber", high: "b-red" };
    elements.congestionBadge.className = `badge ${colors[lvl] || "b-gray"}`;
    elements.congestionBadge.textContent = lvl.toUpperCase() +
      (cs.avg_score ? ` · ${(cs.avg_score * 100).toFixed(0)}%` : "");
  }
  if (elements.congestionDetail) {
    if (!cameras.length) {
      elements.congestionDetail.innerHTML =
        `<span style="color:var(--color-text-tertiary); font-size:10.5px;">Chưa có dữ liệu.</span>`;
      return;
    }
    elements.congestionDetail.innerHTML = `<div class="cong-row">${
      cameras.map(cam => {
        const cl  = (cam.congestion?.level || "low").toLowerCase();
        const sc  = ((cam.congestion?.score || 0) * 100).toFixed(0);
        const spd = cam.avg_speed_kmh ?? 0;
        return `<div class="cong-cam cong-${cl}">
          <span class="cong-cam-name">${escapeHtml(cam.name || "")}</span>
          <span class="cong-cam-stats">${cam.count ?? 0}v · ${cl.toUpperCase()} (${sc}%) · ${spd > 0 ? spd.toFixed(0) + "km/h" : "–"}</span>
        </div>`;
      }).join("")
    }</div>`;
  }
}

// ── Alert panel ──────────────────────────────────────────────────────────────

async function refreshAlertPanel() {
  if (!elements.alertList) return;
  try {
    const data = await fetch("/api/alerts?limit=12", { cache: "no-store" }).then(r => r.json());
    const alerts = data.alerts || [];
    if (!alerts.length) {
      elements.alertList.innerHTML =
        '<div class="placeholder" style="font-size:10.5px; padding:12px 0;">Chưa có cảnh báo.</div>';
      return;
    }
    elements.alertList.innerHTML = alerts.map(al => {
      const isCong = (al.alert_type || "").includes("congestion");
      const t = new Date((al.created_at || al.timestamp || "")).toLocaleTimeString("vi-VN");
      return `<div class="alert-item${isCong ? " cong" : ""}">
        <span class="alert-item-title">${escapeHtml(al.alert_type || "ALERT")}</span>
        <span class="alert-item-msg">${escapeHtml(al.message || "")}${al.actual_count ? ` (${al.actual_count})` : ""}</span>
        <span class="alert-item-time">${escapeHtml(al.camera_source || "")} · ${t}</span>
      </div>`;
    }).join("");
  } catch (_) { /* silent */ }
}

// ── MJPEG live streams ───────────────────────────────────────────────────────

function attachExternalCameraLiveStreams() {
  const seed = Date.now();
  renderMedia(
    elements.resultMedia,
    `/api/external-camera/live/stream?view=overview&_=${seed}`,
    "image",
  );

  elements.externalCameraResults.replaceChildren();
  // Show stream items for each known camera (up to 4)
  const camCount = (appState.lastLiveResult?.camera_count) || 1;
  for (let i = 0; i < Math.min(camCount, 4); i++) {
    const article = document.createElement("article");
    article.className = "external-result-item";
    article.dataset.camIndex = String(i);

    const img = document.createElement("img");
    img.src = `/api/external-camera/live/stream?view=camera_${i}&_=${seed}`;
    img.alt = `Camera ${i + 1} live`;

    const speedEl = document.createElement("div");
    speedEl.className = "cam-speed-badge";
    speedEl.id = `cam-speed-${i}`;
    speedEl.innerHTML = "<span>—</span>";

    const congEl = document.createElement("div");
    congEl.className = "cam-cong-badge low";
    congEl.id = `cam-cong-${i}`;
    congEl.textContent = "LOW";

    const copy = document.createElement("div");
    copy.className = "external-result-copy";
    const titleEl = document.createElement("strong");
    titleEl.textContent = `Camera ${i + 1}`;
    const meta = document.createElement("span");
    meta.id = `cam-meta-${i}`;
    meta.textContent = "MJPEG feed";
    copy.append(titleEl, meta);
    article.append(img, speedEl, congEl, copy);
    elements.externalCameraResults.appendChild(article);
  }
}

function setExternalCameraLiveButtons(isRunning) {
  if (elements.externalCameraLiveStart) elements.externalCameraLiveStart.disabled = isRunning;
  if (elements.externalCameraLiveStop)  elements.externalCameraLiveStop.disabled  = !isRunning;
}

export function syncExternalCameraLivePolling() {
  if (appState.livePollTimer) {
    window.clearInterval(appState.livePollTimer);
    appState.livePollTimer = null;
  }
  if (appState.liveMonitorRunning) {
    const ms = getLiveUiPollMs();
    appState.livePollTimer = window.setInterval(() => loadExternalCameraLiveStatus(true), ms);
    loadExternalCameraLiveStatus(true);
  }
}

export async function loadExternalCameraLiveStatus(silent = false, options = {}) {
  try {
    const data = await ApiService.fetchExternalCameraLiveStatus();
    renderExternalCameraLiveStatus(data, options);
  } catch (error) {
    if (!silent) setToast("Failed to load live monitor status.");
  }
}

function renderExternalCameraLiveStatus(data, options = {}) {
  const forceRedraw    = Boolean(options.forceRedraw);
  const running        = Boolean(data.running);
  const statusLabel    = String(data.status || (running ? "active" : "stopped")).toUpperCase();
  const lastUpdated    = data.last_updated_at || "not updated yet";
  const interval       = Number(data.interval_seconds || elements.externalCameraLiveInterval.value || 0);
  const targetFps      = interval > 0 ? (1 / interval).toFixed(1) : "0.0";
  const cycleCount     = data.cycle_count || 0;
  const uiPollMs       = getLiveUiPollMs();
  const uiFpsLabel     = (1000 / uiPollMs).toFixed(1);
  const actualCycleFps = data.actual_cycle_fps != null ? Number(data.actual_cycle_fps).toFixed(2) : "—";
  const cycleDurMs     = data.last_cycle_duration_ms != null ? Number(data.last_cycle_duration_ms).toFixed(1) : "—";
  const spd            = data.speed_summary?.avg_kmh ?? 0;
  const errorBlock     = data.error ? `<span style="color:var(--color-text-danger)">⚠ ${escapeHtml(data.error)}</span>` : "";

  elements.externalCameraLiveStatus.innerHTML = `
    <strong>Live monitor ${statusLabel}</strong>
    <span>Cycle ${interval.toFixed(1)}s | ${targetFps} fps target | ${actualCycleFps} fps actual | ${cycleDurMs} ms | UI ~${uiFpsLabel} fps | Cycles: ${cycleCount}</span>
    <span>Avg speed: ${spd > 0 ? spd.toFixed(1) + " km/h" : "—"} | Congestion: ${(data.congestion_summary?.level || "—").toUpperCase()} | Updated: ${lastUpdated}</span>
    ${errorBlock}
  `;

  setExternalCameraLiveButtons(running);
  if (running !== appState.liveMonitorRunning) {
    appState.set("liveMonitorRunning", running);
    appState.set("liveStreamAttached", false);
    appState.set("lastLiveCycleCount", null);
    appState.set("lastLiveUpdatedAt", null);
    appState.set("lastLiveResult", null);
    syncExternalCameraLivePolling();
  }

  if (running && data.stream_ready && !appState.liveStreamAttached) {
    attachExternalCameraLiveStreams();
    appState.set("liveStreamAttached", true);
  }

  const liveResult = data.last_result;

  // Always update congestion panel + camera overlays if we have live data
  if (liveResult) {
    appState.set("lastLiveResult", liveResult);
    updateCongestionPanel(liveResult);
    updateCameraOverlays(liveResult.cameras || []);
    updateLiveStatsBar(data, liveResult);
    refreshAlertPanel();
  } else {
    updateCongestionPanel(null);
  }

  if (!liveResult) return;

  const lastUpdatedRaw = data.last_updated_at || null;
  const framesAdvanced = forceRedraw || !running ||
    cycleCount !== appState.lastLiveCycleCount ||
    lastUpdatedRaw !== appState.lastLiveUpdatedAt;

  if (running && !framesAdvanced) return;

  if (running) {
    appState.set("lastLiveCycleCount", cycleCount);
    appState.set("lastLiveUpdatedAt", lastUpdatedRaw);
    if (!data.stream_ready) {
      resetDownloads();
      appState.set("latestRecord", null);
      elements.requestId.textContent = "live-monitor";
      elements.savedResult.textContent = "warming up";
      elements.preprocessedMeta.textContent =
        liveResult.preprocessing?.enabled ? "fisheye snapshots" : "raw snapshots";
      elements.resultMeta.textContent = `${liveResult.camera_count} cameras`;
      const bust = `${cycleCount}-${String(lastUpdatedRaw || "").replace(/\D/g, "").slice(-12)}`;
      renderMedia(elements.resultMedia, liveResult.overview || "", "image", bust);
      renderExternalCameraGrid(liveResult, bust);
      renderExternalCameraSummary(liveResult);
    } else {
      // Stream ready — MJPEG active, just update overlays
      renderExternalCameraSummary(liveResult);
      elements.requestId.textContent    = "live-monitor";
      elements.savedResult.textContent  = "mjpeg stream";
      elements.preprocessedMeta.textContent =
        liveResult.preprocessing?.enabled ? "fisheye streaming" : "raw streaming";
      elements.resultMeta.textContent   = `${liveResult.camera_count} cameras`;
    }
    return;
  }

  // Stopped — show last snapshot
  resetDownloads();
  appState.set("latestRecord", null);
  elements.requestId.textContent = "live-monitor";
  elements.savedResult.textContent = "live snapshot";
  elements.preprocessedMeta.textContent =
    liveResult.preprocessing?.enabled ? "fisheye snapshots" : "raw snapshots";
  elements.resultMeta.textContent = `${liveResult.camera_count} cameras`;
  const bust = `${cycleCount}-${String(lastUpdatedRaw || "").replace(/\D/g, "").slice(-12)}`;
  renderMedia(elements.resultMedia, liveResult.overview || "", "image", bust);
  renderExternalCameraGrid(liveResult, bust);
  renderExternalCameraSummary(liveResult);
}

// ── Form helpers ─────────────────────────────────────────────────────────────

function buildExternalCameraFormData() {
  const formData = new FormData();
  const inferredLayout = elements.sourceLayout.value === "fisheye" ? "normal" : elements.sourceLayout.value;
  const computeMode = elements.externalCameraComputeMode.value;
  formData.append("external_camera_url", "https://camera.0511.vn/camera.html");
  formData.append("compute_mode", computeMode);
  formData.append("camera_limit", computeMode === "gpu" ? "4" : "1");
  formData.append("model_key", elements.modelKey.value);
  formData.append("conf", elements.confidence.value);
  formData.append("iou", elements.iou.value);
  formData.append("source_layout", inferredLayout);
  formData.append("fisheye_strength", elements.fisheyeStrength.value);
  formData.append("fisheye_radius", elements.fisheyeRadius.value);
  formData.append("fisheye_effect", elements.fisheyeEffect.value);
  const applyValue = elements.fisheyeEnabled.value === "true" ? "true"
                   : elements.fisheyeEnabled.value === "false" ? "false" : "";
  if (applyValue) formData.append("apply_fisheye", applyValue);
  return formData;
}

async function startExternalCameraLive() {
  const formData = buildExternalCameraFormData();
  formData.append("interval_seconds", elements.externalCameraLiveInterval.value || "1.0");
  try {
    const data = await ApiService.startExternalCameraLive(formData);
    renderExternalCameraLiveStatus(data);
    await loadExternalCameraLiveStatus(true);
    setToast("External live monitor started.", true);
  } catch (error) {
    setToast(error.message || "Failed to start live monitor.");
  }
}

async function stopExternalCameraLive() {
  try {
    const data = await ApiService.stopExternalCameraLive();
    renderExternalCameraLiveStatus(data);
    setToast("External live monitor stopped.", true);
    await refreshAlertPanel();
  } catch (error) {
    setToast(error.message || "Failed to stop live monitor.");
  }
}

async function runExternalCameraDetection(classNames, classColors, onJobCompleted) {
  const formData = buildExternalCameraFormData();
  setLoading(true, appState);
  try {
    const data = await ApiService.runExternalCameraDetection(formData);
    appState.set("latestRecord", data.record);
    elements.requestId.textContent    = data.request_id;
    elements.savedResult.textContent  = data.record.id;
    elements.preprocessedMeta.textContent = data.preprocessing.enabled ? "fisheye snapshots" : "raw snapshots";
    elements.resultMeta.textContent   = `${data.camera_count} cameras`;

    renderMedia(elements.resultMedia, data.overview, "image");
    renderExternalCameraGrid(data);
    renderExternalCameraSummary(data, classNames, classColors);
    // Show congestion from single-shot detect
    if (data.last_result) updateCongestionPanel(data.last_result);
    setArtifactLinks(data.record, "overview_annotated");

    if (onJobCompleted) await onJobCompleted();
    setToast(`Saved external camera detection ${data.record.id} for ${data.camera_count} cameras.`, true);
  } catch (error) {
    setToast(error.message || "External camera detection failed.");
  } finally {
    setLoading(false, appState);
  }
}

function renderExternalCameraSummary(data, classNames, classColors) {
  const summary = data.summary || {};
  const counts  = summary.class_counts || {};

  if (classNames && classColors) {
    elements.statsGrid.innerHTML = classNames.map((name) => `
      <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
        <div class="count" style="color:${classColors[name] || "#ffffff"}; font-size:18px; font-weight:700;">${counts[name] || 0}</div>
        <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">${name}</div>
      </div>`).join("");
  }

  const spd  = data.speed_summary?.avg_kmh ?? 0;
  const cong = data.congestion_summary?.level ?? "—";
  elements.summaryRow.innerHTML = `
    <div class="summary-pill">Task detect</div>
    <div class="summary-pill">Model ${data.model?.loaded_from_name || "unknown"}</div>
    <div class="summary-pill">Cameras ${data.camera_count ?? 0}</div>
    <div class="summary-pill">Objects ${summary.total_objects || 0}</div>
    <div class="summary-pill">Inference ${summary.inference_ms || 0} ms</div>
    <div class="summary-pill" style="${cong === 'high' ? 'color:var(--color-text-danger);' : ''}">Congestion ${cong.toUpperCase()}</div>
    <div class="summary-pill">Avg speed ${spd > 0 ? spd.toFixed(1) + " km/h" : "—"}</div>
  `;

  const ordered = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!ordered.length) {
    elements.detectionList.innerHTML =
      '<div class="placeholder" style="max-width:none;">Không có đối tượng nào được phát hiện.</div>';
    return;
  }
  elements.detectionList.innerHTML = ordered.map(([cls, cnt]) => `
    <div class="det-item">
      <div class="det-main">
        <div class="det-class">
          <span class="det-dot" style="background:${(classColors || {})[cls] || "#ffffff"}"></span>
          <span>${cls}</span>
        </div>
        <div class="det-meta">${cnt}</div>
      </div>
    </div>`).join("");
}

function updateLiveStatsBar(data, liveResult) {
  const bar = document.getElementById("live-stats-bar");
  if (!bar) return;
  const running = Boolean(data.running);
  bar.style.display = running ? "" : "none";
  if (!running) return;

  const spd = data.speed_summary?.avg_kmh ?? 0;
  const cong = (data.congestion_summary?.level || "low").toLowerCase();
  const vehicles = liveResult.total_vehicles ?? 0;
  const cameras  = liveResult.camera_count ?? 0;
  const cycle    = data.cycle_count ?? 0;

  const vehicleEl = document.getElementById("live-stat-vehicles");
  const speedEl   = document.getElementById("live-stat-speed");
  const congEl    = document.getElementById("live-stat-congestion");
  const camEl     = document.getElementById("live-stat-cameras");
  const cycleEl   = document.getElementById("live-stat-cycle");

  if (vehicleEl) vehicleEl.innerHTML = `<i class="ti ti-car" style="margin-right:4px;"></i>${vehicles} xe`;
  if (speedEl) {
    speedEl.innerHTML = `<i class="ti ti-gauge" style="margin-right:4px;"></i>${spd > 0 ? spd.toFixed(1) + " km/h" : "— km/h"}`;
  }
  if (congEl) {
    const congColors = { low: "b-green", moderate: "b-amber", high: "b-red" };
    congEl.className = `badge ${congColors[cong] || "b-gray"}`;
    congEl.innerHTML = `<i class="ti ti-traffic-cone" style="margin-right:4px;"></i>${cong.toUpperCase()}`;
    if (cong === "high") congEl.style.animation = "cong-pulse 1.4s infinite alternate";
    else congEl.style.animation = "";
  }
  if (camEl) camEl.innerHTML = `<i class="ti ti-video" style="margin-right:4px;"></i>${cameras} cam`;
  if (cycleEl) cycleEl.textContent = `cycle ${cycle}`;
}

function resetDownloads() {
  elements.downloadPrimary.style.display = "none";
  elements.downloadJson.style.display    = "none";
}
