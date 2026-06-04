/**
 * FishEye8K Workspace Component
 */
import { elements, setToast, setLoading, updateControlLabels } from './Layout.js';
import { appState } from '../state/appState.js';
import { ApiService } from '../services/api.js';

export function initWorkspace(classNames, classColors, onJobCompleted) {
  // Bind input element clicks and change handlers
  elements.uploadZone.addEventListener("click", () => elements.fileInput.click());
  
  elements.fileInput.addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) handleSelectedFile(file);
  });

  // Drag and drop event listeners
  elements.uploadZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    elements.uploadZone.classList.add("drag");
  });

  elements.uploadZone.addEventListener("dragleave", () => {
    elements.uploadZone.classList.remove("drag");
  });

  elements.uploadZone.addEventListener("drop", (event) => {
    event.preventDefault();
    elements.uploadZone.classList.remove("drag");
    const file = event.dataTransfer.files[0];
    if (file) handleSelectedFile(file);
  });

  // Range and text inputs
  [
    elements.confidence,
    elements.iou,
    elements.fisheyeStrength,
    elements.fisheyeRadius,
  ].forEach((element) => element.addEventListener("input", updateControlLabels));

  // Trigger buttons
  elements.detectBtn.addEventListener("click", () => runDetection(classNames, classColors, onJobCompleted));
  elements.convertBtn.addEventListener("click", () => runConversion(onJobCompleted));
  elements.clearBtn.addEventListener("click", clearCurrentFile);

  // Initialize placeholder views
  renderPlaceholder(elements.originalMedia, "The uploaded image or video preview will appear here.");
  renderPlaceholder(elements.preprocessedMedia, "If preprocessing is enabled, the warped fisheye output will appear here.");
  renderPlaceholder(elements.resultMedia, "Detection annotations or converted fisheye video will appear here.");
}

/**
 * Load an example image from /api/examples/<scenario>.jpg into the workspace.
 */
export async function loadExampleIntoWorkspace(scenario) {
  try {
    const resp = await fetch(`/api/examples/${scenario}.jpg`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const file = new File([blob], `${scenario}_example.jpg`, { type: "image/jpeg" });
    handleSelectedFile(file);
  } catch (e) {
    console.error("Failed to load example:", e);
  }
}

/**
 * Handle selected file and probe sizes
 */
export function handleSelectedFile(file) {
  if (!file) return;

  const fileType = file.type || "";
  const isImage = fileType.startsWith("image/") || /\.(jpg|jpeg|png|bmp|webp|tiff|tif|heic|heif|avif|jfif|gif)$/i.test(file.name);
  const isVideo = fileType.startsWith("video/") || /\.(mp4|avi|mov|mkv|wmv|flv|webm)$/i.test(file.name);
  if (!isImage && !isVideo) {
    setToast("Please choose an image or video file.");
    return;
  }

  appState.set("currentFile", file);
  appState.set("currentMediaType", isVideo ? "video" : "image");

  if (appState.currentObjectUrl) {
    URL.revokeObjectURL(appState.currentObjectUrl);
  }
  appState.set("currentObjectUrl", URL.createObjectURL(file));

  renderMedia(elements.originalMedia, appState.currentObjectUrl, appState.currentMediaType);
  elements.originalMeta.textContent = `${(file.size / 1024).toFixed(0)} KB`;
  elements.selectedFile.textContent = file.name;
  elements.selectedType.textContent = appState.currentMediaType;
  
  resetResultView();
  updateButtonsForCurrentFile();

  if (appState.currentMediaType === "image") {
    const probe = new Image();
    probe.onload = () => {
      elements.selectedSize.textContent = `${probe.naturalWidth} x ${probe.naturalHeight}`;
    };
    probe.src = appState.currentObjectUrl;
  } else {
    const probe = document.createElement("video");
    probe.preload = "metadata";
    probe.onloadedmetadata = () => {
      elements.selectedSize.textContent = `${probe.videoWidth} x ${probe.videoHeight}`;
    };
    probe.src = appState.currentObjectUrl;
  }
}

/**
 * Resets Workspace outputs back to default awaiting states.
 */
export function resetResultView() {
  appState.set("latestRecord", null);
  elements.requestId.textContent = "none";
  elements.savedResult.textContent = "pending";
  elements.preprocessedMeta.textContent = "waiting";
  elements.resultMeta.textContent = "waiting";
  resetDownloads();
  
  renderPlaceholder(elements.preprocessedMedia, "If preprocessing is enabled, the warped fisheye output will appear here.");
  renderPlaceholder(elements.resultMedia, "Detection annotations or converted fisheye video will appear here.");
  elements.statsGrid.innerHTML = "";
  elements.summaryRow.innerHTML = '<div class="summary-pill">No operation has run yet.</div>';
  elements.detectionList.innerHTML = "";
}

export function clearCurrentFile() {
  appState.set("currentFile", null);
  appState.set("currentMediaType", null);
  if (appState.currentObjectUrl) {
    URL.revokeObjectURL(appState.currentObjectUrl);
  }
  appState.set("currentObjectUrl", null);
  elements.fileInput.value = "";
  elements.selectedFile.textContent = "none";
  elements.selectedType.textContent = "unknown";
  elements.selectedSize.textContent = "unknown";
  elements.originalMeta.textContent = "waiting";
  
  renderPlaceholder(elements.originalMedia, "The uploaded image or video preview will appear here.");
  resetResultView();
  setLoading(false, appState);
  updateButtonsForCurrentFile();
}

function updateButtonsForCurrentFile() {
  const hasFile = !!appState.currentFile;
  elements.detectBtn.disabled = !hasFile;
  elements.convertBtn.disabled = !hasFile;
  
  const showVideoFps = appState.currentMediaType === "video";
  elements.videoDetectFpsWrap.style.display = showVideoFps ? "" : "none";
  if (!showVideoFps) {
    elements.videoDetectFps.value = "";
  }
}

function getRequestedFisheyeState() {
  if (elements.fisheyeEnabled.value === "true") return "true";
  if (elements.fisheyeEnabled.value === "false") return "false";
  return "";
}

function buildFormData(fieldName) {
  const formData = new FormData();
  formData.append(fieldName, appState.currentFile);
  formData.append("model_key", elements.modelKey.value);
  formData.append("conf", elements.confidence.value);
  formData.append("iou", elements.iou.value);
  formData.append("source_layout", elements.sourceLayout.value);
  formData.append("fisheye_strength", elements.fisheyeStrength.value);
  formData.append("fisheye_radius", elements.fisheyeRadius.value);
  formData.append("fisheye_effect", elements.fisheyeEffect.value);
  
  const applyValue = getRequestedFisheyeState();
  if (applyValue) {
    formData.append("apply_fisheye", applyValue);
  }
  
  if (appState.currentMediaType === "video") {
    const rawFps = elements.videoDetectFps.value.trim();
    if (rawFps !== "" && Number(rawFps) > 0) {
      formData.append("video_detect_fps", rawFps);
    }
  }
  return formData;
}

/**
 * Execute YOLOv11 / SAHI Object Detection
 */
async function runDetection(classNames, classColors, onJobCompleted) {
  if (!appState.currentFile) {
    setToast("Select an image or video first.");
    return;
  }

  setLoading(true, appState);
  try {
    const formData = buildFormData("file");
    const data = await ApiService.runDetection(formData);

    appState.set("latestRecord", data.record);
    elements.requestId.textContent = data.request_id;
    elements.savedResult.textContent = data.record.id;
    elements.preprocessedMeta.textContent = data.preprocessing.enabled ? "fisheye ready" : "bypassed";

    if (data.media_type === "video") {
      elements.resultMeta.textContent = `${data.summary.total_frames} frames`;
      const previewAnnotated = data.record.artifact_urls?.preview_annotated || null;
      renderMedia(elements.preprocessedMedia, previewAnnotated, "image");
      renderMedia(elements.resultMedia, data.record.artifact_urls?.annotated_video || null, "video");
      renderVideoDetectionSummary(data, classColors);
      setArtifactLinks(data.record, "annotated_video");
    } else {
      elements.resultMeta.textContent = `${data.inference_ms} ms`;
      renderMedia(elements.preprocessedMedia, data.preprocessed, "image");
      renderMedia(elements.resultMedia, data.result, "image");
      renderDetectionSummary(data, classNames, classColors);
      setArtifactLinks(data.record, "annotated");
    }

    // Fire callback to trigger background reload on list dependencies (Stats, Health, Logs, History)
    if (onJobCompleted) {
      await onJobCompleted();
    }

    const successMessage = data.media_type === "video"
      ? `Saved video detection ${data.record.id} with ${data.summary.total_frames} frames.`
      : `Saved run ${data.record.id} with ${data.total_objects} detections.`;
    setToast(successMessage, true);
  } catch (error) {
    setToast(error.message || "Detection failed.");
  } finally {
    setLoading(false, appState);
  }
}

/**
 * Execute Fisheye Preprocessing/Conversion
 */
async function runConversion(onJobCompleted) {
  if (!appState.currentFile) {
    setToast("Select an image or video first.");
    return;
  }

  setLoading(true, appState);
  try {
    const formData = buildFormData("media");
    const data = await ApiService.runConversion(formData);

    appState.set("latestRecord", data.record);
    elements.requestId.textContent = data.request_id;
    elements.savedResult.textContent = data.record.id;
    elements.preprocessedMeta.textContent = `${data.preprocessing.effect} | ${Number(data.preprocessing.strength).toFixed(2)}`;

    if (data.media_type === "image") {
      renderMedia(elements.preprocessedMedia, data.result, "image");
      renderMedia(elements.resultMedia, data.result, "image");
      elements.resultMeta.textContent = "fisheye image";
      setArtifactLinks(data.record, "fisheye_image");
    } else {
      renderMedia(elements.preprocessedMedia, data.preview_result, "image");
      renderMedia(elements.resultMedia, data.record.artifact_urls.fisheye_video, "video");
      elements.resultMeta.textContent = `${data.video_info.processed_frames} frames`;
      setArtifactLinks(data.record, "fisheye_video");
    }

    renderConversionSummary(data);
    
    if (onJobCompleted) {
      await onJobCompleted();
    }
    setToast(`Saved fisheye conversion ${data.record.id}.`, true);
  } catch (error) {
    setToast(error.message || "Conversion failed.");
  } finally {
    setLoading(false, appState);
  }
}

/**
 * Rendering subroutines
 */
export function renderPlaceholder(target, message) {
  if (!target) return;
  target.innerHTML = `<div class="placeholder">${message}</div>`;
}

export function renderMedia(target, source, mediaType, cacheBustToken = null) {
  if (!target) return;
  target.innerHTML = "";
  if (!source) {
    renderPlaceholder(target, "No media available.");
    return;
  }
  if (mediaType === "video") {
    const video = document.createElement("video");
    video.src = source;
    video.controls = true;
    video.muted = true;
    target.appendChild(video);
    return;
  }
  const image = document.createElement("img");
  let src = source;
  if (
    cacheBustToken != null &&
    typeof source === "string" &&
    source.startsWith("data:")
  ) {
    const base = source.split("#")[0];
    src = `${base}#${String(cacheBustToken).replace(/[^a-zA-Z0-9._-]/g, "")}`;
  }
  image.src = src;
  image.alt = "preview";
  target.appendChild(image);
}

function resetDownloads() {
  elements.downloadPrimary.style.display = "none";
  elements.downloadJson.style.display = "none";
  elements.downloadPrimary.href = "#";
  elements.downloadJson.href = "#";
}

export function setArtifactLinks(record, preferredKey) {
  if (!record || !record.artifact_urls) {
    resetDownloads();
    return;
  }
  const keys = Object.keys(record.artifact_urls);
  const primaryKey = preferredKey && record.artifact_urls[preferredKey] ? preferredKey : keys.find((key) => key !== "metadata");
  if (primaryKey) {
    elements.downloadPrimary.href = record.artifact_urls[primaryKey];
    elements.downloadPrimary.textContent = `Open ${primaryKey.replaceAll("_", " ")}`;
    elements.downloadPrimary.style.display = "inline-flex";
  }
  if (record.artifact_urls.metadata) {
    elements.downloadJson.href = record.artifact_urls.metadata;
    elements.downloadJson.style.display = "inline-flex";
  }
}

function renderDetectionSummary(data, classNames, classColors) {
  const counts = data.class_counts || {};
  elements.statsGrid.innerHTML = classNames.map((name) => `
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:${classColors[name] || "#ffffff"}; font-size:18px; font-weight:700;">${counts[name] || 0}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">${name}</div>
    </div>
  `).join("");

  elements.summaryRow.innerHTML = `
    <div class="summary-pill">Task detect</div>
    <div class="summary-pill">Model ${data.model?.loaded_from_name || "unknown"}</div>
    <div class="summary-pill">Objects ${data.total_objects}</div>
    <div class="summary-pill">Inference ${data.inference_ms} ms</div>
    <div class="summary-pill">Layout ${data.preprocessing.source_layout}</div>
    <div class="summary-pill">Fisheye ${data.preprocessing.enabled ? "on" : "off"}</div>
  `;

  if (!data.detections.length) {
    elements.detectionList.innerHTML = '<div class="placeholder" style="max-width:none;">No objects detected above the configured threshold.</div>';
    return;
  }

  elements.detectionList.innerHTML = data.detections.map((item) => `
    <div class="det-item">
      <div class="det-main">
        <div class="det-class">
          <span class="det-dot" style="background:${(classColors || {})[item.class_name] || "#ffffff"}"></span>
          <span>${item.class_name || item.class || "unknown"}</span>
        </div>
        <div class="det-meta">${(item.confidence * 100).toFixed(1)}%</div>
      </div>
      <div class="det-meta">bbox: [${item.bbox.join(", ")}]</div>
    </div>
  `).join("");
}

function renderVideoDetectionSummary(data, classColors) {
  const summary = data.summary || {};
  const counts = summary.class_counts || {};
  const orderedClasses = Object.entries(counts).sort((left, right) => right[1] - left[1]);

  elements.statsGrid.innerHTML = `
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-info); font-size:18px; font-weight:700;">${summary.total_frames || 0}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">Frames</div>
    </div>
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-warning); font-size:18px; font-weight:700;">${summary.fps_original || 0}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">FPS gốc</div>
    </div>
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-success); font-size:18px; font-weight:700;">${summary.inference_ms_avg || 0}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">Avg ms / infer</div>
    </div>
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-primary); font-size:18px; font-weight:700;">${summary.processing_fps ?? "—"}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">FPS xử lý</div>
    </div>
  `;

  const tgt = summary.target_detect_fps;
  const stride = summary.detection_stride;
  const extraPills = [
    tgt != null && tgt > 0 ? `<div class="summary-pill">Target detect ${tgt} fps</div>` : "",
    stride && stride > 1 ? `<div class="summary-pill">Stride ${stride}</div>` : "",
  ].filter(Boolean).join("");
  
  elements.summaryRow.innerHTML = `
    <div class="summary-pill">Task detect</div>
    <div class="summary-pill">Model ${data.model?.loaded_from_name || "unknown"}</div>
    <div class="summary-pill">Media video</div>
    <div class="summary-pill">Resolution ${summary.resolution || "unknown"}</div>
    <div class="summary-pill">Detections ${summary.total_detections || 0}</div>
    <div class="summary-pill">Layout ${data.preprocessing.source_layout}</div>
    <div class="summary-pill">Fisheye ${data.preprocessing.enabled ? "on" : "off"}</div>
    ${extraPills}
  `;

  if (!orderedClasses.length) {
    elements.detectionList.innerHTML = '<div class="placeholder" style="max-width:none;">No objects were accumulated across the processed frames.</div>';
    return;
  }

  elements.detectionList.innerHTML = orderedClasses.map(([className, count]) => `
    <div class="det-item">
      <div class="det-main">
        <div class="det-class">
          <span class="det-dot" style="background:${classColors[className] || "#ffffff"}"></span>
          <span>${className}</span>
        </div>
        <div class="det-meta">${count}</div>
      </div>
      <div class="det-meta">Accumulated detections across all frames</div>
    </div>
  `).join("");
}

function renderConversionSummary(data) {
  elements.statsGrid.innerHTML = `
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-info); font-size:18px; font-weight:700;">${data.media_type}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">Media type</div>
    </div>
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-warning); font-size:18px; font-weight:700;">${data.preprocessing.effect}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">Effect</div>
    </div>
    <div class="stat-card" style="background:var(--color-background-secondary); border-radius:var(--border-radius-md); padding:10px 12px; border:0.5px solid var(--color-border-tertiary);">
      <div class="count" style="color:var(--color-text-success); font-size:18px; font-weight:700;">${Number(data.preprocessing.strength).toFixed(2)}</div>
      <div class="name" style="font-size:10px; color:var(--color-text-secondary); text-transform:uppercase; margin-top:2px;">Strength</div>
    </div>
  `;

  const videoInfo = data.video_info;
  elements.summaryRow.innerHTML = `
    <div class="summary-pill">Task convert</div>
    <div class="summary-pill">Layout ${data.preprocessing.source_layout}</div>
    <div class="summary-pill">Radius ${Number(data.preprocessing.radius).toFixed(2)}</div>
    ${videoInfo ? `<div class="summary-pill">Frames ${videoInfo.processed_frames}</div>` : ""}
    ${videoInfo ? `<div class="summary-pill">Duration ${videoInfo.duration_seconds}s</div>` : ""}
  `;

  elements.detectionList.innerHTML = '<div class="placeholder" style="max-width:none;">Conversion completed. Use the saved artifacts to inspect the warped fisheye media.</div>';
}
