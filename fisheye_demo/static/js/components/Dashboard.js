/**
 * FishEye8K Dashboard Component
 */
import { elements } from './Layout.js';
import { ApiService } from '../services/api.js';
import { drawClassChart, escapeHtml } from '../utils/helpers.js';

let _dashPollTimer = null;

export function initDashboard(classColors) {
  if (elements.statsRefreshBtn) {
    elements.statsRefreshBtn.addEventListener("click", () => loadStats(classColors));
  }
  document.getElementById('dash-refresh-incidents')?.addEventListener('click', loadDashboardExtras);
  document.getElementById('dash-refresh-alerts')?.addEventListener('click', loadDashboardExtras);
}

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

export async function loadStats(classColors) {
  if (elements.statsRefreshBtn) elements.statsRefreshBtn.textContent = "…";
  try {
    const data = await ApiService.fetchStats();
    renderStatCards(data);
    drawClassChart(elements.classChart, data.class_totals || {}, classColors);
  } catch (error) {
    console.error("Failed to load dashboard stats:", error);
  } finally {
    if (elements.statsRefreshBtn) elements.statsRefreshBtn.textContent = "↻";
  }
}

export async function loadDashboardExtras() {
  try {
    const [alertsRes, incidentStatsRes, violationsRes] = await Promise.allSettled([
      ApiService.fetchAlerts(20, false),
      ApiService.fetchIncidentStats(24),
      ApiService.fetchSpeedViolations(24),
    ]);

    if (alertsRes.status === 'fulfilled') renderDashAlerts(alertsRes.value);
    if (incidentStatsRes.status === 'fulfilled') renderDashIncidentBadge(incidentStatsRes.value);
    if (violationsRes.status === 'fulfilled') renderDashViolations(violationsRes.value);
  } catch (err) {
    console.error('Dashboard extras failed:', err);
  }
}

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

function renderDashAlerts(data) {
  const container = document.getElementById('dash-alerts-list');
  if (!container) return;
  const alerts = data.alerts || [];
  if (!alerts.length) {
    container.innerHTML = '<div style="font-size:11px; color:var(--color-text-tertiary); padding:8px 0;">Không có cảnh báo gần đây.</div>';
    return;
  }
  const typeColor = {
    high_density: 'b-amber', speed_violation: 'b-red',
    WRONG_WAY: 'b-red', STOPPED_VEHICLE: 'b-orange', ILLEGAL_PARKING: 'b-amber',
  };
  container.innerHTML = alerts.slice(0, 8).map(a => {
    const ts = (a.created_at || '').slice(11, 16);
    const color = typeColor[a.alert_type] || 'b-gray';
    const ack = a.is_acknowledged ? '' :
      `<button class="btn btn-sm" style="font-size:9px;padding:1px 6px;margin-left:auto;" onclick="window._ackDashAlert(${a.id})">✓</button>`;
    return `<div class="log-line" style="align-items:center;">
      <span class="log-time">${ts}</span>
      <span class="badge ${color}" style="font-size:9px;">${escapeHtml(a.alert_type)}</span>
      <span style="font-size:10.5px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(a.message || '')}</span>
      ${ack}
    </div>`;
  }).join('');
}

function renderDashIncidentBadge(data) {
  const unack = data.unacknowledged ?? 0;
  const badge = document.getElementById('dash-incident-badge');
  if (badge) {
    badge.textContent = unack > 0 ? `${unack} chưa xử lý` : 'Không có';
    badge.className = 'badge ' + (unack > 0 ? 'b-red' : 'b-teal');
  }
  const total = document.getElementById('dash-incidents-total');
  if (total) total.textContent = String(data.total ?? 0);

  const byType = data.by_type || {};
  ['WRONG_WAY', 'STOPPED_VEHICLE', 'ILLEGAL_PARKING'].forEach(t => {
    const el = document.getElementById(`dash-inc-${t.toLowerCase()}`);
    if (el) el.textContent = String(byType[t] ?? 0);
  });
}

function renderDashViolations(data) {
  const el = document.getElementById('dash-violations-count');
  if (el) el.textContent = String(data.total ?? 0);
  const tbody = document.getElementById('dash-violations-tbody');
  if (!tbody) return;
  const violations = (data.violations || []).slice(0, 5);
  if (!violations.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="font-size:10.5px; color:var(--color-text-tertiary); padding:8px;">Không có vi phạm 24h qua.</td></tr>';
    return;
  }
  tbody.innerHTML = violations.map(v => `
    <tr style="font-size:10.5px;">
      <td>#${v.track_id}</td>
      <td>${escapeHtml(v.vehicle_type)}</td>
      <td><span class="badge b-red" style="font-size:9px;">${v.speed_kmh.toFixed(0)} km/h</span></td>
      <td style="color:var(--color-text-tertiary);">${(v.created_at || '').slice(11, 16)}</td>
    </tr>`).join('');
}

window._ackDashAlert = async function(id) {
  try {
    await ApiService.acknowledgeAlert(id);
    loadDashboardExtras();
  } catch (err) { console.error(err); }
};
