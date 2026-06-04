# CHƯƠNG 2. PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG

## 2.1. Đặc tả yêu cầu hệ thống

### 2.1.1. Khảo sát hệ thống camera giao thông trực tuyến

Đề tài khảo sát hai hệ thống: camera.0511.vn (Đà Nẵng) và alltrafficcams.com (quốc tế) nhằm nhận diện tính năng cần thiết, xác định khoảng trống về phân tích thông minh và rút ra bài học thiết kế.

#### 2.1.1.1. Hệ thống camera.0511.vn

camera.0511.vn là hệ thống camera giám sát giao thông của Đà Nẵng, cung cấp live stream công cộng miễn phí. Tính năng: xem live stream/snapshot từ nhiều camera trên bản đồ số, hỗ trợ grid view đa camera. Hạn chế: không có phân tích AI tự động, không đếm phương tiện, không phát hiện tắc nghẽn hay sự cố, không lưu lịch sử, không hỗ trợ camera fisheye.

*[Hình ảnh]*

Hình 2.1. Giao diện của hệ thống camera.0511.vn

#### 2.1.1.2. Hệ thống alltrafficcams.com

alltrafficcams.com là aggregator tổng hợp hàng nghìn camera giao thông quốc tế (Mỹ, Anh, Úc,...). Tính năng: phân loại theo địa lý, tích hợp bản đồ thế giới, xem ảnh lịch sử một số nguồn. Hạn chế: phụ thuộc bên thứ ba, không có AI tự động, độ trễ cao (5–30s), không hỗ trợ fisheye chuyên biệt, không cảnh báo tự động.

*[Hình ảnh]*

Hình 2.2. Giao diện của hệ thống camera alltrafficcams.com

#### 2.1.1.3. Tổng hợp và định hướng

| **Đặc điểm / Tính năng** | **camera.0511.vn** | **alltrafficcams.com** | **Hệ thống đề xuất** |
| --- | --- | --- | --- |
| Xem live camera | Có | Có | Có |
| Tích hợp bản đồ địa lý | Có | Có | Có |
| Hỗ trợ camera fisheye | Hạn chế | Không | Chuyên biệt (fisheye-native) |
| Phân tích AI tự động | Không | Không | Có (YOLOv11-N fine-tune) |
| Đếm phương tiện tự động | Không | Không | Có |
| Ước lượng tốc độ | Không | Không | Có (pixel displacement) |
| Phát hiện tắc nghẽn | Không | Hạn chế (thủ công) | Có (phân tích mật độ ROI) |
| Cảnh báo mật độ cao | Không | Không | Có (Email/Webhook khi ùn tắc) |
| Cảnh báo tự động đa kênh | Không | Không | Có (email/webhook) |
| Lưu trữ và truy vấn lịch sử | Không | Hạn chế | Có (CSDL PostgreSQL/SQLite) |
| REST API mở | Không | Không | Có (20+ endpoint) |
| Xử lý video bất đồng bộ | Không | Không | Có (job queue) |

**Bảng 2.1. So sánh hệ thống camera giao thông hiện có với hệ thống đề xuất**

### 2.1.2. Yêu cầu chức năng

| **ID** | **Chức năng** | **Tác nhân** | **Ưu tiên** | **Mô tả** |
| --- | --- | --- | --- | --- |
| UC-01 | Tải lên và xử lý ảnh tĩnh | Người dùng | Must Have | Nhận ảnh JPEG/PNG, chạy inference YOLOv11, trả về ảnh bbox và danh sách đối tượng |
| UC-02 | Xử lý video bất đồng bộ | Người dùng | Must Have | Nhận video MP4, xếp hàng job, xử lý background, trả về video annotation |
| UC-03 | Theo dõi tiến độ xử lí ảnh | Người dùng | Nice to Have | Truy vấn trạng thái job (pending/running/done/failed) và tải kết quả |
| UC-04 | Phát hiện đối tượng realtime | Người dùng | Should Have | Stream webcam, nhận kết quả detection thời gian thực |
| UC-05 | Ước lượng tốc độ phương tiện | Hệ thống | Should Have | Tính tốc độ km/h cho từng phương tiện tracking, cảnh báo vượt tốc |
| UC-06 | Phát hiện tắc nghẽn giao thông | Hệ thống | Should Have | Phân tích mật độ theo ROI, phân loại mức độ tắc nghẽn |
| UC-07 | Gửi cảnh báo mật độ cao | Hệ thống | Should Have | Thông báo qua email/webhook khi phát hiện ùn tắc giao thông nghiêm trọng |
| UC-08 | Phân tích luồng giao thông | Người dùng | Should Have | Heatmap mật độ, đếm phương tiện qua đường kẻ (line crossing) |
| UC-09 | Lưu trữ và truy vấn lịch sử | Người dùng | Should Have | Lưu kết quả detection vào CSDL, truy vấn theo thời gian và camera |
| UC-10 | SAHI inference đối tượng nhỏ | Người dùng | Nice to Have | Slice-inference để phát hiện tốt hơn đối tượng nhỏ |
| UC-11 | Upload ảnh lên cloud | Người dùng | Nice to Have | Tải ảnh/video kết quả lên Google Cloud Storage, trả về URL |

**Bảng 2.2. Danh sách yêu cầu chức năng hệ thống**

### 2.1.3. Yêu cầu phi chức năng

* Hiệu năng: Thời gian xử lý ảnh đơn lẻ ≤ 500ms trên GPU; thời gian phản hồi API list-jobs ≤ 100ms; throughput tối thiểu 10 request/giây.
* Độ tin cậy: Uptime ≥ 99% trong giờ cao điểm; job queue không mất dữ liệu khi server restart (retention = 1 giờ).
* Khả năng mở rộng: Tăng số worker bằng cách thay đổi cấu hình MAX\_WORKERS không cần sửa code.
* Khả năng bảo trì: Code module hóa rõ ràng; log đầy đủ ở các cấp DEBUG/INFO/WARNING/ERROR.

## 2.2. Kiến trúc tổng thể hệ thống

### 2.2.1. Kiến trúc phân lớp

Hệ thống theo kiến trúc phân lớp 4 tầng:

* Tầng Giao diện (Presentation Layer): Frontend web (HTML/CSS/JavaScript) và CLI tools, giao tiếp qua REST API.
* Tầng Ứng dụng (Application Layer): Flask REST API server (app.py) xử lý routing, validation, business logic.
* Tầng Dịch vụ (Service Layer): Các module độc lập: VideoJobQueue, SpeedEstimator, CongestionDetector, AlertManager, Analytics, CloudStorage.
* Tầng Dữ liệu (Data Layer): db.py hỗ trợ PostgreSQL và SQLite; mô hình YOLO tải vào bộ nhớ khi khởi động.

*[Hình ảnh]*

**Hình 2.3. Sơ đồ kiến trúc hệ thống tổng thể**

### 2.2.2. Kiến trúc xử lý video bất đồng bộ

Do xử lý video tốn nhiều thời gian, đề tài thiết kế job queue bất đồng bộ:

(1) Client POST /api/video/detect → API tạo job\_id, trả về HTTP 202 ngay lập tức; (2) VideoJobQueue.submit() đưa job vào ThreadPoolExecutor background thread; (3) Worker xử lý frame-by-frame với YOLO, tích hợp speed/congestion modules; (4) Client GET /api/jobs/{job\_id} để kiểm tra trạng thái; (5) Khi done, client tải video kết quả qua GET /api/video/download/{job\_id}.

### 2.2.3. Luồng dữ liệu

Dữ liệu đầu vào (ảnh/video từ camera hoặc upload) → Tiền xử lý fisheye → YOLO inference → Phân tích giao thông (speed, congestion) → Lưu vào CSDL → Trả kết quả qua API. Các cảnh báo được phát sinh song song khi phát hiện ùn tắc mức độ nghiêm trọng, gửi qua email/webhook không chặn luồng chính.

## 2.3. Thiết kế cơ sở dữ liệu

### 2.3.1. Sơ đồ thực thể liên kết (ERD)

| **Bảng** | **Các cột chính** | **Mô tả** |
| --- | --- | --- |
| cameras | camera\_id (PK), name, location, camera\_type, fisheye\_strength, status, created\_at, config\_json | Thông tin camera giám sát |
| detections | id (PK), camera\_id (FK), timestamp, frame\_number, class\_name, confidence, bbox\_x1, bbox\_y1, bbox\_x2, bbox\_y2, speed\_kmh, job\_id | Kết quả detection từng đối tượng |
| jobs | job\_id (PK), job\_type, status, created\_at, started\_at, finished\_at, input\_path, output\_path, error\_message, summary\_json | Trạng thái và kết quả xử lý video |
| analytics\_hourly | id (PK), camera\_id (FK), hour\_ts, total\_vehicles, avg\_speed\_kmh, congestion\_level | Thống kê tổng hợp theo giờ |
| alerts | id (PK), channel, sent\_at, status, message\_preview | Lịch sử gửi cảnh báo |

**Bảng 2.3. Cấu trúc các bảng chính trong CSDL**

### 2.3.2. Chiến lược tương thích đa CSDL

Module db.py sử dụng lớp abstraction cho phép chuyển đổi trong suốt giữa PostgreSQL và SQLite. Biến môi trường DATABASE\_URL xác định backend: nếu không có hoặc bắt đầu bằng 'sqlite://', hệ thống dùng SQLite. Điều này giúp developer chạy ứng dụng local mà không cần cài PostgreSQL.

## 2.4. Thiết kế REST API

### 2.4.1. Quy ước thiết kế API

* Tất cả endpoint có tiền tố /api/, resource đặt tên theo danh từ số nhiều.
* HTTP method đúng chuẩn: GET (truy vấn), POST (tạo mới/xử lý), DELETE (xóa).
* Response format: JSON với cấu trúc {"status": "ok"|"error", "data": {...}}.
* HTTP status code chuẩn: 200 (OK), 202 (Accepted – async), 400 (Bad Request), 404 (Not Found), 500 (Server Error).
* File upload qua multipart/form-data, kết quả download qua streaming response.

### 2.4.2. Danh sách API endpoint

| **Method** | **Endpoint** | **Chức năng** | **Ghi chú** |
| --- | --- | --- | --- |
| POST | /api/detect | Phát hiện đối tượng trên ảnh đơn | multipart/form-data |
| POST | /api/sahi | SAHI inference cho đối tượng nhỏ | multipart/form-data |
| POST | /api/video/detect | Gửi video xử lý bất đồng bộ | multipart/form-data |
| GET | /api/jobs | Danh sách job gần đây | query: limit |
| GET | /api/jobs/{job\_id} | Trạng thái và kết quả job | path param |
| DELETE | /api/jobs/{job\_id} | Hủy job đang pending | path param |
| GET | /api/video/download/{job\_id} | Tải video kết quả | stream |
| GET | /api/video/preview/{job\_id} | Xem frame preview | stream |
| GET | /api/stats | Thống kê hệ thống tổng quan | – |
| GET | /api/cameras | Danh sách camera đã đăng ký | – |
| POST | /api/cameras | Đăng ký camera mới | JSON body |
| GET | /api/cameras/{id}/detections | Lịch sử detection theo camera | query: since, until |
| GET | /api/health | Health check hệ thống | – |
| GET | /api/model/info | Thông tin mô hình YOLO | – |
| POST | /api/model/reload | Tải lại mô hình từ file | JSON body |
| GET | /stream | MJPEG stream webcam realtime | SSE |
| POST | /api/analytics/line-crossing | Cấu hình đường đếm phương tiện | JSON body |

**Bảng 2.4. Danh sách API endpoint và mô tả chức năng**

### 2.4.3. Ví dụ luồng API – Xử lý video

Luồng điển hình xử lý video: Client POST /api/video/detect kèm file → Server trả về job\_id và HTTP 202 → Client lặp GET /api/jobs/{job\_id} (mỗi 2 giây) đến khi status=done → Client GET /api/video/preview/{job\_id} để xem frame đầu → Client GET /api/video/download/{job\_id} để tải file MP4 kết quả.

