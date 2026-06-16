/**
 * FishEye8K — ALPR (Nhận diện biển số) Component
 * Upload ảnh → nhận diện biển số → lưu/tra cứu lịch sử.
 */
import { ApiService } from '../services/api.js';
import { escapeHtml } from '../utils/helpers.js';

export function initALPR() {
  document.getElementById('alpr-detect-btn')?.addEventListener('click', runAlprDetect);
  document.getElementById('alpr-refresh-btn')?.addEventListener('click', loadAlprHistory);
  document.getElementById('alpr-search-btn')?.addEventListener('click', runAlprSearch);
  document.getElementById('alpr-search-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runAlprSearch();
  });
}

export async function loadAlprHistory() {
  const tbody = document.getElementById('alpr-history-tbody');
  try {
    const data = await ApiService.fetchAlprHistory(24, 100);
    _setText('alpr-total', data.total ?? 0);
    renderPlateRows(tbody, data.plates || [], 5);
  } catch (err) {
    if (tbody) tbody.innerHTML = _emptyRow(5, `Lỗi tải: ${escapeHtml(err.message)}`);
  }
}

async function runAlprDetect() {
  const fileInput = document.getElementById('alpr-file');
  const file = fileInput?.files?.[0];
  if (!file) {
    _setText('alpr-status', 'Chọn ảnh trước');
    return;
  }
  const btn = document.getElementById('alpr-detect-btn');
  if (btn) btn.disabled = true;
  _setText('alpr-status', 'Đang xử lý…');

  try {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('conf', document.getElementById('alpr-conf')?.value || '0.25');

    const data = await ApiService.alprDetect(formData);

    if (data.available === false) {
      _setText('alpr-status', 'OCR chưa sẵn sàng');
      _renderResultMedia(null);
      const list = document.getElementById('alpr-result-list');
      if (list) list.innerHTML = `<div style="color:var(--color-text-tertiary); font-size:11.5px;">${escapeHtml(data.message || '')}</div>`;
      return;
    }

    _setText('alpr-status', 'Sẵn sàng');
    _setText('alpr-last-count', data.total ?? 0);
    _setText('alpr-last-vehicles', data.vehicles_detected ?? 0);
    _renderResultMedia(data.annotated_image);
    renderDetectList(data.plates || []);
    loadAlprHistory();
  } catch (err) {
    _setText('alpr-status', 'Lỗi');
    const list = document.getElementById('alpr-result-list');
    if (list) list.innerHTML = `<div style="color:var(--color-text-danger); font-size:11.5px;">${escapeHtml(err.message)}</div>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runAlprSearch() {
  const q = document.getElementById('alpr-search-input')?.value?.trim();
  const box = document.getElementById('alpr-search-result');
  if (!q) {
    if (box) box.textContent = 'Nhập từ khoá để tra cứu trong lịch sử.';
    return;
  }
  try {
    const data = await ApiService.searchAlpr(q, 168);
    if (!data.plates.length) {
      box.innerHTML = `<span style="color:var(--color-text-tertiary);">Không tìm thấy biển số khớp "${escapeHtml(q)}".</span>`;
      return;
    }
    box.innerHTML = `<div style="margin-bottom:6px; color:var(--color-text-primary);">Tìm thấy <strong>${data.total}</strong> kết quả:</div>` +
      data.plates.map((p) => `
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--color-border-subtle);">
          <strong style="font-family:monospace;">${escapeHtml(p.plate_text)}</strong>
          <span style="color:var(--color-text-tertiary);">${escapeHtml(p.vehicle_type || '')} · ${escapeHtml(p.created_at || '')}</span>
        </div>`).join('');
  } catch (err) {
    box.innerHTML = `<span style="color:var(--color-text-danger);">${escapeHtml(err.message)}</span>`;
  }
}

// ── Rendering helpers ──────────────────────────────────────────────────────────

function renderDetectList(plates) {
  const list = document.getElementById('alpr-result-list');
  if (!list) return;
  if (!plates.length) {
    list.innerHTML = '<div style="color:var(--color-text-tertiary); font-size:11.5px;">Không nhận diện được biển số nào.</div>';
    return;
  }
  list.innerHTML = plates.map((p) => `
    <span class="badge b-amber" style="margin:2px; font-family:monospace;">
      ${escapeHtml(p.plate)} · ${(p.confidence * 100).toFixed(0)}%
    </span>`).join('');
}

function renderPlateRows(tbody, plates, cols) {
  if (!tbody) return;
  if (!plates.length) {
    tbody.innerHTML = _emptyRow(cols, 'Chưa có biển số nào.');
    return;
  }
  tbody.innerHTML = plates.map((p) => `
    <tr style="border-top:1px solid var(--color-border-subtle);">
      <td style="padding:6px 8px; font-family:monospace; font-weight:700;">${escapeHtml(p.plate_text)}</td>
      <td style="padding:6px 8px;">${(Number(p.confidence) * 100).toFixed(0)}%</td>
      <td style="padding:6px 8px;">${escapeHtml(p.vehicle_type || '—')}</td>
      <td style="padding:6px 8px;">${escapeHtml(p.camera_id || '—')}</td>
      <td style="padding:6px 8px; color:var(--color-text-tertiary);">${escapeHtml(p.created_at || '')}</td>
    </tr>`).join('');
}

function _renderResultMedia(src) {
  const box = document.getElementById('alpr-result-media');
  if (!box) return;
  box.innerHTML = src
    ? `<img src="${src}" alt="ALPR result" style="width:100%; border-radius:8px;">`
    : 'Ảnh kết quả sẽ hiển thị tại đây.';
}

function _emptyRow(cols, msg) {
  return `<tr><td colspan="${cols}" style="text-align:center; color:var(--color-text-tertiary); padding:16px;">${escapeHtml(msg)}</td></tr>`;
}

function _setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(val);
}
