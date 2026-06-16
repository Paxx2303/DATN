# Tài liệu hệ thống FishEye8K

> Nguồn tài liệu **chuẩn & cập nhật** mô tả toàn bộ hệ thống theo đúng mã nguồn hiện tại.
> Cập nhật: 2026-06-14 (sau đợt sửa lỗi + bổ sung feature ALPR).

---

## 1. Tổng quan

**FishEye8K** là hệ thống giám sát giao thông thông minh (ITS) nhận diện phương tiện
từ **camera mắt cá (fisheye)** dùng **YOLO11**. Hệ thống cho phép:

- Nhận diện trên **ảnh**, **video**, và **camera trực tiếp (live)**.
- Phân tích: đếm xe theo hướng, ước lượng tốc độ + vi phạm, phát hiện ùn tắc, phát hiện sự cố.
- Cảnh báo (mật độ/sự cố/tốc độ) + webhook.
- **Nhận diện biển số (ALPR)**.
- Dashboard phân tích + xuất báo cáo CSV/JSON.

**Công nghệ:** Flask 3 (backend) · SPA JavaScript thuần (frontend) · SQLite/PostgreSQL ·
Ultralytics YOLO11 · OpenCV · (tùy chọn) EasyOCR, Google Cloud Storage.

---

## 2. Kiến trúc tổng thể

```
                        ┌─────────────────────────────────────────┐
   Trình duyệt (SPA)    │  templates/index.html + static/js/*      │
   - Dashboard, TOC     │  router.js · appState.js · api.js        │
   - Workspace, ALPR    └───────────────┬─────────────────────────┘
   - Live Streams                       │  HTTP / JSON
                                        ▼
                        ┌─────────────────────────────────────────┐
   Flask (app.py)       │  create_app(): Config→DB→Blueprints→     │
   application factory   │  Extended routes→Logging→atexit cleanup  │
                        └───────────────┬─────────────────────────┘
                ┌───────────────────────┼───────────────────────────┐
                ▼                       ▼                           ▼
        Blueprints (routes/)     routes_extended.py          services/
        core/detect/history/     analytics·alerts·           model_registry
        external_camera/examples incidents·speed·            inference
                │                congestion·ALPR·export       camera_monitor
                ▼                       │                           │
        ┌───────────────────────────────────────────────────────────────┐
        │  Module nghiệp vụ: video_detect · fisheye · speed_estimator ·  │
        │  line_counter · congestion_detector · incident_detector ·      │
        │  alert_manager · analytics · alpr · job_queue · cloud_storage  │
        └───────────────┬───────────────────────────────────────────────┘
                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  db.py (SQLite/PostgreSQL)  +  recent_image_store (buffer ảnh)  │
        └───────────────────────────────────────────────────────────────┘
```

---

## 3. Cấu trúc thư mục (rút gọn)

```
fisheye_demo/
├── app.py                  # Application factory create_app()
├── config.py               # Cấu hình (đọc .env, hỗ trợ alias biến)
├── db.py                   # Tầng DB (SQLite/PostgreSQL)
├── wsgi.py                 # Entry production
│
├── routes/                 # Blueprints
│   ├── core.py             #   /, /api/health, /api/logs, /api/config, /api/stats
│   ├── detect.py           #   /api/detect, /api/convert, /api/jobs/*
│   ├── history.py          #   /api/history, /api/results/*, /api/recent-images
│   ├── external_camera.py  #   /api/external-camera/*
│   └── examples.py         #   /api/examples
├── routes_extended.py      # ~50 endpoint: analytics/alerts/incidents/speed/
│                           #   congestion/ALPR/export
│
├── services/
│   ├── model_registry.py   # Cache YOLO (thread-safe, lazy)
│   ├── inference.py        # Wrap predict 1 ảnh → dict chuẩn
│   └── camera_monitor.py   # Luồng nền cho camera live
│
├── video_detect.py         # Pipeline xử lý video (tracking + analytics)
├── fisheye.py              # Biến đổi mắt cá (ảnh/video)
├── speed_estimator.py      # Ước lượng tốc độ + vi phạm
├── line_counter.py         # Đếm xe 4 hướng (vạch ảo)
├── congestion_detector.py  # Ùn tắc (named-ROI + lưới)
├── incident_detector.py    # Sự cố (đỗ sai/dừng/ngược chiều)
├── alert_manager.py        # Cảnh báo + webhook
├── analytics.py            # Heatmap, density, hourly, class-dist
├── alpr.py                 # ⭐ Nhận diện biển số (EasyOCR, optional)
├── job_queue.py            # Hàng đợi xử lý video bất đồng bộ
├── cloud_storage.py        # Upload GCS (tùy chọn)
├── recent_image_store.py   # Buffer ảnh kết quả nhanh
│
├── static/js/              # Frontend SPA
│   ├── app.js              #   Bootstrap, wiring
│   ├── router.js, services/api.js, state/appState.js, utils/helpers.js
│   └── components/         #   Dashboard, Workspace, LiveStreams, TOC,
│                           #   ALPR ⭐, LogsTerminal, Layout
├── templates/index.html    # Khung SPA (nav + các trang)
│
├── *.pt                    # Trọng số YOLO (gitignored — không commit)
├── tests/                  # pytest (31 test)
└── HE_THONG.md             # ← tài liệu này
```

---

## 4. Các luồng xử lý chính

### 4.1. Nhận diện ẢNH (đồng bộ)
`POST /api/detect` (file ảnh) → `routes/detect.py::_handle_image_detect`:
1. Đọc ảnh → (tùy chọn) fisheye preprocessing.
2. YOLO inference (`services/inference.py`).
3. Vẽ bbox → lưu ra `static/results/<id>/` + `meta.json`.
4. Lưu DB `detections` + buffer ảnh + cập nhật heatmap/density/alert.
5. Trả JSON (base64 ảnh + danh sách detection) → render ngay.

### 4.2. Nhận diện VIDEO (bất đồng bộ — qua job queue) ⭐
> Trước đây chạy đồng bộ gây timeout khi deploy. Đã chuyển sang async.

```
POST /api/detect (video)
   └─> _handle_video_submit → lưu file → video_job_queue.submit_job() → 202 {job_id}
            │ (worker thread)
            ▼
        _video_worker_fn:
          run_video_detect()  ──► tracking YOLO + đếm unique + speed +
          (video_detect.py)        line_counter + congestion + incidents
                                   ghi video annotated + preview
          _persist_video_analytics() ──► traffic_counts / speed_violations / incidents
          insert_detection() ──► summary đầy đủ
   ◄── Frontend (Workspace.js::pollVideoJob):
         poll GET /api/jobs/<id>  → khi "done" → GET /api/jobs/<id>/result
         (payload cùng shape, render video + summary)
```

### 4.3. Camera trực tiếp (LIVE)
`POST /api/external-camera/start` → `services/camera_monitor.py` chạy luồng nền:
poll ảnh từ camera (mặc định `camera.0511.vn`) → detect → cập nhật analytics →
phát alert/incident/violation. Xem qua `/api/external-camera/live/stream` (MJPEG).

### 4.4. Nhận diện biển số (ALPR) ⭐
`POST /api/alpr/detect` (ảnh) → `routes_extended.py`:
1. YOLO khoanh vùng phương tiện.
2. `alpr.py::PlateRecognizer` cắt vùng xe → EasyOCR đọc text.
3. `normalize_vn_plate()` chuẩn hoá về định dạng biển VN (vd `51F-123.45`).
4. Lưu DB `license_plates` → trả ảnh annotated + danh sách biển.
> EasyOCR là **tùy chọn**: nếu chưa cài, endpoint trả `available:false` (không sập app).

---

## 5. Năm tính năng ITS

| # | Tính năng | Module | Cách hoạt động |
|---|-----------|--------|----------------|
| 1 | **Đếm xe theo hướng** | `line_counter.py` | 4 vạch ảo N/S/E/W, phát hiện cắt vạch bằng cross-product; mỗi track đếm 1 lần/hướng |
| 2 | **Tốc độ + vi phạm** | `speed_estimator.py` | Theo dõi dịch chuyển px → km/h (scale calibrate); vượt ngưỡng N frame liên tiếp → vi phạm |
| 3 | **Ùn tắc** | `congestion_detector.py` | ROI có tên (chuẩn hoá 0–1) hoặc lưới; occupancy=count/capacity → low/moderate/high |
| 4 | **Sự cố** | `incident_detector.py` | ILLEGAL_PARKING (đứng yên >30s), STOPPED_VEHICLE (dừng + có xe khác chạy), WRONG_WAY (ngược hướng dòng >120°) |
| 5 | **Biển số (ALPR)** ⭐ | `alpr.py` | YOLO khoanh xe → EasyOCR → chuẩn hoá biển VN → lưu/tra cứu |

Hỗ trợ chung: **cảnh báo** (`alert_manager.py`), **heatmap/analytics** (`analytics.py`),
**xuất CSV/JSON**.

---

## 6. Danh mục API

### Core (`routes/core.py`)
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/` | Trang SPA |
| GET | `/api/health` | Tình trạng hệ thống/model |
| GET | `/api/logs` | Nhật ký (lọc theo từ khoá/level) |
| GET | `/api/config` | Cấu hình hiện hành |
| GET | `/api/stats`, `/api/analytics/stats` | Thống kê tổng hợp |

### Detect (`routes/detect.py`)
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/detect` | Nhận diện ảnh (đồng bộ) / video (→202 job) |
| POST | `/api/convert` | Biến đổi fisheye ảnh/video |
| GET | `/api/jobs/<id>` | Trạng thái job video |
| GET | `/api/jobs/<id>/result` | ⭐ Kết quả video khi job xong |
| GET | `/api/jobs` | Danh sách job |

### History (`routes/history.py`)
`/api/history` · `/api/results/<id>` · `/api/results/<id>/file/<f>` · `/api/recent-images` · `/api/alerts`

### Extended (`routes_extended.py`)
| Nhóm | Endpoints |
|------|-----------|
| Analytics | `/api/analytics`, `/hourly`, `/class-dist`, `/peak-hours`, `/heatmap`, `/heatmap/reset` |
| Alerts | `/api/alerts`, `/<id>/acknowledge`, `/thresholds` (GET/POST), `/webhook/test` |
| Line counter | `/api/line-counter`, `/config`, `/reset`, `/history` |
| Incidents | `/api/incidents`, `/stats`, `/<id>/acknowledge` |
| Speed | `/api/speed/violations`, `/stats`, `/current`, `/config`, `/config-limit`, `/reset`, `/detect-image` |
| Congestion | `/api/congestion/status`, `/rois` (GET/POST/DELETE), `/history/<roi>`, `/reset`, `/detect-image` |
| **ALPR** ⭐ | `POST /api/alpr/detect`, `GET /api/alpr/history`, `GET /api/alpr/search?q=` |
| Export | `/api/export/csv`, `/api/export/json` |
| Cloud | `/api/cloud/gallery`, `/stats`, `/cleanup` |
| DB | `/api/db/health` |

### External Camera (`routes/external_camera.py`)
`/source` · `/detect` · `/start` · `/stop` · `/status` · `/live/stream` · `/snapshot/overview` · `/snapshot/<idx>`

---

## 7. Lược đồ cơ sở dữ liệu

Mặc định **SQLite** (`fisheye.db`); chuyển **PostgreSQL** bằng `DATABASE_URL`.

| Bảng | Mục đích | Cột chính |
|------|----------|-----------|
| `detections` | Mỗi phiên nhận diện | id, filename, task, media_type, source_layout, summary(JSON), artifacts(JSON), created_at |
| `alerts` | Cảnh báo | alert_type, message, camera_source, actual_count, is_acknowledged |
| `incidents` | Sự cố | camera_id, incident_type, severity, vehicle_type, bbox_json, acknowledged, occurred_at |
| `traffic_counts` | Đếm theo hướng/giờ | camera_id, direction, class_name, count, hour_bucket |
| `speed_violations` | Vi phạm tốc độ | camera_id, track_id, vehicle_type, speed_kmh, limit_kmh |
| `vehicle_speeds` | Lịch sử tốc độ | detection_id, track_id, vehicle_type, speed_kmh |
| `heatmap_data` | Lưới heatmap | camera_id, grid_json |
| `license_plates` ⭐ | Biển số (ALPR) | plate_text, confidence, vehicle_type, camera_id, detection_id, bbox_json |

> Ghi chú: `recent_images.db` (buffer thumbnail) là DB riêng do `recent_image_store.py` quản lý.

---

## 8. Frontend (SPA)

- **Điều hướng:** `router.js` chuyển trang `page-<id>` + cập nhật tiêu đề. Các trang:
  `dash`, `workspace`, `streams`, `history`, `logs`, `toc`, **`alpr`** ⭐, `settings`.
- **Component** (`static/js/components/`):
  - `Dashboard.js` — tổng quan, thống kê, legend.
  - `Workspace.js` — upload + nhận diện ảnh/video (có poll job video).
  - `LiveStreams.js` — camera trực tiếp + panel line-counter.
  - `TOC.js` — Trung tâm điều hành (tổng hợp ITS, poll 8s, export).
  - `ALPR.js` ⭐ — nhận diện/tra cứu biển số.
  - `LogsTerminal.js`, `Layout.js`.
- **Giao tiếp API:** tất cả qua `services/api.js`. Trạng thái dùng `state/appState.js`.

---

## 9. Cấu hình (.env)

`config.py` đọc `.env` và **hỗ trợ alias** (một thiết lập nhiều tên):

| Thiết lập | Biến (ưu tiên trái→phải) | Mặc định |
|-----------|--------------------------|----------|
| Model mặc định | `DEFAULT_MODEL` | `traffic` |
| Confidence | `YOLO_CONF` / `FISHEYE_DEFAULT_CONF` | `0.35` |
| IoU | `YOLO_IOU` / `FISHEYE_DEFAULT_IOU` | `0.45` |
| Thiết bị | `COMPUTE_DEVICE` / `FISHEYE_DEVICE` | `cpu` |
| Thư mục upload | `FISHEYE_UPLOAD_DIR` | `static/uploads` |
| Thư mục kết quả | `FISHEYE_RESULTS_DIR` | `static/results` |
| Giới hạn upload (MB) | `FISHEYE_MAX_UPLOAD_MB` | `500` |
| DB buffer ảnh | `FISHEYE_RECENT_IMAGE_DB` | `recent_images.db` |
| PostgreSQL | `DATABASE_URL` | (rỗng → SQLite) |
| Số worker video | `JOB_WORKERS` | `2` |
| Ngưỡng mật độ | `ALERT_HIGH_DENSITY` | `20` |
| Giới hạn tốc độ | `SPEED_LIMIT_KMH` | `50` |
| Webhook | `WEBHOOK_URL` | (rỗng) |
| GCS | `GCS_BUCKET`, `GOOGLE_APPLICATION_CREDENTIALS` | (rỗng) |

---

## 10. Cách chạy

```bash
# 1. Cài phụ thuộc
pip install -r requirements.txt

# 2. (Tùy chọn) bật ALPR — tải model OCR lần đầu cần internet
pip install easyocr

# 3. Đặt trọng số YOLO (*.pt) vào thư mục gốc fisheye_demo/
#    (traffic.pt, yolo11n.pt, yolo11_fisheye_v5_best.pt)

# 4. Chạy dev
python app.py            # http://localhost:5000
#    hoặc production:
#    gunicorn -w 2 wsgi:app   (Linux)

# 5. Chạy test
python -m pytest tests/ -q     # 31 passed
```

---

## 11. Giới hạn đã biết

- **PostgreSQL:** một số truy vấn dùng cú pháp SQLite-only (`datetime('now')`, `strftime`,
  `last_insert_rowid`, `PRAGMA`). App mặc định SQLite nên chạy tốt; chạy PG thật cần
  viết lại tầng truy vấn analytics.
- **ALPR:** không có model phát hiện biển riêng (dựa vào crop xe + OCR) nên độ chính xác
  phụ thuộc chất lượng ảnh; chuỗi 8 ký tự kiểu xe máy không tách seri được sẽ quy về
  định dạng ô tô. Cần internet để tải model OCR lần đầu.
- **Line counter live:** singleton toàn cục chỉ nhận dữ liệu từ camera live; kết quả từ
  upload xem qua `/api/line-counter/history` (đọc DB).
