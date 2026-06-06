# Hướng Dẫn Chạy Ứng Dụng Local

## ✅ Trạng Thái Hiện Tại
Ứng dụng đang chạy thành công tại: **http://localhost:5000**

## 📋 Yêu Cầu Hệ Thống
- Python 3.10+ (Đã cài: Python 3.10.9)
- Các thư viện đã cài đặt:
  - Flask 3.1.2
  - Ultralytics 8.4.47
  - OpenCV 4.13.0
  - Pillow 10.2.0

## 🚀 Cách Chạy Ứng Dụng

### Lần Đầu Tiên
```bash
# 1. Tạo file .env từ template
copy .env.local.example .env

# 2. Cài đặt dependencies (nếu chưa có)
pip install -r requirements.txt

# 3. Chạy ứng dụng
python app.py
```

### Các Lần Sau
```bash
# Chạy trực tiếp
python app.py
```

Ứng dụng sẽ chạy tại: **http://localhost:5000**

## 🔧 Cấu Hình Local (file .env)

```env
# Ngưỡng phát hiện mặc định
FISHEYE_DEFAULT_CONF=0.25
FISHEYE_DEFAULT_IOU=0.45

# Thiết bị xử lý (cpu hoặc cuda)
FISHEYE_DEVICE=cpu

# Không preload model (tải khi cần)
FISHEYE_PRELOAD_MODEL=0
FISHEYE_IMPORT_PRELOAD_MODEL=0

# Thư mục lưu trữ
FISHEYE_UPLOAD_DIR=static/uploads
FISHEYE_RESULTS_DIR=static/results

# Database cho recent images
FISHEYE_RECENT_IMAGE_DB=recent_images.sqlite3
FISHEYE_RECENT_IMAGE_LIMIT=100

# Giới hạn upload
FISHEYE_MAX_UPLOAD_MB=64
FISHEYE_MAX_VIDEO_SECONDS=60

# External camera
FISHEYE_EXTERNAL_CAMERA_LIVE_INTERVAL=1.0
```

## 🌐 Truy Cập Ứng Dụng

Sau khi chạy `python app.py`, mở trình duyệt và truy cập:
- **URL chính**: http://localhost:5000
- **API Health**: http://localhost:5000/api/health
- **Analytics**: http://localhost:5000/analytics

## 🛠️ Các Lệnh Hữu Ích

### Kiểm tra ứng dụng đang chạy
```bash
# Kiểm tra port 5000 đã mở chưa
netstat -ano | findstr :5000
```

### Dừng ứng dụng
Nhấn `Ctrl + C` trong terminal đang chạy ứng dụng

### Kiểm tra logs
Logs sẽ hiển thị trực tiếp trong terminal, bao gồm:
- Database initialization
- Route registration
- Request logs
- Error messages (nếu có)

## 📊 Tính Năng Có Sẵn

1. **Upload & Detect**
   - Upload ảnh/video (max 64MB)
   - Phát hiện xe cộ, người đi bộ
   - Hiển thị kết quả với bounding boxes

2. **External Camera**
   - Kết nối camera từ URL
   - Xem live feed
   - Phát hiện real-time

3. **Analytics**
   - Thống kê phát hiện
   - Biểu đồ phân tích
   - Lịch sử xử lý

4. **Recent Images**
   - Xem lại ảnh đã xử lý
   - Lọc theo thời gian
   - Tải xuống kết quả

## 🐛 Xử Lý Lỗi Thường Gặp

### Port 5000 đã được sử dụng
```bash
# Tìm process đang dùng port
netstat -ano | findstr :5000

# Kill process (thay PID bằng số từ lệnh trên)
taskkill /PID <PID> /F
```

### Thiếu thư viện
```bash
pip install -r requirements.txt
```

### Model chưa tải xuống
Model YOLOv11 sẽ tự động tải xuống lần đầu tiên bạn chạy detection.
Đảm bảo có kết nối internet.

### Database error
```bash
# Xóa database cũ và tạo mới
del fisheye.db
del recent_images.sqlite3
python app.py
```

## 📝 Ghi Chú

- Chế độ **DEBUG** đã tắt trong production
- Sử dụng **CPU mode** mặc định (không cần GPU)
- Database dùng **SQLite** cho local development
- Không cần cài đặt PostgreSQL cho local testing
- Background threads tự động dừng khi tắt ứng dụng

## 🔗 Tài Liệu Thêm

- [INSTALLATION_AND_USAGE.md](./INSTALLATION_AND_USAGE.md) - Hướng dẫn chi tiết
- [feature.md](./feature.md) - Mô tả tính năng
- [DEBUG_REPORT.md](./DEBUG_REPORT.md) - Báo cáo debug
- [SYSTEM_FULL_REPORT.md](./SYSTEM_FULL_REPORT.md) - Báo cáo hệ thống đầy đủ

## ✨ Kiểm Tra Nhanh

Sau khi chạy ứng dụng, thử các chức năng sau:

1. ✅ Truy cập trang chủ: http://localhost:5000
2. ✅ Upload một ảnh test để kiểm tra detection
3. ✅ Xem trang Analytics: http://localhost:5000/analytics
4. ✅ Kiểm tra API health: http://localhost:5000/api/health
5. ✅ Thử tính năng External Camera

Chúc bạn làm việc hiệu quả! 🚀
