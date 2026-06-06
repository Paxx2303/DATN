/**
 * FishEye8K Utility Helpers
 */

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function resolveApplyFisheye(fisheyeEnabled, sourceLayout, { forLive = false } = {}) {
  if (fisheyeEnabled === "true") return "true";
  if (fisheyeEnabled === "false") return "false";
  if (forLive) return "false";
  return sourceLayout === "normal" ? "true" : "false";
}

export function normalizeExternalCameraUrl(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(rawValue)) {
    return rawValue;
  }
  return `https://${rawValue}`;
}

/**
 * Draws the custom bar chart representing detected object counts onto a canvas.
 * Consolidates the original canvas renderClassChart drawing routine.
 */
export function drawClassChart(canvas, classTotals, classColors) {
  if (!canvas) return;

  const labels = Object.keys(classTotals);
  const values = Object.values(classTotals);
  const ctx = canvas.getContext("2d");
  
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const pad = { top: 30, right: 20, bottom: 52, left: 56 };
  const chartWidth = canvas.width - pad.left - pad.right;
  const chartHeight = canvas.height - pad.top - pad.bottom;
  const maxValue = Math.max(...values, 1);
  const slotWidth = chartWidth / labels.length;
  const barWidth = slotWidth * 0.55;
  const orderedColors = labels.map((label) => classColors[label] || "#8ea4b5");

  // Grid and labels configuration
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#93aab9";
  ctx.font = "11px Inter, sans-serif";
  ctx.textAlign = "right";

  const gridLines = 4;
  for (let index = 0; index <= gridLines; index += 1) {
    const y = pad.top + chartHeight - (index / gridLines) * chartHeight;
    const labelValue = Math.round((index / gridLines) * maxValue);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + chartWidth, y);
    ctx.stroke();
    ctx.fillText(String(labelValue), pad.left - 8, y + 4);
  }

  labels.forEach((label, index) => {
    const value = values[index];
    const barHeight = (value / maxValue) * chartHeight;
    const x = pad.left + index * slotWidth + (slotWidth - barWidth) / 2;
    const y = pad.top + chartHeight - barHeight;
    const radius = 4;

    ctx.fillStyle = orderedColors[index];
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + barWidth - radius, y);
    ctx.arcTo(x + barWidth, y, x + barWidth, y + radius, radius);
    ctx.lineTo(x + barWidth, y + barHeight);
    ctx.lineTo(x, y + barHeight);
    ctx.lineTo(x, y + radius);
    ctx.arcTo(x, y, x + radius, y, radius);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#edf5fb";
    ctx.font = "12px IBM Plex Mono, monospace";
    ctx.textAlign = "center";
    ctx.fillText(String(value), x + barWidth / 2, y - 8);

    ctx.fillStyle = "#93aab9";
    ctx.font = "11px Inter, sans-serif";
    ctx.fillText(label, x + barWidth / 2, pad.top + chartHeight + 22);
  });

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + chartHeight);
  ctx.lineTo(pad.left + chartWidth, pad.top + chartHeight);
  ctx.stroke();
}
