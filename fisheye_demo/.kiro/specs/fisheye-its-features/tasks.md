# Implementation Plan: FishEye8K ITS Features

## Overview

Kế hoạch triển khai 4 tính năng ITS mới cho FishEye8K Traffic Monitoring System, chia thành **20 tasks** tuần tự theo Giai đoạn 0–4. Mỗi task xây dựng trên kết quả của task trước — **không bỏ qua thứ tự**.

**Tech stack:** Python/Flask (backend), Vanilla JS + Chart.js (frontend), SQLite/PostgreSQL (DB)

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["0.1"]},
    {"wave": 2, "tasks": ["1.1"]},
    {"wave": 3, "tasks": ["1.2"]},
    {"wave": 4, "tasks": ["1.3"]},
    {"wave": 5, "tasks": ["1.4"]},
    {"wave": 6, "tasks": ["1.5"]},
    {"wave": 7, "tasks": ["1.6"]},
    {"wave": 8, "tasks": ["2.1"]},
    {"wave": 9, "tasks": ["2.2"]},
    {"wave": 10, "tasks": ["2.3"]},
    {"wave": 11, "tasks": ["2.4"]},
    {"wave": 12, "tasks": ["2.5"]},
    {"wave": 13, "tasks": ["3.1"]},
    {"wave": 14, "tasks": ["3.2"]},
    {"wave": 15, "tasks": ["3.3"]},
    {"wave": 16, "tasks": ["3.4"]},
    {"wave": 17, "tasks": ["4.1"]},
    {"wave": 18, "tasks": ["4.2"]},
    {"wave": 19, "tasks": ["4.3"]},
    {"wave": 20, "tasks": ["4.4"]},
    {"wave": 21, "tasks": ["4.5"]}
  ]
}
```

## Tổng quan

Kế hoạch triển khai 4 tính năng ITS mới cho FishEye8K Traffic Monitoring System, chia thành **20 tasks** tuần tự theo Giai đoạn 0–4. Mỗi task xây dựng trên kết quả của task trước — **không bỏ qua thứ tự**.

**Tech stack:** Python/Flask (backend), Vanilla JS + Chart.js (frontend), SQLite/PostgreSQL (DB)

**Quy tắc dependency:**
- Task trong cùng tính năng: phải hoàn thành theo thứ tự (backend core → DB → API → pipeline → UI → test)
- Giai đoạn 4 phụ thuộc vào Giai đoạn 1–3

---

## Tasks

### Giai đoạn 0 — Chuẩn bị nền tảng

- [-] 0.1 Kích hoạt extended routes và tạo stub LineCounter
  - Đọc `routes_extended.py` để xác định các dependency mà `register_extended_routes()` cần: `heatmap`, `density_analyzer`, `alert_manager`, `line_counter`, `speed_estimator`, `congestion_detector`
  - Trong `app.py` → `create_app()`: import và khởi tạo các singleton cần thiết từ `analytics.py`, `alert_manager.py`, `congestion_detector.py`, `speed_estimator.py`
  - Gọi `register_extended_routes(app, ...)` **sau** `register_blueprints(app)` trong `create_app()`
  - Tạo file `line_counter.py` với **stub** `LineCounter`: `get_stats()` trả `{"directions": {}, "grand_total": 0}`, `reset()` pass, `set_lines()` pass — đủ để app boot không lỗi
  - Không thay đổi logic các route hiện có
  - **Tiêu chí:** `python app.py` chạy không có exception; `GET /api/db/health` trả `{"status": "ok"}`; `GET /api/analytics` trả JSON không 500

---

### Giai đoạn 1 — Tính năng 1: Line Counter

- [~] 1.1 Tạo module `line_counter.py` (backend core)
  - Thay thế stub bằng implementation đầy đủ trong `line_counter.py`
  - Class `LineCounter`:
    - Constructor nhận `camera_id: str`, khởi tạo 4 vạch mặc định `north/south/east/west` chia từ tâm khung 640×480 (horizontal center line cho N/S, vertical center line cho E/W)
    - `set_lines(lines: dict)` — nhận dict `{direction: {start:[x,y], end:[x,y]}}` để cập nhật 4 vạch
    - `update(track_id: int, cx: int, cy: int, class_name: str, frame_idx: int) -> str | None` — dùng kiểm tra *side-of-line* (cross product đổi dấu giữa frame trước và frame hiện tại) để phát hiện crossing; trả direction name nếu có crossing, None nếu không; mỗi `track_id` chỉ đếm 1 lần per direction (set `_counted`)
    - `get_stats() -> dict` — trả `{direction: {class_name: count, "total": N}, "grand_total": N}`
    - `reset()` — xóa tất cả counters và track history
  - Dùng `threading.Lock` cho thread-safety (camera_monitor chạy background thread)
  - Tham khảo style từ `incident_detector.py` (defaultdict, deque, logging)
  - **Tiêu chí:** Script test nhỏ hoặc doctest: tạo `LineCounter`, gọi `update()` với track đi qua vạch north → `get_stats()["north"]["total"] == 1`; gọi lại cùng `track_id` không tăng thêm

- [~] 1.2 Thêm bảng `traffic_counts` vào `db.py`
  - **Phụ thuộc:** Task 1.1
  - Thêm vào `_create_tables_sqlite()` và `_create_tables_pg()`:
    ```sql
    CREATE TABLE IF NOT EXISTS traffic_counts (
        id          INTEGER/SERIAL PRIMARY KEY,
        camera_id   TEXT/VARCHAR(128),
        direction   TEXT/VARCHAR(16),
        class_name  TEXT/VARCHAR(64),
        count       INTEGER DEFAULT 0,
        hour_bucket TEXT/VARCHAR(20),  -- format: 'YYYY-MM-DD HH:00'
        updated_at  TEXT/TIMESTAMP DEFAULT NOW()
    )
    ```
  - Thêm `_sqlite_migrate()` entry cho bảng mới nếu DB cũ chưa có
  - Implement `save_traffic_count(camera_id, direction, class_name, hour_bucket)` — UPSERT: nếu row tồn tại thì `count += 1`, nếu chưa thì INSERT count=1
  - Implement `get_traffic_counts(hours=24, camera_id=None) -> list[dict]` — filter theo `hour_bucket >= now - hours`
  - Implement `get_traffic_by_direction(hours=24) -> dict` — group by direction, sum counts
  - **Tiêu chí:** `init_db()` không lỗi; gọi `save_traffic_count(...)` rồi `get_traffic_counts()` trả đúng data

- [~] 1.3 Hoàn thiện API line counter trong `routes_extended.py`
  - **Phụ thuộc:** Task 1.2
  - Endpoint `GET /api/line-counter` đã có stub trong `routes_extended.py` — bổ sung thêm `history_24h` từ `db.get_traffic_by_direction(24)`
  - Thêm endpoint `POST /api/line-counter/config` — nhận body `{"lines": {"north": {"start":[x,y], "end":[x,y]}, ...}}`, validate tọa độ là số, gọi `line_counter.set_lines()`
  - Endpoint `POST /api/line-counter/reset` đã có — đảm bảo gọi cả DB reset nếu cần
  - Thêm endpoint `GET /api/line-counter/history` — query params `hours` (default 24), `camera_id`; gọi `db.get_traffic_counts()`
  - Cập nhật `static/js/services/api.js`: thêm `fetchLineCounterStats()`, `configLineCounter(lines)`, `resetLineCounter()`, `fetchLineCounterHistory(hours)`
  - **Tiêu chí:** `curl GET /api/line-counter` trả JSON có key `directions`; `POST /api/line-counter/config` với JSON hợp lệ trả `{"status": "ok"}`

- [~] 1.4 Tích hợp `LineCounter` vào pipeline video và camera live
  - **Phụ thuộc:** Task 1.3
  - **`video_detect.py`**: sau mỗi frame có tracking result (`track_id`, `bbox`, `class_name`):
    - Tính `cx = (x1+x2)//2`, `cy = (y1+y2)//2`
    - Gọi `line_counter.update(track_id, cx, cy, class_name, frame_idx)`
    - Nếu có crossing → gọi `db.save_traffic_count(camera_id, direction, class_name, hour_bucket)`
    - Reset `line_counter` khi bắt đầu job mới
  - **`services/camera_monitor.py`**: dùng `line_counter` singleton (từ `app.py`) hoặc per-camera instance; gọi `update()` sau mỗi frame detect
  - Vẽ 4 vạch lên frame annotated: dùng `cv2.line()` với màu khác nhau (N=xanh lam, S=xanh lục, E=vàng, W=đỏ) nếu `line_counter` đã có config
  - Đảm bảo `update()` O(1) — không làm chậm pipeline
  - **Tiêu chí:** Chạy video hoặc live camera → `GET /api/line-counter` trả `grand_total > 0`; 4 vạch màu hiển thị trên MJPEG/snapshot

- [~] 1.5 UI LiveStreams: panel lưu lượng 4 hướng
  - **Phụ thuộc:** Task 1.4
  - Trong `static/js/components/LiveStreams.js`:
    - Thêm panel HTML "Lưu lượng theo hướng" bên phải grid camera: 4 ô card (Bắc/Nam/Đông/Tây) hiển thị total count + breakdown loại xe
    - Poll `GET /api/line-counter` mỗi 4 giây khi monitor đang chạy (dùng `setInterval`, clear khi stop)
    - Nút "Cấu hình vạch đếm": hiển thị form 4 hướng với input tọa độ `x1,y1,x2,y2`; nút Submit gọi `POST /api/line-counter/config`; preset mặc định điền sẵn từ tọa độ tâm 640×480
    - Nút "Reset" gọi `POST /api/line-counter/reset`
    - Biểu đồ cột Chart.js: 4 bars = 4 hướng, height = total count; khởi tạo giống pattern đã có trong `Dashboard.js`
  - CSS: match style card hiện có trong `base.css`/`components.css`; không thêm file CSS mới
  - **Tiêu chí:** Mở `/#/live` → thấy panel lưu lượng; số thay đổi theo polling; config vạch submit không lỗi 400/500

- [ ]* 1.6 Kiểm thử end-to-end Tính năng Line Counter
  - **Phụ thuộc:** Task 1.5
  - Tạo `tests/test_line_counter.py`:
    - Test `LineCounter.update()` với synthetic track crossing vạch north → count = 1
    - Test không đếm trùng: cùng `track_id` gọi nhiều lần trên cùng vạch → vẫn count = 1
    - Test `set_lines()` cập nhật vạch và reset count
    - Test `get_stats()` structure hợp lệ
  - Sửa bug nếu count không tăng hoặc API trả 500 trong quá trình test tích hợp
  - Verify: các tính năng cũ (detect, congestion, speed label) không bị regression sau task 1.4
  - **Tiêu chí:** `pytest tests/test_line_counter.py` pass; demo live → số liệu 4 hướng thay đổi

---

### Giai đoạn 2 — Tính năng 2: Smart Incident Detection

- [~] 2.1 Thêm logic `WRONG_WAY` và `STOPPED_VEHICLE` vào `incident_detector.py`
  - **Phụ thuộc:** Task 1.6 (baseline ổn định)
  - Thêm `set_main_flow_direction(angle_degrees: float)` — lưu hướng lưu lượng chính để so sánh; cũng hỗ trợ auto-detect từ histogram vận tốc của tất cả tracks
  - Implement `_check_wrong_way(track_id, frame_idx) -> dict | None`:
    - Tính velocity vector từ 5–10 frame gần nhất trong `self._positions`
    - So sánh góc với `_main_flow_direction`; nếu lệch > 120° **và** speed đủ lớn (> 3 px/frame) → trả incident dict `{"incident_type": "WRONG_WAY", ...}`
    - Dedup: mỗi `track_id` chỉ báo 1 lần per 30 giây (dùng `_wrong_way_reported: dict[int, float]`)
  - Implement `_check_stopped_vehicle(track_id, frame_idx, all_boxes) -> dict | None`:
    - Xe đứng yên (avg displacement < `MIN_MOVEMENT_PX`) trong 10–15 giây
    - Có ≥ 2 track khác di chuyển qua trong bán kính gần trong 5 giây → `STOPPED_VEHICLE`
    - Khác `ILLEGAL_PARKING`: threshold thời gian ngắn hơn (10–15s vs 30s) và yêu cầu có xe khác vượt qua
  - Cập nhật `analyze()` gọi cả 3 checker: `_check_parking`, `_check_wrong_way`, `_check_stopped_vehicle`
  - Thêm constants vào `config.py`: `WRONG_WAY_ANGLE_THRESHOLD = 120`, `STOPPED_VEHICLE_THRESHOLD_S = 12`, `PARKING_THRESHOLD_SECONDS = 30`
  - **Tiêu chí:** Synthetic test: track với velocity ngược 180° trigger `WRONG_WAY`; `ILLEGAL_PARKING` vẫn hoạt động đúng

- [~] 2.2 Lưu incidents vào database và evidence
  - **Phụ thuộc:** Task 2.1
  - **`db.py`**: bảng `incidents` hiện có thiếu cột — thêm migration trong `_sqlite_migrate()`:
    - `vehicle_type TEXT`, `evidence_path TEXT`, `acknowledged INTEGER DEFAULT 0`
    - Cập nhật `_create_tables_pg()` tương ứng
  - Implement `save_incident(incident_dict) -> int` — INSERT và trả `lastrowid`
  - Implement `get_incidents(hours=24, acknowledged=None, incident_type=None) -> list[dict]`
  - Implement `acknowledge_incident(incident_id: int)`
  - **`video_detect.py`** và **`services/camera_monitor.py`**: khi `incident_detector.analyze()` trả incident mới:
    - Lưu frame snapshot vào `static/results/evidence_{incident_type}_{track_id}_{timestamp}.jpg`
    - Gọi `db.save_incident({...incident, "evidence_path": path})`
  - **Tiêu chí:** Sau 30 giây live monitor với xe đứng yên → `db.get_incidents()` trả ≥ 1 record

- [~] 2.3 API incidents trong `routes_extended.py`
  - **Phụ thuộc:** Task 2.2
  - Thêm các endpoints vào `routes_extended.py` (hoặc blueprint `routes/traffic.py` mới):
    - `GET /api/incidents` — list, filter query params: `hours` (default 24), `type`, `acknowledged` (0/1)
    - `GET /api/incidents/<int:id>` — chi tiết + URL ảnh evidence
    - `POST /api/incidents/<int:id>/acknowledge` — set `acknowledged=1`
    - `GET /api/incidents/stats` — đếm theo loại trong 24h: `{"WRONG_WAY": N, "STOPPED_VEHICLE": M, "ILLEGAL_PARKING": K}`
  - Cập nhật `static/js/services/api.js`: `fetchIncidents(filters)`, `acknowledgeIncident(id)`, `fetchIncidentStats()`
  - **Tiêu chí:** `GET /api/incidents` trả JSON array; `POST /api/incidents/1/acknowledge` → record có `acknowledged=1`

- [~] 2.4 UI tab Sự cố trên Dashboard
  - **Phụ thuộc:** Task 2.3
  - Trong `static/js/components/Dashboard.js` (hoặc tạo `Incidents.js` mới và import vào `app.js`/`router.js`):
    - Bảng sự cố: cột `Thời gian | Loại | Camera | Loại xe | Mô tả | Trạng thái | Hành động`
    - Màu row theo mức: `WRONG_WAY` = đỏ, `STOPPED_VEHICLE` = cam, `ILLEGAL_PARKING` = vàng
    - Nút "Xác nhận" gọi `POST /api/incidents/<id>/acknowledge`, sau đó refresh bảng
    - Badge đỏ trên sidebar navigation: hiển thị số incidents `acknowledged=0`; cập nhật mỗi 10 giây
    - Poll `/api/incidents?acknowledged=0` mỗi 10 giây
  - Tích hợp `alert_manager`: khi incident loại `WRONG_WAY` xuất hiện → `alert_manager.check_and_alert()` với priority cao
  - **Tiêu chí:** `/#/dashboard` (hoặc tab Incidents) hiển thị bảng với dữ liệu live; badge sidebar cập nhật

- [ ]* 2.5 Kiểm thử Smart Incident Detection
  - **Phụ thuộc:** Task 2.4
  - Tạo `tests/test_incident_detector.py`:
    - Test `ILLEGAL_PARKING`: inject 31 giây frame data cho 1 track → trigger incident
    - Test `WRONG_WAY` với synthetic velocity ngược chiều
    - Test dedup: cùng track không tạo duplicate incident trong 30 giây
  - Fix dedup bug nếu có (không flood cùng track_id hàng trăm records)
  - Thêm constants vào `config.py` và document ngưỡng: `PARKING_THRESHOLD_SECONDS`, `WRONG_WAY_ANGLE_THRESHOLD`, `STOPPED_VEHICLE_THRESHOLD_S`
  - **Tiêu chí:** `pytest tests/test_incident_detector.py` pass; demo UI với ít nhất 1 loại sự cố; log không flood

---

### Giai đoạn 3 — Tính năng 3: Speed Violation Alert

- [~] 3.1 Class `SpeedViolationChecker` trong `speed_estimator.py`
  - **Phụ thuộc:** Task 2.5 (baseline ổn định)
  - Thêm class `SpeedViolationChecker` vào cuối `speed_estimator.py`:
    - Constructor: `speed_limit_kmh: float = 50.0`, `consecutive_frames: int = 3`, `cooldown_seconds: float = 30.0`
    - `check(track_id: int, speed_kmh: float, frame_idx: int) -> dict | None`:
      - Duy trì `_exceed_streak: dict[int, int]` — đếm số frame liên tiếp vượt ngưỡng
      - Nếu speed > limit: tăng streak; nếu streak >= `consecutive_frames` và cooldown qua → trả violation dict `{"track_id", "speed_kmh", "limit_kmh", "excess_kmh", "timestamp"}`
      - Reset streak nếu speed <= limit
      - Dedup: lưu `_last_violation: dict[int, float]` (timestamp), chỉ báo sau cooldown
    - `get_violations() -> list[dict]` — trả list violations đã ghi
    - `reset()` — xóa tất cả state
  - Tích hợp với `SpeedEstimator`: sau `update()` gọi `violation_checker.check(track_id, speed_kmh, frame_idx)`
  - Cập nhật `config.py`: `SPEED_LIMIT_KMH = int(os.getenv("SPEED_LIMIT_KMH", "50"))`, `SPEED_VIOLATION_FRAMES = int(os.getenv("SPEED_VIOLATION_FRAMES", "3"))`
  - **Tiêu chí:** `speed=60, limit=50, 3 frame liên tiếp` → trả violation dict; `speed=55` rồi `speed=45` → không violation

- [~] 3.2 Bảng `speed_violations` trong DB và API
  - **Phụ thuộc:** Task 3.1
  - **`db.py`**: thêm bảng `speed_violations` vào `_create_tables_sqlite()` và `_create_tables_pg()`:
    ```sql
    CREATE TABLE IF NOT EXISTS speed_violations (
        id           INTEGER/SERIAL PRIMARY KEY,
        camera_id    TEXT/VARCHAR(128),
        track_id     INTEGER,
        vehicle_type TEXT/VARCHAR(64),
        speed_kmh    REAL,
        limit_kmh    REAL,
        evidence_path TEXT/VARCHAR(512),
        created_at   TEXT/TIMESTAMP DEFAULT NOW()
    )
    ```
  - Implement `save_speed_violation(record: dict) -> int`
  - Implement `get_speed_violations(hours=24, camera_id=None) -> list[dict]`
  - **Pipeline**: trong `video_detect.py` và `camera_monitor.py`: khi `violation_checker.check()` trả violation:
    - Lưu frame snapshot `static/results/speed_{track_id}_{speed}kmh_{timestamp}.jpg`
    - Gọi `db.save_speed_violation({...violation, "evidence_path": path, "camera_id": cam_id})`
  - **API** trong `routes_extended.py`:
    - `GET /api/speed/violations` — list, filter `hours`, `camera_id`
    - `GET /api/speed/config` — trả `{"limit_kmh": N, "consecutive_frames": M}`
    - `POST /api/speed/config` — cập nhật `speed_limit_kmh` và `consecutive_frames` trên `violation_checker` instance
  - Cập nhật `static/js/services/api.js`: `fetchSpeedViolations()`, `getSpeedConfig()`, `updateSpeedConfig(config)`
  - **Tiêu chí:** `POST /api/speed/config {"limit_kmh": 20}` → violations trigger với ngưỡng mới; `GET /api/speed/violations` trả array

- [~] 3.3 UI vi phạm tốc độ + bbox đỏ trên live/video
  - **Phụ thuộc:** Task 3.2
  - **Overlay frame**: trong pipeline annotate (sau YOLO detect), xe có violation hiện tại:
    - Vẽ bbox màu đỏ `(0, 0, 255)` thay bbox thường
    - Label: `⚠ {speed:.0f} km/h (vượt {limit})`
    - Logic: kiểm tra `track_id in violation_checker._exceed_streak and streak >= 1`
  - **`static/js/components/Dashboard.js`**: thêm section "Vi phạm tốc độ 24h":
    - Bảng: `Thời gian | Camera | Track ID | Loại xe | Tốc độ | Ngưỡng | Vượt`
    - Poll `GET /api/speed/violations` mỗi 15 giây
  - **`static/js/components/LiveStreams.js`** (hoặc `Workspace.js`): thêm Settings input "Ngưỡng tốc độ (km/h)" với preset buttons 40/50/60/80; onChange gọi `POST /api/speed/config`
  - **Tiêu chí:** Set `SPEED_LIMIT_KMH=20` qua API → thấy bbox đỏ trên live; Dashboard bảng có records

- [ ]* 3.4 Kiểm thử Speed Violation Alert
  - **Phụ thuộc:** Task 3.3
  - Tạo `tests/test_speed_violation.py`:
    - Test `SpeedViolationChecker.check()`: 3 frame liên tiếp vượt ngưỡng → violation
    - Test cooldown: violation không được báo lại trong 30 giây
    - Test false positive: xe speed=0 (đứng yên) không trigger violation
    - Test reset streak: speed vượt ngưỡng 2 frame, rồi không vượt → streak reset về 0
  - Verify 3 luồng đồng bộ: bbox đỏ trên live overlay + DB record + Dashboard table
  - Kiểm tra vi phạm không xuất hiện cho xe đứng yên (speed=0)
  - **Tiêu chí:** `pytest tests/test_speed_violation.py` pass; demo với limit=20 → hiện đủ 3 luồng

---

### Giai đoạn 4 — Tính năng 4: TOC Dashboard

- [~] 4.1 Kiểm tra và hoàn thiện tất cả analytics API
  - **Phụ thuộc:** Task 3.4
  - Verify từng endpoint trả 200 kể cả khi DB trống — sửa nếu trả 500:
    - `GET /api/analytics` — phải aggregate từ `traffic_counts`, `incidents`, `speed_violations`
    - `GET /api/analytics/hourly`
    - `GET /api/analytics/class-dist`
    - `GET /api/analytics/peak-hours`
    - `GET /api/analytics/heatmap`
    - `GET /api/export/csv` — phải tải được file CSV
    - `GET /api/export/json?hours=168`
    - `GET /api/alerts`
  - Cập nhật `analytics.py` → `build_analytics_from_db(hours)`: bổ sung aggregate từ bảng mới `traffic_counts`, `incidents`, `speed_violations` vào dict kết quả:
    - `"line_counter_summary"`: kết quả từ `db.get_traffic_by_direction()`
    - `"incident_summary"`: kết quả từ `db.get_incidents(hours=hours)`
    - `"speed_violation_summary"`: kết quả từ `db.get_speed_violations(hours=hours)`
  - Cập nhật `GET /api/export/json` trả đủ các sections trên
  - **Tiêu chí:** Tất cả endpoints trả HTTP 200; `/api/export/csv` download được; `/api/export/json` có 3 sections mới

- [~] 4.2 Webhook và alert đa loại trong `alert_manager.py`
  - **Phụ thuộc:** Task 4.1
  - Thêm vào `config.py`: `WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")`, `ALERT_COOLDOWN_PER_TYPE: int = 300` (5 phút)
  - Mở rộng `AlertManager`:
    - `_last_alert` dict đổi thành `_last_alert: dict[str, float]` key = `{alert_type}:{camera_source}`
    - Method `trigger_alert(alert_type: str, severity: str, camera_id: str, message: str, extra: dict = {}) -> bool`:
      - Check cooldown per `alert_type:camera_id`
      - Gọi `db.insert_alert()`
      - Nếu `WEBHOOK_URL` được cấu hình → POST JSON payload (timeout 5s, `threading.Thread` để không block pipeline): `{"alert_type", "severity", "camera_id", "message", "timestamp", "extra"}`
    - Cập nhật `check_and_alert()` gọi `trigger_alert()` nội bộ
  - Thêm endpoint `POST /api/alerts/webhook/test` → gửi payload mẫu tới webhook URL và trả kết quả
  - Gọi `alert_manager.trigger_alert()` từ:
    - `congestion_detector` khi HIGH → severity "HIGH"
    - `incident_detector` khi `WRONG_WAY` → severity "CRITICAL"
    - Speed violation cluster (≥3 xe trong 1 phút) → severity "MEDIUM"
  - **Tiêu chí:** Set `WEBHOOK_URL` tới `https://webhook.site/...` test → nhận POST; cooldown ngăn spam

- [~] 4.3 UI TOC Dashboard — trang mới `/#/toc`
  - **Phụ thuộc:** Task 4.2
  - Tạo `static/js/components/TOC.js`:
    - **Layout 3 hàng:**
      - Hàng trên: grid 2×2 camera thumbnail (dùng `<img>` hoặc MJPEG snapshot), kèm status badge online/offline và link tới `/#/live`
      - Hàng giữa: 3 Chart.js charts — (1) lưu lượng theo giờ (line chart, `GET /api/analytics/hourly`), (2) phân bố loại xe (pie/doughnut, `GET /api/analytics/class-dist`), (3) incidents theo loại (bar chart, `GET /api/incidents/stats`)
      - Hàng dưới: bảng cảnh báo gộp — merge `GET /api/alerts` + `GET /api/incidents` + `GET /api/speed/violations`, sort theo `created_at DESC`
      - Sidebar phải: heatmap base64 từ `GET /api/analytics/heatmap`; refresh mỗi 30 giây
    - Nút "Xuất báo cáo" → dropdown (CSV 24h / JSON 24h / JSON 7 ngày) → `GET /api/export/csv` hoặc `GET /api/export/json?hours=N`
    - Auto-refresh toàn trang mỗi 30 giây
  - Đăng ký route trong `static/js/router.js`: case `'toc'` → render `TOC` component
  - Thêm link "TOC" vào navigation trong `static/js/components/Layout.js`
  - **Tiêu chí:** `/#/toc` load không lỗi JS console; charts hiển thị dữ liệu từ Features 1–3; nút xuất CSV hoạt động

- [~] 4.4 Hoàn thiện export báo cáo JSON/CSV
  - **Phụ thuộc:** Task 4.3
  - **`GET /api/export/json?hours=N`**: đảm bảo response đầy đủ:
    ```json
    {
      "summary": {"total_traffic": N, "total_incidents": M, "total_violations": K, "period_hours": N},
      "traffic_by_direction": {...},
      "incidents": [...],
      "speed_violations": [...],
      "peak_hours": [...],
      "class_distribution": {...},
      "generated_at": "ISO timestamp"
    }
    ```
  - **`GET /api/export/csv?hours=N`**: mở rộng CSV hiện có — thêm sheet/section cho incidents và speed_violations (dùng dấu phân cách section `## INCIDENTS` trong CSV), hoặc trả zip file với 3 CSV files: `traffic.csv`, `incidents.csv`, `violations.csv`
  - **UI TOC**: dropdown chọn khoảng thời gian 24h / 7 ngày trước khi download
  - **Tiêu chí:** Download JSON với `hours=168` → file có đủ 6 keys trên với dữ liệu thực; CSV download thành công

- [ ]* 4.5 Kiểm thử tổng hợp & chuẩn bị demo đồ án
  - **Phụ thuộc:** Task 4.4
  - Chạy kiểm thử tổng hợp và sửa lỗi theo danh sách:
    - Live Streams: lưu lượng 4 hướng cập nhật real-time
    - Dashboard: incidents + speed violations hiển thị đúng
    - TOC `/#/toc`: 3 charts + bảng cảnh báo gộp + heatmap load
    - Export CSV 24h download và mở được bằng Excel
    - Export JSON 168h có đủ 6 sections
    - `POST /api/alerts/webhook/test` với WEBHOOK_URL hợp lệ → nhận được POST
    - Chạy liên tục 10 phút: không có lỗi 500 API, không có JS console error
    - Không regression: detect/fisheye/congestion/speed-label vẫn hoạt động
  - Cập nhật `QUICK_START.txt`: thêm section "Demo TOC Dashboard" với bước chạy từng tính năng
  - Tạo `tests/test_integration.py`: smoke tests cho các API chính trả HTTP 200
  - **Tiêu chí:** Kịch bản demo 5 phút liền mạch: live → incidents → violations → TOC → export CSV

---

## Notes

- Tasks có `*` là optional (test/kiểm thử) — có thể skip để tăng tốc MVP, nhưng nên làm để đảm bảo chất lượng
- Mỗi task **phụ thuộc vào task trước trong cùng giai đoạn** — không nhảy cóc
- Giai đoạn 4 chỉ bắt đầu sau khi Giai đoạn 1–3 hoàn thành
- Các file cần sửa chính theo giai đoạn:
  - **G0:** `app.py`, `line_counter.py` (mới)
  - **G1:** `line_counter.py`, `db.py`, `routes_extended.py`, `video_detect.py`, `services/camera_monitor.py`, `static/js/components/LiveStreams.js`, `static/js/services/api.js`
  - **G2:** `incident_detector.py`, `db.py`, `routes_extended.py`, `video_detect.py`, `services/camera_monitor.py`, `config.py`, `static/js/components/Dashboard.js`
  - **G3:** `speed_estimator.py`, `db.py`, `routes_extended.py`, `config.py`, `video_detect.py`, `services/camera_monitor.py`, `static/js/components/Dashboard.js`, `static/js/components/LiveStreams.js`
  - **G4:** `analytics.py`, `alert_manager.py`, `config.py`, `routes_extended.py`, `static/js/components/TOC.js` (mới), `static/js/router.js`, `static/js/components/Layout.js`
