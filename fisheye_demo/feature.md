# FishEye8K — Tính năng Hệ thống & Kế hoạch Phát triển

Tài liệu mô tả các tính năng hiện có của **FishEye8K Traffic Monitoring System** và **4 tính năng mới** cần phát triển, kèm **kế hoạch từng bước chia theo prompt** để triển khai bằng Cursor AI.

> **Bối cảnh:** Hệ thống hiện tại tập trung vào nhận diện YOLO + giám sát camera mắt cá. Cần bổ sung các module ITS phục vụ **đếm lưu lượng, phát hiện sự cố, cảnh báo vi phạm tốc độ và trung tâm điều hành giao thông**.

---

## Phần A — Tính năng hiện có (tóm tắt)

| # | Tính năng | Mô tả ngắn |
|---|-----------|------------|
| 1 | Tiền xử lý Fisheye | Biến đổi ảnh/video thường ↔ mắt cá, tùy chỉnh strength/radius/center |
| 2 | Nhận diện YOLOv11 | Phát hiện Car, Truck, Bus, Motorbike, Bicycle, Pedestrian + tracking |
| 3 | Ước tính tốc độ | `SpeedEstimator` — nhãn km/h trên bbox, tốc độ trung bình |
| 4 | Phát hiện ùn tắc | `CongestionDetector` — điểm mật độ 3 cấp LOW / MODERATE / HIGH |
| 5 | Live Streams | Giám sát 1–4 camera ngoài (VD: camera.0511.vn), MJPEG có bbox |
| 6 | Workspace | Upload ảnh/video, cấu hình ngưỡng, xuất kết quả + JSON metadata |
| 7 | Lịch sử & Dashboard | SQLite, biểu đồ phân bố loại xe, heatmap tích lũy cơ bản |

**Hạn chế so với thực tế:** Chưa có đếm lưu lượng theo hướng, chưa phát hiện đầy đủ sự cố, chưa cảnh báo vi phạm tốc độ, chưa có màn hình TOC và xuất báo cáo.

---

## Phần B — 4 tính năng cần phát triển

### Tính năng 1: Đếm lưu lượng đa hướng tại ngã tư (Virtual Line Counter)

**Vấn đề thực tế:** TOC cần biết mỗi hướng vào/ra ngã tư có bao nhiêu xe/giờ. Camera mắt cá 360° quan sát cả 4 hướng bằng **một thiết bị**.

**Chức năng:**
- 4 vạch đếm ảo (Bắc / Nam / Đông / Tây) trên Live Streams hoặc Workspace.
- Khi `track_id` cắt qua vạch → tăng bộ đếm theo hướng × loại xe × khung giờ.
- Biểu đồ lưu lượng 4 hướng real-time.

**Kỹ thuật:** `line_counter.py`, bảng `traffic_counts`, API trong `routes_extended.py`, tích hợp `video_detect.py` + `camera_monitor.py`.

**Ưu tiên:** ★★★★★

---

### Tính năng 2: Phát hiện sự cố giao thông thông minh (Smart Incident Detection)

**Vấn đề thực tế:** Tai nạn, xe hỏng, đi ngược chiều, đỗ xe trái phép gây ùn ứ nhanh — cần phát hiện sớm.

**Chức năng:** Hoàn thiện `incident_detector.py`:

| Loại | Điều kiện | Mức cảnh báo |
|------|-----------|--------------|
| `ILLEGAL_PARKING` | Đứng yên > 30s | Trung bình |
| `STOPPED_VEHICLE` | Dừng giữa làn chạy, có xe khác vượt qua | Cao |
| `WRONG_WAY` | Vector vận tốc ngược ≥ 70% hướng lưu lượng chính | Rất cao |

Lưu bằng chứng (ảnh + bbox), push cảnh báo lên Dashboard.

**Kỹ thuật:** `incident_detector.py`, bảng `incidents` (`db.py`), API `/api/incidents`, UI tab Sự cố.

**Ưu tiên:** ★★★★★

---

### Tính năng 3: Cảnh báo vi phạm tốc độ tự động (Speed Violation Alert)

**Vấn đề thực tế:** Camera cần tự động gắn cờ xe vượt ngưỡng, không chỉ hiển thị nhãn tốc độ.

**Chức năng:**
- Cấu hình ngưỡng: đô thị 50, trường học 40, cao tốc 80 km/h.
- Tốc độ > ngưỡng trong ≥ 3 frame liên tiếp → bản ghi vi phạm.
- Bbox đỏ + nhãn `⚠ 72 km/h (vượt 50)`.
- Log: track_id, tốc độ, ngưỡng, thời gian, ảnh bằng chứng.

**Kỹ thuật:** `SpeedViolationChecker` trong `speed_estimator.py`, bảng `speed_violations`, API `/api/speed/*`.

**Ưu tiên:** ★★★★☆

---

### Tính năng 4: Trung tâm điều hành & Báo cáo giao thông (TOC Dashboard)

**Vấn đề thực tế:** Dữ liệu AI cần tổng hợp, trực quan hóa và xuất báo cáo cho cơ quan quản lý.

**Chức năng:**
- Màn hình TOC: lưới 4 camera + heatmap + bảng cảnh báo (ùn tắc, sự cố, vi phạm).
- Biểu đồ lưu lượng theo giờ, phân bố loại xe, giờ cao điểm.
- Xuất CSV/JSON báo cáo ngày/tuần.
- Webhook HTTP khi ùn tắc HIGH hoặc sự cố WRONG_WAY.

**Kỹ thuật:** Kích hoạt `routes_extended.py`, mở rộng `alert_manager.py`, nâng cấp `Dashboard.js`.

**Ưu tiên:** ★★★★★ (làm sau Tính năng 1–3)

---

## Phần C — Lộ trình tổng quan

```
Giai đoạn 0 (1 ngày)     Giai đoạn 1 (1 tuần)        Giai đoạn 2 (1 tuần)       Giai đoạn 3 (1 tuần)
────────────────────     ────────────────────        ────────────────────       ────────────────────
Chuẩn bị nền tảng   →    Tính năng 1: Line Counter  Tính năng 2: Incidents     Tính năng 3: Speed
                         (backend → API → UI)        (logic → DB → UI)           Violation
                                                                                 ↓
                                                                          Giai đoạn 4 (1 tuần)
                                                                          Tính năng 4: TOC Dashboard
```

| Tính năng | Prompts | Phụ thuộc |
|-----------|---------|-----------|
| 1. Line Counter | 6 prompts | Tracking YOLO (có sẵn) |
| 2. Incident Detection | 5 prompts | Tracking + `incident_detector.py` (khung sẵn) |
| 3. Speed Violation | 4 prompts | `SpeedEstimator` (có sẵn) |
| 4. TOC Dashboard | 5 prompts | Tính năng 1–3 + `routes_extended.py` |

---

## Phần D — Kế hoạch phát triển theo Prompt

> **Cách dùng:** Copy từng prompt vào Cursor, chạy **tuần tự** theo thứ tự đánh số. Mỗi prompt có **tiêu chí hoàn thành** — chỉ chuyển prompt tiếp theo khi đã đạt.

---

### Giai đoạn 0 — Chuẩn bị nền tảng

#### Prompt 0.1 — Kích hoạt extended routes

```
Trong dự án fisheye_demo (Flask), đăng ký các API mở rộng đã có trong routes_extended.py.

Yêu cầu:
1. Đọc routes_extended.py để hiểu register_extended_routes() cần những dependency gì (heatmap, density_analyzer, alert_manager, line_counter, ...).
2. Tạo các singleton/instance cần thiết trong routes/__init__.py hoặc app.py (import từ analytics.py, alert_manager.py).
3. Gọi register_extended_routes() sau register_blueprints() trong create_app().
4. Nếu line_counter chưa có class, tạo stub LineCounter tạm trong line_counter.py (get_stats trả dict rỗng, reset() pass) để app khởi động được.
5. Không thay đổi logic không liên quan.

Tiêu chí hoàn thành:
- python app.py chạy không lỗi
- GET /api/db/health trả JSON status ok
- GET /api/analytics trả JSON (có thể rỗng)
```

---

### Giai đoạn 1 — Tính năng 1: Line Counter

#### Prompt 1.1 — Module line_counter.py (backend core)

```
Tạo module fisheye_demo/line_counter.py cho đếm lưu lượng đa hướng.

Yêu cầu:
1. Class LineCounter hỗ trợ 4 vạch đếm (directions: north, south, east, west).
   Mỗi vạch: line_start (x1,y1), line_end (x2,y2).
2. Method update(track_id, cx, cy, class_name, frame_idx):
   - Lưu vị trí trước của track_id
   - Phát hiện crossing: tọa độ trung tâm bbox cắt qua vạch (dùng kiểm tra segment intersection hoặc side-of-line đổi dấu giữa 2 frame)
   - Mỗi track_id chỉ đếm 1 lần per direction (tránh đếm trùng)
3. Method get_stats() → dict: {direction: {class_name: count, "total": N}, "grand_total": N}
4. Method reset(), set_lines(lines: dict) để cấu hình 4 vạch từ API
5. Thread-safe nếu cần (camera_monitor chạy background thread)

Tham khảo style code: speed_estimator.py, incident_detector.py.

Tiêu chí hoàn thành:
- Có unit test đơn giản hoặc script test: 1 track đi qua vạch → count tăng 1
- Không đếm trùng khi track đứng yên trên vạch
```

#### Prompt 1.2 — Database traffic_counts

```
Thêm lưu trữ lưu lượng theo hướng vào db.py.

Yêu cầu:
1. Tạo bảng traffic_counts:
   - id, camera_id, direction, class_name, count, hour_bucket (TEXT ISO hoặc YYYY-MM-DD HH:00), created_at
2. Hàm save_traffic_count(camera_id, direction, class_name, hour_bucket) — upsert hoặc increment
3. Hàm get_traffic_counts(hours=24, camera_id=None) → list dict cho biểu đồ
4. Hàm get_traffic_by_direction(hours=24) → dict grouped by direction
5. Hỗ trợ cả SQLite và PostgreSQL (theo pattern _create_tables_sqlite/_create_tables_pg hiện có)

Tiêu chí hoàn thành:
- init_db() tạo bảng mới không lỗi
- Gọi save + get trả đúng dữ liệu
```

#### Prompt 1.3 — API line counter

```
Hoàn thiện API đếm lưu lượng trong routes_extended.py (hoặc blueprint mới routes/traffic.py).

Endpoints:
- GET  /api/line-counter          → stats từ LineCounter.get_stats() + DB summary 24h
- POST /api/line-counter/config   → body: {lines: {north: {start:[x,y], end:[x,y]}, ...}}
- POST /api/line-counter/reset    → reset counter
- GET  /api/line-counter/history  → query param hours, camera_id

Đăng ký route nếu chưa có. Validate input (tọa độ số, 4 hướng hợp lệ).

Tiêu chí hoàn thành:
- curl GET /api/line-counter trả JSON có directions
- POST config cập nhật được vạch đếm
```

#### Prompt 1.4 — Tích hợp pipeline video & live camera

```
Tích hợp LineCounter vào video_detect.py và services/camera_monitor.py.

Yêu cầu:
1. Sau mỗi frame có tracking result (track_id, bbox, class_name):
   - Tính center (cx, cy)
   - Gọi line_counter.update(...)
2. Khi có crossing mới → gọi db.save_traffic_count()
3. video_detect.py: khởi tạo LineCounter per job, reset khi job mới
4. camera_monitor.py: dùng shared LineCounter instance (hoặc per camera_id)
5. Vẽ 4 vạch đếm lên frame annotated (màu khác nhau theo hướng) nếu đã config

Không làm chậm pipeline: update O(1) per track.

Tiêu chí hoàn thành:
- Chạy live camera hoặc video → get_stats() có count > 0
- Vạch hiển thị trên MJPEG/snapshot khi đã config
```

#### Prompt 1.5 — UI Live Streams: panel lưu lượng

```
Thêm UI đếm lưu lượng vào static/js/components/LiveStreams.js.

Yêu cầu:
1. Panel "Lưu lượng theo hướng" bên cạnh grid camera:
   - 4 ô: Bắc / Nam / Đông / Tây với số đếm real-time
   - Breakdown theo loại xe (Car, Motorbike, ...)
2. Poll GET /api/line-counter mỗi 3–5 giây khi live monitor đang chạy
3. Nút "Cấu hình vạch đếm": form nhập tọa độ 4 vạch (default preset giữa khung hình) → POST /api/line-counter/config
4. Nút Reset counter
5. Biểu đồ cột 4 hướng dùng Chart.js (đã có trong Dashboard)

Cập nhật static/js/services/api.js với các hàm fetch tương ứng.
Match style CSS hiện có (base.css, components.css).

Tiêu chí hoàn thành:
- Mở Live Streams → thấy panel lưu lượng cập nhật khi có xe
- Config vạch → reload không mất cấu hình (lưu server-side)
```

#### Prompt 1.6 — Kiểm thử & hoàn thiện Tính năng 1

```
Kiểm thử end-to-end Tính năng Line Counter trong fisheye_demo.

Yêu cầu:
1. Chạy python app.py, mở Live Streams với camera.0511.vn
2. Sửa lỗi nếu count không tăng hoặc API lỗi 500
3. Thêm preset vạch mặc định hợp lý cho khung 640×480 (chia 4 hướng từ tâm)
4. Ghi kết quả test ngắn vào comment đầu line_counter.py hoặc tests/test_line_counter.py

Tiêu chí hoàn thành:
- Demo được: bật live → số liệu 4 hướng thay đổi
- Không regression các tính năng cũ (detect, congestion, speed label)
```

---

### Giai đoạn 2 — Tính năng 2: Smart Incident Detection

#### Prompt 2.1 — Logic WRONG_WAY và STOPPED_VEHICLE

```
Hoàn thiện incident_detector.py — thêm 2 loại sự cố còn thiếu.

Yêu cầu:
1. _check_wrong_way(track_id, frame_idx):
   - Tính velocity vector từ 5–10 frame gần nhất
   - So sánh với "main flow direction" (cấu hình: angle độ hoặc vector trung bình của tất cả tracks đang di chuyển)
   - Nếu góc lệch > 120° và tốc độ đủ lớn → WRONG_WAY
   - Chỉ báo 1 lần per track_id (dedup)

2. _check_stopped_vehicle(track_id, frame_idx, all_boxes):
   - Xe đứng yên (displacement thấp) TRONG vùng không phải lề đường
   - Có ≥ 2 track khác di chuyển qua gần trong 5 giây → STOPPED_VEHICLE
   - Khác ILLEGAL_PARKING: thời gian đứng yên ngắn hơn (10–15s) nhưng gây cản trở

3. Cập nhật analyze() gọi cả 3 checker
4. Thêm set_main_flow_direction() hoặc auto-detect từ histogram hướng di chuyển

Tiêu chí hoàn thành:
- Test với video mẫu: ít nhất ILLEGAL_PARKING vẫn hoạt động
- WRONG_WAY/STOPPED_VEHICLE có thể trigger với synthetic test case
```

#### Prompt 2.2 — Lưu incidents vào database

```
Lưu sự cố giao thông vào DB và API.

Yêu cầu:
1. Trong db.py — đảm bảo bảng incidents có: id, incident_type, camera_id, track_id, vehicle_type, description, bbox_json, evidence_path, acknowledged, created_at
2. Hàm save_incident(incident_dict) → incident id
3. Hàm get_incidents(hours=24, acknowledged=None, incident_type=None)
4. Hàm acknowledge_incident(id)
5. Tích hợp video_detect.py và camera_monitor.py: khi incident_detector trả incident mới → save_incident + lưu ảnh evidence vào static/results/

Tiêu chí hoàn thành:
- Sự cố mới xuất hiện trong DB sau vài chục giây live monitor
```

#### Prompt 2.3 — API incidents

```
Tạo REST API cho sự cố giao thông.

Endpoints:
- GET  /api/incidents              → list, filter hours/type/acknowledged
- GET  /api/incidents/<id>         → chi tiết + link ảnh evidence
- POST /api/incidents/<id>/acknowledge
- GET  /api/incidents/stats        → đếm theo loại trong 24h

Đăng ký vào routes_extended.py hoặc blueprint traffic.

Tiêu chí hoàn thành:
- curl GET /api/incidents trả JSON array
- acknowledge cập nhật acknowledged=1
```

#### Prompt 2.4 — UI tab Sự cố trên Dashboard

```
Thêm giao diện quản lý sự cố vào Dashboard.

Yêu cầu:
1. Trong static/js/components/Dashboard.js (hoặc component Incidents.js mới):
   - Bảng sự cố: thời gian, loại, camera, loại xe, mô tả, trạng thái
   - Badge đỏ trên sidebar: số sự cố chưa xử lý
   - Nút "Xác nhận" gọi POST acknowledge
   - Màu theo mức: WRONG_WAY đỏ, STOPPED_VEHICLE cam, ILLEGAL_PARKING vàng
2. Poll /api/incidents mỗi 10s
3. Tích hợp alert_manager: khi WRONG_WAY → tạo alert HIGH priority

Tiêu chí hoàn thành:
- Dashboard hiển thị sự cố real-time từ live camera
- Badge cập nhật khi có sự cố mới
```

#### Prompt 2.5 — Kiểm thử Tính năng 2

```
Kiểm thử Smart Incident Detection end-to-end.

Yêu cầu:
1. Test ILLEGAL_PARKING với video có xe đứng lâu
2. Verify DB + API + UI đồng bộ
3. Fix dedup (không spam cùng 1 track_id hàng trăm incident)
4. Document ngưỡng cấu hình trong config.py (PARKING_THRESHOLD, WRONG_WAY_ANGLE, ...)

Tiêu chí hoàn thành:
- Demo được ít nhất 1 loại sự cố trên UI
- Không flood alerts/logs
```

---

### Giai đoạn 3 — Tính năng 3: Speed Violation Alert

#### Prompt 3.1 — SpeedViolationChecker module

```
Mở rộng speed_estimator.py với class SpeedViolationChecker.

Yêu cầu:
1. Class nhận speed_limit_kmh (mặc định 50), consecutive_frames=3
2. Method check(track_id, speed_kmh, frame_idx) → None hoặc violation dict
3. Chỉ tạo violation khi speed > limit đủ N frame liên tiếp
4. Dedup: mỗi track_id chỉ 1 violation per 30 giây
5. get_violations(), reset()

Tích hợp vào SpeedEstimator hoặc dùng song song trong pipeline.

Tiêu chí hoàn thành:
- speed=60, limit=50, 3 frame → trả violation dict
- speed=55 rồi 45 → không violation
```

#### Prompt 3.2 — DB và API speed violations

```
Lưu trữ và API vi phạm tốc độ.

Yêu cầu:
1. Bảng speed_violations: id, camera_id, track_id, vehicle_type, speed_kmh, limit_kmh, evidence_path, created_at
2. db.py: save_speed_violation(), get_speed_violations(hours=24)
3. API:
   - GET  /api/speed/violations
   - GET  /api/speed/config   → {limit_kmh, consecutive_frames}
   - POST /api/speed/config   → cập nhật ngưỡng
4. config.py: SPEED_LIMIT_KMH từ .env

Pipeline: khi violation → save DB + lưu frame evidence

Tiêu chí hoàn thành:
- POST config đổi limit → violation trigger theo ngưỡng mới
```

#### Prompt 3.3 — UI vi phạm tốc độ + bbox đỏ

```
UI và hiển thị vi phạm tốc độ trên live/video.

Yêu cầu:
1. LiveStreams.js + camera_monitor overlay:
   - Xe vi phạm: bbox màu đỏ, label "⚠ {speed} km/h (vượt {limit})"
2. Dashboard: bảng vi phạm 24h gần nhất
3. Settings.js: slider/input ngưỡng tốc độ (40/50/60/80 preset)

Tiêu chí hoàn thành:
- Giảm SPEED_LIMIT_KMH xuống 20 để test dễ → thấy bbox đỏ trên live
- Bảng Dashboard có bản ghi
```

#### Prompt 3.4 — Kiểm thử Tính năng 3

```
Kiểm thử Speed Violation Alert.

Yêu cầu:
1. Test với live camera và video upload
2. Verify không false positive quá nhiều (xe đứng yên speed=0 không violation)
3. Export violations trong metadata JSON của video job

Tiêu chí hoàn thành:
- 3 luồng đồng bộ: overlay đỏ + DB + Dashboard table
```

---

### Giai đoạn 4 — Tính năng 4: TOC Dashboard

#### Prompt 4.1 — Kích hoạt analytics API đầy đủ

```
Đảm bảo toàn bộ analytics API trong routes_extended.py hoạt động.

Kiểm tra và sửa các endpoint:
- GET /api/analytics
- GET /api/analytics/hourly
- GET /api/analytics/class-dist
- GET /api/analytics/peak-hours
- GET /api/analytics/heatmap
- GET /api/export/csv
- GET /api/alerts

Mỗi endpoint trả JSON hợp lệ kể cả khi DB trống.
build_analytics_from_db() trong analytics.py phải aggregate từ traffic_counts, incidents, speed_violations.

Tiêu chí hoàn thành:
- Tất cả endpoint trả 200 (không 500)
- /api/export/csv tải được file CSV
```

#### Prompt 4.2 — Webhook và alert đa loại

```
Mở rộng alert_manager.py hỗ trợ webhook và nhiều loại cảnh báo.

Yêu cầu:
1. Cấu hình WEBHOOK_URL trong .env / config.py
2. Khi trigger alert (HIGH congestion, WRONG_WAY, speed violation cluster):
   - Lưu alerts table (đã có)
   - POST JSON tới webhook (timeout 5s, không block pipeline)
3. POST /api/alerts/webhook/test → gửi payload mẫu
4. Cooldown per alert_type (tránh spam)

Payload mẫu: {alert_type, severity, camera_id, message, timestamp, extra}

Tiêu chí hoàn thành:
- Cấu hình webhook tới webhook.site test → nhận được POST
```

#### Prompt 4.3 — UI TOC Dashboard (trang mới)

```
Tạo màn hình Trung tâm Điều hành Giao thông (TOC).

Yêu cầu:
1. Component static/js/components/TOC.js (hoặc mở rộng Dashboard.js)
2. Layout:
   - Hàng trên: 4 ô camera thumbnail (link tới Live Streams) + trạng thái online
   - Hàng giữa: 3 biểu đồ — lưu lượng theo giờ, phân bố loại xe, sự cố theo loại
   - Hàng dưới: bảng cảnh báo gộp (ùn tắc + incidents + speed violations) sort theo thời gian
   - Sidebar phải: heatmap overlay preview (GET /api/analytics/heatmap)
3. Đăng ký route SPA trong router.js: #/toc
4. Nút "Xuất báo cáo CSV" → GET /api/export/csv

Tiêu chí hoàn thành:
- Truy cập /#/toc thấy dashboard tổng hợp
- Dữ liệu từ Tính năng 1–3 hiển thị đúng
```

#### Prompt 4.4 — Export báo cáo JSON/PDF-ready

```
Hoàn thiện xuất báo cáo cho cơ quan quản lý.

Yêu cầu:
1. GET /api/export/json?hours=168 → JSON tổng hợp:
   - summary: tổng lưu lượng, sự cố, vi phạm
   - traffic_by_direction, incidents, speed_violations, peak_hours
2. GET /api/export/csv → CSV nhiều sheet hoặc nhiều file zip (traffic, incidents, violations)
3. UI TOC: chọn khoảng thời gian (24h / 7 ngày) → tải báo cáo

Tiêu chí hoàn thành:
- Tải JSON và CSV thành công với dữ liệu thật từ demo
```

#### Prompt 4.5 — Kiểm thử tổng hợp & demo đồ án

```
Kiểm thử tổng hợp 4 tính năng cho demo bảo vệ đồ án.

Checklist:
1. [ ] Live Streams: lưu lượng 4 hướng real-time
2. [ ] Dashboard: sự cố + vi phạm tốc độ
3. [ ] TOC: biểu đồ + cảnh báo + heatmap
4. [ ] Xuất CSV báo cáo 24h
5. [ ] Webhook fire khi ùn tắc HIGH (hoặc simulate)
6. [ ] Không lỗi console JS, không 500 API khi chạy 10 phút liên tục

Sửa lỗi tìm được. Cập nhật QUICK_START.txt với hướng dẫn demo TOC.

Tiêu chí hoàn thành:
- Chạy được kịch bản demo 5 phút liền mạch cho hội đồng
```

---

## Phần E — Lợi thế camera mắt cá

| Tiêu chí | Camera thường | Camera mắt cá (FishEye8K) |
|----------|---------------|---------------------------|
| Phạm vi ngã tư | Cần 4 camera | **1 camera** 360° |
| Chi phí lắp đặt | Cao | Thấp hơn đáng kể |
| Đếm lưu lượng đa hướng | Đồng bộ 4 luồng | **1 luồng**, 4 vạch ảo |
| Mô hình AI | YOLO thường | **YOLO fine-tune FishEye8K** |

> *"Hệ thống cung cấp bộ công cụ ITS — đếm lưu lượng, phát hiện sự cố, cảnh báo vi phạm và trung tâm điều hành — tận dụng một camera thay cho bốn."*

---

## Phần F — Map file mã nguồn

| Tính năng | File chính |
|-----------|------------|
| 1. Line Counter | `line_counter.py`, `video_detect.py`, `camera_monitor.py`, `LiveStreams.js` |
| 2. Incidents | `incident_detector.py`, `db.py`, `Dashboard.js` |
| 3. Speed Violation | `speed_estimator.py`, `config.py`, `Settings.js` |
| 4. TOC Dashboard | `routes_extended.py`, `alert_manager.py`, `analytics.py`, `TOC.js` |

---

*Tài liệu cập nhật: 06/2025 — 4 tính năng, 20 prompts triển khai tuần tự*
