# Định Dạng File Được Hỗ Trợ

## 📸 Định Dạng Ảnh

FishEye8K hỗ trợ các định dạng ảnh sau:

- **JPEG/JPG** (`.jpg`, `.jpeg`) - Định dạng phổ biến nhất
- **JFIF** (`.jfif`) - JPEG File Interchange Format
- **PNG** (`.png`) - Hỗ trợ ảnh trong suốt
- **BMP** (`.bmp`) - Windows Bitmap
- **WebP** (`.webp`) - Định dạng ảnh hiện đại của Google
- **TIFF** (`.tiff`) - Tagged Image File Format

### Kích Thước Tối Đa
- **Ảnh**: 64 MB (mặc định)
- **Resolution**: Không giới hạn (khuyến nghị dưới 4K để tốc độ xử lý tốt nhất)

## 🎥 Định Dạng Video

FishEye8K hỗ trợ các định dạng video sau:

- **MP4** (`.mp4`) - Định dạng phổ biến nhất, khuyến nghị sử dụng
- **AVI** (`.avi`) - Audio Video Interleave
- **MOV** (`.mov`) - QuickTime Movie
- **MKV** (`.mkv`) - Matroska Video
- **WebM** (`.webm`) - Web Media format
- **FLV** (`.flv`) - Flash Video

### Kích Thước Tối Đa
- **Video**: 500 MB (mặc định)
- **Độ dài**: 60 giây (mặc định)
- **Resolution**: Khuyến nghị 1080p hoặc thấp hơn

## 📹 Live Stream Support

### Direct Streams
- **HLS** (`.m3u8`) - HTTP Live Streaming
- **RTSP** (`rtsp://`) - Real-Time Streaming Protocol
- **RTMP** (`rtmp://`) - Real-Time Messaging Protocol
- **MJPEG** (`.mjpeg`) - Motion JPEG stream

### YouTube Live
- YouTube live stream URLs tự động được nhận diện và xử lý

### Webcam Portal Support
- Hỗ trợ các trang web có nhiều camera (như webcam.vn, camera.0511.vn)
- Tự động phát hiện và trích xuất snapshot từ HTML

## 🔧 Cấu Hình Upload

Các giới hạn có thể được điều chỉnh trong file `.env`:

```env
# Upload limits
FISHEYE_MAX_UPLOAD_MB=64           # Kích thước tối đa cho ảnh (MB)
FISHEYE_MAX_VIDEO_SECONDS=60       # Độ dài video tối đa (giây)
```

Hoặc trong `config.py`:

```python
MAX_CONTENT_LENGTH = 500 * 1024 * 1024   # 500 MB tổng upload limit
```

## 📝 Lưu Ý

1. **JFIF vs JPEG**: JFIF là một dạng của JPEG với metadata chuẩn hóa. Cả hai đều được xử lý giống nhau.

2. **Video Processing**: 
   - Video dài sẽ được sample với detection stride
   - FPS target mặc định: 5 FPS
   - Có thể điều chỉnh trong UI hoặc API

3. **Performance Tips**:
   - Sử dụng ảnh resolution thấp hơn cho processing nhanh hơn
   - MP4 với H.264 codec cho video processing tốt nhất
   - GPU mode cho xử lý nhiều camera song song

4. **Browser Compatibility**:
   - Tất cả trình duyệt hiện đại đều hỗ trợ
   - File input accept `image/*,video/*` tự động filter đúng loại file

## 🔄 Format Conversion

Nếu bạn có file không được hỗ trợ:

### Ảnh
```bash
# Convert sang JPEG
ffmpeg -i input.heic output.jpg
ffmpeg -i input.raw output.png

# Python (PIL/Pillow)
from PIL import Image
img = Image.open('input.heic')
img.save('output.jpg', 'JPEG')
```

### Video
```bash
# Convert sang MP4
ffmpeg -i input.avi -c:v libx264 -c:a aac output.mp4

# Giảm resolution
ffmpeg -i input.mp4 -vf scale=1280:720 output_720p.mp4

# Cắt video 60 giây đầu
ffmpeg -i input.mp4 -t 60 -c copy output.mp4
```

## ✅ Test Files

Để test hệ thống, bạn có thể sử dụng:
- Example scenarios có sẵn trong UI
- Test images trong thư mục `tests/fixtures/` (nếu có)
- Camera live demo từ các URL webcam công khai

## 🆘 Troubleshooting

### "File type not supported"
- Kiểm tra extension file có trong danh sách hỗ trợ
- Đổi tên file với extension chính xác
- Convert sang format được hỗ trợ

### "File too large"
- Giảm kích thước file
- Tăng `MAX_CONTENT_LENGTH` trong config
- Sử dụng compression tools

### "Video processing failed"
- Kiểm tra codec của video
- Convert sang MP4 với H.264
- Cắt video ngắn hơn 60 giây

---

**Last Updated**: June 2026  
**System**: FishEye8K v2.0
