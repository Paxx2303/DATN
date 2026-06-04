/**
 * FishEye8K Dashboard Component
 */
import { elements } from './Layout.js';
import { ApiService } from '../services/api.js';
import { drawClassChart } from '../utils/helpers.js';

/**
 * Initializes the Dashboard component, hooks click events.
 */
export function initDashboard(classColors) {
  if (elements.statsRefreshBtn) {
    elements.statsRefreshBtn.addEventListener("click", () => loadStats(classColors));
  }
}

/**
 * Renders the vehicle/pedestrian category color legends.
 */
export function renderLegend(classNames, classColors) {
  if (!elements.legend) return;
  
  elements.legend.innerHTML = classNames.map((name) => `
    <div class="legend-item">
      <span class="legend-dot" style="background:${classColors[name] || "#ffffff"}"></span>
      <div>${name}</div>
    </div>
  `).join("");
  
  if (elements.classCount) {
    elements.classCount.textContent = String(classNames.length);
  }
}

/**
 * Loads system statistics from the backend and updates elements.
 */
export async function loadStats(classColors) {
  if (elements.statsRefreshBtn) {
    elements.statsRefreshBtn.textContent = "…";
  }

  try {
    const data = await ApiService.fetchStats();
    renderStatCards(data);
    
    // Draw the custom HTML canvas chart
    drawClassChart(elements.classChart, data.class_totals || {}, classColors);
  } catch (error) {
    console.error("Failed to load dashboard stats:", error);
  } finally {
    if (elements.statsRefreshBtn) {
      elements.statsRefreshBtn.textContent = "↻";
    }
  }
}

/**
 * Updates stats metric widgets.
 */
function renderStatCards(data) {
  const totalRuns = Number(data.total_runs || 0);
  if (totalRuns === 0) {
    elements.statTotal.textContent = "—";
    elements.statDetect.textContent = "—";
    elements.statConvert.textContent = "—";
    elements.statInference.textContent = "—";
    return;
  }

  elements.statTotal.textContent = String(data.total_runs ?? "—");
  elements.statDetect.textContent = String(data.total_detect ?? "—");
  elements.statConvert.textContent = String(data.total_convert ?? "—");
  elements.statInference.textContent = data.avg_inference_ms ? `${data.avg_inference_ms} ms` : "—";
}
