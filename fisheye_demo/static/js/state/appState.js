/**
 * FishEye8K Application State Management
 */
class AppState {
  constructor() {
    this.currentFile = null;
    this.currentObjectUrl = null;
    this.currentMediaType = null;
    this.latestRecord = null;
    this.livePollTimer = null;
    this.liveMonitorRunning = false;
    this.liveStreamAttached = false;
    this.lastLiveCycleCount = null;
    this.lastLiveUpdatedAt = null;

    // Listeners for state changes
    this.listeners = {};
  }

  onChange(property, callback) {
    if (!this.listeners[property]) {
      this.listeners[property] = [];
    }
    this.listeners[property].push(callback);
  }

  set(property, value) {
    const oldValue = this[property];
    if (oldValue !== value) {
      this[property] = value;
      this.trigger(property, value, oldValue);
    }
  }

  trigger(property, value, oldValue) {
    if (this.listeners[property]) {
      this.listeners[property].forEach((callback) => {
        try {
          callback(value, oldValue);
        } catch (e) {
          console.error(`Error in state change listener for ${property}:`, e);
        }
      });
    }
  }
}

export const appState = new AppState();
