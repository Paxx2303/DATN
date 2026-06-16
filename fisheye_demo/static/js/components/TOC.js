/**
 * FishEye8K — Trung tâm Điều hành Giao thông (TOC Dashboard)
 * Tổng hợp: Live Stats | Lưu lượng | Sự cố | Vi phạm tốc độ | Heatmap | Export
 */
import { ApiService } from '../services/api.js';
import { escapeHtml } from '../utils/helpers.js';

let _tocPollTimer = null;
const _POLL_MS = 8000;

export function initTOC() {
  document.getElementById('toc-refresh-btn')?.addEventListener('click', loadTOC);
  document.getElementById('toc-export-csv-btn')?.addEventListener('click', () => exportReport('traffic'));
  document.getElementById('toc-export-incidents-btn')?.addEventListener('click', () => exportReport('incidents'));
  document.getElementById('toc-export-violations-btn')?.addEventListener('click', () => exportReport('violations'));
  document.getElementById('toc-export-json-btn')?.addEventListener('click', exportJSON);
  document.getElementById('toc-test-webhook-btn')?.addEventListener('click', testWebhook);
}

export function startTOCPolling() {
  if (_tocPollTimer) return;
  loadTOC();
  _tocPollTimer = setInterval(loadTOC, _POLL_MS);
}

export function stopTOCPolling() {
  if (_tocPollTimer) {
    clearInterval(_tocPollTimer);
    _tocPollTimer = null;
  }
}

async function loadTOC() {
  try {
    const [analytics, incidentStats, violations, alerts] = await Promise.allSettled([
      ApiService.fetchAnalytics(24),
      ApiService.fetchIncidentStats(24),
      ApiService.fetchSpeedViolations(24),
      ApiService.fetchAlerts(20, false),
    ]);

    if (analytics.status === 'fulfilled') renderTOCSummary(analytics.value);
    if (incidentStats.status === 'fulfilled') renderIncidentStats(incidentStats.value);
    if (violations.status === 'fulfilled') renderViolationsSummary(violations.value);
    if (alerts.status === 'fulfilled') renderTOCAlerts(alerts.value);
  } catch (err) {
    console.error('[TOC] Load error:', err);
  }
}

// ── Summary Cards ─────────────────────────────────────────────────────────────

function renderTOCSummary(data) {
  _setEl('toc-total-detections', data.total_detections ?? '—');
  const density = data.density || {};
  _setEl('toc-current-density', density.current ?? '—');
  _setEl('toc-peak-density', density.peak ?? '—');
  const trend = density.trend || 'stable';
  const trendEl = document.getElementById('toc-density-trend');
  if (trendEl) {
    trendEl.className = 'badge ' + (trend === 'increasing' ? 'b-red' : trend === 'decreasing' ? 'b-teal' : 'b-gray');
    trendEl.textContent = { increasing: '↑ Tăng', decreasing: '↓ Giảm', stable: '→ Ổn định' }[trend] || trend;
  }
}

// ── Incident Stats ────────────────────────────────────────────────────────────

function renderIncidentStats(data) {
  _setEl('toc-incidents-total', data.total ?? 0);
  _setEl('toc-incidents-unack', data.unacknowledged ?? 0);
  const byType = data.by_type || {};
  _setEl('toc-incidents-wrong-way', byType.WRONG_WAY ?? 0);
  _setEl('toc-incidents-stopped', byType.STOPPED_VEHICLE ?? 0);
  _setEl('toc-incidents-parking', byType.ILLEGAL_PARKING ?? 0);

  // Badge badge trên sidebar
  const badge = document.getElementById('toc-sidebar-badge');
  if (badge) {
    const unack = data.unacknowledged ?? 0;
    badge.textContent = unack > 0 ? String(unack) : '';
    badge.style.display = unack > 0 ? 'inline-flex' : 'none';
  }
}

// ── Speed Violations ──────────────────────────────────────────────────────────

function renderViolationsSummary(data) {
  _setEl('toc-violations-total', data.total ?? 0);
  const violations = data.violations || [];
  const maxSpeed = violations.length
    ? Math.max(...violations.map(v => v.speed_kmh || 0))
    : 0;
  _setEl('toc-violations-max-speed', maxSpeed > 0 ? `${maxSpeed.toFixed(0)} km/h` : '—');

  // Render violations table
  const tbody = document.getElementById('toc-violations-tbody');
  if (!tbody) return;
  if (!violations.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--color-text-tertiary); padding:16px;">Không có vi phạm trong 24h.</td></tr>';
    return;
  }
  tbody.innerHTML = violations.slice(0, 20).map(v => {
    const excess = (v.speed_kmh - v.limit_kmh).toFixed(0);
    const ts = v.created_at ? v.created_at.slice(0, 16) : '—';
    return `<tr>
      <td>${escapeHtml(v.camera_id || '—')}</td>
      <td>#${v.track_id}</td>
      <td>${escapeHtml(v.vehicle_type || '—')}</td>
      <td><span class="badge b-red" style="font-size:10px;">${v.speed_kmh.toFixed(0)} km/h</span></td>
      <td>${v.limit_kmh} km/h (+${excess})</td>
      <td style="font-size:10px; color:var(--color-text-tertiary);">${ts}</td>
    </tr>`;
  }).join('');
}

// ── Alerts Table ──────────────────────────────────────────────────────────────

function renderTOCAlerts(data) {
  const alerts = data.alerts || [];
  const tbody = document.getElementById('toc-alerts-tbody');
  if (!tbody) return;

  if (!alerts.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--color-text-tertiary); padding:16px;">Không có cảnh báo gần đây.</td></tr>';
    return;
  }

  const typeColor = {
    high_density:    'b-amber',
    speed_violation: 'b-red',
    WRONG_WAY:       'b-red',
    STOPPED_VEHICLE: 'b-orange',
    ILLEGAL_PARKING: 'b-amber',
  };

  tbody.innerHTML = alerts.slice(0, 20).map(a => {
    const ts = (a.created_at || '').slice(0, 16);
    const ack = a.is_acknowledged ? '<span class="badge b-teal" style="font-size:9px;">✓</span>'
      : `<button class="btn btn-sm" style="font-size:9px; padding:2px 8px;" onclick="window._ackAlert(${a.id})">Xác nhận</button>`;
    const color = typeColor[a.alert_type] || 'b-gray';
    return `<tr>
      <td><span class="badge ${color}" style="font-size:9.5px;">${escapeHtml(a.alert_type)}</span></td>
      <td style="font-size:10px;">${escapeHtml(a.camera_source || '—')}</td>
      <td style="font-size:10.5px; max-width:260px; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(a.message || '—')}</td>
      <td style="font-size:10px; color:var(--color-text-tertiary);">${ts}</td>
      <td>${ack}</td>
    </tr>`;
  }).join('');
}

// ── Heatmap ───────────────────────────────────────────────────────────────────

export async function loadTOCHeatmap() {
  try {
    const data = await ApiService.fetchHeatmap();
    const img = document.getElementById('toc-heatmap-img');
    if (img && data.heatmap_b64) {
      img.src = data.heatmap_b64;
    }
    const stats = data.stats || {};
    _setEl('toc-heatmap-updates', stats.total_updates ?? 0);
  } catch (err) {
    console.warn('[TOC] Heatmap load failed:', err.message);
  }
}

// ── Export ────────────────────────────────────────────────────────────────────

function exportReport(sheet) {
  const hours = parseInt(document.getElementById('toc-export-hours')?.value || '24', 10);
  window.open(`/api/export/csv?sheet=${sheet}&hours=${hours}`, '_blank');
}

function exportJSON() {
  const hours = parseInt(document.getElementById('toc-export-hours')?.value || '24', 10);
  window.open(`/api/export/json?hours=${hours}`, '_blank');
}

async function testWebhook() {
  const btn = document.getElementById('toc-test-webhook-btn');
  if (btn) btn.textContent = '…';
  try {
    const result = await ApiService.testWebhook();
    const msg = result.status === 'ok' ? `✓ Webhook OK (${result.http_status})` : `✗ ${result.error || result.status}`;
    if (btn) btn.textContent = msg;
    setTimeout(() => { if (btn) btn.textContent = 'Test Webhook'; }, 3000);
  } catch (err) {
    if (btn) btn.textContent = '✗ Error';
    setTimeout(() => { if (btn) btn.textContent = 'Test Webhook'; }, 3000);
  }
}

// ── Global handlers ───────────────────────────────────────────────────────────

window._ackAlert = async function(alertId) {
  try {
    await ApiService.acknowledgeAlert(alertId);
    loadTOC();
  } catch (err) {
    console.error('Acknowledge failed:', err);
  }
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function _setEl(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(value);
}
