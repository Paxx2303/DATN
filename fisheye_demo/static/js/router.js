/**
 * FishEye8K Page Router Controller
 */
class PageRouter {
  constructor() {
    this.currentPage = 'dash';
    this.hooks = [];
    this.titles = {
      dash: "Hệ thống giám sát (Dashboard)",
      workspace: "Phòng thí nghiệm (Workspace)",
      streams: "Camera ngoài (Live Streams)",
      history: "Lịch sử Inference (History)",
      logs: "Nhật ký hệ thống (Logs)",
      settings: "Cấu hình hệ thống (Settings)",
      toc: "Trung tâm Điều hành Giao thông (TOC)",
      alpr: "Nhận diện biển số (ALPR)",
    };
  }

  onNavigate(callback) {
    this.hooks.push(callback);
  }

  navigate(pageId) {
    this.currentPage = pageId;

    // Remove active classes
    document.querySelectorAll(".page").forEach((page) => {
      page.classList.remove("active");
    });
    document.querySelectorAll(".sicon").forEach((icon) => {
      icon.classList.remove("active");
    });
    document.querySelectorAll(".ptab").forEach((tab) => {
      tab.classList.remove("active");
    });

    // Activate selected container
    const pageEl = document.getElementById(`page-${pageId}`);
    if (pageEl) {
      pageEl.classList.add("active");
    }

    // Activate sidebar icon
    const sidebarBtn = document.getElementById(`side-btn-${pageId}`);
    if (sidebarBtn) {
      sidebarBtn.classList.add("active");
    }

    // Activate top tab
    const tabBtn = document.getElementById(`tab-btn-${pageId}`);
    if (tabBtn) {
      tabBtn.classList.add("active");
    }

    // Update header title
    const titleEl = document.getElementById("ptitle");
    if (titleEl && this.titles[pageId]) {
      titleEl.textContent = this.titles[pageId];
    }

    // Execute post-navigation hooks
    this.hooks.forEach((callback) => {
      try {
        callback(pageId);
      } catch (e) {
        console.error('Error in post-navigation hook:', e);
      }
    });
  }
}

export const router = new PageRouter();
