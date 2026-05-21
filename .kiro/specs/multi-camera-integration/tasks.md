# Implementation Plan: Multi-Camera Integration

## Overview

Triển khai tính năng Multi-Camera Integration theo từng bước tăng dần, bắt đầu từ việc mở rộng `external_camera_detector.py` hiện có, sau đó xây dựng `MultiCameraManager`, `CrossCameraTracker`, mở rộng API routes, và cuối cùng cập nhật frontend dashboard. Mỗi bước đều tích hợp vào hệ thống hiện có và được kiểm tra trước khi chuyển sang bước tiếp theo.

## Tasks

- [x] 1. Mở rộng `external_camera_detector.py` để hỗ trợ 6 camera đồng thời
  - [x] 1.1 Tăng giới hạn `limit` mặc định từ 4 lên 6 trong `extract_camera_entries()`
    - Cập nhật signature: `def extract_camera_entries(page_url: str, limit: int = 6, timeout: int = 20)`
    - Thêm field `stream_type: StreamType` vào `ExternalCameraItem` dataclass (enum: `YOUTUBE_LIVE`, `HTTP_SNAPSHOT`)
    - Thêm field `priority: int = 1` và `coordinates: Optional[Tuple[float, float]] = None` vào `ExternalCameraItem`
    - _Requirements: 1.1, 1.3, 1.5_

  - [x] 1.2 Thêm hàm `serialize_camera_item()` và `deserialize_camera_item()` cho round-trip config
    - `serialize_camera_item(item: ExternalCameraItem) -> dict` — chuyển dataclass thành dict JSON-serializable
    - `deserialize_camera_item(data: dict) -> ExternalCameraItem` — parse dict thành dataclass, raise `ValueError` nếu thiếu field bắt buộc
    - _Requirements: 11.1, 11.4_

  - [x]* 1.3 Viết property test cho round-trip consistency (Property 1)
    - **Property 1: Camera Discovery Round-Trip Consistency**
    - **Validates: Requirements 11.4**
    - Dùng `hypothesis` để generate arbitrary `ExternalCameraItem` objects
    - Assert `deserialize_camera_item(serialize_camera_item(item)) == item`

- [ ] 2. Tạo `multi_camera_manager.py` — lõi quản lý đa camera
  - [ ] 2.1 Định nghĩa data models và enums cốt lõi
    - Tạo file `fisheye_demo/multi_camera_manager.py`
    - Định nghĩa `StreamType(Enum)`: `YOUTUBE_LIVE`, `HTTP_SNAPSHOT`
    - Định nghĩa `CameraStatus(Enum)`: `ACTIVE`, `DEGRADED`, `OFFLINE`, `RECOVERING`
    - Định nghĩa `Priority(Enum)`: `LOW=1`, `NORMAL=2`, `HIGH=3`, `CRITICAL=4`
    - Định nghĩa `CameraInfo` dataclass với các fields: `id`, `title`, `location_description`, `stream_url`, `snapshot_url`, `stream_type`, `coordinates`, `priority`
    - Định nghĩa `HealthMetrics` dataclass: `fps`, `latency_ms`, `uptime_ratio`, `error_rate`, `last_check`
    - _Requirements: 1.5, 1.6, 5.3_

  - [ ] 2.2 Implement `CameraHealthMonitor` class
    - Method `calculate_health_score(metrics: HealthMetrics) -> float` — trả về giá trị trong [0, 100]
      - fps_score = min(metrics.fps / 30.0, 1.0) * 40
      - latency_score = max(0, 1 - metrics.latency_ms / 5000) * 30
      - uptime_score = metrics.uptime_ratio * 20
      - error_score = max(0, 1 - metrics.error_rate) * 10
      - Clamp kết quả: `max(0.0, min(100.0, total))`
    - Method `check_camera_health(camera_id: str, camera_info: CameraInfo) -> HealthMetrics` — thực hiện HTTP HEAD request đến snapshot_url, đo latency
    - Method `get_uptime_stats(camera_id: str) -> dict` — trả về uptime percentage và downtime events
    - _Requirements: 5.1, 5.3, 5.4, 5.7_

  - [ ]* 2.3 Viết property test cho health score invariant (Property 2)
    - **Property 2: Health Score Invariant**
    - **Validates: Requirements 5.7**
    - Dùng `hypothesis` với `@given(fps=floats(0, 120), latency_ms=floats(0, 10000), uptime_ratio=floats(0, 1), error_rate=floats(0, 1))`
    - Assert `0 <= calculate_health_score(metrics) <= 100` với mọi input hợp lệ

  - [ ] 2.4 Implement `MultiCameraManager` class — camera discovery và lifecycle
    - Method `discover_cameras(source_url: str, limit: int = 6) -> List[CameraInfo]` — gọi `extract_camera_entries()` và chuyển đổi sang `CameraInfo`
    - Method `add_camera(camera_info: CameraInfo) -> str` — thêm camera vào registry, trả về camera_id
    - Method `remove_camera(camera_id: str) -> bool` — xóa camera khỏi registry
    - Method `get_camera_status(camera_id: str) -> CameraStatus` — trả về trạng thái hiện tại
    - Method `list_cameras() -> List[CameraInfo]` — liệt kê tất cả camera đã đăng ký
    - Method `sync_timestamps() -> Dict[str, float]` — đồng bộ timestamp, đảm bảo sai lệch ≤ 100ms
    - Lưu trữ camera registry trong `Dict[str, CameraInfo]`
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 10.1_

  - [ ]* 2.5 Viết property test cho timestamp synchronization (Property 5)
    - **Property 5: Timestamp Synchronization Accuracy**
    - **Validates: Requirements 10.1**
    - Generate arbitrary camera timestamp offsets, gọi `sync_timestamps()`, assert `|ts_i - ts_j| <= 0.1` (100ms) cho mọi cặp

  - [ ] 2.6 Implement `LoadBalancer` class
    - Method `distribute_cameras(cameras: List[str], nodes: List[ProcessingNode]) -> Dict[str, str]` — phân phối cameras vào nodes
    - Thuật toán: weighted round-robin dựa trên `camera.priority` và `node.capacity`
    - Assert invariant: tổng load của mỗi node ≤ node.capacity sau khi phân phối
    - Method `get_resource_metrics() -> ResourceMetrics` — trả về CPU/memory usage hiện tại qua `psutil`
    - Method `adjust_quality(camera_id: str, resource_usage: float)` — giảm FPS target khi CPU > 80%
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7_

  - [ ]* 2.7 Viết property test cho load distribution (Property 4)
    - **Property 4: Load Distribution Does Not Exceed Capacity**
    - **Validates: Requirements 6.1, 6.4**
    - Generate arbitrary camera lists (1–6) và node capacities, assert không node nào bị overload sau `distribute_cameras()`

- [ ] 3. Checkpoint — Kiểm tra các module cốt lõi
  - Chạy tất cả unit tests và property tests cho `external_camera_detector.py` và `multi_camera_manager.py`
  - Đảm bảo `CameraHealthMonitor`, `MultiCameraManager`, `LoadBalancer` hoạt động đúng
  - Hỏi người dùng nếu có vấn đề cần làm rõ.

- [ ] 4. Tạo `cross_camera_tracker.py` — theo dõi xe đa camera
  - [ ] 4.1 Định nghĩa data models cho tracking
    - Tạo file `fisheye_demo/cross_camera_tracker.py`
    - Định nghĩa `VehicleFeatures` dataclass: `vehicle_class`, `bbox_area`, `aspect_ratio`, `color_histogram` (Optional)
    - Định nghĩa `VehicleTrack` dataclass: `track_id`, `camera_id`, `vehicle_class`, `first_seen`, `last_seen`, `trajectory`, `features`, `confidence`
    - Định nghĩa `Checkpoint` dataclass: `camera_id`, `timestamp`, `position`
    - Định nghĩa `Journey` dataclass: `journey_id`, `vehicle_class`, `start_camera`, `end_camera`, `start_time`, `end_time`, `travel_time`, `checkpoints`
    - _Requirements: 3.3, 3.4, 3.6, 3.7_

  - [ ] 4.2 Implement `CrossCameraTracker` class — core tracking logic
    - Method `update_detections(camera_id: str, detections: List[dict], timestamp: datetime) -> List[str]` — cập nhật tracks với detections mới, trả về list track_ids
    - Method `match_cross_camera(exiting_track: VehicleTrack, entering_detections: List[dict], time_window_sec: float = 30.0) -> Optional[str]` — match xe rời camera này với xe vào camera khác dựa trên vehicle_class và feature similarity
    - Method `generate_journey_id() -> str` — tạo UUID v4 duy nhất
    - Method `get_active_journeys() -> List[Journey]` — trả về journeys đang active
    - Method `calculate_travel_time(from_camera: str, to_camera: str) -> Optional[float]` — tính thời gian di chuyển trung bình
    - Lưu `active_tracks: Dict[str, VehicleTrack]` và `journey_history: List[Journey]`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7_

  - [ ] 4.3 Implement duplicate counting prevention cho overlapping cameras
    - Method `get_unique_vehicle_count(camera_ids: List[str]) -> int` — đếm xe unique, loại bỏ duplicates từ overlapping cameras
    - Logic: nếu cùng vehicle_class xuất hiện trong 2+ cameras trong cùng time window (5 giây), chỉ đếm 1 lần
    - Method `mark_cameras_overlapping(cam_a: str, cam_b: str)` — đánh dấu 2 cameras có vùng phủ chồng lấp
    - _Requirements: 3.5_

  - [ ]* 4.4 Viết property test cho no duplicate counting (Property 3)
    - **Property 3: Cross-Camera No Duplicate Counting**
    - **Validates: Requirements 3.5**
    - Generate detections của cùng xe xuất hiện trong 2 overlapping cameras
    - Assert `get_unique_vehicle_count([cam_a, cam_b]) <= count(cam_a) + count(cam_b)`

  - [ ]* 4.5 Viết property test cho journey ID uniqueness (Property 6)
    - **Property 6: Journey ID Uniqueness**
    - **Validates: Requirements 3.7**
    - Generate 100+ tracking events, collect tất cả journey_ids
    - Assert `len(set(journey_ids)) == len(journey_ids)`

- [ ] 5. Mở rộng database schema cho multi-camera
  - [ ] 5.1 Thêm migration script cho SQLite (tương thích với `db.py` hiện có)
    - Tạo file `fisheye_demo/migrations/001_multi_camera.sql`
    - Tạo bảng `cameras`: `id`, `name`, `source_url`, `stream_type`, `priority`, `created_at`, `updated_at`
    - Tạo bảng `camera_health`: `camera_id`, `timestamp`, `status`, `fps`, `latency_ms`, `health_score`, `error_message`
    - Tạo bảng `cross_camera_tracks`: `journey_id`, `vehicle_class`, `start_camera`, `end_camera`, `start_time`, `end_time`, `travel_time_seconds`, `checkpoints_json`
    - Thêm indexes: `idx_camera_health_timestamp`, `idx_cross_camera_tracks_time`
    - _Requirements: 10.2, 10.3_

  - [ ] 5.2 Cập nhật `db.py` để thêm helper functions cho multi-camera tables
    - `save_camera(camera_info: CameraInfo) -> None`
    - `get_all_cameras() -> List[dict]`
    - `save_health_check(camera_id: str, metrics: HealthMetrics) -> None`
    - `get_camera_health_history(camera_id: str, limit: int = 100) -> List[dict]`
    - `save_journey(journey: Journey) -> None`
    - `get_journeys(from_camera: str = None, to_camera: str = None) -> List[dict]`
    - _Requirements: 10.2, 10.3, 10.7_

- [ ] 6. Mở rộng API routes cho multi-camera
  - [ ] 6.1 Tạo `multi_camera_routes.py` với Blueprint Flask
    - Tạo file `fisheye_demo/multi_camera_routes.py`
    - `GET /api/cameras` — liệt kê tất cả cameras đã đăng ký
    - `POST /api/cameras/discover` — trigger discovery từ camera.0511.vn, body: `{"source_url": "...", "limit": 6}`
    - `POST /api/cameras` — thêm camera thủ công, body: `CameraInfo` JSON
    - `DELETE /api/cameras/<camera_id>` — xóa camera
    - `GET /api/cameras/<camera_id>/status` — trả về `CameraStatus` và `HealthMetrics`
    - `GET /api/cameras/<camera_id>/snapshot` — trả về snapshot image hiện tại (JPEG)
    - _Requirements: 14.1, 14.4, 1.1, 1.2_

  - [ ] 6.2 Thêm routes cho health monitoring và analytics
    - `GET /api/cameras/<camera_id>/health` — trả về health score và uptime stats
    - `GET /api/cameras/health/summary` — health summary cho tất cả cameras
    - `GET /api/journeys` — liệt kê cross-camera journeys, query params: `from_camera`, `to_camera`, `limit`
    - `GET /api/analytics/multi-camera` — aggregated traffic stats từ tất cả cameras
    - `GET /api/analytics/correlation` — correlation matrix giữa các camera pairs
    - _Requirements: 14.1, 5.7, 3.3, 15.3_

  - [ ] 6.3 Đăng ký Blueprint vào `app.py`
    - Import `multi_camera_routes` blueprint trong `app.py`
    - Khởi tạo `MultiCameraManager` và inject vào blueprint
    - Đăng ký blueprint với prefix `/api`
    - _Requirements: 14.1_

  - [ ]* 6.4 Viết unit tests cho API routes
    - Test `GET /api/cameras` trả về list đúng format
    - Test `POST /api/cameras/discover` với mock của `extract_camera_entries()`
    - Test error handling khi camera không tồn tại (404)
    - Test `GET /api/cameras/<id>/health` trả về health score trong [0, 100]
    - _Requirements: 14.1, 5.7_

- [ ] 7. Implement `TrafficCorrelator` trong `analytics.py`
  - [ ] 7.1 Thêm class `TrafficCorrelator` vào `analytics.py`
    - Method `calculate_correlation(series_a: List[int], series_b: List[int]) -> float` — tính Pearson correlation, trả về giá trị trong [-1, 1], xử lý constant series (trả về 0.0)
    - Method `build_correlation_matrix(camera_ids: List[str], time_window_hours: int = 24) -> Dict[str, Dict[str, float]]` — tính correlation matrix cho tất cả camera pairs
    - Method `detect_rush_hour_patterns(camera_id: str) -> List[dict]` — phát hiện peak traffic hours
    - Method `identify_lead_lag(series_a: List[int], series_b: List[int], max_lag: int = 10) -> int` — tìm lag tối ưu giữa 2 series
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [ ]* 7.2 Viết property test cho correlation coefficient bounds (Property 7)
    - **Property 7: Traffic Correlation Coefficient Bounds**
    - **Validates: Requirements 15.3**
    - Dùng `hypothesis` với `@given(lists(integers(min_value=0, max_value=1000), min_size=2))`
    - Assert `-1.0 <= calculate_correlation(series_a, series_b) <= 1.0` với mọi input hợp lệ
    - Test edge case: constant series không raise exception

- [ ] 8. Checkpoint — Kiểm tra backend hoàn chỉnh
  - Chạy tất cả tests: `pytest fisheye_demo/tests/ -v`
  - Kiểm tra tất cả API endpoints hoạt động đúng với `curl` hoặc test client
  - Đảm bảo database migrations chạy thành công
  - Hỏi người dùng nếu có vấn đề cần làm rõ.

- [ ] 9. Cập nhật frontend dashboard cho multi-camera
  - [ ] 9.1 Tạo template `multi_camera_dashboard.html`
    - Tạo file `fisheye_demo/templates/multi_camera_dashboard.html`
    - Grid layout 2x2 và 3x3 cho camera feeds (CSS Grid)
    - Mỗi camera cell hiển thị: snapshot image, camera title, health indicator (màu xanh/vàng/đỏ), vehicle count
    - Panel thống kê tổng hợp: tổng xe, số camera active, alerts
    - Controls: nút "Refresh All", "Discover Cameras", toggle từng camera
    - _Requirements: 4.1, 4.2, 4.5, 4.6_

  - [ ] 9.2 Thêm JavaScript cho real-time updates và camera grid
    - Polling `GET /api/cameras/health/summary` mỗi 30 giây để cập nhật health indicators
    - Polling `GET /api/cameras/<id>/snapshot` mỗi 5 giây cho mỗi camera active
    - Click vào camera cell để xem full-screen snapshot
    - Highlight camera cell màu đỏ khi congestion detected (dựa trên analytics data)
    - Toggle grid layout 2x2 / 3x3 bằng nút UI
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.7_

  - [ ] 9.3 Thêm route Flask cho dashboard page
    - Thêm `GET /multi-camera` route vào `multi_camera_routes.py`
    - Render `multi_camera_dashboard.html` với initial camera list
    - Thêm link đến dashboard trong navigation của `app.py`
    - _Requirements: 4.1, 4.4_

  - [ ] 9.4 Thêm cross-camera tracking panel vào dashboard
    - Section "Active Journeys" hiển thị list journeys đang active từ `GET /api/journeys`
    - Mỗi journey hiển thị: vehicle_class, from_camera → to_camera, elapsed time
    - Auto-refresh mỗi 10 giây
    - _Requirements: 4.8_

- [ ] 10. Implement `FailoverManager` trong `multi_camera_manager.py`
  - [ ] 10.1 Thêm `FailoverManager` class
    - Method `start_monitoring(camera_id: str, retry_interval_sec: int = 120)` — bắt đầu background thread theo dõi camera
    - Method `handle_camera_failure(camera_id: str, error: Exception)` — log lỗi, cập nhật status thành `OFFLINE`, trigger retry
    - Method `attempt_recovery(camera_id: str) -> bool` — thử kết nối lại, cập nhật status thành `ACTIVE` nếu thành công
    - Method `get_failover_log() -> List[dict]` — trả về log các sự kiện failover
    - Tích hợp với `CameraHealthMonitor` để nhận health alerts
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6_

  - [ ]* 10.2 Viết unit tests cho failover logic
    - Test camera failure detection và status transition `ACTIVE → OFFLINE`
    - Test auto-recovery sau retry interval
    - Test `OFFLINE → ACTIVE` transition khi camera phục hồi
    - Mock HTTP requests để simulate camera failures
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 11. Tích hợp với hệ thống Alert Manager hiện có
  - [ ] 11.1 Mở rộng `alert_manager.py` để hỗ trợ multi-camera alerts
    - Thêm alert types: `CAMERA_OFFLINE`, `CAMERA_DEGRADED`, `MULTI_CAMERA_CONGESTION`, `FAILOVER_TRIGGERED`
    - Method `send_camera_alert(camera_id: str, alert_type: str, severity: str, message: str)` — gửi alert qua channels hiện có
    - Method `aggregate_similar_alerts(alerts: List[dict], time_window_sec: int = 60) -> List[dict]` — gộp alerts tương tự để tránh spam
    - _Requirements: 13.1, 13.3, 13.4_

  - [ ]* 11.2 Viết unit tests cho alert aggregation
    - Test rằng 5 alerts tương tự trong 60 giây được gộp thành 1
    - Test severity escalation khi alert không được acknowledge
    - _Requirements: 13.3, 13.7_

- [ ] 12. Final checkpoint — Kiểm tra toàn bộ hệ thống
  - Chạy toàn bộ test suite: `pytest fisheye_demo/ -v --tb=short`
  - Kiểm tra dashboard render đúng trong browser
  - Kiểm tra API endpoints trả về đúng format JSON
  - Kiểm tra database schema được tạo đúng
  - Hỏi người dùng nếu có vấn đề cần làm rõ.

## Notes

- Tasks đánh dấu `*` là optional và có thể bỏ qua để triển khai MVP nhanh hơn
- Mỗi task tham chiếu đến requirements cụ thể để đảm bảo traceability
- Property tests dùng thư viện `hypothesis` — cần thêm vào `requirements.txt`
- Checkpoints đảm bảo kiểm tra tăng dần sau mỗi nhóm task lớn
- Property tests validate các invariants toán học quan trọng (health score bounds, correlation bounds, no duplicates)
- Unit tests validate các ví dụ cụ thể và edge cases
- Tất cả code mới phải tương thích với cả SQLite (dev) và PostgreSQL (prod)
