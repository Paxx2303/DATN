> ⚠️ **TÀI LIỆU CŨ.** Nguồn chuẩn & cập nhật là [`HE_THONG.md`](HE_THONG.md). File này giữ lại để tham khảo lịch sử.

# Tài liệu Kiến trúc Hệ thống FishEye8K & Kế hoạch Refactor (System Overview & Refactor Guide)

Tài liệu này cung cấp cái nhìn chi tiết và toàn diện về toàn bộ mã nguồn của dự án **DATN - FishEye8K Detection System** (nằm trong thư mục `fisheye_demo`), nhằm mục đích làm tài liệu tham khảo cho **Claude** (hoặc bất kỳ AI nào khác) để tiến hành đánh giá, tối ưu hóa và tái cấu trúc (refactor) hệ thống một cách an toàn và hiệu quả nhất.

---

## 1. Tổng quan Hệ thống (System Overview)

Hệ thống được xây dựng nhằm mục đích **phát hiện và phân tích lưu lượng giao thông trên ảnh hoặc video từ camera góc rộng (Fisheye8K)**. 
- **Công nghệ cốt lõi**: Python 3.10+, Flask, OpenCV, PyTorch, YOLOv11 (Ultralytics), và SQLite / PostgreSQL.
- **Tính năng chính**:
  1. **Distortion Preprocessing**: Áp dụng các thuật toán nắn chỉnh / tạo biến dạng mắt cá (radial distortion) trên ảnh/video gốc để khớp hoặc mô phỏng môi trường camera thực tế.
  2. **YOLO Detection**: Nhận diện các lớp phương tiện giao thông chính bao gồm: `Car`, `Bus`, `Truck`, `Pedestrian`, `Motorbike`.
  3. **Video Processing**: Đọc, xử lý từng khung hình (apply mắt cá, chạy model, vẽ khung nhận diện) và ghi lại video đầu ra một cách đồng bộ / không đồng bộ thông qua một Job Queue nội bộ.
  4. **Traffic Analytics**: Ước lượng vận tốc phương tiện (`speed_estimator.py`), nhận diện mật độ ùn tắc (`congestion_detector.py`), lưu trữ lịch sử đếm xe (`db.py`).
  5. **Incident Detection**: Phát hiện các sự cố giao thông (tai nạn, đỗ xe sai quy định, đi ngược chiều...) thông qua `incident_detector.py`.
  6. **External Camera Live Polling**: Lấy ảnh chụp nhanh từ nguồn camera giao thông thực tế, hiển thị lưới đa camera và chạy phân tích giả lập thời gian thực.

---

## 2. Bản đồ Cấu trúc Dự án (Project Directory Map)

```text
fisheye_demo/
├── app.py                      # Điểm khởi chạy chính, định nghĩa Flask app, cấu hình và toàn bộ API Core
├── fisheye.py                  # Module thuật toán biến dạng ảnh mắt cá (radial/barrel distortion)
├── video_detect.py             # Module đọc, xử lý và ghi video sử dụng OpenCV & YOLO
├── db.py                       # Lớp cơ sở dữ liệu trừu tượng hóa (chế độ PostgreSQL GCP Cloud SQL và SQLite fallback)
├── recent_image_store.py       # Quản lý kho ảnh tĩnh hiển thị gần đây trên UI (sử dụng SQLite nội bộ)
├── external_camera_detector.py # Adapter xử lý lấy thông tin và snapshot từ camera ngoài
├── job_queue.py                # Quản lý hàng đợi xử lý video chạy ngầm sử dụng Python ThreadPool
├── config.py                   # Quản lý nạp biến môi trường (.env) và lớp lưu trữ cấu hình AppSettings
├── analytics.py                # Tính toán heatmap và phân tích mật độ phương tiện theo thời gian thực
├── alert_manager.py            # Quản lý lịch sử và kích hoạt cảnh báo mật độ cao
├── cloud_storage.py            # Hỗ trợ upload ảnh/video kết quả lên Google Cloud Storage (GCS)
├── speed_estimator.py          # Thuật toán ước lượng vận tốc dựa trên vết di chuyển (tracking)
├── congestion_detector.py      # Thuật toán tính toán CAPACITY và ROIs để đánh giá ùn tắc
├── incident_detector.py        # Logic phát hiện sự cố giao thông (đỗ xe trái phép, đi ngược chiều...)
├── templates/
│   └── index.html              # Single Page Application UI (106 KB) chứa toàn bộ CSS và logic Javascript
├── static/
│   ├── results/                # Lưu trữ kết quả (ảnh, video, metadata.json) của các phiên chạy
│   └── uploads/                # Lưu trữ tạm thời các file tải lên
├── .env.example                # File môi trường mẫu dành cho cấu hình cục bộ và sản xuất
└── requirements.txt            # Danh sách các thư viện dependencies cần thiết
```

---

## 3. Vai trò chi tiết của từng Module mã nguồn

### 3.1 `app.py` (Flask Web Server & Orchestrator)
- **Kích thước**: ~135 KB.
- **Nhiệm vụ chính**:
  - Tạo app Flask bằng App Factory `create_app(config_overrides)`.
  - Khởi tạo `ModelRegistry` để quản lý việc tải model YOLOv11 thích hợp (`yolo11_fisheye_v5_best.pt`, `yolo11n.pt`...) vào CPU hoặc GPU.
  - Khởi động `ExternalCameraLiveMonitor` (một background thread nội bộ) để quét và lấy snapshot từ nguồn camera ngoài theo chu kỳ.
  - Quản lý API Routes cho hệ thống:
    - `GET /`: Trả về giao diện người dùng SPA `index.html`.
    - `GET /api/health`: Kiểm tra sức khỏe hệ thống (trạng thái DB, GCS, dung lượng ổ đĩa, RAM, trạng thái tải Model).
    - `POST /api/detect`: Nhận ảnh/video tải lên, thực hiện nhận diện đồng bộ (đối với ảnh) hoặc đẩy vào `VideoJobQueue` (đối với video) và trả về thông tin kết quả.
    - `POST /api/convert`: Chuyển đổi ảnh hoặc video thường sang định dạng mắt cá.
    - `GET /api/history`: Lấy lịch sử các lượt chạy gần nhất.
    - `GET /api/logs`: Xuất log thời gian thực được ghi lại bởi `DequeLogHandler` lên UI.

### 3.2 `fisheye.py` (Thuật toán Biến dạng Hình học)
- **Nhiệm vụ chính**: Định nghĩa hàm `apply_fisheye()` dùng để giả lập hiệu ứng ống kính camera góc rộng từ ảnh giao thông bình thường.
- **Các bộ nắn chỉnh (Mapping functions)**:
  - `standard`: Mắt cá góc rộng chuẩn bằng hàm lượng giác `arcsin`.
  - `extreme`: Biến dạng cực đại dạng parabol.
  - `subtle`: Hiệu ứng phồng nhẹ ở tâm.
  - `traffic_camera`: Preset tối ưu hóa riêng mô phỏng camera giao thông.
- **Kỹ thuật**: Sử dụng lưới tọa độ `np.mgrid` và nội suy song tuyến tính (`bilinear_sample`) tự viết bằng Numpy để đạt hiệu năng xử lý cực nhanh trên ma trận ảnh.

### 3.3 `video_detect.py` (Xử lý Video bằng OpenCV)
- **Nhiệm vụ chính**: Xử lý toàn bộ luồng pipeline đối với video.
- **Quy trình hoạt động**:
  1. Mở video bằng `cv2.VideoCapture`.
  2. Xác định FPS và kích thước khung hình gốc.
  3. Sử dụng cấu hình `detection_stride` để giảm thiểu số lượng frame cần chạy mô hình YOLO (nhằm tăng tốc độ xử lý khi chạy CPU).
  4. Duyệt qua từng khung hình:
     - Nếu có bật `apply_fisheye_transform`, nắn ảnh sang dạng mắt cá trước.
     - Gọi `model.predict()` để nhận diện xe cộ.
     - Nếu không phải frame cần chạy YOLO, vẽ lại bounding box cũ lên khung hình mới bằng hàm nội suy thông minh.
     - Đưa dữ liệu qua `SpeedEstimator` và `CongestionDetector` để vẽ thêm vận tốc và ROIs cảnh báo trực tiếp lên khung hình.
  5. Ghi khung hình đã vẽ vào file đầu ra bằng `cv2.VideoWriter`.

### 3.4 `db.py` (Lớp trừu tượng hóa Cơ sở dữ liệu)
- **Nhiệm vụ chính**: Quản lý lưu trữ trạng thái lâu dài của hệ thống.
- **Khả năng tương thích**:
  - Tự động phát hiện biến môi trường `DATABASE_URL`. Nếu có, khởi tạo connection pool `psycopg2` để ghi nhận dữ liệu vào **PostgreSQL** (GCP Cloud SQL).
  - Nếu không có, tự động fallback sang sử dụng cơ sở dữ liệu **SQLite** cục bộ (`fisheye.db`) và dịch câu lệnh SQL (thay thế `%s` bằng `?`) hoàn toàn tự động.
- **Bảng dữ liệu**:
  - `detections`: Ghi lịch sử kết quả của các phiên detect.
  - `live_sessions`: Theo dõi các đợt kích hoạt live polling camera giao thông.
  - `traffic_counts`: Lưu số lượng xe đếm được gom nhóm theo khung giờ thực tế.
  - `alerts`, `incidents`, `vehicle_speeds`, `congestion_logs`: Lưu dữ liệu sự cố và vận tốc nâng cao.

### 3.5 `recent_image_store.py`
- **Nhiệm vụ chính**: Quản lý một database SQLite nhỏ chỉ chứa tối đa 100 ảnh kết quả gần đây nhất để hiển thị trực tiếp lên UI mà không làm ảnh hưởng đến tốc độ truy vấn của cơ sở dữ liệu chính.

---

## 4. Các điểm nghẽn & Đề xuất tái cấu trúc (Current Issues & Refactor Targets)

Để hỗ trợ đợt refactor quy mô lớn sắp tới, dưới đây là các phân tích lỗi và đề xuất cải tiến kỹ thuật mà **Claude** nên tập trung giải quyết:

### ⚠️ Issue 1: Tập tin `app.py` quá cồng kềnh (Monolithic Code)
- **Vấn đề**: `app.py` hiện tại chứa hơn 3300 dòng code, tích hợp cả app factory, định nghĩa cấu hình, kết nối DB, xử lý camera ngoài, hàng đợi job video, và toàn bộ router API. Việc này gây khó khăn rất lớn cho việc kiểm thử, mở rộng và bảo trì.
- **Đề xuất**:
  - **Tách cấu hình**: Chuyển định nghĩa cấu hình `AppSettings` và logic nạp biến môi trường sang tập tin `config.py` riêng biệt.
  - **Áp dụng Blueprint**: Tách các route API theo nhóm chức năng và đăng ký bằng Flask Blueprint:
    - `/routes/core.py`: Xử lý phục vụ giao diện trang chủ, static files và logging.
    - `/routes/detect.py`: Nhóm API xử lý upload ảnh, video, và convert mắt cá.
    - `/routes/external_camera.py`: Nhóm API điều khiển start/stop live polling và detect grid camera.
    - `/routes/history.py`: Nhóm API lấy thống kê đếm xe, lịch sử, detail chạy ngầm.
  - **Tách Service Layer**: Đưa logic xử lý nghiệp vụ ra ngoài Router:
    - `services/inference.py`: Chứa ModelRegistry và logic tương tác với model YOLO.
    - `services/storage.py`: Các helper tương tác lưu trữ file cục bộ và GCS.

### ⚠️ Issue 2: Tính năng Live Stream ngoài chưa phải live thực tế
- **Vấn đề**: Giao diện hiển thị tính năng "Live", tuy nhiên trong backend hiện tại (`external_camera_detector.py`), hệ thống chỉ thực hiện việc **tải ảnh snapshot dạng JPG tĩnh từ trang web nguồn theo chu kỳ** (polling mỗi 3-5 giây) rồi ghép lưới ảnh và phát hiện xe cộ.
- **Đề xuất**:
  - Làm rõ trong tài liệu và nhãn giao diện (UI labels) rằng đây là chế độ **Live Snapshot Polling** chứ chưa phải Video Live Stream thực tế.
  - Trong tương lai, để nâng cấp lên video stream thực, cần tích hợp thư viện `yt-dlp` hoặc một bộ đọc HLS stream để decode trực tiếp luồng video từ YouTube/camera nguồn bằng OpenCV và xuất ra luồng annotated dưới dạng giao thức **MJPEG** (qua `/api/external-camera/live/stream`) hoặc HLS.

### ⚠️ Issue 3: Xử lý video trực tiếp trong Flask Request hoặc Queue Thread in-memory thô sơ
- **Vấn đề**: Khi tải lên video, việc xử lý tốn rất nhiều thời gian (đặc biệt là khi chạy trên CPU). Việc xử lý trong luồng HTTP request sẽ gây ra lỗi Gateway Timeout (504). Hệ thống hiện dùng một `VideoJobQueue` bằng `threading.Thread` trong RAM, điều này sẽ làm mất toàn bộ tiến trình xử lý khi restart server Flask hoặc khi chạy chế độ multi-worker (Gunicorn).
- **Đề xuất**:
  - Đối với môi trường cục bộ (local/demo), giữ nguyên cơ chế `VideoJobQueue` thread-safe nhưng bổ sung API check trạng thái tiến độ xử lý chi tiết (ví dụ: đang xử lý bao nhiêu % kèm FPS).
  - Chuẩn bị sẵn sơ đồ cấu trúc tích hợp hàng đợi công việc chuẩn hóa (như **Celery / Redis** hoặc **RQ**) để phục vụ cho việc deploy môi trường sản xuất thực tế (Production Track).

---

## 5. Hướng dẫn chạy và Kiểm thử Hệ thống (Execution & Test Guide)

### 5.1 Cài đặt môi trường
Đảm bảo đã kích hoạt môi trường ảo (virtual environment) và cài đặt đầy đủ các thư viện phụ thuộc:
```powershell
pip install -r requirements.txt
```

### 5.2 Khởi chạy ứng dụng Web (Chế độ Local Demo)
Khởi chạy trực tiếp file `app.py` bằng Python:
```powershell
python -u app.py
```
Sau khi khởi động thành công, Flask sẽ lắng nghe trên cổng 5000:
- **Địa chỉ truy cập**: [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Tệp cơ sở dữ liệu mặc định**: `fisheye.db` (sẽ tự động được tạo ở thư mục gốc nếu chưa tồn tại).

### 5.3 Chạy ứng dụng phụ Streamlit (Tùy chọn)
Hệ thống có kèm một giao diện Streamlit cổ điển để test nhanh thuật toán nắn chỉnh mắt cá:
```powershell
streamlit run demo.py
```
- **Địa chỉ truy cập**: [http://127.0.0.1:8501](http://127.0.0.1:8501)

### 5.4 Chạy bộ kiểm thử (Unit Tests)
Hệ thống hỗ trợ kiểm thử tự động sử dụng `pytest` hoặc `unittest`:
```powershell
# Sử dụng unittest của Python
python -m unittest discover -s tests

# Hoặc sử dụng pytest
pytest tests -v
```

---

*Tài liệu này được tạo ra để phục vụ cho việc cấu trúc lại mã nguồn của dự án một cách khoa học, chuyên nghiệp, giữ nguyên mọi tính năng nghiệp vụ cũ đồng thời gia tăng hiệu năng và độ ổn định.*
