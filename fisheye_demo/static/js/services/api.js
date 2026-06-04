/**
 * FishEye8K API Service Wrapper
 */
export const ApiService = {
  async fetchHealth() {
    const response = await fetch('/api/health');
    if (!response.ok) throw new Error(`Health check failed: Status ${response.status}`);
    return response.json();
  },

  async fetchHistory() {
    const response = await fetch('/api/history');
    if (!response.ok) throw new Error(`Failed to load run history: Status ${response.status}`);
    return response.json();
  },

  async fetchStats() {
    const response = await fetch('/api/stats');
    if (!response.ok) throw new Error(`Failed to load system stats: Status ${response.status}`);
    return response.json();
  },

  async fetchLogs(queryParams = {}) {
    const params = new URLSearchParams(queryParams);
    const response = await fetch(`/api/logs?${params.toString()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load logs: Status ${response.status}`);
    return response.json();
  },

  async fetchExternalCameraSource(url) {
    const query = new URLSearchParams({ external_camera_url: url });
    const response = await fetch(`/api/external-camera/source?${query.toString()}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to load camera source.');
    }
    return data;
  },

  async fetchExternalCameraLiveStatus() {
    const response = await fetch('/api/external-camera/status', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load live status: Status ${response.status}`);
    return response.json();
  },

  async startExternalCameraLive(formData) {
    const response = await fetch('/api/external-camera/start', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to start live monitor');
    }
    return data;
  },

  async stopExternalCameraLive() {
    const response = await fetch('/api/external-camera/stop', { method: 'POST' });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to stop live monitor');
    }
    return data;
  },

  async runDetection(formData) {
    const response = await fetch('/api/detect', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Detection failed');
    }
    return data;
  },

  async runConversion(formData) {
    const response = await fetch('/api/convert', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Conversion failed');
    }
    return data;
  },

  async runExternalCameraDetection(formData) {
    const response = await fetch('/api/external-camera/detect', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'External camera detection failed');
    }
    return data;
  },

  async runFetchJobStatus(jobId) {
    const response = await fetch(`/api/jobs/${jobId}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to fetch job status: Status ${response.status}`);
    return response.json();
  }
};
