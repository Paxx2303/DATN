/**
 * FishEye8K System Logs Terminal Component
 */
import { setToast } from './Layout.js';
import { ApiService } from '../services/api.js';
import { escapeHtml } from '../utils/helpers.js';

const logsElements = {
  search: document.getElementById("logs-search"),
  level: document.getElementById("logs-level"),
  limit: document.getElementById("logs-limit"),
  pause: document.getElementById("logs-pause"),
  clearBtn: document.getElementById("logs-clear-btn"),
  terminal: document.getElementById("logs-terminal"),
  content: document.getElementById("logs-content"),
};

let isFetchingLogs = false;

export function initLogsTerminal() {
  if (!logsElements.terminal) return;

  // Clear screen
  logsElements.clearBtn.addEventListener("click", () => {
    logsElements.content.innerHTML = `<div style="color: #64748b; font-style: italic;">Đã xóa màn hình. Nhật ký hệ thống mới sẽ tiếp tục xuất hiện bên dưới...</div>`;
    setToast("Terminal screen cleared.", true);
  });

  // Level and limits filters change listeners
  [logsElements.level, logsElements.limit].forEach(el => {
    el.addEventListener("change", loadLogs);
  });

  // Debounced keyboard keywords search
  let searchDebounceTimer;
  logsElements.search.addEventListener("input", () => {
    window.clearTimeout(searchDebounceTimer);
    searchDebounceTimer = window.setTimeout(loadLogs, 300);
  });

  // Start background log polling (runs every 1.5s when logs tab is visible)
  window.setInterval(() => {
    const logsPageActive = document.getElementById("page-logs").classList.contains("active");
    const isPaused = logsElements.pause.checked;

    if (logsPageActive && !isPaused) {
      loadLogs();
    }
  }, 1500);
}

/**
 * Loads system logs from backend and updates logs console container.
 */
export async function loadLogs() {
  if (isFetchingLogs || !logsElements.terminal) return;
  isFetchingLogs = true;

  try {
    const queryParams = {
      limit: logsElements.limit.value || "100",
      level: logsElements.level.value || "",
      q: logsElements.search.value || "",
    };

    const data = await ApiService.fetchLogs(queryParams);
    
    // Check scroll position before updating content (auto scroll only if user was already near the bottom)
    const isScrolledToBottom = logsElements.terminal.scrollHeight - logsElements.terminal.clientHeight - logsElements.terminal.scrollTop < 40;

    if (data.logs && data.logs.length > 0) {
      logsElements.content.innerHTML = data.logs.map(formatLogLine).join("");
    } else {
      logsElements.content.innerHTML = `<div style="color: #64748b; font-style: italic;">Không tìm thấy nhật ký hệ thống nào khớp với bộ lọc.</div>`;
    }

    if (isScrolledToBottom) {
      scrollToBottom();
    }
  } catch (error) {
    console.error("Failed to load logs:", error);
  } finally {
    isFetchingLogs = false;
  }
}

/**
 * Scrolls the console log terminal viewport to the bottom.
 */
export function scrollToBottom() {
  if (logsElements.terminal) {
    logsElements.terminal.scrollTop = logsElements.terminal.scrollHeight;
  }
}

/**
 * Helper to style and format log records.
 */
function formatLogLine(log) {
  let color = "#10b981"; // INFO: green-teal
  if (log.level === "WARNING") color = "#fbbf24"; // WARNING: amber-yellow
  if (log.level === "ERROR" || log.level === "CRITICAL") color = "#f43f5e"; // ERROR: rose-red
  
  const timeStr = log.timestamp ? log.timestamp.split("T")[1].slice(0, 8) : "";
  
  return `<div style="margin-bottom: 5px; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 3px; font-family: inherit;">
    <span style="color: #64748b; font-weight: 500;">[${timeStr}]</span>
    <span style="color: ${color}; font-weight: 700; width: 62px; display: inline-block; text-transform: uppercase; font-size: 11px; padding: 1px 4px; border-radius: 3px; background: rgba(${log.level === "ERROR" ? "244,63,94,0.1" : log.level === "WARNING" ? "251,191,36,0.1" : "16,185,129,0.1"}); text-align: center; margin-right: 4px;">${log.level}</span>
    <span style="color: #38bdf8; font-weight: 500; margin-right: 8px;">${log.logger}:</span>
    <span style="color: #cbd5e1; white-space: pre-wrap; word-break: break-all;">${escapeHtml(log.message)}</span>
  </div>`;
}
