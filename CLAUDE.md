# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
cd fisheye_demo
pip install -r requirements.txt
python app.py          # dev server → http://localhost:5000
```

Production deploys automatically via GitHub Actions on push to `main` (Docker Compose on GCP VM).  
Single test file: `cd fisheye_demo && pytest tests/<file>.py -v`

## Architecture

**Flask SPA** — `fisheye_demo/app.py::create_app()` is the factory. It registers five blueprints (`routes/core`, `detect`, `history`, `external_camera`, `examples`) plus ~50 additional endpoints in `routes_extended.py` (analytics, alerts, speed violations, ALPR, incidents).

**Frontend** — `templates/index.html` is the single HTML shell. All UI lives in `static/js/components/` (Workspace, Dashboard, LiveStreams, ALPR, TOC, LogsTerminal). State is in `state/appState.js`, routing in `router.js`, HTTP in `services/api.js`.

**Key data flows:**

| Flow | Entry | Notes |
|------|-------|-------|
| Image detect | `POST /api/detect` → `_handle_image_detect` | Sync; returns base64 annotated image + detections |
| Video detect | `POST /api/detect` → `_handle_video_submit` | Async job queue; poll `/api/jobs/<id>` |
| Live camera | `POST /api/external-camera/start` → `camera_monitor.py` background thread | MJPEG at `GET /api/external-camera/live/stream` |
| ALPR | `POST /api/alpr/detect` in `routes_extended.py` | Optional; returns `available:false` if EasyOCR missing |

**Fisheye pipeline:** `apply_preprocessing()` in `utils/helpers.py` wraps `fisheye.py::apply_fisheye()`. For video frames, `fisheye.py::apply_fisheye_to_cv2()` is called directly from `video_detect.py`. Both now use `full_frame=True` so no corner masking occurs.

**DB abstraction** — `db.py` supports SQLite (default) and PostgreSQL. All SQL is written with `%s` placeholders; `_adapt_sql()` converts to `?` for SQLite at runtime. No ORM.

**Model loading** — `services/model_registry.py` lazy-loads and caches YOLO models keyed by `(model_key, device)`. Device is auto-detected at startup in `config.py::_resolve_device()` (CUDA → MPS → CPU).

**Optional features that degrade gracefully:** EasyOCR/ALPR, Google Cloud Storage, yt-dlp. Each wraps its import in `try/except` and returns a safe fallback.

## Config

All settings are in `config.py::Config` (class attributes), populated from env vars via `_env()`. Copy `.env.local.example` → `.env` for development. Key vars:

- `COMPUTE_DEVICE` — `auto|cuda:0|mps|cpu`
- `DATABASE_URL` — if set, uses PostgreSQL; else SQLite at `DB_PATH`
- `EXT_CAM_SOURCE_URL` — HTML page to scrape for camera snapshot URLs (default: `https://camera.0511.vn/camera.html`)
- `FISHEYE_STRENGTH`, `FISHEYE_RADIUS`, `FISHEYE_EFFECT` — fisheye defaults (now overridden to 1.0/1.0/standard in UI)

## Non-obvious patterns

- **Source layout modes:** `source_layout="normal"` → fisheye conversion applied before detection; `"fisheye"` → detect raw. Frontend `resolveApplyFisheye()` in `helpers.js` enforces this.
- **Video job queue** (`job_queue.py`): max 2 concurrent workers. The worker fn `_video_worker_fn` runs in a thread pool; progress reported via `progress_cb` callback.
- **Live camera monitor** (`services/camera_monitor.py`): singleton `ExternalCameraLiveMonitor`. Parses camera HTML page, fetches snapshots in parallel, runs inference, tracks centroids across cycles for speed/incident detection.
- **Recent image store** (`recent_image_store.py`): in-memory ring buffer of last N annotated images; used by `/api/recent-images` for dashboard preview.
- **SQL schema** is created on first `init_db()` call — no migration framework. Schema changes require manual `DROP TABLE` or `ALTER TABLE`.

## Model files

Stored in `fisheye_demo/` (not committed). `traffic.pt` (~5.6 MB) is the default. `yolo11_fisheye_v5_best.pt` is the fisheye-trained model. Missing model falls back to `yolo11n.pt` at startup.
