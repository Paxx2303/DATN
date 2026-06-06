# Dữ Liệu Streaming Trong Hệ Thống FishEye8K

## 📡 Tổng Quan

Hệ thống có tính năng **Live Streaming** để giám sát camera giao thông real-time với YOLO detection.

---

## 🎬 Các Loại Streaming

### 1. **MJPEG Streaming** (Motion JPEG)
Phát trực tiếp video đã được YOLO detect qua HTTP multipart stream.

**Endpoint:** `GET /api/external-camera/live/stream?view=overview`

**Content-Type:** `multipart/x-mixed-replace; boundary=frame`

**Cách hoạt động:**
- Server liên tục gửi từng frame JPEG riêng lẻ
- Browser tự động thay thế frame cũ bằng frame mới
- Tạo hiệu ứng video stream không cần WebSocket

**Views hỗ trợ:**
- `overview` - Tổng quan (collage 2x2 cameras)
- `camera_0` - Camera đầu tiên
- `camera_1` - Camera thứ 2
- `camera_2` - Camera thứ 3
- `camera_3` - Camera thứ 4

### 2. **Snapshot Mode**
Lấy ảnh tĩnh từ các camera ngoài.

**Endpoints:**
- `GET /api/external-camera/snapshot/overview` - Collage tổng quan
- `GET /api/external-camera/snapshot/0` - Camera 0
- `GET /api/external-camera/snapshot/1` - Camera 1
- `GET /api/external-camera/snapshot/2` - Camera 2
- `GET /api/external-camera/snapshot/3` - Camera 3

**Content-Type:** `image/jpeg`

---

## 🔧 API Endpoints

### Start Live Monitoring

```http
POST /api/external-camera/start
Content-Type: application/json

{
  "source_mode": "snapshot",
  "source_url": "https://webcam.vn",
  "camera_limit": 4,
  "interval": 2.0,
  "device": "cpu",
  "fisheye": true,
  "fisheye_strength": 0.7,
  "fisheye_radius": 0.85,
  "fisheye_effect": "standard",
  "conf": 0.25,
  "iou": 0.45,
  "model_key": "best"
}
```

**Response:**
```json
{
  "message": "Monitor started",
  "status": {
    "running": true,
    "status": "active",
    "active_cameras": 4,
    "total_vehicles": 0,
    "cycle_count": 0,
    "stream_ready": false
  }
}
```

### Stop Live Monitoring

```http
POST /api/external-camera/stop
```

**Response:**
```json
{
  "status": "stopped",
  "running": false,
  "message": "Monitor stopped"
}
```

### Get Monitor Status

```http
GET /api/external-camera/status
```

**Response:**
```json
{
  "running": true,
  "status": "active",
  "camera_counts": {
    "Camera 1": 12,
    "Camera 2": 8,
    "Camera 3": 15,
    "Camera 4": 6
  },
  "total_vehicles": 41,
  "active_cameras": 4,
  "cycle_count": 125,
  "last_updated_at": "2026-06-05T14:30:25.123456",
  "last_cycle_duration_ms": 1250.5,
  "actual_cycle_fps": 0.8,
  "interval_seconds": 2.0,
  "stream_ready": true,
  "speed_summary": {
    "avg_kmh": 42.3,
    "max_kmh": 68.5
  },
  "congestion_summary": {
    "level": "moderate",
    "avg_score": 0.45
  },
  "last_result": {
    "camera_count": 4,
    "cameras": [...],
    "total_vehicles": 41,
    "overview": "/api/external-camera/snapshot/overview"
  },
  "error": null,
  "config": {
    "source_mode": "snapshot",
    "source_url": "https://webcam.vn",
    "camera_limit": 4,
    "device": "cpu"
  }
}
```

### Single-shot Detection

```http
POST /api/external-camera/detect
Content-Type: multipart/form-data

external_camera_url=https://webcam.vn
camera_limit=4
conf=0.25
iou=0.45
apply_fisheye=true
fisheye_strength=0.7
fisheye_radius=0.85
```

**Response:**
```json
{
  "request_id": "20260605143025-abc123",
  "camera_count": 4,
  "overview": "data:image/jpeg;base64,...",
  "cameras": [
    {
      "title": "Camera 1",
      "total_objects": 12,
      "annotated": "data:image/jpeg;base64,...",
      "youtube_id": ""
    },
    ...
  ],
  "summary": {
    "total_objects": 41,
    "class_counts": {
      "Car": 28,
      "Motorcycle": 10,
      "Truck": 2,
      "Bus": 1
    },
    "inference_ms": 1250,
    "camera_count": 4
  }
}
```

---

## 📊 Dữ Liệu Streaming Chứa Gì?

### Frame Data (MJPEG Stream)
Mỗi frame trong stream chứa:

1. **Ảnh đã annotated:**
   - Bounding boxes cho từng phương tiện
   - Track ID (số định danh xe)
   - Class label (Car, Truck, Bus, etc.)
   - Confidence score

2. **Metadata embedded trong label:**
   - Tên camera
   - Số lượng xe (`12v`)
   - Mức độ ùn tắc (`L`, `M`, `H`)
   - Tốc độ trung bình (`45k` = 45km/h)

**Format label:** `Camera1|12v|M|45k`

### Status Data (JSON)
API `/status` trả về:

1. **Thống kê tổng quan:**
   - `total_vehicles` - Tổng số xe hiện tại
   - `active_cameras` - Số camera đang hoạt động
   - `cycle_count` - Số lần xử lý đã chạy

2. **Hiệu năng:**
   - `last_cycle_duration_ms` - Thời gian xử lý 1 cycle (ms)
   - `actual_cycle_fps` - FPS thực tế
   - `interval_seconds` - Khoảng thời gian giữa các cycle

3. **Analytics:**
   - **Speed summary:**
     - `avg_kmh` - Tốc độ trung bình
     - `max_kmh` - Tốc độ cao nhất
   - **Congestion summary:**
     - `level` - Mức độ ùn tắc (low/moderate/high)
     - `avg_score` - Điểm ùn tắc trung bình (0-1)

4. **Per-camera data:**
   ```json
   "cameras": [
     {
       "name": "Camera 1",
       "index": 0,
       "count": 12,
       "avg_speed_kmh": 42.5,
       "congestion": {
         "level": "moderate",
         "score": 0.45,
         "percentage": 45.2
       },
       "annotated": "/api/external-camera/snapshot/0",
       "total_objects": 12
     }
   ]
   ```

5. **Detection details:**
   - Class counts (Car, Motorcycle, Truck, Bus, etc.)
   - Bounding boxes coordinates
   - Confidence scores
   - Track IDs

---

## 🔄 Live Monitoring Workflow

```
1. Client gửi POST /api/external-camera/start
   ↓
2. Background thread bắt đầu loop:
   ├─ Fetch snapshots từ cameras (every 2s)
   ├─ Apply fisheye preprocessing (nếu enabled)
   ├─ Run YOLO inference (parallel nếu GPU)
   ├─ Centroid tracking (gán track ID)
   ├─ Speed estimation (tính km/h)
   ├─ Congestion detection (tính % density)
   ├─ Alert checking (cảnh báo nếu cần)
   ├─ Build collage overview
   └─ Update frame buffer
   ↓
3. Client request MJPEG stream:
   GET /api/external-camera/live/stream?view=overview
   ↓
4. Server streaming frames liên tục (10 FPS)
   ↓
5. Client có thể poll status:
   GET /api/external-camera/status (mỗi 1-2s)
   ↓
6. Client gửi POST /api/external-camera/stop khi muốn dừng
```

---

## 💾 Database Storage

### Table: `live_sessions`

```sql
CREATE TABLE live_sessions (
    id              TEXT PRIMARY KEY,
    source_url      TEXT,
    source_mode     TEXT,  -- 'snapshot' | 'stream'
    started_at      TIMESTAMP,
    ended_at        TIMESTAMP,
    cycle_count     INTEGER,
    total_objects   INTEGER,
    class_counts    JSON,   -- {"Car": 100, "Motorcycle": 50, ...}
    status          TEXT    -- 'active' | 'ended'
);
```

**Functions:**
- `insert_live_session()` - Lưu session khi start
- `update_live_session()` - Update counters mỗi cycle
- `close_live_session()` - Đánh dấu ended khi stop
- `list_live_sessions()` - Lấy lịch sử sessions

---

## 🎯 2 Compute Modes

### CPU Mode (Default)
- **Cameras:** 1 camera (để tiết kiệm tài nguyên)
- **Processing:** Sequential (tuần tự từng frame)
- **FPS:** ~0.5-1 FPS (tùy cấu hình)
- **Use case:** Development, testing, VPS nhỏ

### GPU Mode
- **Cameras:** 4 cameras (parallel)
- **Processing:** ThreadPoolExecutor (song song)
- **FPS:** ~2-5 FPS (tùy GPU)
- **Use case:** Production, high traffic monitoring

**Cấu hình:**
```python
# CPU Mode
camera_monitor.start(compute_mode="cpu", camera_limit=1)

# GPU Mode
camera_monitor.start(compute_mode="cuda", camera_limit=4)
```

---

## 🔍 Analytics Tích Hợp

### 1. Centroid Tracking
- Gán track ID cho mỗi xe
- Theo vết qua các frames
- Max distance: 80 pixels

### 2. Speed Estimation
- Tính toán dựa trên pixel displacement
- Scale factor: `SPEED_SCALE_FACTOR` (config)
- Output: km/h

### 3. Congestion Detection
- Tính % diện tích bị chiếm bởi xe
- 3 levels: LOW (<30%), MODERATE (30-60%), HIGH (>60%)
- Trigger alerts nếu HIGH

### 4. Heatmap
- Ghi nhận vị trí xuất hiện xe
- Tích lũy qua nhiều frames
- Visualize hotspots

### 5. Density Analysis
- Theo dõi số lượng xe theo thời gian
- Tính moving average
- Phát hiện xu hướng

### 6. Alert Manager
- Tự động cảnh báo khi:
  - Số xe vượt ngưỡng
  - Ùn tắc mức HIGH
  - Tốc độ trung bình quá thấp (dự kiến)

---

## 🌐 Source Modes

### 1. Snapshot Mode (webcam.vn)
- Fetch ảnh tĩnh từ các trang camera
- Parse HTML để tìm `<img>` tags
- Regex pattern matching cho URL camera
- Parallel fetch với ThreadPoolExecutor

**Keywords phát hiện:**
- `snap`, `snapshot`, `cam`, `camera`
- `live`, `view`, `stream`, `cctv`
- `traffic`, `webcam`

### 2. Stream Mode (RTSP/HLS/MJPEG)
- Connect trực tiếp vào video stream
- Sử dụng OpenCV VideoCapture
- Capture frame-by-frame

**Hỗ trợ:**
- RTSP: `rtsp://...`
- HLS: `.m3u8`
- MJPEG: `.mjpeg`
- MP4: `.mp4`

### 3. YouTube Mode
- Parse YouTube video ID
- Generate embed URL
- Frontend hiển thị iframe

---

## 📝 Configuration

Trong `.env`:

```env
# External Camera defaults
EXT_CAM_SOURCE_URL=https://webcam.vn
EXT_CAM_INTERVAL=2.0           # Seconds between cycles
EXT_CAM_LIMIT=1                # Default camera limit
EXT_CAM_LIMIT_CPU=1            # CPU mode limit
EXT_CAM_LIMIT_GPU=4            # GPU mode limit

# Speed estimation
SPEED_SCALE_FACTOR=0.1         # Pixel-to-meter scale

# Congestion thresholds
CONGESTION_LOW_THRESHOLD=0.3   # 30%
CONGESTION_HIGH_THRESHOLD=0.6  # 60%
```

---

## 🧪 Test Streaming

### Với curl (MJPEG)

```bash
# Stream overview (collage)
curl http://localhost:5000/api/external-camera/live/stream?view=overview > stream.mjpeg

# Stream camera 0
curl http://localhost:5000/api/external-camera/live/stream?view=camera_0 > cam0.mjpeg
```

### Với Browser

```html
<!-- MJPEG trong HTML -->
<img src="http://localhost:5000/api/external-camera/live/stream?view=overview" 
     alt="Live Stream" />
```

### Với Python

```python
import requests
import cv2
import numpy as np

url = "http://localhost:5000/api/external-camera/live/stream?view=overview"
stream = requests.get(url, stream=True)

bytes_data = b''
for chunk in stream.iter_content(chunk_size=1024):
    bytes_data += chunk
    
    # Tìm boundary frame
    a = bytes_data.find(b'\xff\xd8')  # JPEG start
    b = bytes_data.find(b'\xff\xd9')  # JPEG end
    
    if a != -1 and b != -1:
        jpg = bytes_data[a:b+2]
        bytes_data = bytes_data[b+2:]
        
        # Decode và hiển thị
        img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        cv2.imshow('Live Stream', img)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
```

---

## 🚨 Limitations & Known Issues

1. **Cold Start:** First cycle có thể mất 10-20s để load model
2. **Memory:** GPU mode cần ít nhất 4GB VRAM
3. **Network:** Snapshot mode phụ thuộc tốc độ mạng đến camera nguồn
4. **Accuracy:** Speed estimation cần calibration tốt
5. **Scale:** Cloud Run có timeout 60 phút (không phù hợp long-running stream)

---

## 💡 Best Practices

1. **CPU Mode cho demo:** Đơn giản, ổn định
2. **GPU Mode cho production:** Nhanh hơn, nhiều camera
3. **Interval 2-5s:** Cân bằng real-time vs tài nguyên
4. **Monitor status:** Poll `/status` mỗi 2-3s để update UI
5. **Graceful shutdown:** Luôn gọi `/stop` trước khi đóng app
6. **Error handling:** Check `error` field trong status response

---

**Cập nhật:** 2026-06-05  
**File liên quan:**
- `services/camera_monitor.py` - Core monitoring logic
- `routes/external_camera.py` - API endpoints
- `external_camera_detector.py` - Camera snapshot fetcher
