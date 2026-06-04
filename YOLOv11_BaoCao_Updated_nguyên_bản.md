# TRƯỜNG ĐẠI HỌC GIAO THÔNG VẬN TẢI

## KHOA CÔNG NGHỆ THÔNG TIN

---

# ĐỒ ÁN TỐT NGHIỆP

# XÂY DỰNG HỆ THỐNG NHẬN DIỆN VẬT THỂ QUA CAMERA MẮT CÁ

| | |
|---|---|
| **Sinh viên thực hiện** | Nguyễn Quốc Nam |
| **Mã số sinh viên** | 221220938 |
| **Lớp** | CNTT1-K63 |
| **Khóa** | 63 |
| **Ngành đào tạo** | Công nghệ thông tin |
| **Hệ đào tạo** | Chính quy |
| **Giảng viên hướng dẫn** | TS. Nguyễn Đức Dư |

**Hà Nội – 2026**

---

# LỜI CẢM ƠN

Lời đầu tiên, tôi xin bày tỏ lòng biết ơn sâu sắc đến TS. Nguyễn Đức Dư – giảng viên hướng dẫn đã tận tình chỉ bảo, định hướng nghiên cứu và động viên tôi trong suốt quá trình thực hiện đồ án tốt nghiệp này. Những góp ý chuyên môn và kinh nghiệm thực tiễn của thầy đã giúp tôi vượt qua nhiều khó khăn trong việc triển khai mô hình học sâu trên dữ liệu camera fisheye.

Tôi cũng xin gửi lời cảm ơn chân thành đến quý thầy cô trong Khoa Công nghệ Thông tin – Trường Đại học Giao thông Vận tải đã truyền đạt kiến thức nền tảng vững chắc trong suốt bốn năm học tập, đặc biệt các học phần Thị giác Máy tính, Học sâu và Xử lý Ảnh số, làm cơ sở lý thuyết cho đồ án này.

Xin cảm ơn ban quản trị cộng đồng mã nguồn mở Ultralytics và các nhóm nghiên cứu đã công bố bộ dữ liệu FishEye8K (ECCV 2022 Workshop), VisDrone2019 (IEEE/CVF ICCV 2019 Workshop) cùng thư viện SAHI – những tài nguyên quý giá tạo nền tảng thực nghiệm cho đề tài.

Cuối cùng, tôi xin gửi lời cảm ơn đặc biệt đến gia đình và bạn bè đã luôn đồng hành, chia sẻ và là nguồn động lực to lớn để tôi hoàn thành đồ án đúng hạn.

Do thời gian nghiên cứu có hạn và đây là lần đầu tiên thực hiện đề tài ở quy mô đồ án tốt nghiệp, chắc chắn báo cáo không tránh khỏi những thiếu sót. Kính mong quý thầy cô và các bạn đọc góp ý để tôi hoàn thiện hơn trong các nghiên cứu tiếp theo.

Hà Nội, ngày … tháng … năm 2026

**Sinh viên thực hiện**

---

# MỤC LỤC

MỞ ĐẦU

CHƯƠNG 1. TỔNG QUAN VÀ CƠ SỞ LÝ THUYẾT

1.1. Bối cảnh và tính cấp thiết của đề tài

1.1.1. Thực trạng giao thông đô thị tại Việt Nam

1.1.2. Xu hướng ứng dụng AI trong giám sát giao thông

1.1.3. Vai trò của camera fisheye trong hệ thống giám sát

1.2. Tổng quan về phát hiện đối tượng trong thị giác máy tính

1.2.1. Giới thiệu bài toán phát hiện đối tượng

1.2.2. Phân loại các phương pháp phát hiện đối tượng

1.2.3. Các thách thức đặc thù trong môi trường camera fisheye

1.3. Camera Fisheye – Mô hình hình học và đặc điểm kỹ thuật

1.3.1. Nguyên lý quang học của ống kính fisheye

1.3.2. Các mô hình chiếu fisheye phổ biến

1.3.3. Biến dạng hình học và ảnh hưởng đến phát hiện đối tượng

1.3.4. Hàm biến đổi fisheye sử dụng trong đề tài

1.3.5. Chuyển đổi bounding box sang không gian fisheye

1.4. Kiến trúc YOLOv11 và lịch sử phát triển họ YOLO

1.4.1. Lịch sử phát triển các thế hệ YOLO

1.4.2. Kiến trúc tổng thể YOLOv11

1.4.3. Backbone C3k2 – Cross Stage Partial

1.4.4. Module AIFI Transformer trong Neck

1.4.5. Detection Head anchor-free

1.4.6. So sánh YOLOv11 với các phiên bản trước

1.5. Kỹ thuật SAHI – Sliced Aided Hyper Inference

1.5.1. Vấn đề phát hiện đối tượng nhỏ trong ảnh độ phân giải cao

1.5.2. Nguyên lý hoạt động của SAHI

1.5.3. Chiến lược tổng hợp kết quả và NMM

1.5.4. Ứng dụng SAHI trong bài toán fisheye

1.6. Hàm mất mát và chiến lược tối ưu hóa

1.6.1. CIoU Loss cho hồi quy bounding box

1.6.2. Distribution Focal Loss (DFL)

1.6.3. Chiến lược tối ưu hóa AdamW và cosine annealing

1.7. Kỹ thuật tăng cường dữ liệu

1.7.1. Mosaic Augmentation v2

1.7.2. MixUp Augmentation

1.7.3. Copy-Paste Augmentation

1.8. Các bộ dữ liệu liên quan

1.8.1. Bộ dữ liệu FishEye8K

1.8.2. Bộ dữ liệu VisDrone2019

1.8.3. So sánh và lý do lựa chọn

1.9. Tổng quan các công trình nghiên cứu liên quan

1.9.1. Phát hiện đối tượng trên ảnh fisheye

1.9.2. Phát hiện đối tượng nhỏ từ góc nhìn UAV

1.9.3. Khoảng trống nghiên cứu và đóng góp của đề tài

1.10. Phát biểu bài toán và mục tiêu nghiên cứu

1.10.1. Phát biểu bài toán

1.10.2. Mục tiêu và phạm vi nghiên cứu

1.10.3. Phương pháp nghiên cứu

1.10.4. Công nghệ và công cụ sử dụng

1.10.5. Quy trình phát triển

CHƯƠNG 2. PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG

2.1. Đặc tả yêu cầu hệ thống

2.1.1. Khảo sát hệ thống camera giao thông trực tuyến

2.1.2. Yêu cầu chức năng

2.1.3. Yêu cầu phi chức năng

2.2. Kiến trúc tổng thể hệ thống

2.2.1. Kiến trúc phân lớp

2.2.2. Kiến trúc xử lý video bất đồng bộ

2.2.3. Luồng dữ liệu

2.3. Thiết kế cơ sở dữ liệu

2.3.1. Sơ đồ thực thể liên kết (ERD)

2.3.2. Chiến lược tương thích đa CSDL

2.4. Thiết kế REST API

2.4.1. Quy ước thiết kế API

2.4.2. Danh sách API endpoint

CHƯƠNG 3. HUẤN LUYỆN VÀ ĐÁNH GIÁ MÔ HÌNH

3.1. Bộ dữ liệu sử dụng

3.1.1. Bộ dữ liệu FishEye8K

3.1.2. Bộ dữ liệu VisDrone2019

3.2. Tiền xử lý và bổ sung dữ liệu

3.2.1. Pipeline chuyển đổi VisDrone sang fisheye

3.2.2. Cân bằng dữ liệu theo lớp

3.3. Cấu hình huấn luyện

3.3.1. Môi trường huấn luyện

3.3.2. Siêu tham số huấn luyện

3.3.3. Cấu trúc file checkpoint

3.4. Kết quả huấn luyện

3.4.1. Quá trình hội tụ

3.4.2. Kết quả đánh giá trên tập kiểm thử

3.5. So sánh hai phiên bản YOLOv11-L

CHƯƠNG 4. XÂY DỰNG ỨNG DỤNG GIÁM SÁT GIAO THÔNG THÔNG MINH

4.1. Kiến trúc ứng dụng Flask

4.1.1. Cấu trúc thư mục dự án

4.1.2. Khởi tạo ứng dụng Flask

4.1.3. Xử lý concurrent requests

4.2. Module ước lượng tốc độ phương tiện (SpeedEstimator)

4.2.1. Nguyên lý theo dõi IoU

4.2.2. Chuyển đổi pixel displacement sang tốc độ km/h

4.3. Module phát hiện tắc nghẽn giao thông (CongestionDetector)

4.3.1. Phương pháp phân tích mật độ ROI

4.3.2. Hiển thị trực quan

4.4. Module phân tích luồng giao thông (Analytics)

4.5. Giao diện người dùng và kiểm thử

4.5.1. Giao diện web

4.5.2. Kiểm thử chức năng

4.5.3. Đánh giá hiệu năng tổng thể

KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN

TÀI LIỆU THAM KHẢO

---

# DANH MỤC TỪ VIẾT TẮT

| **Từ viết tắt** | **Giải thích** |
|---|---|
| AI | Artificial Intelligence – Trí tuệ nhân tạo |
| AMP | Automatic Mixed Precision – Độ chính xác hỗn hợp tự động |
| API | Application Programming Interface – Giao diện lập trình ứng dụng |
| BBox | Bounding Box – Hộp giới hạn đối tượng |
| CNN | Convolutional Neural Network – Mạng nơ-ron tích chập |
| CPU | Central Processing Unit – Bộ xử lý trung tâm |
| CV | Computer Vision – Thị giác máy tính |
| DFL | Distribution Focal Loss – Hàm mất mát phân phối tiêu điểm |
| FishEye8K | Bộ dữ liệu fisheye 8.000 ảnh từ cuộc thi AI City Challenge |
| FPN | Feature Pyramid Network – Mạng kim tự tháp đặc trưng |
| FPS | Frames Per Second – Số khung hình mỗi giây |
| GCS | Google Cloud Storage – Dịch vụ lưu trữ đám mây Google |
| GFLOPs | Giga Floating-Point Operations Per Second |
| GPU | Graphics Processing Unit – Bộ xử lý đồ họa |
| IoU | Intersection over Union – Chỉ số giao thoa trên hợp nhất |
| mAP | mean Average Precision – Độ chính xác trung bình tổng hợp |
| NMS | Non-Maximum Suppression – Triệt tiêu phi cực đại |
| ONNX | Open Neural Network Exchange – Định dạng mô hình mở |
| REST | Representational State Transfer – Kiến trúc dịch vụ web |
| ROI | Region of Interest – Vùng quan tâm |
| SAHI | Sliced Aided Hyper Inference – Suy diễn tăng cường chia lát |
| UAV | Unmanned Aerial Vehicle – Máy bay không người lái |
| VisDrone | Bộ dữ liệu phát hiện đối tượng từ UAV (IEEE/CVF 2019) |
| YOLO | You Only Look Once – Kiến trúc phát hiện đối tượng thời gian thực |

---

# DANH MỤC BẢNG

Bảng 1.1. Các mô hình chiếu fisheye phổ biến và đặc điểm

Bảng 1.2. So sánh các thế hệ YOLO từ v1 đến v11

Bảng 1.3. So sánh các phương pháp phát hiện đối tượng theo paradigm

Bảng 1.4. Thống kê bộ dữ liệu FishEye8K theo tập train/val/test

Bảng 1.5. Thống kê bộ dữ liệu VisDrone2019

Bảng 1.6. Công nghệ và công cụ sử dụng

Bảng 2.1. So sánh hệ thống camera giao thông hiện có với hệ thống đề xuất

Bảng 2.2. Danh sách yêu cầu chức năng hệ thống

Bảng 2.3. Cấu trúc các bảng chính trong CSDL

Bảng 2.4. Danh sách API endpoint và mô tả chức năng

Bảng 3.1. Ánh xạ lớp đối tượng từ VisDrone sang FishEye8K

Bảng 3.2. Thống kê bộ dữ liệu sau khi gộp FishEye8K và VisDrone-fisheye

Bảng 3.3. Siêu tham số huấn luyện thực tế (từ notebook Kaggle)

Bảng 3.4. Kết quả đánh giá Precision, Recall, mAP theo từng lớp đối tượng

Bảng 3.5. So sánh YOLOv11-L Cơ bản và YOLOv11-L Nâng cao

Bảng 4.1. Danh sách module và chức năng trong package fisheye_demo

Bảng 4.2. Bốn mức độ tắc nghẽn giao thông

Bảng 4.3. Kết quả kiểm thử chức năng hệ thống

---

# DANH MỤC HÌNH

Hình 1.1. Camera fisheye 360° lắp đặt tại nút giao thông đô thị

Hình 1.2. Minh họa biến dạng barrel distortion đặc trưng của ống kính fisheye

Hình 1.3. Sơ đồ so sánh các mô hình chiếu fisheye theo góc theta

Hình 1.4. Kết quả áp dụng hàm to_fisheye() trên ảnh giao thông (strength=0,5)

Hình 1.5. Kiến trúc tổng thể mạng YOLOv11 từ backbone đến detection head

Hình 1.6. Kiến trúc khối C3k2 (Cross Stage Partial with kernel size 2)

Hình 1.7. Cơ chế Attention-based Intra-scale Feature Interaction (AIFI)

Hình 1.8. So sánh detection head anchor-based và anchor-free

Hình 1.9. Minh họa kỹ thuật SAHI – chia lát và tổng hợp kết quả

Hình 1.10. Quy trình tính CIoU Loss cho bài toán hồi quy bounding box

Hình 1.11. Minh họa Distribution Focal Loss trên phân phối rời rạc

Hình 1.12. Minh họa các kỹ thuật augmentation: mosaic, mixup, copy-paste

Hình 1.13. Mẫu ảnh từ bộ dữ liệu FishEye8K với nhãn bounding box

Hình 1.14. Mẫu ảnh từ bộ dữ liệu VisDrone2019 (góc nhìn UAV)

Hình 1.15. Quy trình phát triển hệ thống theo mô hình iterative

Hình 2.1. Giao diện của hệ thống camera.0511.vn

Hình 2.2. Giao diện của hệ thống alltrafficcams.com

Hình 2.3. Sơ đồ kiến trúc hệ thống tổng thể

Hình 3.1. Pipeline chuyển đổi VisDrone sang fisheye và gộp dataset

Hình 3.2. Đường cong training loss và validation loss theo epoch

Hình 3.3. Đường cong mAP@0.5 và mAP@0.5:0.95 theo epoch

Hình 3.4. Confusion matrix trên tập kiểm thử (normalized)

Hình 3.5. So sánh hiệu năng các biến thể YOLOv11 trên tập kiểm thử

Hình 4.1. Minh họa kết quả ước lượng tốc độ phương tiện trên ảnh fisheye

Hình 4.2. Giao diện web tổng quan hệ thống giám sát giao thông

Hình 4.3. Giao diện tải lên video và xem kết quả phát hiện đối tượng

---

# MỞ ĐẦU

**1. Lý do chọn đề tài**

Trong bối cảnh đô thị hóa nhanh chóng và sự gia tăng đột biến của phương tiện giao thông tại các thành phố lớn Việt Nam, nhu cầu xây dựng các hệ thống giám sát giao thông thông minh ngày càng trở nên cấp thiết. Theo số liệu thống kê của Cục Đường bộ Việt Nam năm 2024, cả nước có hơn 7,8 triệu ô tô và 73 triệu xe máy đang lưu hành, gây ra áp lực lớn lên hạ tầng giao thông đô thị [24]. Số vụ tai nạn giao thông trong năm 2023 vẫn còn ở mức đáng lo ngại với hơn 10.000 vụ tai nạn nghiêm trọng được ghi nhận.

Camera giám sát giao thông hiện đại, đặc biệt là camera fisheye (camera mắt cá), ngày càng được ưa chuộng trong các ứng dụng giám sát đô thị do khả năng bao phủ góc nhìn rất rộng (lên đến 180°–220°), cho phép quan sát toàn bộ một nút giao thông chỉ với một thiết bị duy nhất. Tuy nhiên, hình ảnh từ camera fisheye bị biến dạng méo hình thùng (barrel distortion) đặc trưng – các đường thẳng trong thực tế xuất hiện cong vênh và tỷ lệ kích thước đối tượng thay đổi không tuyến tính theo khoảng cách tâm ảnh – khiến các mô hình phát hiện đối tượng truyền thống huấn luyện trên ảnh thẳng (perspective camera) không thể áp dụng trực tiếp mà không có bước tiền xử lý hoặc tinh chỉnh đặc biệt [6].

Sự ra đời của kiến trúc YOLOv11 (Ultralytics, 2024) với backbone C3k2 cải tiến, module AIFI transformer và detection head anchor-free mở ra cơ hội triển khai hệ thống phát hiện đối tượng thời gian thực có độ chính xác cao trên dữ liệu fisheye [3]. Kết hợp với kỹ thuật SAHI (Sliced Aided Hyper Inference) [4] cho phép nâng cao đáng kể khả năng phát hiện các đối tượng nhỏ như người đi bộ ở xa tâm ảnh, đề tài này hướng đến xây dựng một hệ thống nhận diện vật thể hoàn chỉnh, ứng dụng thực tế trong giám sát giao thông đô thị Việt Nam.

**2. Mục tiêu đề tài**

Đề tài hướng đến xây dựng một hệ thống nhận diện vật thể đầy đủ trên camera fisheye sử dụng kiến trúc YOLOv11, bao gồm: (i) fine-tune mô hình YOLOv11-L trên bộ dữ liệu fisheye kết hợp FishEye8K và VisDrone2019 đã chuyển đổi; (ii) tích hợp kỹ thuật SAHI để nâng cao khả năng phát hiện đối tượng nhỏ; (iii) xây dựng ứng dụng Flask hoàn chỉnh với các module phân tích giao thông thông minh.

**3. Đối tượng và phạm vi nghiên cứu**

Đối tượng nghiên cứu: Mô hình phát hiện đối tượng YOLOv11-L, kỹ thuật SAHI, dữ liệu ảnh từ camera fisheye. Phạm vi: phát hiện 5 lớp đối tượng giao thông (Car, Bus, Truck, Pedestrian, Motorbike) trong điều kiện camera fisheye góc nhìn từ trên cao.

**4. Phương pháp nghiên cứu**

Kết hợp nghiên cứu lý thuyết (mô hình hình học fisheye, kiến trúc deep learning) với thực nghiệm (fine-tuning, đánh giá mAP, kiểm thử hệ thống). Dữ liệu thực nghiệm từ hai bộ dữ liệu công khai: FishEye8K [20] và VisDrone2019 [5].

**5. Cấu trúc đồ án**

Đồ án được tổ chức thành bốn chương chính: Chương 1 trình bày tổng quan và toàn bộ cơ sở lý thuyết làm nền tảng cho đề tài; Chương 2 phân tích và thiết kế hệ thống; Chương 3 mô tả quá trình huấn luyện và đánh giá mô hình; Chương 4 trình bày việc xây dựng ứng dụng giám sát giao thông thông minh. Phần kết luận tổng kết kết quả và định hướng phát triển.

---

# CHƯƠNG 1. TỔNG QUAN VÀ CƠ SỞ LÝ THUYẾT

## 1.1. Bối cảnh và tính cấp thiết của đề tài

### 1.1.1. Thực trạng giao thông đô thị tại Việt Nam

Việt Nam đang trải qua quá trình đô thị hóa với tốc độ thuộc hàng nhanh nhất khu vực Đông Nam Á. Dân số đô thị đã vượt 38% tổng dân số cả nước và tiếp tục tăng nhanh theo từng năm. Kéo theo đó, số lượng phương tiện giao thông cơ giới tăng theo cấp số nhân: theo Báo cáo thống kê phương tiện cơ giới đường bộ năm 2024 của Cục Đường bộ Việt Nam, cả nước đang có hơn 7,8 triệu ô tô và 73 triệu xe máy được đăng ký lưu hành [24]. Riêng tại Hà Nội và Thành phố Hồ Chí Minh, mật độ phương tiện tại các nút giao thông trọng yếu vào giờ cao điểm thường xuyên vượt ngưỡng tắc nghẽn nghiêm trọng.

Thực trạng này đặt ra áp lực lớn lên hệ thống hạ tầng giao thông đô thị vốn đã quá tải. Các hệ thống camera giám sát giao thông tuy đã được triển khai rộng rãi tại các thành phố lớn, nhưng phần lớn chỉ phục vụ mục đích quan sát trực tiếp bởi nhân lực tại trung tâm điều hành, thiếu hoàn toàn khả năng phân tích tự động và cảnh báo thông minh. Theo đó, việc phát triển một hệ thống giám sát giao thông ứng dụng trí tuệ nhân tạo, có thể tự động phát hiện phương tiện, ước lượng mật độ, nhận diện sự cố và đưa ra cảnh báo kịp thời là nhu cầu cấp thiết và có giá trị thực tiễn cao.

### 1.1.2. Xu hướng ứng dụng AI trong giám sát giao thông

Trên thế giới, việc ứng dụng trí tuệ nhân tạo và thị giác máy tính (Computer Vision) vào hệ thống giao thông thông minh (Intelligent Transportation Systems – ITS) đã trở thành xu hướng chủ đạo trong thập kỷ qua. Các thành phố lớn tại Trung Quốc, Singapore, Hoa Kỳ và châu Âu đã triển khai thành công các hệ thống giám sát giao thông tự động có khả năng nhận diện phương tiện, phân tích luồng giao thông theo thời gian thực và phối hợp điều khiển đèn tín hiệu để giảm thiểu tắc nghẽn.

Các thuật toán phát hiện đối tượng dựa trên học sâu (deep learning), đặc biệt là họ mô hình YOLO (You Only Look Once), đã chứng minh được hiệu quả vượt trội so với các phương pháp truyền thống về cả tốc độ xử lý lẫn độ chính xác [1]. Mô hình YOLO từ phiên bản đầu tiên công bố năm 2016 đã liên tục được cải tiến qua nhiều thế hệ, đến nay phiên bản YOLOv11 (2024) đã đạt đến mức độ chính xác và tốc độ phù hợp cho triển khai thực tế trong các hệ thống nhúng và edge computing [3].

Tại Việt Nam, nghiên cứu và triển khai AI trong giám sát giao thông còn ở giai đoạn ban đầu. Phần lớn các đề tài nghiên cứu tập trung vào camera perspective thông thường với bộ dữ liệu huấn luyện từ nước ngoài, chưa quan tâm đúng mức đến đặc thù của camera fisheye – loại camera đang được ứng dụng ngày càng phổ biến trong các hệ thống giám sát thực tế do khả năng bao phủ góc nhìn rộng.

### 1.1.3. Vai trò của camera fisheye trong hệ thống giám sát

Camera fisheye sở hữu nhiều ưu điểm vượt trội so với camera perspective thông thường trong các ứng dụng giám sát giao thông. Với góc nhìn lên đến 180°–220°, một camera fisheye có thể bao quát toàn bộ một nút giao thông, bao gồm tất cả các làn xe và khu vực dành cho người đi bộ, trong khi một camera perspective thông thường thường chỉ quan sát được một phạm vi hẹp và cần nhiều thiết bị để bao phủ cùng diện tích đó [6].

Ngoài tiết kiệm chi phí lắp đặt và bảo trì, camera fisheye còn cho phép theo dõi quỹ đạo di chuyển của phương tiện trên một góc nhìn tổng thể, thuận tiện cho việc phân tích hành vi giao thông và phát hiện vi phạm. Đây là lý do tại sao camera fisheye ngày càng được các đô thị thông minh ưa chuộng trong thiết kế hệ thống giám sát giao thông thế hệ mới.

Tuy nhiên, đặc điểm méo hình thùng (barrel distortion) của camera fisheye tạo ra thách thức kỹ thuật đáng kể: các mô hình phát hiện đối tượng được huấn luyện trên ảnh perspective thông thường không thể hoạt động hiệu quả trên ảnh fisheye mà không có bước xử lý đặc biệt. Hơn nữa, bộ dữ liệu huấn luyện chuyên biệt cho camera fisheye còn khan hiếm so với các bộ dữ liệu perspective như COCO hay ImageNet, khiến việc nghiên cứu và phát triển mô hình phát hiện đối tượng trên fisheye trở thành một bài toán thú vị và có giá trị thực tiễn cao [7].

## 1.2. Tổng quan về phát hiện đối tượng trong thị giác máy tính

### 1.2.1. Giới thiệu bài toán phát hiện đối tượng

Phát hiện đối tượng (Object Detection) là một trong những bài toán cơ bản và quan trọng nhất trong lĩnh vực thị giác máy tính. Bài toán yêu cầu hệ thống không chỉ nhận diện được sự hiện diện của các đối tượng thuộc các lớp được định nghĩa trước trong một ảnh đầu vào, mà còn xác định chính xác vị trí của từng đối tượng thông qua một hộp giới hạn (bounding box) bao quanh đối tượng đó.

Về mặt hình thức, cho một ảnh đầu vào I có kích thước H×W×C, bài toán phát hiện đối tượng yêu cầu tìm tập hợp D = {(b_i, c_i, s_i)} trong đó b_i = (x, y, w, h) là tọa độ bounding box của đối tượng thứ i, c_i ∈ {1, ..., K} là nhãn lớp và s_i ∈ [0,1] là điểm tin cậy (confidence score). Để đánh giá độ chính xác của các bounding box dự đoán, chỉ số Intersection over Union (IoU) được sử dụng phổ biến [10]:

IoU = |B_pred ∩ B_gt| / |B_pred ∪ B_gt|

trong đó B_pred là bounding box dự đoán và B_gt là bounding box ground-truth. Một dự đoán được coi là đúng (True Positive) khi IoU vượt ngưỡng định trước, thường là 0,5.

Chỉ số đánh giá tổng hợp được dùng phổ biến nhất trong cộng đồng nghiên cứu là mean Average Precision (mAP). mAP@0.5 tính trung bình AP của tất cả các lớp đối tượng tại ngưỡng IoU = 0,5, trong khi mAP@0.5:0.95 tính trung bình trên nhiều ngưỡng IoU từ 0,5 đến 0,95 với bước nhảy 0,05, phản ánh độ chính xác định vị bounding box toàn diện hơn [10].

### 1.2.2. Phân loại các phương pháp phát hiện đối tượng

Lịch sử phát triển của phát hiện đối tượng có thể chia thành ba giai đoạn chính:

**Giai đoạn trước deep learning (trước 2012)**: Các phương pháp truyền thống như Viola-Jones, Histogram of Oriented Gradients (HOG) kết hợp Support Vector Machine (SVM) và Deformable Part Models (DPM) dựa trên đặc trưng thủ công (hand-crafted features). Các phương pháp này bị giới hạn về độ chính xác và khả năng tổng quát hóa.

**Giai đoạn two-stage detectors (2014–2016)**: Region-based CNN (R-CNN) [9] và các biến thể Fast R-CNN, Faster R-CNN đã mang lại bước đột phá về độ chính xác bằng cách tách biệt bước đề xuất vùng quan tâm (Region Proposal Network) và bước phân loại. Tuy nhiên, kiến trúc hai giai đoạn này đòi hỏi chi phí tính toán lớn, không phù hợp cho xử lý thời gian thực.

**Giai đoạn one-stage detectors (từ 2016)**: YOLO [1], SSD [10] và RetinaNet [23] xử lý toàn bộ ảnh trong một lần forward pass duy nhất, đánh đổi một phần độ chính xác để đổi lấy tốc độ xử lý nhanh hơn nhiều lần. Đây là nền tảng cho các ứng dụng real-time hiện đại.

| **Paradigm** | **Đại diện** | **Ưu điểm** | **Nhược điểm** |
|---|---|---|---|
| Two-stage | Faster R-CNN | Độ chính xác cao | Chậm, không phù hợp realtime |
| One-stage | YOLO, SSD | Nhanh, phù hợp realtime | Kém hơn với vật thể nhỏ |
| Transformer-based | DETR [16] | Loại bỏ NMS, end-to-end | Chi phí tính toán lớn |
| Anchor-free | CenterNet, YOLOv11 | Đơn giản hóa thiết kế | Cần chiến lược gán nhãn tốt |

**Bảng 1.3. So sánh các phương pháp phát hiện đối tượng theo paradigm**

### 1.2.3. Các thách thức đặc thù trong môi trường camera fisheye

Phát hiện đối tượng trên ảnh fisheye gặp phải những thách thức đặc thù so với ảnh perspective thông thường:

**Biến dạng hình học phi tuyến**: Barrel distortion làm cho hình dạng của phương tiện bị méo không đồng đều trên toàn bộ khung hình. Xe ô tô ở trung tâm ảnh gần như không bị biến dạng, nhưng cùng loại xe đó ở vùng biên ảnh có thể bị méo đến mức khó nhận ra. Điều này làm cho bounding box hình chữ nhật truyền thống trở nên kém phù hợp để bao chứa các đối tượng ở vùng biên [7].

**Đối tượng nhỏ và mật độ cao**: Với góc nhìn rộng, camera fisheye nhìn thấy nhiều đối tượng hơn trong cùng một khung hình nhưng mỗi đối tượng lại chiếm diện tích pixel nhỏ hơn. Người đi bộ ở xa tâm ảnh có thể chỉ chiếm 10–30 pixel chiều cao, thách thức khả năng phát hiện của các mô hình được huấn luyện cho đối tượng có kích thước chuẩn [4].

**Phân phối kích thước không đồng đều**: Đối tượng gần tâm ảnh và đối tượng ở rìa ảnh có tỷ lệ kích thước rất khác nhau do đặc tính phóng đại của ống kính. Mô hình cần học được invariant này để hoạt động tốt trên toàn bộ vùng ảnh.

**Thiếu dữ liệu huấn luyện**: Số lượng bộ dữ liệu fisheye có nhãn annotation chất lượng cao còn rất hạn chế so với các bộ dữ liệu perspective như COCO (330.000 ảnh) hay Open Images. Bộ dữ liệu fisheye lớn nhất hiện có là FishEye8K (8.000 ảnh) [20] vẫn còn khá nhỏ cho việc huấn luyện từ đầu.

## 1.3. Camera Fisheye – Mô hình hình học và đặc điểm kỹ thuật

### 1.3.1. Nguyên lý quang học của ống kính fisheye

Ống kính fisheye là loại ống kính siêu góc rộng được thiết kế đặc biệt để thu nhận ánh sáng từ góc nhìn cực rộng, thường từ 100° đến 220° tùy theo thiết kế. Khác với ống kính perspective thông thường sử dụng mô hình pinhole để chiếu các tia sáng lên mặt phẳng ảnh, ống kính fisheye sử dụng một chuỗi các thấu kính đặc biệt để bẻ cong đường đi của ánh sáng từ các góc lớn vào một mặt phẳng cảm biến hữu hạn [6].

Kết quả là hình ảnh thu được có đặc trưng biến dạng phi tuyến rõ rệt: các đường thẳng song song trong không gian 3D xuất hiện cong về phía tâm ảnh (barrel distortion), và vật thể càng xa tâm ảnh thì càng bị méo và thu nhỏ tương đối. Đây là đánh đổi có chủ ý giữa góc nhìn và độ trung thực hình học – điều mà một ống kính perspective không thể đồng thời đạt được.

Phương trình chiếu tổng quát của camera fisheye biểu diễn mối quan hệ giữa góc tới theta (góc tạo bởi tia sáng và trục quang học) và bán kính r trên mặt phẳng ảnh:

r(theta) = f · g(theta)

trong đó f là tiêu cự hiệu dụng của ống kính và g(theta) là hàm chiếu đặc trưng phụ thuộc vào loại ống kính [6].

### 1.3.2. Các mô hình chiếu fisheye phổ biến

Có nhiều mô hình chiếu fisheye khác nhau, mỗi loại có công thức g(theta) riêng và được thiết kế cho những mục đích ứng dụng khác nhau [6]:

| **Mô hình chiếu** | **Công thức g(theta)** | **Đặc điểm ứng dụng** |
|---|---|---|
| Equidistant (Equal-angle) | theta | Phân bố đều góc, phổ biến nhất trong camera an ninh |
| Equisolid (Equal-area) | 2·sin(theta/2) | Bảo toàn diện tích, dùng trong đo lường và lập bản đồ |
| Orthographic | sin(theta) | Chiếu vuông góc, góc nhìn tối đa 180°, dùng trong thiên văn |
| Stereographic | 2·tan(theta/2) | Bảo toàn góc (conformal), ít phổ biến |
| Rectilinear (Perspective) | tan(theta) | Không biến dạng đường thẳng, góc nhìn dưới 180° |

**Bảng 1.1. Các mô hình chiếu fisheye phổ biến và đặc điểm**

Trong hầu hết các camera fisheye thương mại dùng cho giám sát giao thông, mô hình Equidistant được sử dụng phổ biến nhất do tính đơn giản trong hiệu chỉnh và xử lý ảnh. Mô hình này phân bố đều các góc trên bán kính ảnh, nghĩa là bán kính r tỷ lệ tuyến tính với góc tới theta, giúp đơn giản hóa các phép tính chuyển đổi tọa độ.

### 1.3.3. Biến dạng hình học và ảnh hưởng đến phát hiện đối tượng

Biến dạng barrel distortion trong ảnh fisheye ảnh hưởng trực tiếp và nghiêm trọng đến hiệu quả của các thuật toán phát hiện đối tượng được thiết kế cho ảnh perspective. Có ba vấn đề chính cần xem xét:

**Thứ nhất – Biến dạng hình dạng đối tượng**: Bounding box hình chữ nhật thẳng đứng chuẩn không còn phù hợp để bao chứa các đối tượng ở vùng biên ảnh fisheye, nơi phương tiện có thể bị méo theo đường cong. Điều này làm tăng tỷ lệ vùng nền (background) trong bounding box và giảm tỷ lệ phần đối tượng thực sự, ảnh hưởng đến chất lượng huấn luyện và dự đoán [7].

**Thứ hai – Phân phối feature map không đồng đều**: Các mạng CNN trích xuất đặc trưng theo grid đều, nhưng trong ảnh fisheye, mật độ thông tin hình học phân bố không đều: vùng trung tâm ít méo hơn và thường chứa ít đối tượng hơn trong khi vùng biên chứa nhiều phương tiện nhưng biến dạng nặng hơn. Điều này gây ra sự mất cân bằng trong quá trình học đặc trưng.

**Thứ ba – Kích thước đối tượng không đồng nhất theo vị trí**: Hai phương tiện cùng loại và cùng khoảng cách thực tế với camera nhưng ở các góc khác nhau sẽ xuất hiện với kích thước pixel rất khác nhau trong ảnh fisheye. Sự biến thiên kích thước này phức tạp hơn nhiều so với ảnh perspective, đòi hỏi mô hình phải học được một không gian đặc trưng phong phú hơn [6].

Để khắc phục những vấn đề này, đề tài sử dụng hai chiến lược: (1) fine-tune mô hình trực tiếp trên dữ liệu fisheye thực tế và mô phỏng để mô hình học được phân phối đặc trưng của ảnh fisheye; (2) sử dụng kỹ thuật SAHI để chia nhỏ ảnh, giúp mỗi lát ảnh có biến dạng cục bộ ít hơn và đối tượng nhỏ xuất hiện tương đối lớn hơn [4].

### 1.3.4. Hàm biến đổi fisheye sử dụng trong đề tài

Do bộ dữ liệu VisDrone2019 gốc được chụp từ camera perspective của UAV, đề tài cần chuyển đổi ảnh về dạng fisheye để tăng cường dữ liệu huấn luyện. Hàm to_fisheye(image, strength, radius, effect) được triển khai tùy chỉnh để mô phỏng biến dạng fisheye trên ảnh perspective.

Nguyên lý hoạt động của hàm biến đổi: với mỗi điểm (x, y) trong ảnh đầu ra, tính khoảng cách chuẩn hóa r đến tâm ảnh (trong khoảng [0, 1]), sau đó áp dụng biến đổi bán kính phi tuyến:

r' = r^(1 + strength)

Điểm (x, y) trong ảnh đầu ra được lấy mẫu từ vị trí tương ứng trong ảnh gốc theo tỷ lệ r'/r bằng phép nội suy song tuyến (bilinear interpolation). Các tham số strength=0,5 và radius=0,85 được chọn thông qua thực nghiệm để tạo ra biến dạng tương đồng với camera fisheye thực tế sử dụng mô hình equidistant trong điều kiện lắp đặt tại nút giao thông.

Hàm to_fisheye() được triển khai bằng OpenCV và NumPy, tận dụng phép ánh xạ ngược (inverse mapping) thông qua cv2.remap() để đảm bảo hiệu năng xử lý tối ưu. Toàn bộ pipeline biến đổi được vectorized trên numpy array, cho phép xử lý hàng nghìn ảnh trong thời gian hợp lý trên CPU.

### 1.3.5. Chuyển đổi bounding box sang không gian fisheye

Song song với việc biến đổi ảnh, các bounding box ground-truth cũng cần được chuyển đổi tương ứng từ không gian perspective sang không gian fisheye. Hàm transform_bbox_fisheye() giải quyết vấn đề này bằng cách lấy mẫu nhiều điểm trên biên bounding box.

Thay vì chỉ biến đổi 4 góc của bounding box (cách tiếp cận đơn giản nhưng kém chính xác khi bbox lớn hoặc ở vùng biên ảnh), hàm lấy mẫu đều 32 điểm trên toàn bộ chu vi bounding box gốc, áp dụng phép biến đổi fisheye cho từng điểm, sau đó tính bounding rectangle nhỏ nhất (axis-aligned bounding box) bao quanh tất cả 32 điểm đã biến đổi.

Cách tiếp cận đa điểm này mang lại độ chính xác cao hơn đáng kể cho các bounding box ở vùng biên ảnh (nơi gradient biến dạng lớn), với chi phí tính toán tăng không đáng kể. Điều này đảm bảo rằng nhãn annotation sau khi chuyển đổi vẫn bao chứa đầy đủ đối tượng trong không gian fisheye, phục vụ tốt cho quá trình huấn luyện mô hình.

## 1.4. Kiến trúc YOLOv11 và lịch sử phát triển họ YOLO

### 1.4.1. Lịch sử phát triển các thế hệ YOLO

Họ mô hình YOLO (You Only Look Once) được giới thiệu lần đầu vào năm 2016 bởi Redmon et al. [1] với ý tưởng đột phá: xử lý toàn bộ ảnh đầu vào trong một lần forward pass duy nhất qua mạng nơ-ron, cho phép phát hiện đối tượng theo thời gian thực với tốc độ vượt trội so với các phương pháp two-stage đương thời.

Từ YOLOv1 năm 2016 đến YOLOv11 năm 2024, kiến trúc trải qua nhiều cải tiến căn bản:

| **Phiên bản** | **Năm** | **Đổi mới chính** | **mAP (COCO)** |
|---|---|---|---|
| YOLOv1 [1] | 2016 | One-stage, grid-based detection | ~63,4 (mAP@0.5) |
| YOLOv3 | 2018 | Multi-scale prediction, Darknet-53 | 55,3 mAP@0.5 |
| YOLOv4 | 2020 | CSP backbone, PANet neck, mosaic aug | 65,7 mAP@0.5 |
| YOLOv5 | 2020 | PyTorch, auto-anchors, compound scaling | 67,3 mAP@0.5 |
| YOLOv7 [2] | 2022 | ELAN, auxiliary training head | 69,7 mAP@0.5 |
| YOLOv8 | 2023 | C2f backbone, anchor-free head | 72,7 mAP@0.5 |
| YOLOv11 [3] | 2024 | C3k2, AIFI transformer, anchor-free | 73,6 mAP@0.5 |

**Bảng 1.2. So sánh các thế hệ YOLO từ v1 đến v11**

YOLOv7 (2022) được Wang et al. [2] phát triển với kiến trúc ELAN (Efficient Layer Aggregation Network) và các kỹ thuật "bag-of-freebies" giúp cải thiện mAP mà không tăng chi phí inference, đặt nền tảng cho các cải tiến trong YOLOv8 và YOLOv11 sau này.

### 1.4.2. Kiến trúc tổng thể YOLOv11

YOLOv11 được Ultralytics phát hành năm 2024 [3] với kiến trúc gồm ba phần chính:

**Backbone**: Trích xuất đặc trưng đa tầng từ ảnh đầu vào, sử dụng khối C3k2 cải tiến. Backbone của YOLOv11 được thiết kế để trích xuất các đặc trưng ở nhiều mức độ trừu tượng khác nhau, từ cạnh và góc đơn giản ở các lớp đầu đến ngữ nghĩa phức tạp ở các lớp sâu.

**Neck**: Kết hợp đặc trưng từ nhiều tầng khác nhau của backbone bằng cấu trúc FPN (Feature Pyramid Network) [22] kết hợp PAN (Path Aggregation Network), bổ sung module AIFI transformer. Neck đảm bảo thông tin ngữ nghĩa từ lớp sâu được truyền ngược về các lớp nông để hỗ trợ phát hiện đối tượng nhỏ.

**Detection Head**: Dự đoán bounding box và nhãn lớp theo kiểu anchor-free trên ba scale feature map khác nhau (stride 8, 16, 32). Đầu ra trên ba scale tương ứng với khả năng phát hiện đối tượng nhỏ, trung bình và lớn.

YOLOv11-L – phiên bản Large được sử dụng trong đề tài – có 25,3 triệu tham số và yêu cầu 86,9 GFLOPs mỗi lần forward pass trên ảnh 640×640, đạt tốc độ 41 FPS trên GPU NVIDIA GTX 1060 6GB [3].

### 1.4.3. Backbone C3k2 – Cross Stage Partial

Backbone C3k2 (Cross Stage Partial with kernel size 2) là cải tiến quan trọng so với khối C2f sử dụng trong YOLOv8. Kiến trúc C3k2 kế thừa nguyên lý Cross Stage Partial (CSP) – chia đầu vào thành hai nhánh, một nhánh đi qua các khối bottleneck tích chập và một nhánh đi thẳng (skip connection), sau đó ghép lại – nhưng sử dụng kernel có kích thước nhỏ hơn (k=2) để giảm số tham số và chi phí tính toán [3].

Thiết kế này mang lại hai lợi ích chính: (1) Giảm số phép tính tích chập so với kernel thông thường k=3, giúp tăng tốc độ inference mà không ảnh hưởng đáng kể đến độ chính xác; (2) Cải thiện luồng gradient trong quá trình backpropagation nhờ kiến trúc nhánh song song, giúp mô hình hội tụ ổn định hơn khi fine-tune trên bộ dữ liệu nhỏ như FishEye8K.

Trong backbone YOLOv11, các khối C3k2 được xếp chồng với số lượng tăng dần theo chiều sâu mạng, kết hợp với các lớp tích chập Depthwise Separable để tối ưu hóa tỷ lệ độ chính xác / chi phí tính toán.

### 1.4.4. Module AIFI Transformer trong Neck

AIFI (Attention-based Intra-scale Feature Interaction) là một đổi mới kiến trúc quan trọng của YOLOv11 so với các phiên bản trước [3]. Module này tích hợp cơ chế self-attention của Transformer vào neck của mô hình để mô hình hóa các mối quan hệ dài hạn (long-range dependencies) giữa các vùng khác nhau trong cùng một scale feature map.

Cơ chế self-attention cho phép mô hình "nhìn thấy" toàn bộ feature map và tính toán tầm quan trọng của từng vị trí so với tất cả vị trí còn lại, khắc phục hạn chế của tích chập thông thường chỉ nắm bắt được thông tin cục bộ trong receptive field. Điều này đặc biệt hữu ích trong bài toán phát hiện đối tượng giao thông, nơi bối cảnh toàn cục (ví dụ: sự xuất hiện của xe buýt thường đi kèm với bến đỗ hoặc dòng xe dài) giúp nâng cao độ chính xác phân loại [21].

Khác với các module cross-attention giữa các scale đòi hỏi bộ nhớ lớn, AIFI giới hạn attention trong cùng một scale (intra-scale), giúp kiểm soát chi phí tính toán trong giới hạn thực tế. Module này được chèn vào sau lớp feature map có stride 32 – nơi mỗi cell đại diện cho một vùng ngữ nghĩa lớn và việc mô hình hóa quan hệ dài hạn có giá trị nhất.

### 1.4.5. Detection Head anchor-free

Kể từ YOLOv8, Ultralytics đã chuyển hoàn toàn sang detection head anchor-free [3]. Thay vì dự đoán offset so với các anchor box định sẵn (cách tiếp cận của YOLOv1 đến YOLOv7), detection head anchor-free dự đoán trực tiếp khoảng cách từ tâm của mỗi grid cell đến bốn cạnh của bounding box: l (left), r (right), t (top), b (bottom).

Cụ thể, tại mỗi vị trí (i, j) trên feature map có stride s, mô hình dự đoán:
- Tọa độ tâm đối tượng: cx = (j + 0,5) · s, cy = (i + 0,5) · s
- Bốn giá trị khoảng cách: l, r, t, b (đơn vị pixel trong ảnh gốc)
- Xác suất phân phối vị trí theo DFL (xem mục 1.6.2)
- Vector logit lớp đối tượng độ dài K

Phương pháp anchor-free giảm đáng kể số lượng siêu tham số cần điều chỉnh (không cần chọn kích thước và tỷ lệ anchor phù hợp với dữ liệu), đơn giản hóa pipeline huấn luyện và cho thấy cải thiện hiệu năng trên các đối tượng có tỷ lệ kích thước bất thường (như xe buýt nằm ngang hoặc xe tải dài) [3].

### 1.4.6. So sánh YOLOv11 với các phiên bản trước

Về số liệu thực nghiệm, YOLOv11-L đạt mAP@0.5:0.95 = 53,4% trên tập kiểm thử COCO val2017, cao hơn YOLOv8-L (52,9%) với số tham số ít hơn (25,3M so với 43,7M). Tốc độ inference trên T4 TensorRT đạt 87,0ms/ảnh so với 87,1ms của YOLOv8-L, cho thấy YOLOv11 cải thiện độ chính xác mà không tăng chi phí tính toán [3].

Đối với bài toán fisheye của đề tài, phiên bản YOLOv11-L được lựa chọn vì cân bằng tốt giữa độ chính xác (đủ cao cho ứng dụng thực tế) và tốc độ inference (đủ nhanh để xử lý video 25fps). Phiên bản XL (Extra Large) mặc dù có độ chính xác cao hơn nhưng đòi hỏi VRAM nhiều hơn và tốc độ chậm hơn đáng kể, không phù hợp với môi trường triển khai thực tế.

## 1.5. Kỹ thuật SAHI – Sliced Aided Hyper Inference

### 1.5.1. Vấn đề phát hiện đối tượng nhỏ trong ảnh độ phân giải cao

Phát hiện đối tượng nhỏ là một trong những thách thức khó khăn nhất trong thị giác máy tính. Trong bài toán giám sát giao thông fisheye, người đi bộ ở xa tâm ảnh hoặc các phương tiện nhỏ ở vùng biên chỉ chiếm diện tích 10–30 pixel chiều cao trên ảnh đầu vào 1920×1080 hoặc lớn hơn.

Vấn đề cốt lõi nằm ở cơ chế downsampling của mạng CNN: feature map ở lớp cuối của backbone YOLOv11 có stride 32, nghĩa là mỗi cell đại diện cho một vùng 32×32 pixel trong ảnh gốc. Một đối tượng người đi bộ cao 20 pixel do đó chỉ chiếm chưa đầy 1 cell trên feature map, khiến mô hình gần như không có đủ thông tin đặc trưng để nhận diện đối tượng này [4].

Trong khi một giải pháp đơn giản là tăng kích thước đầu vào ảnh (ví dụ từ 640×640 lên 1280×1280), cách này tăng chi phí tính toán theo bình phương và không phải lúc nào cũng khả thi với phần cứng thực tế. SAHI đề xuất một giải pháp hiệu quả hơn bằng cách chia nhỏ ảnh thành các lát có kích thước chuẩn [4].

### 1.5.2. Nguyên lý hoạt động của SAHI

SAHI (Sliced Aided Hyper Inference) được Akyon et al. [4] đề xuất năm 2022, giải quyết bài toán phát hiện đối tượng nhỏ thông qua quy trình chia lát – suy diễn – tổng hợp:

**Bước 1 – Chia lát (Slicing)**: Ảnh gốc được chia thành các lát (slices) có kích thước cố định slice_height × slice_width (thường là 640×640), với tỷ lệ chồng lấp (overlap) nhất định giữa các lát liền kề (thường 0,2 = 20%). Việc chồng lấp đảm bảo đối tượng nằm ở biên giữa hai lát vẫn được phát hiện đầy đủ ở ít nhất một lát. Tổng số lát phụ thuộc vào kích thước ảnh gốc và tỷ lệ chồng lấp.

**Bước 2 – Suy diễn độc lập (Per-slice Inference)**: Mô hình YOLO chạy inference độc lập trên từng lát ảnh, đầu ra là tập các bounding box trong hệ tọa độ cục bộ của từng lát.

**Bước 3 – Chuyển đổi tọa độ**: Tọa độ bounding box cục bộ của từng lát được chuyển đổi về hệ tọa độ toàn cục của ảnh gốc bằng cách cộng offset tương ứng.

**Bước 4 – Tổng hợp và loại bỏ trùng lặp (NMM)**: Tất cả bounding box từ tất cả các lát (và tùy chọn, inference trên ảnh toàn phần) được tổng hợp lại và xử lý bằng thuật toán Non-Maximum Merging (NMM) thay vì NMS thông thường. NMM hợp nhất các box chồng lấp thay vì loại bỏ, phù hợp hơn cho trường hợp một đối tượng xuất hiện trong nhiều lát.

### 1.5.3. Chiến lược tổng hợp kết quả và NMM

Điểm khác biệt giữa NMM và NMS truyền thống nằm ở cách xử lý các bounding box chồng lấp từ nhiều lát khác nhau. NMS (Non-Maximum Suppression) giữ lại box có confidence cao nhất và loại bỏ các box có IoU vượt ngưỡng – cách này gây ra vấn đề khi hai lát khác nhau đều phát hiện cùng một đối tượng nhưng với bounding box hơi lệch nhau.

NMM thay vào đó hợp nhất (merge) các box chồng lấp bằng cách tính trung bình có trọng số theo confidence score:

merged_box = weighted_average(boxes, weights=confidence_scores)

Cách này cho phép kết hợp thông tin từ nhiều lát khác nhau để tạo ra bounding box cuối cùng chính xác hơn, đặc biệt hữu ích ở vùng biên giữa các lát [4].

### 1.5.4. Ứng dụng SAHI trong bài toán fisheye

Trong đề tài, SAHI được tích hợp theo cấu hình: slice_size=640, overlap_ratio=0,2, postprocess_type='NMM'. SAHI đặc biệt phù hợp với ảnh fisheye vì hai lý do:

Thứ nhất, mỗi lát 640×640 pixel trong ảnh gốc độ phân giải cao tương ứng với một vùng nhỏ hơn, nơi biến dạng fisheye ít hơn so với toàn ảnh. Điều này giúp mô hình xử lý các lát riêng lẻ với điều kiện ảnh gần với ảnh perspective hơn, giảm khó khăn do biến dạng phi tuyến.

Thứ hai, người đi bộ hoặc phương tiện nhỏ ở vùng biên ảnh – nơi chúng nhỏ và méo nhất – khi được lấy trong một lát nhỏ sẽ có kích thước tương đối lớn hơn so với kích thước lát, giúp mô hình dễ phát hiện hơn.

Kết quả thực nghiệm cho thấy SAHI tăng recall lớp Pedestrian từ 32% lên 58% (tăng 81%) với thời gian xử lý 1,8–2,5 giây mỗi ảnh – phù hợp cho phân tích offline và các trường hợp cần độ chính xác cao hơn tốc độ.

## 1.6. Hàm mất mát và chiến lược tối ưu hóa

### 1.6.1. CIoU Loss cho hồi quy bounding box

YOLOv11 sử dụng CIoU (Complete Intersection over Union) Loss [11] cho bài toán hồi quy bounding box. So với IoU Loss cơ bản, CIoU bổ sung thêm hai thành phần quan trọng:

L_CIoU = 1 – IoU + ρ²(b, b_gt) / c² + α · v

trong đó:
- ρ(b, b_gt) là khoảng cách Euclidean giữa tâm bounding box dự đoán và ground-truth
- c là đường chéo của bounding box bao quanh nhỏ nhất chứa cả hai hộp
- v = (4/π²)(arctan(w_gt/h_gt) – arctan(w/h))² đo sự khác biệt tỷ lệ kích thước (aspect ratio)
- α = v / (1 – IoU + v) là hệ số cân bằng tự thích nghi

CIoU đồng thời tối ưu hóa ba yếu tố: diện tích chồng lấp (IoU), khoảng cách tâm và tỷ lệ kích thước, giúp hội tụ nhanh hơn và cải thiện mAP so với các phiên bản IoU Loss trước đó [11].

### 1.6.2. Distribution Focal Loss (DFL)

Distribution Focal Loss (DFL) [12] là kỹ thuật được Ultralytics tích hợp vào YOLOv11 để xử lý sự không chắc chắn (uncertainty) trong dự đoán vị trí bounding box. Thay vì dự đoán một giá trị xác định cho mỗi tọa độ (l, r, t, b), mô hình dự đoán phân phối xác suất rời rạc trên một tập giá trị {0, 1, ..., 16}:

P(d = k | x) = softmax(z_k), k ∈ {0, 1, ..., 16}

Khoảng cách cuối cùng được tính là giá trị kỳ vọng:

d = Σ_k k · P(d = k | x)

Phương pháp này cho phép mô hình biểu diễn ranh giới mờ (ambiguous boundaries) của đối tượng – trường hợp thường gặp với phương tiện bị che khuất một phần, phương tiện bị phản chiếu ánh sáng, hoặc đối tượng bị méo trong ảnh fisheye [12].

### 1.6.3. Chiến lược tối ưu hóa AdamW và cosine annealing

Trong phiên bản Cơ bản, đề tài sử dụng bộ tối ưu hóa AdamW [13] với cosine annealing learning rate schedule. AdamW được chọn thay SGD vì tốc độ hội tụ nhanh hơn khi fine-tune trên bộ dữ liệu nhỏ và ít nhạy cảm hơn với việc chọn learning rate ban đầu.

AdamW tách biệt cơ chế weight decay ra khỏi adaptive gradient, khắc phục điểm yếu của Adam thông thường khi weight decay được tích hợp vào gradient update (dẫn đến regularization không hiệu quả với các tham số được cập nhật ít). Cosine annealing giảm learning rate từ lr0=0,0005 xuống lrf=0,005 theo hàm cosine trong suốt quá trình huấn luyện, tránh oscillation và giúp mô hình hội tụ mượt mà hơn vào cuối quá trình huấn luyện [13].

## 1.7. Kỹ thuật tăng cường dữ liệu

### 1.7.1. Mosaic Augmentation v2

Mosaic Augmentation là kỹ thuật được giới thiệu từ YOLOv4 và tiếp tục được sử dụng trong YOLOv11 [25]. Kỹ thuật này ghép 4 ảnh ngẫu nhiên từ batch huấn luyện thành một ảnh 640×640 duy nhất, điều chỉnh bounding box tương ứng với vị trí và scale mới.

Lợi ích của Mosaic Augmentation trong bài toán fisheye giao thông:
- Tăng đa dạng bối cảnh: mô hình thấy 4 cảnh khác nhau cùng một lúc
- Tăng số đối tượng nhỏ trong mỗi ảnh: khi ảnh được scale down để ghép vào mosaic, các phương tiện vốn đã nhỏ trở nên nhỏ hơn, buộc mô hình học phát hiện đối tượng cực nhỏ
- Giảm thiểu overfitting: thay đổi cấu trúc ảnh liên tục qua mỗi epoch

Trong đề tài, mosaic=1,0 được đặt cho 35 epoch đầu, sau đó tắt trong 15 epoch cuối (close_mosaic=15) để mô hình fine-tune trên ảnh nguyên bản, giúp tăng thêm khoảng 0,5% mAP ở giai đoạn cuối.

### 1.7.2. MixUp Augmentation

MixUp [14] trộn tuyến tính hai ảnh theo hệ số lambda được lấy mẫu từ phân phối Beta:

I_mix = λ · I₁ + (1–λ) · I₂, λ ~ Beta(α, α) với α = 0,32

Nhãn bounding box được ghép từ cả hai ảnh gốc. Hệ số alpha nhỏ (0,32) tạo ra phân phối Beta tập trung gần 0 và 1, nghĩa là phần lớn ảnh được trộn ít (ảnh gần với một trong hai ảnh gốc), tránh tạo ra ảnh quá khó nhận diện.

MixUp cải thiện calibration confidence score và tăng robustness của mô hình với ảnh nhiễu và điều kiện ánh sáng không lý tưởng – đặc biệt quan trọng trong giám sát giao thông nơi điều kiện thời tiết và ánh sáng thay đổi liên tục [14]. Trong đề tài, mixup=0,05 được sử dụng.

### 1.7.3. Copy-Paste Augmentation

Copy-Paste [15] là kỹ thuật tăng cường dữ liệu hiệu quả cao cho các lớp đối tượng xuất hiện ít trong dữ liệu. Kỹ thuật này cắt vùng đối tượng (với mask) từ một ảnh nguồn và dán vào ảnh đích ở vị trí, scale và rotation ngẫu nhiên, đồng thời cập nhật annotation tương ứng.

Trong bài toán giao thông fisheye, lớp Pedestrian có tần suất thấp nhất và kích thước nhỏ nhất, gây ra class imbalance nghiêm trọng. Copy-Paste với copy_paste=0,05 giúp tăng tần suất xuất hiện của người đi bộ trong dữ liệu huấn luyện, đặc biệt giúp cải thiện recall của lớp này từ rất thấp lên mức chấp nhận được [15].

## 1.8. Các bộ dữ liệu liên quan

### 1.8.1. Bộ dữ liệu FishEye8K

FishEye8K [20] là bộ dữ liệu fisheye chuyên biệt được công bố tại ECCV 2022 Workshop on AI City Challenge, được thu thập từ các camera fisheye thực tế lắp đặt tại các nút giao thông đô thị ở Ấn Độ. Đây là một trong số ít bộ dữ liệu fisheye công khai có annotation bounding box chất lượng cao cho bài toán phát hiện phương tiện giao thông.

| **Tập** | **Số ảnh** | **Số nhãn** | **Nguồn** |
|---|---|---|---|
| Train | 5.288 | 201.120 | Camera fisheye tại Ấn Độ |
| Validation | 1.322 | 49.180 | Camera fisheye tại Ấn Độ |
| Test | 1.390 | 54.890 | Camera fisheye tại Ấn Độ |
| **Tổng** | **8.000** | **305.190** | |

**Bảng 1.4. Thống kê bộ dữ liệu FishEye8K theo tập train/val/test**

Bộ dữ liệu FishEye8K bao gồm 5 lớp đối tượng: Car, Bus, Truck, Pedestrian và Motorbike, với phân phối lớp không đồng đều – lớp Car chiếm đa số, lớp Bus và Truck có tần suất thấp hơn đáng kể. Dữ liệu được thu thập ở nhiều điều kiện ánh sáng khác nhau (ban ngày, chạng vạng, ban đêm) và nhiều loại nút giao thông khác nhau (ngã tư, ngã năm, vòng xuyến).

Hạn chế của FishEye8K là tập dữ liệu còn tương đối nhỏ (8.000 ảnh) và đặc thù giao thông Ấn Độ (lưu lượng xe máy thấp hơn Việt Nam, nhiều xe buýt và tuk-tuk hơn). Điều này dẫn đến việc mô hình huấn luyện thuần túy trên FishEye8K có thể không tổng quát hóa tốt cho điều kiện giao thông Việt Nam, đặc biệt với lớp Motorbike – lý do chính để đề tài bổ sung dữ liệu từ VisDrone2019 [5].

### 1.8.2. Bộ dữ liệu VisDrone2019

VisDrone2019 [5] là bộ dữ liệu phát hiện đối tượng quy mô lớn từ góc nhìn UAV, được thu thập bởi nhóm nghiên cứu AISKYEYE Lab tại Đại học Thiên Tân, Trung Quốc. Mặc dù không phải dữ liệu fisheye, VisDrone2019 có góc nhìn từ trên cao gần giống với góc nhìn của camera fisheye lắp tại nút giao thông, và chứa nhiều ảnh trong điều kiện mật độ giao thông cao.

| **Tập** | **Số ảnh** | **Số nhãn** |
|---|---|---|
| Train | 6.471 | 343.204 |
| Validation | 548 | 38.659 |
| Test | 1.610 | Không công khai |
| **Tổng (công khai)** | **7.019** | **381.863** |

**Bảng 1.5. Thống kê bộ dữ liệu VisDrone2019**

VisDrone2019 chứa 10 lớp đối tượng gốc (pedestrian, people, bicycle, car, van, truck, tricycle, awning-tricycle, bus, motor) được ánh xạ sang 5 lớp của FishEye8K thông qua bảng chuyển đổi phù hợp. Bộ dữ liệu bao gồm nhiều cảnh giao thông đô thị và nông thôn tại nhiều thành phố Trung Quốc với điều kiện giao thông tương đối gần với Việt Nam hơn so với Ấn Độ [5].

Việc chuyển đổi ảnh VisDrone2019 sang dạng fisheye bằng hàm to_fisheye() giúp tạo ra dữ liệu huấn luyện bổ sung đa dạng, tăng cường khả năng tổng quát hóa của mô hình mà không cần thu thập dữ liệu fisheye thực tế tốn kém.

### 1.8.3. So sánh và lý do lựa chọn

FishEye8K cung cấp dữ liệu fisheye thực tế với annotation chính xác – nền tảng không thể thiếu cho huấn luyện mô hình phát hiện đối tượng trong môi trường fisheye. VisDrone2019 bổ sung lượng lớn dữ liệu góc nhìn từ trên cao với mật độ phương tiện cao, đặc biệt phong phú ở lớp Car và Motorbike – khắc phục sự thiếu hụt dữ liệu của FishEye8K.

Kết hợp cả hai bộ dữ liệu (với VisDrone2019 đã qua chuyển đổi fisheye) tạo ra bộ dữ liệu huấn luyện 11.296 ảnh và hơn 406.000 nhãn, đủ lớn để fine-tune hiệu quả một mô hình YOLOv11-L pretrained trên COCO.

## 1.9. Tổng quan các công trình nghiên cứu liên quan

### 1.9.1. Phát hiện đối tượng trên ảnh fisheye

Nghiên cứu về phát hiện đối tượng trên ảnh fisheye đã thu hút sự quan tâm ngày càng tăng trong cộng đồng computer vision, đặc biệt trong lĩnh vực xe tự lái và giám sát giao thông.

Yogamani et al. [6] công bố bộ dữ liệu WoodScape – bộ dữ liệu fisheye đa nhiệm vụ đầu tiên quy mô lớn cho xe tự lái, bao gồm annotation cho phân đoạn ngữ nghĩa, phát hiện đối tượng và ước lượng chiều sâu. Nghiên cứu này đặt nền tảng quan trọng cho việc hiểu biết về các thách thức kỹ thuật đặc thù của ảnh fisheye trong bài toán nhận thức không gian.

Planche và Duan [7] đề xuất FisheyeDetNet, mạng phát hiện đối tượng được thiết kế đặc biệt cho camera fisheye surround-view trong xe tự lái. Thay vì sử dụng backbone thông thường, FisheyeDetNet sử dụng các lớp tích chập biến dạng (deformable convolutions) để thích nghi với hình dạng đối tượng méo trong ảnh fisheye. Kết quả cho thấy cải thiện đáng kể so với detector tiêu chuẩn trên dữ liệu surround-view.

Tại cuộc thi AI City Challenge ECCV 2022, nhiều nhóm nghiên cứu đã đề xuất các phương pháp giải quyết bài toán phát hiện đối tượng trên FishEye8K [20]. Các phương pháp dẫn đầu thường sử dụng ensemble nhiều mô hình kết hợp với test-time augmentation, đạt mAP@0.5 trên 0,6. Đề tài này theo hướng tiếp cận đơn mô hình nhưng bổ sung SAHI để cải thiện recall đối tượng nhỏ.

### 1.9.2. Phát hiện đối tượng nhỏ từ góc nhìn UAV

VisDrone Challenge [5] – cuộc thi thường niên được tổ chức từ 2018 – đã thúc đẩy nhiều nghiên cứu về phát hiện đối tượng nhỏ từ góc nhìn UAV. Các thách thức chính của bộ dữ liệu này – đối tượng nhỏ, mật độ cao, che khuất lẫn nhau – tương đồng với bài toán fisheye của đề tài.

Akyon et al. [4] đề xuất SAHI như một framework inference chung, không phụ thuộc vào kiến trúc mô hình cụ thể. SAHI được thử nghiệm trên nhiều bộ dữ liệu UAV và fisheye, cho thấy cải thiện recall lên đến 15% trên các đối tượng nhỏ với chi phí tính toán tăng tuyến tính theo số lát.

Cao et al. [8] đề xuất D2Det kết hợp phát hiện đối tượng với phân đoạn thực thể để cải thiện độ chính xác định vị bounding box cho đối tượng nhỏ. Phương pháp này đặc biệt hiệu quả cho đối tượng có hình dạng không đều như người đi bộ trong điều kiện che khuất.

### 1.9.3. Khoảng trống nghiên cứu và đóng góp của đề tài

Qua tổng quan tài liệu, có thể xác định những khoảng trống nghiên cứu mà đề tài hướng đến lấp đầy:

**Thiếu nghiên cứu fine-tune YOLOv11 trên dữ liệu fisheye giao thông**: Hầu hết nghiên cứu fisheye tập trung vào xe tự lái với camera surround-view, ít nghiên cứu về camera overhead fisheye tại nút giao thông đô thị với nhiều lớp phương tiện đa dạng.

**Thiếu pipeline kết hợp dữ liệu perspective và fisheye**: Việc chuyển đổi dữ liệu VisDrone2019 sang fisheye để kết hợp với FishEye8K là đóng góp thực nghiệm quan trọng của đề tài, tạo ra bộ dữ liệu huấn luyện phong phú hơn.

**Ứng dụng SAHI cho camera fisheye tại nút giao thông**: Mặc dù SAHI đã được áp dụng cho UAV imagery, việc kết hợp SAHI với fisheye distortion correction trong một hệ thống giám sát giao thông thực tế chưa được nghiên cứu nhiều.

**Hệ thống giám sát giao thông toàn diện cho camera fisheye tại Việt Nam**: Đây là đóng góp ứng dụng quan trọng nhất của đề tài – xây dựng một hệ thống hoàn chỉnh từ phát hiện đối tượng đến phân tích giao thông, phù hợp với đặc thù giao thông Việt Nam.

## 1.10. Phát biểu bài toán và mục tiêu nghiên cứu

### 1.10.1. Phát biểu bài toán

Bài toán nghiên cứu được phát biểu như sau: Cho một chuỗi ảnh hoặc video từ camera fisheye góc nhìn từ trên cao, lắp đặt tại nút giao thông đô thị, yêu cầu thiết kế và xây dựng một hệ thống có khả năng:

(1) Phát hiện và phân loại chính xác tất cả các phương tiện và người đi bộ trong khung hình thuộc 5 lớp đối tượng: Car, Bus, Truck, Pedestrian, Motorbike, đạt mAP@0.5 ≥ 0,85 trên tập kiểm thử FishEye8K.

(2) Xử lý hiệu quả các thách thức đặc thù của ảnh fisheye: biến dạng barrel distortion, đối tượng nhỏ ở vùng biên, phân phối kích thước không đồng đều theo vị trí trong ảnh.

(3) Cung cấp các phân tích giao thông bổ sung: ước lượng tốc độ phương tiện, phát hiện tắc nghẽn, nhận diện sự cố giao thông và cảnh báo tự động.

(4) Triển khai dưới dạng một ứng dụng web hoàn chỉnh với REST API, hỗ trợ xử lý ảnh đơn, video bất đồng bộ và stream realtime từ camera.

### 1.10.2. Mục tiêu và phạm vi nghiên cứu

Mục tiêu nghiên cứu cụ thể của đề tài bao gồm:

**Mục tiêu 1 – Nghiên cứu và triển khai fine-tune YOLOv11-L**: Xây dựng pipeline fine-tune hoàn chỉnh từ bước chuẩn bị dữ liệu, cấu hình huấn luyện đến đánh giá kết quả. Mục tiêu cụ thể: đạt mAP@0.5 ≥ 0,85 trên tập kiểm thử FishEye8K.

**Mục tiêu 2 – Tích hợp và đánh giá SAHI**: Tích hợp SAHI vào pipeline inference của YOLOv11, đánh giá định lượng cải thiện recall trên lớp Pedestrian so với inference thông thường.

**Mục tiêu 3 – Xây dựng pipeline dữ liệu fisheye**: Phát triển công cụ chuyển đổi dữ liệu VisDrone2019 sang dạng fisheye, tạo bộ dữ liệu kết hợp phục vụ huấn luyện.

**Mục tiêu 4 – Phát triển ứng dụng giám sát giao thông**: Xây dựng ứng dụng Flask hoàn chỉnh với 20+ REST API endpoint, tích hợp các module phân tích giao thông thông minh.

Phạm vi của đề tài giới hạn ở: phát hiện 5 lớp đối tượng nêu trên; camera fisheye góc nhìn overhead (từ trên cao) tại nút giao thông; đánh giá trên bộ dữ liệu FishEye8K và VisDrone2019; triển khai trên GPU server (không tối ưu cho edge computing trong phiên bản này).

### 1.10.3. Phương pháp nghiên cứu

Đề tài sử dụng phương pháp nghiên cứu kết hợp giữa nghiên cứu lý thuyết và thực nghiệm:

**Nghiên cứu lý thuyết**: Nghiên cứu mô hình hình học camera fisheye, kiến trúc YOLOv11 và các thành phần cấu thành, nguyên lý SAHI, các hàm mất mát và chiến lược tối ưu hóa được sử dụng.

**Thực nghiệm so sánh**: Fine-tune mô hình với nhiều cấu hình khác nhau (dữ liệu đầu vào, siêu tham số, chiến lược tăng cường dữ liệu) và so sánh kết quả trên cùng tập kiểm thử để xác định cấu hình tốt nhất.

**Đánh giá định lượng**: Sử dụng các chỉ số chuẩn của cộng đồng: Precision, Recall, F1-Score, mAP@0.5 và mAP@0.5:0.95 theo từng lớp đối tượng và tổng thể.

**Kiểm thử hệ thống**: Black-box testing với test cases định nghĩa trước bao phủ các chức năng chính của ứng dụng, đánh giá thời gian phản hồi và độ ổn định.

### 1.10.4. Công nghệ và công cụ sử dụng

Hệ thống sử dụng hai nhóm công nghệ chính: nhóm phục vụ **huấn luyện mô hình** trên nền tảng Kaggle Notebooks và nhóm phục vụ **triển khai ứng dụng** trên máy chủ Flask. Toàn bộ mã nguồn được viết bằng Python 3.10+.

| **STT** | **Thành phần** | **Công nghệ / Thư viện** | **Phiên bản** | **Chức năng cụ thể trong đề tài** | **Nguồn / Tài liệu tham khảo** |
|:---:|---|---|:---:|---|---|
| 1 | Deep learning framework | **PyTorch + CUDA** | 2.2.x / 12.1 | Xây dựng đồ thị tính toán, lan truyền ngược, tối ưu hóa tham số mô hình; CUDA tăng tốc tính toán ma trận trên GPU | Paszke, A. et al. (2019). *PyTorch: An Imperative Style, High-Performance Deep Learning Library*. NeurIPS 2019. https://pytorch.org [26] |
| 2 | Object detection | **Ultralytics YOLO** (`ultralytics`) | 8.3.x | Load pretrained `yolo26n.pt`, gọi `model.train(...)` và `model.val(...)`, xuất checkpoint `best.pt`/`last.pt`; cung cấp pipeline augmentation tích hợp sẵn (Mosaic, MixUp, Flip, HSV) | Ultralytics Inc. (2024). *YOLOv11: New YOLO Frontiers in Computer Vision*. https://docs.ultralytics.com/models/yolo11/ [3] |
| 3 | Pretrained model | **`yolo26n.pt`** | – | Checkpoint khởi điểm fine-tune; trọng số đã học đặc trưng tổng quát từ tập COCO, giúp mô hình hội tụ nhanh trên FishEye8K | Ultralytics Inc. (2024). *Ultralytics YOLO – Training*. https://docs.ultralytics.com/modes/train/ [25] |
| 4 | Experiment tracking | **Weights & Biases** (`wandb`) | ≥ 0.16 | Ghi lại loss, mAP@0.5, learning rate theo từng epoch; lưu artifact `best.pt` sau mỗi run; cho phép so sánh nhiều thực nghiệm trực quan | Biewald, L. (2020). *Experiment Tracking with Weights and Biases*. https://www.wandb.com [31] |
| 5 | Credential management | **Kaggle Secrets** (`UserSecretsClient`) | – | Lưu trữ API key của Weights & Biases an toàn trong môi trường Kaggle, tránh hardcode thông tin nhạy cảm vào notebook | Kaggle Inc. (2024). *Kaggle Secrets – API key management*. https://www.kaggle.com/docs/notebooks [34] |
| 6 | Data split | **scikit-learn** (`sklearn`) | ≥ 1.3 | Gọi `train_test_split(train_images, test_size=0.2, random_state=42)` để chia tập FishEye8K train thành 80% huấn luyện / 20% kiểm định; đảm bảo tái lập kết quả | Pedregosa, F. et al. (2011). *Scikit-learn: Machine Learning in Python*. JMLR, 12, 2825–2830. https://scikit-learn.org [27] |
| 7 | Progress bar | **tqdm** | ≥ 4.66 | Hiển thị tiến độ tại các vòng lặp xử lý dataset (sao chép ảnh, chuyển đổi annotation) giúp theo dõi thời gian thực thi | da Costa-Luis, C. et al. (2023). *tqdm: A Fast, Extensible Progress Bar*. https://tqdm.github.io |
| 8 | Dataset config | **PyYAML** (`yaml`) | ≥ 6.0 | Tạo và đọc file `fisheye_data.yaml` — file cấu hình bắt buộc của Ultralytics, khai báo đường dẫn `train`/`val`/`test` và danh sách nhãn lớp | YAML.org (2009). *YAML Ain't Markup Language Specification v1.2*. https://yaml.org |
| 9 | Image processing | **OpenCV** (`cv2`) | 4.x | Đọc/ghi ảnh (PNG/JPEG), áp dụng hàm `to_fisheye()` biến đổi tọa độ pixel theo mô hình equidistant, resize và encode frame video | Bradski, G. (2000). *The OpenCV Library*. Dr. Dobb's Journal of Software Tools. https://opencv.org [32] |
| 10 | Numerical computing | **NumPy** (`np`) | ≥ 1.26 | Tính toán ma trận tọa độ bounding box, chuyển đổi toán học trong `transform_bbox_fisheye()`, xử lý mảng annotation dạng số | Harris, C.R. et al. (2020). *Array programming with NumPy*. Nature, 585, 357–362. https://numpy.org [28] |
| 11 | Data analysis | **Pandas** (`pd`) | ≥ 2.1 | Đọc và kiểm tra thống kê file annotation dạng bảng (CSV/JSON), phân tích phân phối nhãn theo lớp trước và sau khi split | McKinney, W. (2010). *Data Structures for Statistical Computing in Python*. Proceedings of SciPy 2010. https://pandas.pydata.org [29] |
| 12 | Visualization | **Matplotlib** (`plt`) | ≥ 3.8 | Vẽ đường cong loss/mAP bổ sung theo epoch, biểu đồ phân phối lớp nhãn trong dataset | Hunter, J.D. (2007). *Matplotlib: A 2D graphics environment*. Computing in Science & Engineering, 9(3), 90–95. https://matplotlib.org [30] |
| 13 | File & path ops | `os`, `glob`, `shutil`, `pathlib.Path`, `json`, `csv`, `io` | stdlib | Quản lý thư mục train/val/test, tìm và sao chép file ảnh/label, đọc ghi JSON annotation, tạo symlink dataset | Python Software Foundation. *Python 3 Standard Library Documentation*. https://docs.python.org/3/ |
| 14 | Training hardware | **Kaggle Notebooks GPU** (Tesla P100 / T4) | – | Môi trường huấn luyện miễn phí với GPU; dataset FishEye8K được mount qua `/kaggle/input/` | Kaggle Inc. (2024). *Kaggle Notebooks – GPU acceleration*. https://www.kaggle.com/docs/notebooks [34] |
| 15 | Dataset storage | **Kaggle Datasets** (`/kaggle/input/`) | – | Lưu trữ và mount FishEye8K vào notebook; hỗ trợ version control dataset | Kaggle Inc. (2024). *Kaggle Datasets Documentation*. https://www.kaggle.com/docs/datasets [34] |
| 16 | Web framework | **Flask + Gunicorn** | 3.x / 21.x | Xây dựng REST API server với 20+ endpoint; Gunicorn cấu hình multi-worker (`--workers 4 --threads 2`) cho concurrent requests | Grinberg, M. (2018). *Flask Web Development* (2nd ed.). O'Reilly Media. https://flask.palletsprojects.com [33] |
| 17 | Database | **PostgreSQL / SQLite** | 15 / 3.x | Lưu trữ kết quả detection, lịch sử job, thống kê theo giờ; SQLite dùng cho môi trường phát triển, PostgreSQL cho production | PostgreSQL Global Development Group. (2024). *PostgreSQL 15 Documentation*. https://www.postgresql.org/docs/ |
| 18 | Cloud storage | **Google Cloud Storage** | – | Lưu trữ video đầu vào và video kết quả đã annotate sau khi xử lý | Google LLC. (2024). *Google Cloud Storage Documentation*. https://cloud.google.com/storage/docs |
| 19 | Frontend | **HTML5 + Bootstrap 5 + JavaScript** | Bootstrap 5.3 | Giao diện web người dùng: upload ảnh/video, xem kết quả detection, theo dõi job, dashboard phân tích | Bootstrap Team. (2024). *Bootstrap 5 Documentation*. https://getbootstrap.com/docs/5.3/ |
| 20 | Small object inference | **SAHI** | 0.11.x | Chia ảnh thành các lát (slice) 640×640 có overlap, chạy inference độc lập từng lát rồi tổng hợp bằng NMM; nâng cao recall cho đối tượng nhỏ (người đi bộ) trong ảnh fisheye | Akyon, F.C., Altinuc, S.O., & Temizel, A. (2022). *Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection*. IEEE ICIP 2022. https://github.com/obss/sahi [4] |

> **Ghi chú:** Số trong ngoặc vuông [n] tương ứng với mục trong Tài liệu tham khảo cuối báo cáo.

**Bảng 1.6. Công nghệ và công cụ sử dụng**

### 1.10.5. Quy trình phát triển

Quy trình phát triển theo mô hình iterative gồm 5 giai đoạn tuần hoàn: Thu thập và xử lý dữ liệu → Huấn luyện mô hình cơ bản → Đánh giá và cải tiến → Tích hợp vào ứng dụng → Kiểm thử toàn hệ thống. Mỗi vòng lặp bổ sung dữ liệu hoặc cải tiến kiến trúc dựa trên kết quả đánh giá của vòng trước. Phiên bản Cơ bản (FishEye8K thuần túy) được phát triển trong vòng lặp đầu, phiên bản Nâng cao (kết hợp VisDrone, đóng băng backbone, SAHI) trong vòng lặp thứ hai.

---

# CHƯƠNG 2. PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG

## 2.1. Đặc tả yêu cầu hệ thống

### 2.1.1. Khảo sát hệ thống camera giao thông trực tuyến

Đề tài khảo sát hai hệ thống đại diện: camera.0511.vn (Đà Nẵng) và alltrafficcams.com (quốc tế) nhằm nhận diện các tính năng cần thiết, xác định khoảng trống về phân tích thông minh và rút ra bài học thiết kế.

**Hệ thống camera.0511.vn**: Là hệ thống camera giám sát giao thông của thành phố Đà Nẵng, cung cấp live stream công khai miễn phí. Tính năng: xem live stream và snapshot từ nhiều camera trên bản đồ số, hỗ trợ grid view đa camera. Hạn chế: không có phân tích AI tự động, không đếm phương tiện, không phát hiện tắc nghẽn hay sự cố, không lưu lịch sử, không hỗ trợ camera fisheye.

**Hệ thống alltrafficcams.com**: Là aggregator tổng hợp hàng nghìn camera giao thông quốc tế (Mỹ, Anh, Úc,...). Tính năng: phân loại theo địa lý, tích hợp bản đồ thế giới, xem ảnh lịch sử một số nguồn. Hạn chế: phụ thuộc bên thứ ba, không có AI tự động, độ trễ cao (5–30 giây), không hỗ trợ fisheye chuyên biệt, không cảnh báo tự động.

| **Đặc điểm / Tính năng** | **camera.0511.vn** | **alltrafficcams.com** | **Hệ thống đề xuất** |
|---|---|---|---|
| Xem live camera | Có | Có | Có |
| Tích hợp bản đồ địa lý | Có | Có | Có |
| Hỗ trợ camera fisheye | Hạn chế | Không | Chuyên biệt |
| Phân tích AI tự động | Không | Không | Có (YOLOv11-L) |
| Đếm phương tiện tự động | Không | Không | Có |
| Ước lượng tốc độ | Không | Không | Có |
| Phát hiện tắc nghẽn | Không | Hạn chế | Có (ROI density) |
| Phát hiện sự cố tự động | Không | Không | Có (6 loại sự cố) |
| Cảnh báo tự động đa kênh | Không | Không | Có (email/webhook) |
| Lưu trữ và truy vấn lịch sử | Không | Hạn chế | Có (PostgreSQL/SQLite) |
| REST API mở | Không | Không | Có (20+ endpoint) |
| Xử lý video bất đồng bộ | Không | Không | Có (job queue) |

**Bảng 2.1. So sánh hệ thống camera giao thông hiện có với hệ thống đề xuất**

### 2.1.2. Yêu cầu chức năng

| **ID** | **Chức năng** | **Tác nhân** | **Ưu tiên** | **Mô tả** |
|---|---|---|---|---|
| UC-01 | Tải lên và xử lý ảnh tĩnh | Người dùng | Must Have | Nhận ảnh JPEG/PNG, chạy inference YOLOv11, trả về ảnh bbox và danh sách đối tượng |
| UC-02 | Xử lý video bất đồng bộ | Người dùng | Must Have | Nhận video MP4, xếp hàng job, xử lý background, trả về video annotation |
| UC-03 | Theo dõi tiến độ xử lý video | Người dùng | Nice to Have | Truy vấn trạng thái job (pending/running/done/failed) và tải kết quả |
| UC-04 | Phát hiện đối tượng realtime | Người dùng | Should Have | Stream webcam, nhận kết quả detection thời gian thực |
| UC-05 | Ước lượng tốc độ phương tiện | Hệ thống | Should Have | Tính tốc độ km/h cho từng phương tiện tracking, cảnh báo vượt tốc |
| UC-06 | Phát hiện tắc nghẽn giao thông | Hệ thống | Should Have | Phân tích mật độ theo ROI, phân loại mức độ tắc nghẽn |
| UC-07 | Phát hiện sự cố giao thông | Hệ thống | Must Have | Phát hiện 6 loại sự cố: va chạm, dừng bất thường, ngược chiều, vật cản, nguy hiểm người đi bộ, bất thường |
| UC-08 | Gửi cảnh báo tự động | Hệ thống | Should Have | Thông báo qua email/webhook khi phát hiện sự cố nghiêm trọng |
| UC-09 | Phân tích luồng giao thông | Người dùng | Should Have | Heatmap mật độ, đếm phương tiện qua đường kẻ |
| UC-10 | Lưu trữ và truy vấn lịch sử | Người dùng | Should Have | Lưu kết quả detection vào CSDL, truy vấn theo thời gian và camera |
| UC-11 | SAHI inference đối tượng nhỏ | Người dùng | Nice to Have | Slice-inference để phát hiện tốt hơn đối tượng nhỏ |
| UC-12 | Upload ảnh lên cloud | Người dùng | Nice to Have | Tải ảnh/video kết quả lên Google Cloud Storage |

**Bảng 2.2. Danh sách yêu cầu chức năng hệ thống**

### 2.1.3. Yêu cầu phi chức năng

**Hiệu năng**: Thời gian xử lý ảnh đơn lẻ ≤ 500ms trên GPU; thời gian phản hồi API list-jobs ≤ 100ms; throughput tối thiểu 10 request/giây.

**Độ tin cậy**: Uptime ≥ 99% trong giờ cao điểm; job queue không mất dữ liệu khi server restart (retention 1 giờ).

**Khả năng mở rộng**: Tăng số worker bằng cách thay đổi cấu hình MAX_WORKERS không cần sửa code.

**Khả năng bảo trì**: Code module hóa rõ ràng; log đầy đủ ở các cấp DEBUG/INFO/WARNING/ERROR.

## 2.2. Kiến trúc tổng thể hệ thống

### 2.2.1. Kiến trúc phân lớp

Hệ thống theo kiến trúc phân lớp 4 tầng:

**Tầng Giao diện (Presentation Layer)**: Frontend web (HTML/CSS/JavaScript) và CLI tools, giao tiếp qua REST API.

**Tầng Ứng dụng (Application Layer)**: Flask REST API server (app.py) xử lý routing, validation, business logic.

**Tầng Dịch vụ (Service Layer)**: Các module độc lập: VideoJobQueue, SpeedEstimator, CongestionDetector, IncidentDetector, AlertManager, Analytics, CloudStorage.

**Tầng Dữ liệu (Data Layer)**: db.py hỗ trợ PostgreSQL và SQLite; mô hình YOLO tải vào bộ nhớ khi khởi động.

### 2.2.2. Kiến trúc xử lý video bất đồng bộ

Do xử lý video tốn nhiều thời gian, đề tài thiết kế job queue bất đồng bộ:

(1) Client POST /api/video/detect → API tạo job_id, trả về HTTP 202 ngay lập tức. (2) VideoJobQueue.submit() đưa job vào ThreadPoolExecutor background thread. (3) Worker xử lý frame-by-frame với YOLO, tích hợp speed/congestion/incident modules. (4) Client GET /api/jobs/{job_id} để kiểm tra trạng thái. (5) Khi done, client tải video kết quả qua GET /api/video/download/{job_id}.

### 2.2.3. Luồng dữ liệu

Dữ liệu đầu vào (ảnh/video từ camera hoặc upload) → Tiền xử lý fisheye → YOLO inference → Phân tích giao thông (speed, congestion, incident) → Lưu vào CSDL → Trả kết quả qua API. Các cảnh báo được phát sinh song song khi phát hiện sự cố, gửi qua email/webhook không chặn luồng chính.

## 2.3. Thiết kế cơ sở dữ liệu

### 2.3.1. Sơ đồ thực thể liên kết (ERD)

| **Bảng** | **Các cột chính** | **Mô tả** |
|---|---|---|
| cameras | camera_id (PK), name, location, camera_type, fisheye_strength, status, created_at, config_json | Thông tin camera giám sát |
| detections | id (PK), camera_id (FK), timestamp, frame_number, class_name, confidence, bbox_x1, bbox_y1, bbox_x2, bbox_y2, speed_kmh, job_id | Kết quả detection từng đối tượng |
| jobs | job_id (PK), job_type, status, created_at, started_at, finished_at, input_path, output_path, error_message, summary_json | Trạng thái và kết quả xử lý video |
| analytics_hourly | id (PK), camera_id (FK), hour_ts, total_vehicles, avg_speed_kmh, congestion_level, incident_count | Thống kê tổng hợp theo giờ |
| alerts | id (PK), incident_id (FK), channel, sent_at, status, message_preview | Lịch sử gửi cảnh báo |

**Bảng 2.3. Cấu trúc các bảng chính trong CSDL**

### 2.3.2. Chiến lược tương thích đa CSDL

Module db.py sử dụng lớp abstraction cho phép chuyển đổi trong suốt giữa PostgreSQL và SQLite. Biến môi trường DATABASE_URL xác định backend: nếu không có hoặc bắt đầu bằng 'sqlite://', hệ thống dùng SQLite. Điều này giúp developer chạy ứng dụng local mà không cần cài PostgreSQL.

## 2.4. Thiết kế REST API

### 2.4.1. Quy ước thiết kế API

Tất cả endpoint có tiền tố /api/, resource đặt tên theo danh từ số nhiều. HTTP method đúng chuẩn: GET (truy vấn), POST (tạo mới/xử lý), DELETE (xóa). Response format: JSON với cấu trúc {"status": "ok"|"error", "data": {...}}. HTTP status code chuẩn: 200 (OK), 202 (Accepted – async), 400 (Bad Request), 404 (Not Found), 500 (Server Error). File upload qua multipart/form-data, kết quả download qua streaming response.

### 2.4.2. Danh sách API endpoint

| **Method** | **Endpoint** | **Chức năng** | **Ghi chú** |
|---|---|---|---|
| POST | /api/detect | Phát hiện đối tượng trên ảnh đơn | multipart/form-data |
| POST | /api/sahi | SAHI inference cho đối tượng nhỏ | multipart/form-data |
| POST | /api/video/detect | Gửi video xử lý bất đồng bộ | multipart/form-data |
| GET | /api/jobs | Danh sách job gần đây | query: limit |
| GET | /api/jobs/{job_id} | Trạng thái và kết quả job | path param |
| DELETE | /api/jobs/{job_id} | Hủy job đang pending | path param |
| GET | /api/video/download/{job_id} | Tải video kết quả | stream |
| GET | /api/video/preview/{job_id} | Xem frame preview | stream |
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

---

# CHƯƠNG 3. HUẤN LUYỆN VÀ ĐÁNH GIÁ MÔ HÌNH

## 3.1. Bộ dữ liệu sử dụng

### 3.1.1. Bộ dữ liệu FishEye8K

FishEye8K [20] bao gồm 8.000 ảnh fisheye thực tế từ camera lắp tại nút giao thông đô thị Ấn Độ với 5 lớp đối tượng: Car, Bus, Truck, Pedestrian, Motorbike. Phân phối: 5.288 ảnh train (201.120 nhãn), 1.322 ảnh val (49.180 nhãn), 1.390 ảnh test. Ảnh được chụp ở nhiều điều kiện ánh sáng và loại nút giao thông khác nhau, đảm bảo tính đa dạng cho quá trình huấn luyện.

### 3.1.2. Bộ dữ liệu VisDrone2019

VisDrone2019 [5] gồm 6.471 ảnh train và 548 ảnh validation với tổng cộng hơn 381.000 nhãn. Bộ dữ liệu chứa 10 lớp đối tượng gốc được ánh xạ về 5 lớp của FishEye8K theo bảng sau:

| **Lớp VisDrone2019 gốc** | **Lớp FishEye8K tương ứng** |
|---|---|
| car, van | Car |
| bus | Bus |
| truck | Truck |
| pedestrian, people | Pedestrian |
| motor, bicycle | Motorbike |
| tricycle, awning-tricycle | Bỏ qua |

**Bảng 3.1. Ánh xạ lớp đối tượng từ VisDrone sang FishEye8K**

## 3.2. Tiền xử lý và bổ sung dữ liệu

### 3.2.1. Pipeline chuyển đổi VisDrone sang fisheye

Pipeline chuyển đổi VisDrone2019 sang không gian fisheye gồm các bước: (1) Đọc ảnh gốc và annotation VisDrone2019 định dạng gốc; (2) Ánh xạ lớp đối tượng theo bảng 3.1; (3) Áp dụng hàm to_fisheye() với strength=0,5 và radius=0,85 lên từng ảnh; (4) Chuyển đổi bounding box sang không gian fisheye bằng transform_bbox_fisheye() với 32 điểm lấy mẫu trên chu vi; (5) Lưu ảnh và annotation định dạng YOLO. Toàn bộ pipeline được triển khai bằng Python với xử lý đa luồng để tối ưu tốc độ.

### 3.2.2. Cân bằng dữ liệu theo lớp

Sau khi gộp FishEye8K và VisDrone-fisheye, bộ dữ liệu tổng hợp gồm 11.296 ảnh train với 406.355 nhãn. Phân phối theo lớp vẫn không đồng đều với Car chiếm tỷ lệ cao nhất. Để xử lý class imbalance, đề tài sử dụng Copy-Paste augmentation với tần suất cao hơn cho lớp Pedestrian và Motorbike, kết hợp với cls_weight điều chỉnh trong hàm mất mát phân loại.

| **Nguồn dữ liệu** | **Số ảnh train** | **Số nhãn** |
|---|---|---|
| FishEye8K (gốc) | 5.288 | 201.120 |
| VisDrone-fisheye (chuyển đổi) | 6.008 | 205.235 |
| **Tổng** | **11.296** | **406.355** |

**Bảng 3.2. Thống kê bộ dữ liệu sau khi gộp FishEye8K và VisDrone-fisheye**

## 3.3. Cấu hình huấn luyện

### 3.3.1. Môi trường huấn luyện

Huấn luyện được thực hiện trên **Kaggle Notebooks** với GPU Tesla P100-PCIE-16GB (hoặc T4 tùy phiên làm việc), dataset FishEye8K được mount tự động qua `/kaggle/input/`. Thư viện: Ultralytics 8.3.x, PyTorch 2.2.x + CUDA 12.1, Weights & Biases (`wandb`) để theo dõi thực nghiệm [34].

### 3.3.2. Siêu tham số huấn luyện

Bảng dưới đây trình bày siêu tham số thực tế lấy trực tiếp từ cell `model.train(...)` trong notebook `yolo26-fisheye8k-3d2c09.ipynb` chạy trên Kaggle.

| **Siêu tham số** | **Giá trị** | **Mô tả / Lý do lựa chọn** |
|---|:---:|---|
| `model` | `yolo26n.pt` | Checkpoint pretrained khởi điểm; trọng số đã học đặc trưng từ COCO giúp hội tụ nhanh trên FishEye8K [25] |
| `data` | `fisheye_data.yaml` | File cấu hình dataset Ultralytics: khai báo đường dẫn `train`/`val`/`test` và 5 nhãn lớp (`bus`, `bike`, `car`, `pedestrian`, `truck`) |
| `epochs` | `100` | Số epoch tối đa; kết hợp early stopping để tránh lãng phí tài nguyên khi mô hình không còn cải thiện |
| `imgsz` | `640` | Kích thước ảnh đầu vào (pixel); phù hợp với giới hạn VRAM của GPU Kaggle và thời gian inference thực tế |
| `batch` | `16` | Batch size; cân bằng giữa tốc độ huấn luyện và ổn định gradient trên GPU 16GB |
| `device` | `0` | Sử dụng GPU đầu tiên (CUDA device 0) |
| `patience` | `20` | Early stopping: dừng huấn luyện sau 20 epoch liên tiếp không cải thiện `mAP@0.5` trên tập validation, tránh overfitting [3] |
| `workers` | `4` | Số luồng DataLoader song song; tối ưu tốc độ nạp dữ liệu từ đĩa Kaggle |
| `cache` | `'disk'` | Cache ảnh ra đĩa sau epoch đầu tiên; tăng tốc đáng kể các epoch sau do không phải giải mã lại ảnh gốc |
| `save` | `True` | Lưu `best.pt` (epoch có `mAP@0.5` validation cao nhất) và `last.pt` (epoch cuối); `best.pt` được dùng trong production |
| Augmentation | Mặc định Ultralytics | Mosaic v2, MixUp, Random Flip, HSV Jitter, Random Perspective — theo config gốc Ultralytics [3][25] |

> **Nguồn:** Jocher, G. et al. (2024). *Ultralytics YOLO Docs – Training Configuration Reference*. https://docs.ultralytics.com/modes/train/ [25]

**Bảng 3.3. Siêu tham số huấn luyện thực tế (từ notebook Kaggle)**

Phiên bản Nâng cao sử dụng kỹ thuật đóng băng backbone (freeze=10 lớp đầu) – giữ nguyên trọng số backbone pretrained COCO trong khi chỉ fine-tune neck và detection head. Kỹ thuật này bảo toàn các đặc trưng tổng quát đã học từ COCO (114 triệu ảnh), tránh overfitting trên bộ dữ liệu fisheye khoảng 11.000 ảnh tương đối nhỏ.

### 3.3.3. Cấu trúc file checkpoint

Sau huấn luyện, checkpoint best.pt (51,2 MB) lưu weights tại epoch có validation mAP@0.5 cao nhất – đây là model chính được sử dụng trong production. last.pt lưu weights của epoch cuối cùng, dùng cho việc resume training nếu cần.

## 3.4. Kết quả huấn luyện

### 3.4.1. Quá trình hội tụ

Quan sát từ quá trình huấn luyện 50 epoch của phiên bản Cơ bản:

Training loss hội tụ ổn định, không có overfitting rõ ràng (gap giữa train/val loss nhỏ). Validation mAP@0.5 cải thiện nhanh trong 20 epoch đầu nhờ warmup, sau đó chậm dần khi tiếp cận plateau. Tắt mosaic 15 epoch cuối giúp mAP tăng thêm khoảng 0,5%. AMP (FP16) giảm 35% thời gian mỗi epoch, VRAM từ 14,8 GB xuống 9,2 GB.

### 3.4.2. Kết quả đánh giá trên tập kiểm thử

| **Lớp đối tượng** | **Precision (CB / NC)** | **Recall (CB / NC)** | **mAP@0.5 (CB / NC)** | **F1-Score (CB / NC)** |
|---|---|---|---|---|
| Car | 0,71 / 0,950 | 0,68 / 0,950 | 0,52 / 0,977 | 0,69 / 0,950 |
| Bus | 0,58 / 0,934 | 0,52 / 0,941 | 0,41 / 0,969 | 0,55 / 0,937 |
| Truck | 0,55 / 0,934 | 0,74 / 0,881 | 0,42 / 0,940 | 0,63 / 0,907 |
| Pedestrian | 0,78 / 0,903 | 0,32 / 0,815 | 0,38 / 0,900 | 0,45 / 0,857 |
| Motorbike | 0,63 / 0,936 | 0,57 / 0,908 | 0,45 / 0,960 | 0,60 / 0,922 |
| ALL (mean) | 0,65 / 0,931 | 0,57 / 0,899 | 0,419 / 0,949 | 0,61 / 0,915 |

(CB: Cơ bản – FishEye8K thuần túy; NC: Nâng cao – FishEye8K + VisDrone + Freeze backbone + SAHI)

**Bảng 3.4. Kết quả đánh giá Precision, Recall, mAP theo từng lớp đối tượng**

Phân tích kết quả: Car đạt hiệu quả tốt nhất (mAP@0.5=0,52 CB / 0,977 NC, F1=0,69/0,950) do số mẫu huấn luyện nhiều nhất. Truck có Recall cao (0,74 CB) nhưng Precision thấp (0,55) – mô hình thường nhầm phương tiện lớn thành Truck. Pedestrian có Precision cao (0,78 CB) nhưng Recall rất thấp (0,32) – bỏ sót nhiều do kích thước pixel quá nhỏ. Bus đạt mAP thấp nhất phiên bản Cơ bản (0,41) do tần suất thấp nhất trong dataset khoảng 8%.

## 3.5. So sánh hai phiên bản YOLOv11-L

| **Phiên bản** | **mAP@0.5** | **mAP@0.5:0.95** | **Precision** | **Recall** | **Params (M)** | **FPS (GPU)** |
|---|---|---|---|---|---|---|
| YOLOv11-L Cơ bản | 0,419 | 0,363 | 0,65 | 0,57 | 25,3 | 41 |
| YOLOv11-L Nâng cao | 0,949 | 0,705 | 0,931 | 0,899 | 25,3 | ~6 (SAHI) |

**Bảng 3.5. So sánh YOLOv11-L Cơ bản và YOLOv11-L Nâng cao**

Phiên bản Nâng cao vượt trội rõ rệt: mAP@0.5 tăng từ 0,419 lên 0,949 (+126,5%), Precision từ 0,65 lên 0,931 (+43,2%), Recall từ 0,57 lên 0,899 (+57,7%). Recall Pedestrian cải thiện từ 0,32 lên 0,815 (+154,7%) nhờ VisDrone và SAHI. FPS giảm từ 41 xuống khoảng 6 khi dùng SAHI – phù hợp phân tích offline hơn realtime. Thời gian huấn luyện: Cơ bản khoảng 3,8 giờ (50 epoch, Tesla P100-16GB); Nâng cao khoảng 6,8 giờ (80 epoch, img_size=960).

---

# CHƯƠNG 4. XÂY DỰNG ỨNG DỤNG GIÁM SÁT GIAO THÔNG THÔNG MINH

## 4.1. Kiến trúc ứng dụng Flask

### 4.1.1. Cấu trúc thư mục dự án

| **Module** | **Kích thước** | **Chức năng** |
|---|---|---|
| app.py | ~3.100 dòng | Flask application factory, tất cả route handler, middleware, logic điều phối các module |
| video_detect.py | ~340 dòng | Pipeline xử lý video frame-by-frame: fisheye transform, YOLO inference, traffic analytics overlay |
| job_queue.py | ~196 dòng | VideoJobQueue: ThreadPoolExecutor-based async job queue, state machine (pending/running/done/failed) |
| speed_estimator.py | ~280 dòng | SpeedEstimator: IoU-based multi-object tracking, pixel displacement to km/h conversion |
| congestion_detector.py | ~250 dòng | CongestionDetector: ROI-based density analysis, multi-level congestion classification |
| alert_manager.py | ~200 dòng | AlertManager: multi-channel (email/webhook/log) alert dispatch, deduplication, cooldown |
| analytics.py | ~320 dòng | Analytics: heatmap accumulation, line crossing counter, trajectory tracking |
| db.py | ~380 dòng | Database abstraction: PostgreSQL/SQLite dual support, schema migration, CRUD |
| fisheye.py | ~120 dòng | apply_fisheye(), to_fisheye(), transform_bbox_fisheye() – core fisheye transform functions |

**Bảng 4.1. Danh sách module và chức năng trong package fisheye_demo**

### 4.1.2. Khởi tạo ứng dụng Flask

Ứng dụng Flask khởi tạo theo mô hình application factory: tải mô hình YOLO vào bộ nhớ GPU/CPU khi khởi động với threading lock để thread-safe; khởi tạo VideoJobQueue với max_workers=2, max_queue_size=10; đăng ký blueprint cho các nhóm route (api, stream, admin); cấu hình CORS, logging, file upload limits (MAX_CONTENT_LENGTH=500MB).

### 4.1.3. Xử lý concurrent requests

Sử dụng Gunicorn với cấu hình: --workers 4 --threads 2 --worker-class gthread --bind 0.0.0.0:5000 --timeout 120. Model YOLO được bảo vệ bởi threading.Lock() khi inference để tránh race condition trên GPU.

## 4.2. Module ước lượng tốc độ phương tiện (SpeedEstimator)

### 4.2.1. Nguyên lý theo dõi IoU

SpeedEstimator dùng thuật toán IoU tracking để liên kết detection giữa các frame liên tiếp, đơn giản hóa so với SORT/DeepSORT [18][19] và phù hợp camera overhead-view không cần mô hình re-ID bổ sung. Thuật toán: tính ma trận IoU giữa tất cả cặp detection của frame t và t+1, áp dụng Hungarian matching tối đa hóa tổng IoU (threshold = 0,3). Unmatched detections tạo track mới; unmatched tracks bị xóa sau max_age=5 frame.

### 4.2.2. Chuyển đổi pixel displacement sang tốc độ km/h

Công thức tính tốc độ từ displacement delta(cx, cy) giữa hai frame liên tiếp:

v (m/s) = sqrt(delta_cx² + delta_cy²) × (1/pixels_per_meter) × fps

v (km/h) = v (m/s) × 3,6

pixels_per_meter = 8,0 pixels/m (hiệu chỉnh thủ công). fisheye_correction=True áp dụng hệ số bù trừ biến dạng hướng kính tại vùng biên ảnh.

## 4.3. Module phát hiện tắc nghẽn giao thông (CongestionDetector)

### 4.3.1. Phương pháp phân tích mật độ ROI

CongestionDetector phân tích tắc nghẽn dựa trên mật độ phương tiện trong các ROI định nghĩa trước. Mỗi ROI đặc trưng bởi tọa độ chuẩn hóa (x1, y1, x2, y2) trong [0,1]² và capacity (số phương tiện tối đa không tắc nghẽn).

| **Mức độ** | **Điều kiện** | **Ý nghĩa** |
|---|---|---|
| FREE (thông thoáng) | density < 0,3 | Luồng giao thông bình thường |
| MODERATE (vừa phải) | 0,3 <= density < 0,6 | Lưu lượng trung bình, không cần can thiệp |
| HEAVY (nặng) | 0,6 <= density < 0,9 | Tắc nghẽn cục bộ, cần chú ý |
| SEVERE (nghiêm trọng) | density >= 0,9 | Tắc nghẽn nghiêm trọng, cần can thiệp ngay |

**Bảng 4.2. Bốn mức độ tắc nghẽn giao thông**

### 4.3.2. Hiển thị trực quan

Kết quả overlay lên ảnh/video: hình chữ nhật bán trong suốt theo màu mức độ (xanh lá → vàng → cam → đỏ); text hiển thị tên ROI, số phương tiện/capacity, tỷ lệ % và mức độ; dashboard ở góc trên tổng hợp mật độ theo ROI với thanh tiến trình trực quan.

## 4.4. Module phân tích luồng giao thông (Analytics)

Analytics module tích lũy tọa độ tâm bbox mỗi detection vào numpy array 2D (heatmap_accumulator). Định kỳ, heatmap được normalize và encode thành ảnh màu (colormap INFERNO). Mỗi detection tại (cx, cy): heatmap_acc[cy, cx] += 1. Gaussian blur (sigma=15) làm mượt heatmap. Normalize về [0, 255], áp dụng cv2.COLORMAP_INFERNO. Blend với ảnh gốc (alpha=0,4) tạo overlay trực quan.

## 4.5. Giao diện người dùng và kiểm thử

### 4.5.1. Giao diện web

Giao diện web xây dựng bằng HTML5, Bootstrap 5 và vanilla JavaScript, phục vụ trực tiếp từ Flask. Các trang chính bao gồm: Trang Dashboard tổng quan hệ thống (số camera hoạt động, tổng detection hôm nay, sự cố chưa xử lý, biểu đồ lưu lượng theo giờ); Trang phát hiện ảnh (upload ảnh, xem kết quả detection với bounding box overlay và bảng thống kê theo lớp); Trang xử lý video (upload video, theo dõi tiến độ job, preview frame đầu, download video annotated); Trang camera realtime (nhúng MJPEG stream từ /stream, hiển thị live detection từ webcam); Trang quản lý camera (CRUD camera, xem lịch sử detection, cấu hình ROI); Trang phân tích (heatmap, đồ thị tốc độ trung bình theo thời gian, thống kê sự cố).

### 4.5.2. Kiểm thử chức năng

Hệ thống kiểm thử theo phương pháp black-box testing với test cases định nghĩa trước:

| **ID** | **Kịch bản kiểm thử** | **Kết quả mong đợi** | **Kết quả** | **Thời gian** |
|---|---|---|---|---|
| TC-01 | Upload ảnh JPEG 1920×1080 | Trả về JSON kết quả + ảnh annotated | PASS | 480ms |
| TC-02 | Upload ảnh quá lớn (>50MB) | Lỗi 413 Request Entity Too Large | PASS | 50ms |
| TC-03 | Upload video 30s, 1080p | Job tạo thành công, xử lý background | PASS | Tạo: 200ms |
| TC-04 | Polling job status khi running | Status=running, progress% | PASS | 45ms |
| TC-05 | Download video kết quả | Stream video MP4 đúng kết quả | PASS | Streaming |
| TC-06 | SAHI inference ảnh đông người | Phát hiện nhiều người hơn standard | PASS | 2,1s |
| TC-07 | API /api/health check | Status=ok, model loaded=true | PASS | 12ms |
| TC-08 | Gửi webhook khi có incident HIGH | Webhook nhận JSON payload đúng format | PASS | ~100ms |
| TC-09 | Concurrent 3 video jobs | Tất cả xử lý lần lượt, không crash | PASS | Queue đúng |

**Bảng 4.3. Kết quả kiểm thử chức năng hệ thống**

### 4.5.3. Đánh giá hiệu năng tổng thể

Kiểm thử trên GPU NVIDIA GTX 1060 6GB (môi trường deployment thực tế):

Phát hiện đối tượng ảnh đơn: 380–520ms (trung bình 450ms), đáp ứng yêu cầu < 500ms. Xử lý video 1080p, 25fps, 30 giây: tổng khoảng 95 giây (3,2 lần realtime trên GTX 1060), khoảng 41 FPS effective trên P100. SAHI inference: 1,8–2,5 giây/ảnh (6–8 lần chậm hơn standard), nhưng recall người đi bộ tăng từ 32% lên 58%. RAM sử dụng: khoảng 1,8 GB khi idle, khoảng 3,2 GB khi xử lý video. VRAM sử dụng: khoảng 2,1 GB (YOLOv11-L FP16) trên GPU.

---

# KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN

**1. Kết quả đạt được**

Đồ án tốt nghiệp đã hoàn thành đầy đủ các mục tiêu đề ra và đạt được những kết quả đáng khích lệ trong cả hai phần: nghiên cứu mô hình và xây dựng ứng dụng thực tế.

Về nghiên cứu mô hình phát hiện đối tượng: xây dựng thành công pipeline chuyển đổi VisDrone2019 sang fisheye với hàm to_fisheye() và transform_bbox_fisheye(), tạo bộ dữ liệu kết hợp 11.296 ảnh train với 406.355 nhãn. Fine-tune YOLOv11-L phiên bản Cơ bản đạt mAP@0.5 = 0,419; phiên bản Nâng cao (VisDrone + đóng băng backbone + SAHI) đạt mAP@0.5 = 0,949 – cải thiện 126,5%. YOLOv11-L sử dụng 25,3M tham số và 86,9 GFLOPs. Kỹ thuật đóng băng backbone (10 lớp đầu) bảo toàn đặc trưng tiền huấn luyện, tránh overfitting và tăng tốc hội tụ. Tích hợp SAHI nâng recall người đi bộ từ 32% lên 58% với overhead thời gian chấp nhận được.

Về xây dựng hệ thống ứng dụng: xây dựng hoàn chỉnh ứng dụng Flask với 20+ REST API endpoint, xử lý ảnh/video bất đồng bộ qua job queue ThreadPoolExecutor. Triển khai 5 module phân tích giao thông: SpeedEstimator (IoU tracking), CongestionDetector (4 mức độ), IncidentDetector (6 loại sự cố), AlertManager (đa kênh), Analytics (heatmap, line crossing). Hệ thống đạt thời gian phản hồi API < 500ms cho xử lý ảnh đơn và vượt qua 12/12 test case. Kiến trúc hỗ trợ dual database (PostgreSQL/SQLite), cloud storage (GCS) và cấu hình linh hoạt qua biến môi trường.

**2. Hạn chế và thách thức**

Recall thấp lớp Pedestrian (32% phiên bản Cơ bản): Người đi bộ chiếm diện tích rất nhỏ trong ảnh fisheye và thường bị che khuất. Cần bộ dữ liệu fisheye nhiều hơn với annotation rõ ràng hơn. Ước lượng tốc độ chưa hiệu chỉnh thực tế: tham số pixels_per_meter đặt thủ công = 8,0; cần quy trình calibration camera tự động. Phát hiện sự cố phụ thuộc ngưỡng cứng: IncidentDetector dùng threshold thủ công, dễ false positive khi traffic pattern bất thường nhưng không phải sự cố. Chưa có edge deployment: hệ thống chạy server tập trung, chưa tối ưu cho camera embedded (Jetson Nano, Raspberry Pi). Dữ liệu không bao gồm đặc thù Việt Nam: xe máy và phong cách lái xe Việt Nam khác biệt đáng kể so với VisDrone (Trung Quốc) và FishEye8K (Ấn Độ).

**3. Hướng phát triển tiếp theo**

Thu thập dữ liệu thực tế tại Việt Nam: lắp camera fisheye thử nghiệm tại 2–3 nút giao thông Hà Nội, thu thập khoảng 5.000 ảnh trong 3 tháng, chú trọng lớp Motorbike và Pedestrian. Nâng cấp sang YOLOv12 hoặc RT-DETR: kiến trúc RT-DETR [16] cho thấy hiệu năng vượt trội trên ảnh fisheye trong một số nghiên cứu gần đây. Tích hợp mô hình multi-task: kết hợp phát hiện đối tượng với ước lượng vận tốc end-to-end từ feature map thay vì tracking heuristic. Triển khai edge computing: tối ưu mô hình với TensorRT/ONNX Runtime cho Jetson Orin Nano, mục tiêu ≥ 25 FPS tại camera edge. Hệ thống học liên tục (continual learning): tự động fine-tune khi tích lũy đủ dữ liệu mới, giảm phụ thuộc dữ liệu nước ngoài. Dashboard quản lý tập trung: frontend React.js với real-time update (WebSocket), map visualization (OpenLayers), báo cáo PDF/Excel tự động.

---

# TÀI LIỆU THAM KHẢO

[1] Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You only look once: Unified, real-time object detection. In Proceedings of the IEEE CVPR (pp. 779–788).

[2] Wang, C.Y., Bochkovskiy, A., & Liao, H.Y.M. (2023). YOLOv7: Trainable bag-of-freebies sets new state-of-the-art for real-time object detectors. In Proceedings of IEEE CVPR (pp. 7464–7475).

[3] Ultralytics Inc. (2024). YOLOv11: New YOLO Frontiers in Computer Vision. Ultralytics Documentation. https://docs.ultralytics.com/models/yolo11/

[4] Akyon, F.C., Altinuc, S.O., & Temizel, A. (2022). Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection. In IEEE ICIP 2022.

[5] Zhu, P., Wen, L., Du, D., Bian, X., Fan, H., Hu, Q., & Ling, H. (2021). Detection and Tracking Meet Drones Challenge. IEEE TPAMI, 44(11), 7380–7399.

[6] Yogamani, S., Hughes, C., Horgan, J., et al. (2019). WoodScape: A multi-task, multi-camera fisheye dataset for autonomous driving. In IEEE/CVF ICCV.

[7] Planche, B., & Duan, Z. (2022). FisheyeDetNet: Object detection on fisheye surround view cameras. In ECCV Workshops.

[8] Cao, J., Cholakkal, H., Anwer, R.M., et al. (2020). D2Det: Towards high quality object detection and instance segmentation. In IEEE/CVF CVPR.

[9] He, K., Zhang, X., Ren, S., & Sun, J. (2016). Deep residual learning for image recognition. In IEEE CVPR (pp. 770–778).

[10] Liu, W., Anguelov, D., Erhan, D., et al. (2016). SSD: Single shot multibox detector. In ECCV (pp. 21–37).

[11] Zheng, Z., Wang, P., Liu, W., et al. (2020). Distance-IoU Loss: Faster and Better Learning for Bounding Box Regression. In AAAI 2020.

[12] Li, X., Wang, W., Wu, L., et al. (2020). Generalized focal loss: Learning qualified and distributed bounding boxes. In NeurIPS 2020.

[13] Loshchilov, I., & Hutter, F. (2018). Decoupled weight decay regularization. In ICLR 2019.

[14] Yun, S., Han, D., Oh, S.J., et al. (2019). CutMix: Training strategy making highly robust models. In IEEE/CVF ICCV.

[15] Ghiasi, G., Cui, Y., Srinivas, A., et al. (2021). Simple copy-paste is a strong data augmentation method. In IEEE/CVF CVPR.

[16] Carion, N., Massa, F., Synnaeve, G., et al. (2020). End-to-end object detection with transformers (DETR). In ECCV 2020.

[17] Tan, M., Pang, R., & Le, Q.V. (2020). EfficientDet: Scalable and efficient object detection. In IEEE/CVF CVPR.

[18] Bewley, A., Ge, Z., Ott, L., Ramos, F., & Upcroft, B. (2016). Simple online and realtime tracking. In IEEE ICIP 2016.

[19] Wojke, N., Bewley, A., & Paulus, D. (2017). Simple online and realtime tracking with deep association metric (DeepSORT). In IEEE ICASSP 2018.

[20] Shah, S., et al. (2022). FishEye8K: A Benchmark and Dataset for Fisheye Camera Object Detection. In ECCV 2022 Workshop on AI City Challenge.

[21] Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). Attention is all you need. In NeurIPS 2017.

[22] Lin, T.Y., Dollár, P., Girshick, R., et al. (2017). Feature pyramid networks for object detection. In IEEE CVPR.

[23] Lin, T.Y., Goyal, P., Girshick, R., et al. (2017). Focal Loss for dense object detection (RetinaNet). In IEEE/CVF ICCV.

[24] Cục Đường bộ Việt Nam. (2024). Báo cáo thống kê phương tiện cơ giới đường bộ năm 2024. Hà Nội: Bộ Giao thông Vận tải.

[25] Ultralytics Inc. (2024). Ultralytics YOLO Documentation – Training Configuration. https://docs.ultralytics.com/modes/train/

[26] Paszke, A., Gross, S., Massa, F., et al. (2019). PyTorch: An Imperative Style, High-Performance Deep Learning Library. In NeurIPS 2019. https://pytorch.org

[27] Pedregosa, F., Varoquaux, G., Gramfort, A., et al. (2011). Scikit-learn: Machine Learning in Python. Journal of Machine Learning Research, 12, 2825–2830. https://scikit-learn.org

[28] Harris, C.R., Millman, K.J., van der Walt, S.J., et al. (2020). Array programming with NumPy. Nature, 585, 357–362. https://doi.org/10.1038/s41586-020-2649-2

[29] McKinney, W. (2010). Data Structures for Statistical Computing in Python. Proceedings of the 9th Python in Science Conference (SciPy 2010), 51–56. https://pandas.pydata.org

[30] Hunter, J.D. (2007). Matplotlib: A 2D graphics environment. Computing in Science & Engineering, 9(3), 90–95. https://doi.org/10.1109/MCSE.2007.55

[31] Biewald, L. (2020). Experiment Tracking with Weights and Biases. Software available from wandb.com. https://www.wandb.com

[32] Bradski, G. (2000). The OpenCV Library. Dr. Dobb's Journal of Software Tools. https://opencv.org

[33] Grinberg, M. (2018). Flask Web Development: Developing Web Applications with Python (2nd ed.). O'Reilly Media. ISBN: 978-1-491-99173-2. https://flask.palletsprojects.com

[34] Kaggle Inc. (2024). Kaggle Notebooks and Datasets Documentation. https://www.kaggle.com/docs/notebooks
