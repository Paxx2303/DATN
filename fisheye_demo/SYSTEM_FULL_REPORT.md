# Fisheye Demo System - Báo Cáo Hệ Thống Chi Tiết

## 1. Tổng Quan Hệ Thống

### 1.1 Mục Tiêu
Hệ thống `fisheye_demo` là một ứng dụng web phân tích giao thông thông minh, tập trung vào 3 chức năng chính:
- **Object Detection**: Phát hiện đối tượng trên ảnh fisheye
- **Image/Video Conversion**: Chuyển đổi ảnh/video thường sang định dạng fisheye
- **Real-time Analytics**: Phân tích giao thông theo thời gian thực với các tính năng nâng cao

### 1.2 Kiến Trúc Tổng Thể
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Flask API     │    │   Database      │
│   (HTML/JS)     │◄──►│   Backend       │◄──►│   PostgreSQL    │
│                 │    │                 │    │   /SQLite       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   AI/ML Layer   │
                    │   (YOLOv11)     │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Cloud Storage  │
                    │     (GCS)       │
                    └─────────────────┘
```

## 2. Cấu Trúc Hệ Thống

### 2.1 Thành Phần Chính

#### 2.1.1 Core Components
- **Flask Backend** (`app.py`): API server chính
- **Fisheye Engine** (`fisheye.py`): Xử lý biến dạng ảnh
- **Database Layer** (`db.py`): Quản lý dữ liệu PostgreSQL/SQLite
- **Model Registry** (`app.py`): Quản lý model YOLO

#### 2.1.2 Advanced Analytics
- **Traffic Analytics** (`analytics.py`): Phân tích giao thông
- **Speed Estimator** (`speed_estimator.py`): Ước tính tốc độ xe
- **Congestion Detector** (`congestion_detector.py`): Phát hiện ùn tắc
- **Alert Manager** (`alert_manager.py`): Hệ thống cảnh báo

#### 2.1.3 Infrastructure
- **Cloud Storage** (`cloud_storage.py`): Tích hợp Google Cloud Storage
- **External Camera** (`external_camera_detector.py`): Xử lý camera ngoài
- **Recent Image Store** (`recent_image_store.py`): Lưu trữ ảnh gần đây

### 2.2 Cấu Trúc Thư Mục
```
fisheye_demo/
├── app.py                      # Flask application chính
├── db.py                       # Database layer
├── fisheye.py                  # Fisheye transformation engine
├── analytics.py                # Traffic analytics
├── speed_estimator.py          # Speed estimation
├── congestion_detector.py      # Congestion detection
├── alert_manager.py            # Alert system
├── cloud_storage.py            # GCS integration
├── external_camera_detector.py # External camera handling
├── recent_image_store.py       # Recent images storage
├── routes_extended.py          # Extended API routes
├── deploy/                     # Deployment configurations
│   ├── Dockerfile
│   ├── docker-compose.prod.yml
│   └── deploy_gcp.sh
├── static/
│   ├── uploads/               # Temporary uploads
│   └── results/               # Processing results
└── templates/
    └── index.html             # Frontend interface
```

## 3. Chức Năng Hệ Thống

### 3.1 Core Features

#### 3.1.1 Object Detection
**Mô tả**: Phát hiện đối tượng giao thông trên ảnh/video fisheye
**Classes hỗ trợ**: Car, Bus, Truck, Pedestrian, Motorbike
**Model**: YOLOv11 (custom trained trên fisheye data)

**Workflow**:
1. Upload ảnh/video
2. Preprocessing (fisheye correction nếu cần)
3. YOLO inference
4. Post-processing và annotation
5. Lưu kết quả và metadata

#### 3.1.2 Fisheye Conversion
**Mô tả**: Chuyển đổi ảnh/video thường sang định dạng fisheye
**Effects hỗ trợ**: 
- `standard`: Mắt cá tiêu chuẩn
- `extreme`: Biến dạng cực độ  
- `subtle`: Vết lồi nhỏ
- `traffic_camera`: Preset cho camera giao thông

**Thuật toán**: Inverse mapping với bilinear interpolation

#### 3.1.3 Real-time Analytics
**Các tính năng**:
- Traffic density analysis
- Speed estimation
- Congestion detection
- Line crossing counter
- Heatmap generation

### 3.2 Advanced Features

#### 3.2.1 Speed Estimation (`speed_estimator.py`)

**Mục đích**: Ước tính tốc độ xe qua 2 frame liên tiếp

**Nguyên lý hoạt động**:
- **Object Tracking**: Track đối tượng qua IoU matching giữa các frame
- **Displacement Calculation**: Đo khoảng cách di chuyển của centroid (pixel)
- **Speed Conversion**: Chuyển đổi pixel/frame → m/s → km/h
- **Fisheye Correction**: Hiệu chỉnh cho vùng rìa ảnh bị co lại
- **Speed Smoothing**: Weighted moving average để giảm noise

**Cấu hình chính**:
```python
# Khởi tạo Speed Estimator
estimator = SpeedEstimator(
    fps=25.0,                    # Frame rate video
    pixels_per_meter=8.0,        # Hệ số calibration (px/m)
    fisheye_correction=True,     # Bật hiệu chỉnh fisheye
    speed_limit_kmh=60.0         # Ngưỡng tốc độ cho cảnh báo
)
```

**Tính năng nâng cao**:
- **Multi-object tracking**: Theo dõi nhiều xe cùng lúc
- **Speed history**: Lưu lịch sử tốc độ 10 frame gần nhất
- **Overspeed detection**: Phát hiện vi phạm tốc độ
- **Speed categorization**: Phân loại tốc độ (Chậm/Bình thường/Nhanh/Quá tốc)
- **Thread-safe**: Hỗ trợ xử lý đa luồng

**Màu cảnh báo tốc độ**:
- **Xanh** (#4FC3F7): < 40 km/h (Bình thường)
- **Cam** (#FFB74D): 40-70 km/h (Nhanh)  
- **Đỏ** (#EF5350): > 70 km/h (Quá tốc)

**Calibration**:
- `pixels_per_meter` phụ thuộc độ cao camera và góc nhìn
- Camera 5m, góc 45° → ~8-12 px/m ở vùng trung tâm
- Có thể calibrate bằng cách đo khoảng cách thực tế

**API Endpoints**:
```bash
GET  /api/speed/stats      # Thống kê tốc độ tổng hợp
GET  /api/speed/current    # Tốc độ hiện tại của các xe
POST /api/speed/config     # Cập nhật cấu hình
POST /api/speed/reset      # Reset thống kê
POST /api/speed/detect-image  # Ước tính tốc độ từ 2 ảnh
```

#### 3.2.2 Congestion Detection (`congestion_detector.py`)

**Mục đích**: Phát hiện ùn tắc giao thông theo vùng ROI (Region of Interest)

**Level of Service (LoS)**:
- **FREE** (< 20% capacity): Thông thoáng - Xanh lá (#4CAF50)
- **SLOW** (20-50%): Chậm - Vàng (#FFD166)
- **CONGESTED** (50-80%): Ùn tắc - Cam (#FF9800)
- **JAMMED** (> 80%): Kẹt xe nặng - Đỏ (#F44336)

**Nguyên lý hoạt động**:
- **ROI Definition**: Chia ảnh thành các vùng quan sát
- **Vehicle Counting**: Đếm số xe trong mỗi ROI
- **Density Calculation**: Tính mật độ = số xe / capacity ROI
- **Trend Analysis**: Phân tích xu hướng tăng/giảm/ổn định
- **Duration Tracking**: Theo dõi thời gian ùn tắc

**Trọng số xe theo loại**:
```python
VEHICLE_WEIGHTS = {
    "Car":        1.0,    # Xe con
    "Motorbike":  0.5,    # Xe máy (nhỏ hơn)
    "Bus":        2.5,    # Xe buýt (lớn)
    "Truck":      2.0,    # Xe tải
    "Pedestrian": 0.3,    # Người đi bộ
}
```

**ROI Management**:
```python
# Thêm vùng ROI tùy chỉnh
detector.add_roi(
    name="intersection",     # Tên vùng
    x1=0.1, y1=0.1,         # Góc trên trái (normalized 0-1)
    x2=0.9, y2=0.9,         # Góc dưới phải
    capacity=15             # Sức chứa tối đa
)
```

**ROI mặc định**:
- **full_frame**: Toàn bộ ảnh (0.0, 0.0, 1.0, 1.0) - capacity 20
- **intersection**: Vùng trung tâm (0.25, 0.25, 0.75, 0.75) - capacity 10

**Tính năng nâng cao**:
- **Multi-ROI support**: Hỗ trợ nhiều vùng quan sát
- **Historical tracking**: Lưu lịch sử 60 frame
- **Congestion duration**: Tính thời gian ùn tắc liên tục
- **Alert callbacks**: Gọi callback khi có ùn tắc
- **Trend detection**: Phát hiện xu hướng tăng/giảm mật độ

**API Endpoints**:
```bash
GET    /api/congestion/status           # Trạng thái ùn tắc hiện tại
GET    /api/congestion/rois             # Danh sách ROI
POST   /api/congestion/rois             # Thêm ROI mới
DELETE /api/congestion/rois/<name>      # Xóa ROI
GET    /api/congestion/history/<name>   # Lịch sử ROI
POST   /api/congestion/reset            # Reset thống kê
POST   /api/congestion/detect-image     # Phân tích ùn tắc từ ảnh
```

**Visualization**:
- Vẽ viền màu quanh ROI theo mức độ ùn tắc
- Overlay màu mờ khi ùn tắc nặng
- Hiển thị % occupancy và số xe
- Badge tổng thể ở góc ảnh

#### 3.2.3 Alert System
**Loại cảnh báo**:
- High density: Mật độ cao
- Class threshold: Vượt ngưỡng theo loại xe
- Speed violation: Vi phạm tốc độ
- Congestion: Ùn tắc giao thông

**Rate limiting**: Cooldown 60s giữa các alert cùng loại

## 4. API Endpoints

### 4.1 Core APIs

#### 4.1.1 Detection APIs
```
POST /api/detect          # Object detection
POST /api/convert         # Fisheye conversion
GET  /api/health          # System health
GET  /api/config          # System configuration
GET  /api/history         # Processing history
GET  /api/stats           # System statistics
```

#### 4.1.2 Extended APIs
```
# Analytics
GET  /api/analytics                 # Dashboard analytics
GET  /api/analytics/hourly          # Hourly traffic chart
GET  /api/analytics/class-dist      # Class distribution
GET  /api/analytics/peak-hours      # Peak hours detection
GET  /api/analytics/heatmap         # Detection heatmap

# Alerts
GET  /api/alerts                    # List alerts
POST /api/alerts/<id>/acknowledge   # Acknowledge alert
GET  /api/alerts/thresholds         # Get thresholds
POST /api/alerts/thresholds         # Update thresholds

# Speed Estimation
GET  /api/speed/stats               # Speed statistics
GET  /api/speed/current             # Current speeds
POST /api/speed/config              # Update config
POST /api/speed/detect-image        # Speed on 2 frames

# Congestion Detection
GET  /api/congestion/status         # Congestion status
GET  /api/congestion/rois           # List ROIs
POST /api/congestion/rois           # Add ROI
DELETE /api/congestion/rois/<name>  # Delete ROI

# Cloud Storage
GET  /api/cloud/gallery             # Cloud image gallery
GET  /api/cloud/stats               # GCS statistics
POST /api/cloud/cleanup             # Manual cleanup

# Export
GET  /api/export/csv                # Export CSV
GET  /api/export/json               # Export JSON
```

### 4.2 Request/Response Format

#### 4.2.1 Detection Request
```json
{
  "file": "<image/video file>",
  "conf": 0.25,
  "iou": 0.45,
  "source_layout": "fisheye|normal",
  "apply_fisheye": true,
  "fisheye_strength": 0.7,
  "fisheye_radius": 0.85,
  "fisheye_effect": "standard"
}
```

#### 4.2.2 Detection Response
```json
{
  "id": "20260521123456-abc123",
  "task": "detect",
  "media_type": "image",
  "summary": {
    "total_objects": 15,
    "class_counts": {
      "Car": 8,
      "Motorbike": 5,
      "Pedestrian": 2
    },
    "inference_ms": 245.6
  },
  "artifacts": {
    "original": "original.jpg",
    "annotated": "annotated.jpg"
  },
  "artifact_urls": {
    "original": "/api/artifacts/20260521123456-abc123/original.jpg",
    "annotated": "/api/artifacts/20260521123456-abc123/annotated.jpg"
  }
}
```

## 5. Database Schema

### 5.1 Dual Backend Support
- **Production**: PostgreSQL (GCP Cloud SQL)
- **Development**: SQLite fallback

### 5.2 Tables

#### 5.2.1 detections
```sql
CREATE TABLE detections (
    id              TEXT PRIMARY KEY,
    task            TEXT NOT NULL,
    media_type      TEXT NOT NULL,
    filename        TEXT,
    source_layout   TEXT,
    created_at      TIMESTAMPTZ NOT NULL,
    conf_threshold  REAL,
    iou_threshold   REAL,
    total_objects   INTEGER DEFAULT 0,
    inference_ms    REAL,
    class_counts    JSONB,
    model_name      TEXT,
    device          TEXT,
    preprocessing   JSONB,
    artifacts       JSONB,
    gcs_urls        JSONB
);
```

#### 5.2.2 traffic_counts
```sql
CREATE TABLE traffic_counts (
    id              BIGSERIAL PRIMARY KEY,
    hour_bucket     TIMESTAMPTZ NOT NULL,
    camera_source   TEXT NOT NULL DEFAULT 'upload',
    class_name      TEXT NOT NULL,
    count           INTEGER NOT NULL DEFAULT 0,
    UNIQUE(hour_bucket, camera_source, class_name)
);
```

#### 5.2.3 alerts
```sql
CREATE TABLE alerts (
    id              BIGSERIAL PRIMARY KEY,
    alert_type      TEXT NOT NULL,
    camera_source   TEXT,
    class_name      TEXT,
    threshold       INTEGER,
    actual_count    INTEGER,
    message         TEXT,
    created_at      TIMESTAMPTZ NOT NULL,
    acknowledged    BOOLEAN DEFAULT FALSE
);
```

#### 5.2.4 cloud_snapshots
```sql
CREATE TABLE cloud_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    detection_id    TEXT REFERENCES detections(id),
    gcs_bucket      TEXT NOT NULL,
    gcs_object_name TEXT NOT NULL UNIQUE,
    gcs_public_url  TEXT,
    image_role      TEXT,
    created_at      TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ,
    deleted         BOOLEAN DEFAULT FALSE
);
```

#### 5.2.5 live_sessions
```sql
CREATE TABLE live_sessions (
    id              TEXT PRIMARY KEY,
    source_url      TEXT,
    source_mode     TEXT,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    cycle_count     INTEGER DEFAULT 0,
    total_objects   INTEGER DEFAULT 0,
    class_counts    JSONB,
    conf_threshold  REAL,
    iou_threshold   REAL,
    status          TEXT DEFAULT 'active'
);
```

## 6. Configuration Management

### 6.1 Environment Variables

#### 6.1.1 Core Settings
```bash
# Model & Inference
FISHEYE_DEFAULT_CONF=0.25
FISHEYE_DEFAULT_IOU=0.45
FISHEYE_DEVICE=0
FISHEYE_PRELOAD_MODEL=1
FISHEYE_MODEL_PATH=/path/to/model.pt

# Storage
FISHEYE_UPLOAD_DIR=/app/static/uploads
FISHEYE_RESULTS_DIR=/app/static/results
FISHEYE_RECENT_IMAGE_DB=/app/data/recent_images.sqlite3

# Fisheye Effects
FISHEYE_DEFAULT_STRENGTH=0.7
FISHEYE_DEFAULT_RADIUS=0.85
FISHEYE_DEFAULT_EFFECT=standard
```

#### 6.1.2 Database Configuration
```bash
# PostgreSQL (Production)
DATABASE_URL=postgresql://user:pass@host:5432/db
CLOUD_SQL_INSTANCE_CONNECTION_NAME=project:region:instance

# SQLite (Development)
FISHEYE_SQLITE_DB=fisheye_demo/fisheye.db
```

#### 6.1.3 Cloud Storage
```bash
# Google Cloud Storage
FISHEYE_CLOUD_STORAGE=1
GCS_BUCKET_NAME=fisheye-snapshots
GCS_PROJECT_ID=my-project
GCS_CREDENTIALS_JSON='{"type":"service_account",...}'
FISHEYE_SNAPSHOT_TTL_HOURS=6
```

#### 6.1.4 Alert Thresholds
```bash
ALERT_THRESHOLD_TOTAL=15
ALERT_THRESHOLD_CAR=10
ALERT_THRESHOLD_BUS=3
ALERT_THRESHOLD_TRUCK=3
ALERT_THRESHOLD_PEDESTRIAN=8
ALERT_THRESHOLD_MOTORBIKE=12
ALERT_COOLDOWN_SECONDS=60
```

### 6.2 Configuration Priority
1. Runtime overrides (AppSettings)
2. Environment variables
3. `.env` file
4. Default values in code

## 7. Deployment Architecture

### 7.1 Docker Deployment

#### 7.1.1 Production Stack
```yaml
# docker-compose.prod.yml
services:
  fisheye-web:
    image: fisheye-demo:prod
    gpus: all
    ports:
      - "5000:5000"
    environment:
      - FISHEYE_DEVICE=0
      - DATABASE_URL=${DATABASE_URL}
      - GCS_BUCKET_NAME=${GCS_BUCKET_NAME}
    volumes:
      - fisheye-results:/app/static/results
      - fisheye-data:/app/data
```

#### 7.1.2 GPU Support
- Base image: `pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime`
- NVIDIA Container Toolkit required
- GPU device mapping: `gpus: all`

### 7.2 Google Cloud Platform Deployment

#### 7.2.1 GCE VM Configuration
```bash
# Machine specs
MACHINE_TYPE="g2-standard-4"        # 4 vCPUs, 16GB RAM
ACCELERATOR="type=nvidia-l4,count=1" # NVIDIA L4 GPU
ZONE="asia-southeast1-b"             # Singapore
```

#### 7.2.2 Services Integration
- **Compute Engine**: VM hosting
- **Cloud SQL**: PostgreSQL database
- **Cloud Storage**: Image storage
- **Cloud SQL Proxy**: Secure DB connection

#### 7.2.3 Deployment Script
```bash
./deploy/deploy_gcp.sh
```
**Chức năng**:
1. Tạo GCE VM với GPU
2. Cài đặt Docker + NVIDIA drivers
3. Upload code và model weights
4. Khởi động production stack

### 7.3 Network & Security

#### 7.3.1 Firewall Rules
```bash
# Allow web traffic
gcloud compute firewall-rules create allow-fisheye \
    --allow tcp:5000 \
    --target-tags=fisheye-port
```

#### 7.3.2 Health Checks
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## 8. Workflow Processes

### 8.1 Image Detection Workflow
```mermaid
graph TD
    A[Upload Image] --> B[Validate Format]
    B --> C[Read Image]
    C --> D{Source Layout?}
    D -->|fisheye| E[Skip Preprocessing]
    D -->|normal| F[Apply Fisheye Transform]
    E --> G[Load YOLO Model]
    F --> G
    G --> H[Run Inference]
    H --> I[Post-process Results]
    I --> J[Generate Annotations]
    J --> K[Save Artifacts]
    K --> L[Update Database]
    L --> M[Return Results]
```

### 8.2 Video Detection Workflow
```mermaid
graph TD
    A[Upload Video] --> B[Validate & Check Duration]
    B --> C[Extract Frames]
    C --> D[Process Each Frame]
    D --> E{Apply Fisheye?}
    E -->|Yes| F[Transform Frame]
    E -->|No| G[Use Original]
    F --> H[YOLO Inference]
    G --> H
    H --> I[Draw Annotations]
    I --> J[Compile Video]
    J --> K[Generate Preview]
    K --> L[Save Results]
    L --> M[Cleanup Temp Files]
```

### 8.3 Analytics Workflow
```mermaid
graph TD
    A[Detection Results] --> B[Update Traffic Counts]
    B --> C[Speed Estimation]
    C --> D[Congestion Analysis]
    D --> E[Alert Checking]
    E --> F{Alert Triggered?}
    F -->|Yes| G[Send Notifications]
    F -->|No| H[Update Heatmap]
    G --> H
    H --> I[Store Analytics Data]
    I --> J[Update Dashboard]
```

### 8.4 Speed Estimation Workflow
```mermaid
graph TD
    A[Frame N-1] --> B[Extract Detections]
    C[Frame N] --> D[Extract Detections]
    B --> E[Initialize/Update Tracks]
    D --> E
    E --> F[IoU Matching]
    F --> G[Calculate Displacement]
    G --> H[Apply Fisheye Correction]
    H --> I[Convert to km/h]
    I --> J[Smooth Speed History]
    J --> K[Check Speed Violations]
    K --> L[Update Statistics]
    L --> M[Annotate Frame]
```

### 8.5 Congestion Detection Workflow
```mermaid
graph TD
    A[Frame Detections] --> B[Normalize Coordinates]
    B --> C[For Each ROI]
    C --> D[Count Vehicles in ROI]
    D --> E[Apply Vehicle Weights]
    E --> F[Calculate Occupancy %]
    F --> G[Determine LoS Level]
    G --> H[Update History]
    H --> I[Analyze Trend]
    I --> J[Track Duration]
    J --> K{Congestion Alert?}
    K -->|Yes| L[Trigger Callbacks]
    K -->|No| M[Update Visualization]
    L --> M
    M --> N[Return Status]
```

## 9. Performance & Scalability

### 9.1 Performance Metrics

#### 9.1.1 Inference Performance
- **Image Detection**: ~200-400ms (GPU)
- **Video Processing**: ~1-2 FPS (depends on resolution)
- **Fisheye Transform**: ~50-100ms per frame
- **Speed Estimation**: ~5-10ms per frame (tracking overhead)
- **Congestion Analysis**: ~2-5ms per frame (ROI processing)

#### 9.1.2 Throughput
- **Concurrent Requests**: 1-2 (limited by GPU memory)
- **Daily Capacity**: ~10,000 images or 100 videos
- **Storage Growth**: ~1GB per 1000 processed items

### 9.2 Optimization Strategies

#### 9.2.1 Model Optimization
- Model quantization for faster inference
- Batch processing for multiple images
- Model caching and warm-up

#### 9.2.2 Storage Optimization
- Automatic cleanup of old results
- Cloud storage with TTL (6 hours)
- Compressed artifact storage

#### 9.2.3 Database Optimization
- Indexed queries on timestamps
- Partitioning for large tables
- Connection pooling

### 9.3 Scalability Considerations

#### 9.3.1 Horizontal Scaling
- Load balancer for multiple instances
- Shared storage (GCS/NFS)
- Database clustering

#### 9.3.2 Vertical Scaling
- Multi-GPU support
- Larger VM instances
- Memory optimization

## 10. Monitoring & Maintenance

### 10.1 Health Monitoring

#### 10.1.1 System Health Endpoints
```bash
GET /api/health           # Overall system status
GET /api/db/health        # Database connectivity
GET /api/cloud/stats      # Cloud storage status
```

#### 10.1.2 Metrics Tracked
- Model loading status
- Database connection health
- GPU utilization
- Storage usage
- Processing queue length
- **Speed estimation accuracy**: Tracking success rate, speed distribution
- **Congestion detection**: ROI occupancy levels, alert frequency
- **Traffic analytics**: Hourly counts, peak detection accuracy

### 10.2 Logging & Debugging

#### 10.2.1 Log Levels
```python
# Logger configuration
logging.getLogger("fisheye_demo.live").setLevel(logging.INFO)
logging.getLogger("fisheye_demo.db").setLevel(logging.INFO)
logging.getLogger("fisheye_demo.analytics").setLevel(logging.INFO)
```

#### 10.2.2 Log Categories
- **Request logs**: API calls and responses
- **Processing logs**: Inference and transformation
- **Error logs**: Exceptions and failures
- **Performance logs**: Timing and metrics

### 10.3 Maintenance Tasks

#### 10.3.1 Automated Cleanup
- GCS expired snapshots (every 30 minutes)
- Old result artifacts (configurable retention)
- Database log rotation

#### 10.3.2 Manual Maintenance
- Model updates and redeployment
- Database schema migrations
- Performance tuning

## 11. Security Considerations

### 11.1 Input Validation
- File type validation (images/videos only)
- File size limits (configurable)
- Content sanitization

### 11.2 Data Protection
- Temporary file cleanup
- Secure file storage paths
- Database connection encryption

### 11.3 Access Control
- No authentication (demo system)
- Rate limiting considerations
- Network-level security (firewall)

## 12. Future Enhancements

### 12.1 Planned Features
- Real-time video streaming support
- Multi-camera synchronization
- Advanced tracking algorithms (DeepSORT, ByteTrack)
- Machine learning model updates
- **Speed estimation enhancements**:
  - Multi-lane speed detection
  - Vehicle trajectory prediction
  - Speed limit enforcement zones
- **Congestion detection improvements**:
  - Dynamic ROI adjustment
  - Traffic flow prediction
  - Incident detection integration

### 12.2 Architecture Improvements
- Microservices decomposition
- Message queue integration
- Caching layer (Redis)
- API versioning

### 12.3 Scalability Enhancements
- Kubernetes deployment
- Auto-scaling policies
- Multi-region deployment
- CDN integration

## 13. Testing & Validation

### 13.1 Speed Estimator Testing

#### 13.1.1 Unit Tests
```python
# Test tracking accuracy
def test_speed_estimation_accuracy():
    estimator = SpeedEstimator(fps=25.0, pixels_per_meter=10.0)
    
    # Simulate vehicle moving 50 pixels in 1 frame
    # Expected speed: (50/10) * 25 * 3.6 = 45 km/h
    det1 = {"class": "Car", "bbox": [100, 100, 150, 150]}
    det2 = {"class": "Car", "bbox": [150, 100, 200, 150]}
    
    estimator.update([det1], 800, 600)
    results = estimator.update([det2], 800, 600)
    
    assert abs(results[0]["speed_kmh"] - 45.0) < 5.0
```

#### 13.1.2 Integration Tests
```bash
# Test API endpoints
curl -X POST http://127.0.0.1:5000/api/speed/detect-image \
  -F "image1=@test_frame1.jpg" \
  -F "image2=@test_frame2.jpg" \
  -F "fps=25" \
  -F "pixels_per_meter=8.0"

# Expected response format validation
{
  "speeds": [
    {
      "track_id": "0",
      "class": "Car", 
      "speed_kmh": 42.3,
      "is_overspeed": false
    }
  ],
  "config": {
    "fps": 25.0,
    "pixels_per_meter": 8.0
  }
}
```

### 13.2 Congestion Detector Testing

#### 13.2.1 ROI Validation Tests
```python
def test_roi_vehicle_counting():
    detector = CongestionDetector()
    detector.add_roi("test_zone", 0.2, 0.2, 0.8, 0.8, capacity=10)
    
    # Vehicles inside ROI
    detections = [
        {"class": "Car", "bbox": [200, 200, 250, 250]},  # Inside
        {"class": "Car", "bbox": [100, 100, 150, 150]},  # Outside
    ]
    
    result = detector.update(detections, 800, 600)
    zone = next(z for z in result["zones"] if z["name"] == "test_zone")
    
    assert zone["current_count"] == 1
    assert zone["occupancy_pct"] == 10.0  # 1/10 * 100%
```

#### 13.2.2 LoS Classification Tests
```python
def test_los_classification():
    detector = CongestionDetector()
    detector.add_roi("test", 0.0, 0.0, 1.0, 1.0, capacity=10)
    
    # Test different congestion levels
    test_cases = [
        (1, "FREE"),      # 10% occupancy
        (3, "SLOW"),      # 30% occupancy  
        (7, "CONGESTED"), # 70% occupancy
        (9, "JAMMED"),    # 90% occupancy
    ]
    
    for count, expected_los in test_cases:
        detections = [{"class": "Car", "bbox": [i*50, 100, i*50+40, 140]} 
                     for i in range(count)]
        result = detector.update(detections, 800, 600)
        assert result["zones"][0]["los"] == expected_los
```

### 13.3 Performance Benchmarks

#### 13.3.1 Speed Estimation Benchmarks
```bash
# Benchmark tracking performance
python -m pytest fisheye_demo/tests/test_speed_estimator.py::test_performance -v

# Expected results:
# - Processing time: < 10ms per frame
# - Memory usage: < 50MB for 100 tracks
# - Tracking accuracy: > 85% IoU match rate
```

#### 13.3.2 Congestion Detection Benchmarks  
```bash
# Benchmark ROI processing
python -m pytest fisheye_demo/tests/test_congestion_detector.py::test_performance -v

# Expected results:
# - ROI processing: < 5ms per frame
# - Memory usage: < 20MB for 10 ROIs
# - Classification accuracy: > 90% LoS correctness
```

## 14. Troubleshooting Guide

### 14.1 Common Issues

#### 14.1.1 Model Loading Failures
```bash
# Check model file exists
ls -la *.pt

# Check GPU availability
nvidia-smi

# Check CUDA compatibility
python -c "import torch; print(torch.cuda.is_available())"
```

#### 14.1.2 Database Connection Issues
```bash
# Test PostgreSQL connection
psql $DATABASE_URL -c "SELECT 1;"

# Check SQLite file permissions
ls -la fisheye_demo/fisheye.db
```

#### 14.1.3 Storage Issues
```bash
# Check disk space
df -h

# Check GCS credentials
gcloud auth list
```

#### 14.1.4 Speed Estimation Issues
```bash
# Check tracking performance
curl http://127.0.0.1:5000/api/speed/stats

# Verify calibration settings
curl http://127.0.0.1:5000/api/speed/current

# Test with known speed reference
curl -X POST http://127.0.0.1:5000/api/speed/detect-image \
  -F "image1=@frame1.jpg" \
  -F "image2=@frame2.jpg" \
  -F "fps=25" \
  -F "pixels_per_meter=8.0"
```

#### 14.1.5 Congestion Detection Issues
```bash
# Check ROI configuration
curl http://127.0.0.1:5000/api/congestion/rois

# Monitor congestion status
curl http://127.0.0.1:5000/api/congestion/status

# Review ROI history
curl http://127.0.0.1:5000/api/congestion/history/intersection
```

### 14.2 Performance Issues

#### 14.2.1 Slow Inference
- Check GPU utilization: `nvidia-smi`
- Monitor memory usage: `free -h`
- Review model size and complexity

#### 14.2.2 Database Slowness
- Check connection pool settings
- Review query performance
- Monitor database metrics

## 15. Conclusion

Hệ thống Fisheye Demo là một giải pháp phân tích giao thông thông minh với kiến trúc modular và khả năng mở rộng cao. Với việc tích hợp AI/ML, cloud storage, real-time analytics, speed estimation, và congestion detection, hệ thống cung cấp một nền tảng mạnh mẽ và toàn diện cho việc phân tích và giám sát giao thông đô thị hiện đại.

### 15.1 Điểm Mạnh
- Kiến trúc linh hoạt và modular
- Hỗ trợ đa dạng định dạng media
- Tích hợp cloud services
- Real-time analytics và alerting
- Deployment automation
- **Advanced traffic analysis**:
  - Speed estimation với fisheye correction
  - Multi-ROI congestion detection
  - Real-time tracking và monitoring
  - Comprehensive API coverage

### 15.2 Khuyến Nghị
- Triển khai monitoring và alerting toàn diện
- Implement authentication và authorization
- Tối ưu hóa performance cho production
- Xây dựng CI/CD pipeline
- Backup và disaster recovery planning

---

**Tài liệu này được tạo vào**: May 21, 2026  
**Phiên bản hệ thống**: v1.0  
**Tác giả**: Fisheye Demo Development Teamase wait before tryin