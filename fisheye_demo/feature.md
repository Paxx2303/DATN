# Danh sách Chức năng Hệ thống Giám sát Giao thông mắt cá (FishEye8K)

Tài liệu này tổng hợp toàn bộ các tính năng, công nghệ và khả năng xử lý hiện tại của hệ thống **FishEye8K Traffic Monitoring System**. Hệ thống được tối ưu hóa cho ống kính mắt cá diện rộng, kết hợp học sâu (YOLOv11) và phân tích luồng giao thông thời gian thực.

---

## 1. Tiền xử lý & Biến đổi hình ảnh mắt cá (Fisheye Preprocessing)
Hệ thống tích hợp bộ xử lý chuyển đổi hình học diện rộng (Fisheye Warping & Unwarping) hỗ trợ kiểm thử và giả lập camera mắt cá:
- **Đa dạng mô hình biến đổi**: Hỗ trợ đầy đủ các hiệu ứng mắt cá phổ biến bao gồm `Standard` (Tiêu chuẩn), `Stereographic` (Lập thể), `Orthographic` (Chính giao), `Equisolid` (Đồng diện tích), và `Thoby`.
- **Cấu hình tham số trực quan**:
  - Tùy chỉnh tiêu cự / độ mạnh thấu kính (`Fisheye Strength`).
  - Điều chỉnh bán kính thấu kính (`Fisheye Radius`) để crop viền đen mắt cá.
  - Tùy chỉnh tọa độ tâm quang học (`Center X / Y`) để lệch góc nhìn.
- **Xử lý linh hoạt**: Cho phép áp dụng trực tiếp hiệu ứng mắt cá vào ảnh/video thường trước khi đưa vào YOLO (giúp huấn luyện/đánh giá độ bền mô hình), hoặc bỏ qua nếu nguồn vào đã là camera mắt cá thực tế.

---

## 2. Nhận diện & Theo vết Đối tượng bằng YOLOv11
Trọng tâm xử lý AI sử dụng mạng nơ-ron tích chập tiên tiến nhất:
- **Nhận diện đa lớp phương tiện giao thông**: Phân loại chính xác các loại đối tượng bao gồm: `Xe con` (Car), `Xe máy` (Motorcycle), `Xe tải` (Truck), `Xe khách / xe buýt` (Bus), `Xe đạp` (Bicycle), và `Người đi bộ` (Person).
- **Theo vết liên tục (Object Tracking)**: Sử dụng thuật toán tracking tích hợp trong YOLOv11 để cấp phát định danh duy nhất (`track_id`) cho từng phương tiện. Đảm bảo theo vết xe xuyên suốt từ lúc đi vào đến khi ra khỏi vùng quét của camera.
- **Tối ưu hóa tốc độ xử lý (Detection Stride)**: Tự động tính toán bước nhảy khung hình dựa trên FPS thực tế và FPS mục tiêu của luồng xử lý (ví dụ: chạy YOLO mỗi 5 khung hình một lần) giúp hệ thống hoạt động cực kỳ mượt mà.

---

## 3. Ước tính Tốc độ Phương tiện (Speed Estimation)
- **Đo tốc độ thời gian thực**: Sử dụng dịch vụ `SpeedEstimator` tính toán vận tốc di chuyển (km/h) của từng phương tiện dựa trên độ dịch chuyển pixel qua các khung hình và tỷ lệ quy đổi khoảng cách thực tế (Physical Calibration).
- **Hiển thị trực quan**: Gán trực tiếp nhãn tốc độ lên bounding box của xe đang chạy (ví dụ: `Car#12 45km/h`).
- **Thống kê tốc độ trung bình**: Tự động tính toán tốc độ trung bình của toàn bộ các xe xuất hiện trong phân đoạn xử lý để đánh giá lưu lượng dòng xe.

---

## 4. Phân tích & Phát hiện Ùn tắc (Congestion Detection)
- **Đo lường mật độ giao thông**: Tự động tính toán diện tích chiếm dụng khung hình của các phương tiện nhằm chấm điểm ùn tắc (`Congestion Score` dưới dạng %).
- **Phân cấp mức độ ùn tắc**: Tự động gắn nhãn cảnh báo dựa trên 3 cấp độ:
  - `LOW` (Thấp - Dưới 30%): Giao thông thông thoáng (nhãn xanh lá).
  - `MODERATE` (Trung bình - Từ 30% đến 60%): Giao thông đông đúc (nhãn cam).
  - `HIGH` (Cao - Trên 60%): Ún ứ / Tắc nghẽn nghiêm trọng (nhãn đỏ, có hiệu ứng nhấp nháy cảnh báo tự động).
- **Cảnh báo lưu lượng**: Tự động gửi cảnh báo mật độ cao/ùn tắc nghiêm trọng khi vượt ngưỡng cấu hình.

---

## 5. Giám sát Camera trực tiếp (Live Streams Monitor)
Giao diện quản lý giám sát thời gian thực cực kỳ cao cấp:
- **Tích hợp nguồn camera ngoài**: Hỗ trợ kết nối luồng camera ngoài (URL trực tiếp) hoặc nhúng nguồn phát YouTube.
- **Đa chế độ tính toán (Compute Mode)**:
  - `CPU Mode`: Chạy tuần tự khung hình/khung hình cho 1 camera, tối ưu hóa tài nguyên cho thiết bị cấu hình thấp.
  - `GPU Mode`: Hỗ trợ luồng chạy song song đồng thời cả **4 camera** cùng lúc để giám sát các ngã tư phức tạp.
- **Truyền luồng trực tiếp MJPEG (MJPEG Multi-Stream)**: Cung cấp API phát trực tuyến luồng ảnh đã được vẽ bounding box và ước tính tốc độ cho từng camera riêng biệt hoặc màn hình tổng quan ghép 4 camera.

---

## 6. Giao diện Không gian làm việc (Interactive Workspace)
Trang phân tích tệp tin độc lập giúp thử nghiệm nhanh chóng:
- **Kéo thả / Tải tệp tin thông minh**: Hỗ trợ người dùng kéo thả trực tiếp ảnh/video vào khu vực upload.
- **Khả năng tương thích tệp cao trên Windows**: Khắc phục triệt để lỗi lọc định dạng tệp nhờ cơ chế kiểm tra đuôi mở rộng tự động (nhận diện tốt các tệp ảnh nén thế hệ mới như `.jfif`, `.heic`, `.avif`, `.webp` và các tệp video `.mp4`, `.avi`, `.mov`).
- **Bảng cấu hình linh hoạt**: Cho phép điều chỉnh ngưỡng tin cậy (`Confidence Threshold`) và ngưỡng trùng khớp hộp giao nhau (`IoU Threshold`) trực tiếp trên giao diện để tinh chỉnh độ nhạy YOLO.
- **Xem trước & Tải xuống thành phẩm**:
  - Trực quan hóa ảnh đã vẽ bounding box hoặc video đã render chú thích ngay trên màn hình.
  - Cung cấp liên kết tải xuống tức thì cho tệp tin video/ảnh kết quả cùng tệp dữ liệu chi tiết JSON Metadata chứa toàn bộ tọa độ bbox, phân loại và định danh của từng xe phục vụ lưu trữ hoặc phân tích sâu.

---

## 7. Quản lý Lịch sử & Lưu trữ Cơ sở dữ liệu
- **Lưu trữ SQLite**: Hệ thống sử dụng cơ sở dữ liệu `fisheye.db` cục bộ để ghi nhận thông tin của tất cả các phiên chạy (Inference Runs).
- **Trình duyệt lịch sử trực quan (History Logs)**:
  - Cho phép người dùng xem lại toàn bộ các lượt phân tích trước đó dưới dạng bảng phân trang.
  - Hỗ trợ xem nhanh kết quả, biểu đồ tỷ lệ các loại phương tiện đã phát hiện, và nhấp để tải lại trực tiếp kết quả cũ vào không gian làm việc mà không cần phân tích lại từ đầu.
- **Biểu đồ thống kê tổng quan (Dashboard)**: Thống kê số lượng lượt chạy, tổng số đối tượng phát hiện, thời gian suy luận trung bình, và vẽ biểu đồ hình cột phân phối các loại xe thông qua thư viện `Chart.js` cao cấp.
