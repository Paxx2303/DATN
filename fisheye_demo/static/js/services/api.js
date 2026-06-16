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
  },

  async runFetchJobResult(jobId) {
    const response = await fetch(`/api/jobs/${jobId}/result`, { cache: 'no-store' });
    if (response.status === 202) return { pending: true };
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Failed to fetch job result');
    return data;
  },

  async fetchAnalytics(hours = 24) {
    const response = await fetch(`/api/analytics?hours=${hours}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load analytics: Status ${response.status}`);
    return response.json();
  },

  async fetchAlerts(limit = 50, unacknowledgedOnly = false) {
    const params = new URLSearchParams({ limit, unacknowledged: unacknowledgedOnly ? '1' : '0' });
    const response = await fetch(`/api/alerts?${params}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load alerts: Status ${response.status}`);
    return response.json();
  },

  async acknowledgeAlert(alertId) {
    const response = await fetch(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' });
    if (!response.ok) throw new Error(`Failed to acknowledge alert`);
    return response.json();
  },

  async fetchLineCounter() {
    const response = await fetch('/api/line-counter', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load line counter`);
    return response.json();
  },

  async configLineCounter(lines) {
    const response = await fetch('/api/line-counter/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Config failed');
    return data;
  },

  async resetLineCounter() {
    const response = await fetch('/api/line-counter/reset', { method: 'POST' });
    if (!response.ok) throw new Error('Reset failed');
    return response.json();
  },

  async fetchLineCounterHistory(hours = 24) {
    const response = await fetch(`/api/line-counter/history?hours=${hours}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Failed to load history');
    return response.json();
  },

  async fetchIncidents(hours = 24, acknowledged = null, type = null) {
    const params = new URLSearchParams({ hours });
    if (acknowledged !== null) params.set('acknowledged', acknowledged ? '1' : '0');
    if (type) params.set('type', type);
    const response = await fetch(`/api/incidents?${params}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load incidents`);
    return response.json();
  },

  async acknowledgeIncident(incidentId) {
    const response = await fetch(`/api/incidents/${incidentId}/acknowledge`, { method: 'POST' });
    if (!response.ok) throw new Error('Failed to acknowledge incident');
    return response.json();
  },

  async fetchIncidentStats(hours = 24) {
    const response = await fetch(`/api/incidents/stats?hours=${hours}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Failed to load incident stats');
    return response.json();
  },

  async fetchSpeedViolations(hours = 24) {
    const response = await fetch(`/api/speed/violations?hours=${hours}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load speed violations`);
    return response.json();
  },

  async fetchHeatmap() {
    const response = await fetch('/api/analytics/heatmap', { cache: 'no-store' });
    if (!response.ok) throw new Error('Failed to load heatmap');
    return response.json();
  },

  async fetchClassDist(hours = 24) {
    const response = await fetch(`/api/analytics/class-dist?hours=${hours}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Failed to load class distribution');
    return response.json();
  },

  async fetchHourlyTraffic(hours = 24) {
    const response = await fetch(`/api/analytics/hourly?hours=${hours}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Failed to load hourly traffic');
    return response.json();
  },

  async testWebhook() {
    const response = await fetch('/api/alerts/webhook/test', { method: 'POST' });
    return response.json();
  },

  async alprDetect(formData) {
    const response = await fetch('/api/alpr/detect', { method: 'POST', body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'ALPR detection failed');
    return data;
  },

  async fetchAlprHistory(hours = 24, limit = 100) {
    const response = await fetch(`/api/alpr/history?hours=${hours}&limit=${limit}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Failed to load plate history');
    return response.json();
  },

  async searchAlpr(query, hours = 168) {
    const params = new URLSearchParams({ q: query, hours });
    const response = await fetch(`/api/alpr/search?${params}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Search failed');
    return data;
  },
};
