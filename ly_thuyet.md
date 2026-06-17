# LÝ THUYẾT BẢO VỆ ĐỒ ÁN — FishEye8K ITS

**Sinh viên:** Nguyễn Quốc Nam (221220938)  
**Đề tài:** Xây dựng Hệ thống Nhận diện Vật thể qua Camera Mắt Cá phục vụ Giao thông Thông minh  
**GVHD:** TS. Nguyễn Đức Dư  

---

## MỤC LỤC

1. [Camera Mắt Cá — Quang học & Mô hình hình học](#1-camera-mắt-cá--quang-học--mô-hình-hình-học)
2. [Deep Learning & Mạng Nơ-ron Tích chập](#2-deep-learning--mạng-nơ-ron-tích-chập)
3. [Kiến trúc YOLO — Từ v1 đến v11](#3-kiến-trúc-yolo--từ-v1-đến-v11)
4. [Phát hiện Vật thể & Các Metric Đánh giá](#4-phát-hiện-vật-thể--các-metric-đánh-giá)
5. [Dataset & Kỹ thuật Huấn luyện](#5-dataset--kỹ-thuật-huấn-luyện)
6. [SAHI — Phát hiện Vật thể Nhỏ](#6-sahi--phát-hiện-vật-thể-nhỏ)
7. [Theo dõi Vật thể (Object Tracking)](#7-theo-dõi-vật-thể-object-tracking)
8. [Các Module ITS](#8-các-module-its)
9. [Nhận dạng Biển số Xe (ALPR)](#9-nhận-dạng-biển-số-xe-alpr)
10. [Kiến trúc Hệ thống Web](#10-kiến-trúc-hệ-thống-web)
11. [Cơ sở Dữ liệu](#11-cơ-sở-dữ-liệu)
12. [Triển khai & DevOps](#12-triển-khai--devops)
13. [Câu hỏi Thường gặp khi Bảo vệ](#13-câu-hỏi-thường-gặp-khi-bảo-vệ)

---

## 1. Camera Mắt Cá — Quang học & Mô hình hình học

### 1.1 Khái niệm cơ bản

**Camera mắt cá (fisheye camera)** là camera sử dụng ống kính góc cực rộng (ultra-wide-angle lens), cho phép ghi lại góc nhìn từ **180° đến 220°** trong một khung hình duy nhất.

**Ưu điểm so với camera thường:**
| Tiêu chí | Camera thường | Camera mắt cá |
|----------|--------------|---------------|
| Phạm vi bao phủ giao lộ | Cần 4 camera | 1 camera (180–220°) |
| Chi phí lắp đặt | Cao (4× thiết bị) | Thấp hơn đáng kể |
| Đồng bộ dữ liệu | Phức tạp (4 luồng) | Đơn giản (1 luồng) |
| Điểm mù | Có nhiều góc chết | Gần như không có |
| Ứng dụng AI | Model chuẩn | Cần fine-tune |

### 1.2 Các mô hình chiếu (Projection Models)

Camera thường dùng chiếu **phối cảnh (perspective)**: đường thẳng trong không gian → đường thẳng trong ảnh. Camera mắt cá dùng các mô hình đặc biệt:

**1. Equidistant (f-theta)** — phổ biến nhất, camera an ninh:
```
r = f × θ
```
- `r`: khoảng cách từ tâm ảnh đến điểm ảnh (pixel)
- `f`: tiêu cự hiệu dụng (pixel)
- `θ`: góc tới (angle of incidence) so với trục quang học

**2. Equisolid angle (orthographic)** — camera thiên văn:
```
r = 2f × sin(θ/2)
```

**3. Stereographic** — bảo toàn hình dạng cục bộ:
```
r = 2f × tan(θ/2)
```

**4. Orthographic** — camera chiếu vuông góc:
```
r = f × sin(θ)
```

**Trong project này:** sử dụng mô hình **equidistant** với tham số `strength` để mô phỏng mức độ bóp méo, áp dụng mapping ngược (inverse mapping) kết hợp bilinear interpolation.

### 1.3 Méo hình (Distortion)

Camera mắt cá tạo ra **barrel distortion (méo thùng)**: các đường thẳng trong thực tế trở thành đường cong lồi ra ngoài trong ảnh.

**Hàm méo hình đa thức (Brown-Conrady model):**
```
r' = r × (1 + k₁r² + k₂r⁴ + k₃r⁶ + ...)
```
- `r`: khoảng cách từ tâm ảnh (chuẩn hóa)
- `r'`: khoảng cách sau khi méo
- `k₁, k₂, k₃`: hệ số méo hình xuyên tâm

Với barrel distortion: `k₁ < 0` (hệ số âm → bóp vào)  
Với fisheye mạnh: `k₁ > 0` (hệ số dương → phồng ra)

### 1.4 Giải méo hình (Undistortion / Rectification)

**Bước 1: Inverse mapping**
- Mỗi pixel đầu ra (x, y) → tìm điểm tương ứng trong ảnh gốc
- Tránh "lỗ hổng" pixel (aliasing) khi dùng forward mapping

**Bước 2: Bilinear interpolation**
- Điểm nguồn thường không nằm đúng vào pixel nguyên
- Nội suy từ 4 pixel lân cận: `I(x,y) = (1-dx)(1-dy)I₀₀ + dx(1-dy)I₁₀ + (1-dx)dyI₀₁ + dxdyI₁₁`

**Thuật toán trong project (fisheye.py):**
```
Cho mỗi pixel đầu ra (x, y):
  1. Chuẩn hóa về [-1, 1] quanh tâm ảnh: u = (x - cx)/(w/2)
  2. Tính khoảng cách xuyên tâm: r = √(u² + v²)
  3. Áp dụng hàm phi tuyến: r' = r^(1 + strength)
  4. Tính tỷ lệ: scale = r' / r  (nếu r ≠ 0)
  5. Ánh xạ về tọa độ nguồn: src_x = u × scale × (w/2) + cx
  6. Bilinear interpolation từ nguồn tại (src_x, src_y)
```

**Vectorized với NumPy** → ~50–100ms/frame cho ảnh 1080p (không dùng vòng lặp Python).

### 1.5 Chuyển đổi Bounding Box (32-Point Method)

**Vấn đề:** Khi ảnh bị méo hình, hộp bao (bounding box) hình chữ nhật không còn bao phủ đúng vật thể.

**Giải pháp 32-Point:**
- Lấy mẫu **32 điểm** dọc theo chu vi bbox (không chỉ 4 góc)
- Áp dụng fisheye transform cho cả 32 điểm
- Tính axis-aligned bbox bao phủ tất cả 32 điểm sau biến đổi
- Chính xác hơn đáng kể ở rìa ảnh nơi méo hình mạnh nhất

---

## 2. Deep Learning & Mạng Nơ-ron Tích chập

### 2.1 Nền tảng: Mạng Nơ-ron Nhân tạo (ANN)

**Perceptron:** đơn vị tính toán cơ bản
```
y = f(Σ wᵢxᵢ + b)
```
- `wᵢ`: trọng số (weights)
- `xᵢ`: đầu vào
- `b`: bias
- `f`: hàm kích hoạt (activation function)

**Hàm kích hoạt phổ biến:**
- **ReLU:** `f(x) = max(0, x)` — hiệu quả, giảm vanishing gradient
- **Sigmoid:** `f(x) = 1/(1+e^(-x))` — dùng cho output nhị phân
- **Softmax:** `f(xᵢ) = e^xᵢ / Σe^xⱼ` — dùng cho phân loại nhiều lớp
- **SiLU (Swish):** `f(x) = x × sigmoid(x)` — YOLOv8/v11 dùng trong backbone

### 2.2 Mạng Nơ-ron Tích chập (CNN)

**Phép tích chập (Convolution):**
```
(I * K)(i,j) = ΣΣ I(i+m, j+n) × K(m,n)
```
- `I`: ảnh đầu vào
- `K`: kernel/filter (ma trận nhỏ học được)

**Các layer trong CNN:**
- **Convolutional Layer:** học đặc trưng cục bộ (edges, textures, patterns)
- **Batch Normalization:** chuẩn hóa đầu ra từng batch → ổn định huấn luyện
- **Pooling (Max/Avg):** giảm kích thước không gian, tăng tính bất biến dịch chuyển
- **Dropout:** tắt ngẫu nhiên một số neuron → chống overfitting

**Backpropagation & Gradient Descent:**
```
θ ← θ - α × ∂L/∂θ
```
- `α`: learning rate
- `L`: hàm loss
- `∂L/∂θ`: gradient của loss theo trọng số

**Optimizers:**
- **SGD (Stochastic Gradient Descent):** Phase 2 của project dùng với Cosine LR
- **AdamW:** Phase 1 dùng; kết hợp Momentum + RMSprop + Weight Decay

**Cosine LR Schedule:**
```
lr(t) = lr_min + 0.5 × (lr_max - lr_min) × (1 + cos(πt/T))
```
Giảm dần learning rate theo hình dạng cosin → hội tụ tốt hơn.

### 2.3 Transfer Learning & Fine-tuning

**Pretrained model (COCO):** YOLOv11 được pretrain trên dataset COCO (80 lớp, 118K ảnh).

**Fine-tuning chiến lược:**
- **Full fine-tune:** train toàn bộ mạng
- **Freeze backbone:** đóng băng các layer đầu → chỉ train neck + head
  - Project Phase 2: freeze 10 layer backbone đầu
  - Lợi ích: giữ lại đặc trưng thấp (edges, textures) từ COCO
  - Giảm overfitting khi dataset nhỏ (11K ảnh)

---

## 3. Kiến trúc YOLO — Từ v1 đến v11

### 3.1 Lịch sử YOLO

| Phiên bản | Năm | Đóng góp chính |
|-----------|-----|---------------|
| YOLOv1 | 2016 | Phát hiện 1-stage đầu tiên; chia ảnh thành S×S grid |
| YOLOv2 | 2017 | Anchor boxes; Darknet-19 |
| YOLOv3 | 2018 | Multi-scale detection; Darknet-53 |
| YOLOv4 | 2020 | CSP backbone; PANet neck; Mosaic augmentation |
| YOLOv5 | 2020 | PyTorch; Focus layer; AutoAnchor |
| YOLOv6/7 | 2022 | Rep-VGG blocks; E-ELAN |
| YOLOv8 | 2023 | Anchor-free; C2f block; Decoupled head |
| **YOLOv11** | **2024** | **C3k2; AIFI transformer; 2.6M params (nhỏ hơn v8)** |

### 3.2 Kiến trúc YOLOv11-N (dùng trong project)

#### Backbone: C3k2 (Cross Stage Partial Network - 2 bottlenecks)

**CSP (Cross Stage Partial) tư tưởng:**
- Tách input thành 2 nhánh: nhánh qua bottleneck + nhánh skip connection
- Ghép lại → gradient flow phong phú, tránh vanishing gradient

**C3k2 vs C3 (YOLOv5):**
- C3: 3 bottleneck modules
- C3k2: 2 bottleneck modules (compact, ít params hơn)
- Hiệu suất tương đương nhưng FLOP thấp hơn

#### Neck: FPN + PAN + AIFI Transformer

**FPN (Feature Pyramid Network - Lin et al., 2017):**
- Truyền đặc trưng từ layer sâu (semantic cao) → layer nông (resolution cao)
- Đường đi **top-down**: concat feature maps từ nhiều scale
- Giúp phát hiện vật thể nhỏ ở resolution cao

**PAN (Path Aggregation Network - Liu et al., 2018):**
- Bổ sung đường đi **bottom-up** ngược lại
- FPN + PAN = thông tin đi cả hai chiều → đặc trưng giàu hơn

**AIFI (Attention-based Intra-scale Feature Interaction):**
- Kế thừa từ **RT-DETR** (2023)
- **Self-attention** mô hình hóa phụ thuộc tầm xa (long-range dependencies)
- Chạy trên **một mức resolution** (intra-scale) → tránh chi phí cross-scale attention
- Ứng dụng: phát hiện xe bus trong đoàn xe, cụm xe máy

#### Detection Head: Anchor-free

**Anchor-based (cũ):** dự đoán offset so với anchor box định sẵn
- Cần thiết kế anchor box phù hợp (AutoAnchor)
- Khó khăn với tỷ lệ khung hình cực đoan

**Anchor-free (YOLOv8/11):**
```
Dự đoán: (l, r, t, b) = khoảng cách từ tâm ô đến 4 cạnh bbox
Bbox thực tế: (cx - l, cy - t, cx + r, cy + b)
```
- Không cần thiết kế anchor
- Tốt hơn với vật thể tỷ lệ đặc biệt (xe tải dài, người đứng cao)

**Decoupled Head:**
- Tách riêng nhánh **classification** và nhánh **regression**
- Cải thiện accuracy so với coupled head của YOLOv5

### 3.3 Thông số YOLOv11-N

| Thông số | Giá trị |
|----------|---------|
| Parameters | **2.6M** (nhỏ hơn YOLOv8-N: 3.2M) |
| GFLOPs | **6.5** |
| Input Size (Phase 2) | **960×960** (tăng từ 640 để phát hiện vật thể nhỏ) |
| FPS (P100 GPU, standard) | ~41 fps |
| FPS (SAHI) | ~12 fps |
| File size weights | 5.3 MB |

### 3.4 So sánh YOLOv11-N vs YOLOv8-N

| Metric | YOLOv11-N | YOLOv8-N |
|--------|-----------|----------|
| mAP@0.5:0.95 (COCO) | 39.5% | 37.3% |
| Parameters | 2.6M | 3.2M |
| GFLOPs | 6.5 | 8.7 |

**Kết luận:** YOLOv11-N vừa chính xác hơn vừa nhỏ gọn hơn → phù hợp deployment.

---

## 4. Phát hiện Vật thể & Các Metric Đánh giá

### 4.1 Bài toán Object Detection

**Output:** tập hợp các bounding box + nhãn lớp + confidence
```
{(bbox₁, class₁, conf₁), (bbox₂, class₂, conf₂), ...}
bbox = (x₁, y₁, x₂, y₂) hoặc (cx, cy, w, h)
```

**Hai paradigm:**
- **2-stage (R-CNN, Faster R-CNN):** đề xuất vùng RoI → phân loại từng vùng; chậm nhưng chính xác
- **1-stage (YOLO, SSD):** phát hiện trực tiếp trên toàn ảnh; nhanh, phù hợp real-time

### 4.2 IoU (Intersection over Union)

```
IoU = Area(A ∩ B) / Area(A ∪ B)
```
- `A`: predicted bounding box
- `B`: ground truth bounding box
- IoU = 1: hoàn hảo; IoU = 0: không chồng lấp

**Ứng dụng trong YOLO:**
- NMS (Non-Maximum Suppression): loại bỏ boxes trùng nhau
- Đánh giá True Positive: IoU ≥ threshold (thường 0.5)
- Loss function: CIoU loss

### 4.3 Precision, Recall, F1

```
Precision = TP / (TP + FP)   -- Trong những cái model dự đoán, bao nhiêu đúng?
Recall    = TP / (TP + FN)   -- Trong những cái thực tế có, model tìm được bao nhiêu?
F1-Score  = 2 × P × R / (P + R)
```

| Term | Ý nghĩa |
|------|---------|
| TP (True Positive) | Phát hiện đúng (có xe, model nói có) |
| FP (False Positive) | Báo nhầm (không có xe, model nói có) |
| FN (False Negative) | Bỏ sót (có xe, model không phát hiện) |

**Trade-off:** tăng confidence threshold → tăng Precision, giảm Recall.

### 4.4 AP và mAP

**Precision-Recall Curve:** với mỗi threshold khác nhau → vẽ đồ thị P-R

**AP (Average Precision):** diện tích dưới đường cong P-R của 1 lớp
```
AP = ∫₀¹ P(R) dR  ≈  Σ Pₙ × ΔRₙ
```

**mAP (mean Average Precision):** trung bình AP qua tất cả lớp
```
mAP = (1/C) × ΣAP_c   (C = số lớp)
```

**mAP@0.5:** tính với IoU threshold = 0.5  
**mAP@0.5:0.95:** trung bình mAP từ IoU 0.5 đến 0.95 (bước 0.05) — khắt khe hơn

**Kết quả project:**
- Phase 1: mAP@0.5 = **0.619**
- Phase 2: mAP@0.5 = **0.862** (+39.3%)

### 4.5 Hàm Loss trong YOLO

**Classification Loss:** Binary Cross-Entropy (BCE) cho từng lớp
```
L_cls = -[y × log(p) + (1-y) × log(1-p)]
```

**Regression Loss: CIoU Loss** (Complete IoU)
```
CIoU = IoU - ρ²(b, bᵍᵗ)/c² - αv
```
- `ρ²`: khoảng cách bình phương Euclidean giữa tâm hai box
- `c²`: đường chéo của vùng bao hai box
- `αv`: penalty cho tỷ lệ chiều rộng-chiều cao (aspect ratio)

**DFL Loss (Distribution Focal Loss):** YOLOv8/11 dùng cho regression
- Dự đoán phân phối xác suất cho từng biên bbox → ổn định hơn scalar

**Total Loss:**
```
L = λ₁L_cls + λ₂L_box + λ₃L_dfl
```

---

## 5. Dataset & Kỹ thuật Huấn luyện

### 5.1 FishEye8K Dataset

- **Nguồn:** CVPR Workshop 2023, AI City Challenge
- **Nguồn gốc ảnh:** Camera CCTV cảnh sát Hsinchu, Đài Loan
- **Đặc điểm:** Góc nhìn từ trên xuống, đa dạng điều kiện (ngày/đêm/mưa/sương)
- **Phân chia:** 4,230 train | 1,058 val | 2,712 test
- **Tổng cộng:** ~8,000 ảnh, 112,213 bbox được gán nhãn
- **Trung bình:** 21.2 nhãn/ảnh

### 5.2 VisDrone2019 Dataset

- **Nguồn:** IEEE/CVF ICCV 2019, Đại học Thiên Tân
- **Nguồn gốc ảnh:** UAV (máy bay không người lái), độ cao 10–70m
- **10 lớp gốc** → ánh xạ về **5 lớp** của project:
  - car → Car | bus → Bus | truck → Truck
  - pedestrian → Pedestrian | motorcycle + bicycle → Motorbike
  - (bỏ: van, awning-tricycle, tricycle, others)
- **Phân chia:** 6,471 train | 548 val | 1,610 test-dev
- **Tổng nhãn train:** 343,205

### 5.3 Kết hợp Dataset

| Dataset | Train ảnh | Val ảnh | Nhãn Train |
|---------|-----------|---------|------------|
| FishEye8K | 4,230 | 1,058 | 89,676 |
| VisDrone (đã convert) | 6,471 | 548 | 316,679 |
| **Tổng hợp** | **10,701** | **1,606** | **406,355** |

**Vấn đề phân phối lớp (class imbalance):**
- Car chiếm ~45%; Bus chỉ ~8%
- Model dễ học Car tốt, Bus kém

**Giải pháp:**
- **Copy-Paste Augmentation:** sao chép-dán xe Bus/Truck từ ảnh này sang ảnh khác → tăng tần suất lớp hiếm
- Áp dụng trong Phase 2 để cân bằng phân phối

### 5.4 Data Augmentation

**Mosaic (YOLOv4, v=0.8 trong Phase 2):**
- Ghép 4 ảnh lại thành 1 ảnh training
- Tăng đa dạng bối cảnh; giúp phát hiện vật thể nhỏ
- `mosaic=0.8`: 80% batch dùng mosaic, 20% ảnh đơn

**Mixup (v=0.15 trong Phase 2):**
- Trộn 2 ảnh: `I = α×I₁ + (1-α)×I₂`
- Label cũng trộn (soft labels) → regularization mạnh

**Augmentation thêm:** flip ngang, rotation, color jitter, scale, blur

### 5.5 Hai Phase Huấn luyện

**Phase 1 (Cơ bản):**
- Dataset: FishEye8K only (4,230 ảnh)
- Epochs: 50 | Batch: 16 | Image size: 640×640
- Optimizer: **AdamW** | LR: 0.0005
- Kết quả: mAP@0.5 = 0.619, mAP@0.5:0.95 = 0.363

**Phase 2 (Nâng cao):**
- Dataset: FishEye8K + VisDrone converted (11,296 ảnh)
- Epochs: 80 | Batch: 16 | Image size: **960×960** (tăng để phát hiện vật thể nhỏ)
- Optimizer: **SGD + Cosine LR** | LR: 0.01
- Freeze: 10 layer backbone (giữ đặc trưng COCO)
- Augmentation: Copy-Paste, Mosaic=0.8, Mixup=0.15
- Kết quả: mAP@0.5 = **0.862**, mAP@0.5:0.95 = **0.572**

**Lý do đổi từ AdamW sang SGD ở Phase 2:**
- AdamW hội tụ nhanh, tốt cho dataset nhỏ (Phase 1)
- SGD + Cosine LR tổng quát hóa tốt hơn khi dataset lớn → mAP cao hơn ở validation

---

## 6. SAHI — Phát hiện Vật thể Nhỏ

### 6.1 Vấn đề

Người đi bộ ở rìa ảnh fisheye chỉ chiếm **10–30 pixel** sau méo hình:
- YOLO phát hiện ở resolution 640×640 hoặc 960×960
- Vật thể quá nhỏ → feature map mất thông tin → bỏ sót
- Phase 1 Recall người đi bộ chỉ đạt **0.42**

### 6.2 SAHI (Sliced Aided Hyper Inference)

**Tác giả:** Akyon et al., 2022, IEEE ICIP (International Conference on Image Processing)  
**Ý tưởng:** chia nhỏ ảnh → inference từng tile → gộp kết quả

**Quy trình:**
```
1. Chia ảnh 1920×1080 thành các tile 640×640 chồng lấp nhau (overlap 0.2)
2. Inference YOLO trên từng tile độc lập
3. Inference YOLO trên toàn ảnh gốc (thu nhỏ)
4. Chuyển đổi tọa độ bbox về coordinate ảnh gốc
5. Áp dụng NMM (Non-Maximum Merging) loại bỏ duplicate ở biên tile
```

**NMM vs NMS:**
- NMS (Non-Maximum Suppression): giữ box có score cao nhất, xóa các box IoU > threshold
- NMM: hợp nhất (merge) các box thay vì chỉ xóa → phù hợp khi cùng 1 vật thể bị phát hiện ở 2 tile chồng nhau

**Kết quả:**
- Pedestrian Recall: 0.42 → **0.75** (+78.6%)
- Inference time: 1.8–2.5 giây/ảnh (chấp nhận được cho offline analysis)

**Khi nào dùng SAHI:** ảnh tĩnh/video offline cần độ chính xác cao; không dùng cho real-time (quá chậm).

---

## 7. Theo dõi Vật thể (Object Tracking)

### 7.1 Bài toán Tracking

Liên kết detection qua các frame liên tiếp để duy trì ID nhất quán cho mỗi vật thể:
```
Frame t: {(id=1, bbox₁), (id=2, bbox₂), ...}
Frame t+1: {(id=1, bbox₁'), (id=2, bbox₂'), ...}
```

### 7.2 IoU-based Tracking (dùng trong project)

**Thuật toán đơn giản, phù hợp traffic:**
1. Frame t: tập detections D_t = {d₁, d₂, ...}
2. Frame t+1: tập detections D_{t+1} = {d₁', d₂', ...}
3. Tính ma trận IoU: `IoU[i,j]` = IoU giữa dᵢ và dⱼ'
4. **Hungarian Algorithm:** gán tối ưu → maximize Σ IoU (O(n³))
5. Gán nếu IoU ≥ 0.3; ngược lại → track mới
6. Track không được gán sau `max_age=5` frame → xóa

**So với SORT/DeepSORT:**
- SORT: dùng Kalman Filter + IoU
- DeepSORT: thêm feature embedding (re-identification)
- **Project dùng IoU-only:** đủ với traffic (xe di chuyển chậm, đặc trưng rõ ràng)

### 7.3 Hungarian Algorithm

**Bài toán gán (Assignment Problem):**
- n công việc, m người làm
- `cost[i,j]` = chi phí giao việc j cho người i
- Tìm gán 1-1 để minimize tổng chi phí

**Trong tracking:** cost = 1 - IoU (vì Hungarian minimize, ta muốn maximize IoU)

**Độ phức tạp:** O(n³) — chấp nhận được với n < 100 vật thể/frame trong traffic.

---

## 8. Các Module ITS

### 8.1 Ước tính Tốc độ (Speed Estimation)

**Nguyên lý:**
```
distance_px = √(Δcx² + Δcy²)  -- khoảng cách pixel giữa 2 frame liên tiếp
distance_m  = distance_px / pixels_per_meter
speed_m_s   = distance_m × fps
speed_km_h  = speed_m_s × 3.6
```

**Hiệu chỉnh (Calibration):**
- `pixels_per_meter = 8.0` — cần hiệu chỉnh thủ công theo chiều cao camera và góc nghiêng
- Cách hiệu chỉnh: đo vật tham chiếu (vạch kẻ đường, làn xe đã biết rộng)

**Làm mịn kết quả (smoothing):**
- Dùng deque (rolling window) trên n=10 frame
- `speed = mean(speed_history)` → tránh jump đột ngột

**Phát hiện vi phạm:**
- Tốc độ > limit ≥ 3 frame liên tiếp → vi phạm
- Cooldown 30s/track để tránh báo trùng lặp
- Mã màu: xanh (<40) → vàng (40–70) → đỏ (>70 km/h)

### 8.2 Phát hiện Tắc nghẽn (Congestion Detection)

**Level of Service (LoS)** — khái niệm từ Highway Capacity Manual (HCM):
- **LOS A:** Free flow — đường thông thoáng
- **LOS B/C:** Steady flow — lưu thông ổn định
- **LOS D:** Near capacity — gần bão hòa
- **LOS E/F:** Congested — tắc nghẽn

**Công thức Occupancy:**
```
occupancy = Σ(count × vehicle_weight) / capacity
```

**Trọng số theo phương tiện:**
| Phương tiện | Trọng số | Lý do |
|-------------|---------|-------|
| Xe máy | 0.5 | Nhỏ, chiếm ít không gian |
| Ô tô | 1.0 | Baseline |
| Người đi bộ | 0.3 | Rất nhỏ |
| Xe tải | 2.0 | Lớn, chiếm nhiều diện tích |
| Xe buýt | 2.5 | Rất lớn |

**4 cấp độ:**
| Level | Occupancy | Hành động |
|-------|-----------|-----------|
| LOW | < 0.5 | Không cần can thiệp |
| MODERATE | 0.5–0.85 | Theo dõi |
| HIGH | ≥ 0.85 | Cần can thiệp |
| JAMMED | > 1.2 | Khẩn cấp |

**ROI (Region of Interest):**
- Người dùng định nghĩa vùng quan tâm bằng tọa độ chuẩn hóa [0,1]²
- Ví dụ: làn xe bên trái, nút giao thông
- Theo dõi lịch sử 300 frame gần nhất

### 8.3 Đếm Phương tiện theo Đường ảo (Virtual Line Counter)

**Nguyên lý:**
- Định nghĩa 4 đường ảo: Bắc / Nam / Đông / Tây
- Mỗi đường là đoạn thẳng (x₁,y₁)-(x₂,y₂) trong ảnh

**Phát hiện xe vượt đường:**
- Theo dõi tâm xe: (cx_t, cy_t) ở frame t
- Nếu (cx_t, cy_t) và (cx_{t-1}, cy_{t-1}) nằm khác phía so với đường → vượt đường
- Dùng phép kiểm tra **half-plane** (cross product): 
  ```
  cross = (x₂-x₁)×(py-y₁) - (y₂-y₁)×(px-x₁)
  dấu cross thay đổi → vượt đường
  ```
- Mỗi track_id chỉ được đếm **1 lần** cho mỗi hướng

**Lưu trữ:** bảng `traffic_counts` (hour_bucket, camera_id, direction, class_name, count)

### 8.4 Phát hiện Sự cố (Incident Detection)

**3 loại sự cố:**

**1. ILLEGAL_PARKING (Đỗ xe trái phép)**
- Điều kiện: xe đứng yên > 30 giây ngoài vùng cho phép
- Phát hiện: displacement < threshold trong 30s
- Severity: Medium

**2. STOPPED_VEHICLE (Xe dừng trong làn)**
- Điều kiện: xe dừng (displacement thấp) trong khi xe khác di chuyển xung quanh
- Phát hiện: speed ≈ 0 + có xe khác moving gần đó
- Gây cản trở giao thông
- Severity: High

**3. WRONG_WAY (Đi ngược chiều)**
- Điều kiện: vector vận tốc của xe ngược với luồng giao thông chính (góc > 120°)
- Phát hiện: so sánh heading của track với median heading của tất cả xe trong frame
- Nguy hiểm nhất (va chạm trực diện)
- Severity: Very High

**Anti-spam:** mỗi track_id chỉ tạo tối đa 1 sự cố mỗi loại.

---

## 9. Nhận dạng Biển số Xe (ALPR)

### 9.1 ALPR (Automatic License Plate Recognition)

**Pipeline 2 giai đoạn:**

**Stage 1: Phát hiện phương tiện**
- Dùng kết quả YOLO detection (Car, Truck, Bus, Motorbike)
- Crop vùng ảnh của xe lớn nhất trong frame

**Stage 2: OCR**
- **EasyOCR** (Jaided AI): CNN-based OCR hỗ trợ 80+ ngôn ngữ
- Chạy trên crop của xe
- Lọc bằng regex biển số Việt Nam
- Ngưỡng confidence: ≥ 0.30

### 9.2 Biển số Việt Nam

**Format chuẩn:**
```
(\d{2})([A-Z]{1,2})(\d?)(\d{4,5})
```

**Ví dụ:**
- `51F-123.45` (29-xx-xxxx = 5 số cuối, TP.HCM)
- `29X1-2345` (Hà Nội, series 1)
- `30A-12345` (Hà Nội, loại thường)

**2 định dạng phổ biến:**
1. **3+2:** `51F12345` → `51F-123.45` (tỉnh - 3chữ số - chấm - 2 chữ số)
2. **4 số:** `29X1234` → `29X1-2345` (tỉnh - series - 4 chữ số)

### 9.3 EasyOCR

**Kiến trúc:** CRNN (Convolutional Recurrent Neural Network)
- **CNN:** extract visual features từ ảnh chữ
- **BiLSTM:** xử lý sequence đặc trưng theo chiều ngang
- **CTC (Connectionist Temporal Classification):** decode sequence → text

**Graceful degradation:** nếu EasyOCR không có → `is_available()` = False, app vẫn chạy bình thường.

---

## 10. Kiến trúc Hệ thống Web

### 10.1 Flask (Python Web Framework)

**Application Factory Pattern (`app.py`):**
```python
def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db(app)
    register_blueprints(app)
    return app
```
- Lợi ích: dễ test (tạo nhiều app instance), tránh circular imports
- Khác với global `app = Flask(__name__)` trực tiếp

**Blueprint Pattern:**
- Tách routes thành module riêng: `core.py`, `detect.py`, `history.py`, `external_camera.py`
- Đăng ký vào app: `app.register_blueprint(blueprint, url_prefix='/api')`
- Tăng tính module hóa, dễ bảo trì

**WSGI (Web Server Gateway Interface):**
- Interface chuẩn giữa Python app và web server (Gunicorn, uWSGI)
- `wsgi.py` expose `app` object → Gunicorn: `gunicorn wsgi:app`

**Gunicorn cấu hình:**
```
--workers 1   # 1 worker process (GPU memory constraint)
--threads 4   # 4 threads/worker (concurrent HTTP requests)
```

### 10.2 Async Job Queue

**Vấn đề:** xử lý video 30s mất ~95 giây → HTTP timeout

**Giải pháp: ThreadPoolExecutor + polling**
```
POST /api/detect (video)
  → validate → save temp file
  → return 202 Accepted {job_id}
  → background thread: process_video()

GET /api/jobs/{job_id}
  → return {status: "running", progress: 45.3}

GET /api/jobs/{job_id}/result   (khi status="done")
  → return result
```

**ThreadPoolExecutor:**
- `max_workers=2`: tránh OOM (out of memory) GPU
- `max_queue_size=10`: tránh quá tải server

### 10.3 Single-Page Application (SPA)

**Vanilla JavaScript (không dùng React/Vue):**
- Lý do: giảm dependency, dễ debug, phù hợp đồ án
- Hash-based routing: `/#dashboard`, `/#workspace`, `/#live-streams`
- Observer pattern cho state management

**8 trang chính:**
1. Dashboard — KPI, biểu đồ tổng quan
2. Workspace — Upload, inference, annotation
3. Live Streams — Giám sát camera thời gian thực
4. History — Lịch sử phát hiện
5. ALPR — Nhận dạng biển số
6. TOC — Traffic Operations Center
7. Logs Terminal — Xem log thời gian thực
8. Settings — Cấu hình ngưỡng, thiết bị

### 10.4 REST API Design

**~80 endpoints**, tuân thủ REST conventions:
- `GET /api/resource` — liệt kê
- `POST /api/resource` — tạo mới
- `GET /api/resource/{id}` — chi tiết
- `PUT /api/resource/{id}` — cập nhật
- `DELETE /api/resource/{id}` — xóa

**HTTP Status Codes:**
- 200 OK — thành công
- 202 Accepted — đã nhận, đang xử lý (async video job)
- 400 Bad Request — dữ liệu không hợp lệ
- 404 Not Found — không tìm thấy
- 413 Payload Too Large — file quá lớn (> 50MB)
- 500 Internal Server Error — lỗi server

**CORS (Cross-Origin Resource Sharing):**
- Cho phép frontend (khác origin) gọi API
- Cấu hình header: `Access-Control-Allow-Origin: *`

---

## 11. Cơ sở Dữ liệu

### 11.1 SQLite vs PostgreSQL

**SQLite (Development):**
- File-based, không cần server
- WAL mode (Write-Ahead Logging): hỗ trợ concurrent reads + writes
- Phù hợp: dev, testing, deployment nhỏ

**PostgreSQL (Production):**
- Client-server architecture
- ACID compliance mạnh hơn
- JSONB: JSON nhị phân, index được, query nhanh hơn JSON text
- Connection pooling: xử lý nhiều request đồng thời
- GCP Cloud SQL: managed service (backup, scaling tự động)

**Dual-mode trong project (db.py):**
```python
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:  # PostgreSQL
    use_psycopg2()
else:             # SQLite fallback
    use_sqlite()
```

### 11.2 Schema Chính

**detections** — kết quả inference:
```sql
id TEXT PRIMARY KEY,
task TEXT,          -- 'detect' | 'convert'
media_type TEXT,    -- 'image' | 'video'
created_at TIMESTAMPTZ,
class_counts JSONB, -- {"Car": 5, "Bus": 1}
model_name TEXT,
inference_ms REAL
```

**traffic_counts** — đếm xe theo giờ:
```sql
hour_bucket TIMESTAMPTZ,  -- làm tròn theo giờ
camera_id TEXT,
direction TEXT,    -- 'north' | 'south' | 'east' | 'west'
class_name TEXT,
count INTEGER,
UNIQUE(hour_bucket, camera_id, direction, class_name)  -- upsert
```

**incidents** — sự cố giao thông:
```sql
incident_type TEXT,  -- 'ILLEGAL_PARKING' | 'STOPPED_VEHICLE' | 'WRONG_WAY'
severity TEXT,       -- 'low' | 'medium' | 'high'
acknowledged BOOLEAN DEFAULT FALSE,
evidence_path TEXT   -- ảnh chụp màn hình
```

**speed_violations**, **alerts**, **license_plates**, **live_sessions** — xem chi tiết trong `db.py`.

### 11.3 SQL Quan trọng

**UPSERT (insert or update) — traffic_counts:**
```sql
-- PostgreSQL
INSERT INTO traffic_counts (hour_bucket, camera_id, direction, class_name, count)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (hour_bucket, camera_id, direction, class_name)
DO UPDATE SET count = traffic_counts.count + EXCLUDED.count;

-- SQLite
INSERT OR REPLACE INTO traffic_counts ...
```

**Aggregation cho analytics:**
```sql
SELECT class_name, SUM(count) as total
FROM traffic_counts
WHERE camera_id = ? AND hour_bucket >= ?
GROUP BY class_name
ORDER BY total DESC;
```

---

## 12. Triển khai & DevOps

### 12.1 Docker

**Dockerfile (Production):**
```dockerfile
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime
# Base image đã có PyTorch + CUDA → không cần install thêm
WORKDIR /app
COPY requirements-prod.txt .
RUN pip install -r requirements-prod.txt
COPY fisheye_demo/ .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "wsgi:app"]
```

**Docker Compose (Production):**
```yaml
services:
  cloud-sql-proxy:
    image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.11.0
    # Tạo tunnel bảo mật đến Cloud SQL
    
  fisheye-web:
    build: .
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]
    depends_on: [cloud-sql-proxy]
```

### 12.2 Google Cloud Platform (GCP)

**Architecture trên GCP:**
```
GitHub Actions (CI/CD)
  ↓ Workload Identity Federation (không cần service account key)
  ↓ SSH đến VM
  ↓ git pull + docker compose up --build

GCP Compute Engine:
  - Machine: g2-standard-4 (4 vCPU, 16GB RAM)
  - GPU: NVIDIA L4 (12GB VRAM, tốt hơn GTX 1060)
  - Zone: asia-southeast1-b (Singapore, gần VN)
  - Preemptible: giảm chi phí ~70% (có thể bị GCP thu hồi)

GCP Cloud SQL: PostgreSQL managed
GCP Cloud Storage (GCS): lưu snapshot ảnh, TTL 6 giờ
```

**Workload Identity Federation:**
- Không cần lưu service account JSON key trong GitHub Secrets
- GitHub Actions dùng OIDC token → xác thực với GCP
- An toàn hơn: không có long-lived credentials

### 12.3 CI/CD Pipeline (GitHub Actions)

```yaml
on:
  push:
    branches: [main]

jobs:
  deploy:
    steps:
      - name: Checkout code
      - name: Authenticate to GCP (WIF)
      - name: SSH to VM
        run: |
          ssh user@vm-ip "cd /app && git pull && \
            docker compose -f deploy/docker-compose.prod.yml up --build -d"
```

**Zero-downtime deployment:**
- Docker Compose restart existing containers với image mới
- Health check endpoint `/api/health` xác nhận deployment thành công

### 12.4 Monitoring & Logging

**Health Check API (`/api/health`):**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "device": "cuda:0",
  "db_connected": true,
  "gcs_available": true,
  "uptime_s": 3600
}
```

**Logging:** Python `logging` module → file + UI terminal
- INFO: normal operations
- WARNING: degraded state (no GPU, no GCS)
- ERROR: failures

**Real-time Log Viewer:** `/api/logs` → `LogsTerminal.js` polling mỗi 2 giây

---

## 13. Câu hỏi Thường gặp khi Bảo vệ

### Q1: Tại sao chọn YOLOv11 mà không phải YOLOv8 hay model khác?

**Trả lời:**
- YOLOv11-N chính xác hơn YOLOv8-N: mAP@0.5:0.95 = 39.5% vs 37.3% trên COCO
- Ít tham số hơn: 2.6M vs 3.2M → nhỏ hơn, nhanh hơn
- Tích hợp AIFI Transformer trong neck → mô hình phụ thuộc tầm xa tốt hơn, hữu ích cho cụm phương tiện
- YOLOv12 (2025) tốt hơn nhưng ra sau khi project đã bắt đầu; RT-DETR nặng hơn (không phù hợp edge)

### Q2: mAP@0.5 = 0.862 có nghĩa là gì? Có tốt không?

**Trả lời:**
- Trung bình 86.2% precision-recall area across 5 lớp, tại IoU threshold 0.5
- Baseline YOLOv11-N pretrain COCO: ~55% mAP@0.5 trên FishEye8K (chưa fine-tune)
- Sau fine-tune Phase 2: 86.2% → cải thiện 56% tuyệt đối
- Trong bối cảnh fisheye (khó hơn camera thường do méo hình + điều kiện đặc thù): đây là kết quả tốt
- So sánh: FishEye8K Challenge 2023 top teams đạt ~70–80% mAP@0.5

### Q3: Tại sao không dùng DeepSORT thay vì IoU tracking?

**Trả lời:**
- DeepSORT cần **appearance features** (CNN embedding) để re-identify — phù hợp tracking người qua nhiều camera
- Traffic: xe ô tô đều có màu tương tự, tốc độ chậm, IoU tracking đủ hiệu quả
- Overhead của DeepSORT (thêm CNN run) không đáng kể hiệu quả trong bài toán này
- IoU tracking: O(n²) tính IoU + O(n³) Hungarian → đủ nhanh với n < 100 xe/frame

### Q4: Calibration tốc độ pixels_per_meter bằng bao nhiêu? Cách tính?

**Trả lời:**
- Dùng `pixels_per_meter = 8.0` (calibrate thủ công)
- Cách hiệu chỉnh: đo vật tham chiếu trong ảnh (vạch kẻ đường biết trước chiều dài, hoặc chiều rộng làn xe 3.5m)
- Đếm số pixel tương ứng → pixels_per_meter = số_pixel / chiều_dài_thực
- Giới hạn: thay đổi theo từng camera (chiều cao, góc nghiêng khác nhau)
- Giải pháp tự động: homography matrix từ 4 điểm chuẩn (nâng cao, phần future work)

### Q5: Tại sao cần kết hợp FishEye8K + VisDrone? Chỉ dùng FishEye8K không được sao?

**Trả lời:**
- FishEye8K: 4,230 ảnh → nhỏ, dễ overfitting
- VisDrone bổ sung 6,471 ảnh với điều kiện đa dạng hơn → tổng quát hóa tốt hơn
- VisDrone có nhiều người đi bộ hơn FishEye8K (UAV chụp gần người) → cải thiện pedestrian recall
- Sau khi convert VisDrone sang fisheye format: mAP tăng từ 0.619 → 0.862 (+39.3%)
- Trade-off: VisDrone gốc không phải fisheye, cần transform → thêm noise; nhưng lợi ích volume data > cost

### Q6: SAHI làm chậm 6-8x, tại sao vẫn dùng?

**Trả lời:**
- SAHI chỉ dùng cho ảnh tĩnh (offline analysis), không dùng real-time
- Với live stream: dùng YOLO standard (12-41 fps)
- Với ảnh tĩnh: 2.1s/ảnh chấp nhận được nếu kết quả tốt hơn
- Pedestrian recall 0.42 → 0.75 là cải thiện quan trọng cho an toàn giao thông
- Người đi bộ bị bỏ sót = rủi ro tai nạn → trade-off tốc độ/safety rõ ràng

### Q7: Tại sao không dùng WebSocket thay vì polling?

**Trả lời:**
- WebSocket: kết nối persistent, server push
- Polling: client hỏi định kỳ mỗi 2-10 giây
- Với Flask (không async), WebSocket cần Flask-SocketIO → thêm complexity
- Traffic analytics không cần sub-second latency (xe không thay đổi trong 2 giây)
- Đơn giản hóa deployment (stateless), dễ debug, phù hợp phạm vi đồ án

### Q8: Hệ thống xử lý được bao nhiêu camera cùng lúc?

**Trả lời:**
- Video job queue: max 2 jobs song song (giới hạn VRAM GPU)
- Live camera monitor: có thể nhiều hơn (mỗi camera 1 thread, không cần GPU liên tục)
- GCP L4 GPU (12GB VRAM): có thể tăng max_workers lên 4
- Bottleneck thực sự: RAM hệ thống và băng thông mạng khi stream

### Q9: Tại sao dùng SQLite cho dev và PostgreSQL cho production?

**Trả lời:**
- SQLite: không cần cài database server, chạy luôn → tiết kiệm thời gian dev
- PostgreSQL: ACID tốt hơn, concurrent writes, JSON operators mạnh (JSONB)
- GCP Cloud SQL: managed → không cần quản lý backup, scaling
- Dual-mode: `db.py` auto-detect → không cần sửa code khi deploy

### Q10: Phân biệt Precision và Recall, khi nào dùng cái nào?

**Trả lời:**
- **Precision (Độ chính xác):** quan trọng khi FP tốn kém — VD: cảnh báo nhầm làm người lái phản ứng không cần thiết
- **Recall (Độ phủ):** quan trọng khi FN nguy hiểm — VD: bỏ sót người đi bộ có thể gây tai nạn
- **Trong ITS:** Recall thường quan trọng hơn vì bỏ sót nguy hiểm hơn báo nhầm
- **Với SAHI:** ưu tiên tăng Recall người đi bộ (từ 0.42 → 0.75) dù có giảm Precision nhẹ

### Q11: Incident detection có đáng tin không?

**Trả lời:**
- Dựa trên rule-based logic (không phải ML riêng) → có thể false positive
- WRONG_WAY: reliable nhất (angle > 120° rõ ràng)
- STOPPED_VEHICLE: cần ít nhất 5-10 frame để confirm
- ILLEGAL_PARKING: cần 30 giây → rất it false positive
- Anti-spam: 1 incident/loại/track_id → tránh spam database
- Trong thực tế: dùng để alert operator để xác nhận thủ công, không auto-action

### Q12: Tại sao chọn Flask mà không phải FastAPI hay Django?

**Trả lời:**
- **Flask:** lightweight, flexible, tốt cho prototype và project vừa
- **FastAPI:** async/await, tự động tạo OpenAPI docs — nhưng cần hiểu async Python
- **Django:** full-featured (ORM, auth, admin) — quá nặng cho project này
- Flask phù hợp vì: team quen thuộc, đủ tính năng, không cần async (polling thay vì WebSocket)
- Nếu scale: có thể migrate sang FastAPI sau

### Q13: Hệ thống có thể deploy trên edge device (Raspberry Pi, Jetson) không?

**Trả lời:**
- Hiện tại: tối ưu cho server-class GPU (GTX 1060, L4)
- YOLOv11-N (2.6M params): nhỏ nhất trong YOLO family → tiềm năng edge
- Jetson Orin Nano: cần TensorRT quantization (INT8/FP16) → ~5-10x speedup
- Raspberry Pi: không có GPU, chậm (~2-3 fps) nhưng khả thi với YOLOv11-N CPU
- Future work: ONNX export + TensorRT optimization

---

## BẢNG TÓM TẮT CÁC CON SỐ QUAN TRỌNG

| Thông số | Giá trị |
|----------|---------|
| Dataset train | 11,296 ảnh, 406,355 bbox |
| Model parameters | 2.6M |
| Input size | 960×960 (Phase 2) |
| mAP@0.5 (Phase 1) | 0.619 |
| mAP@0.5 (Phase 2) | **0.862** (+39.3%) |
| mAP@0.5:0.95 (Phase 2) | 0.572 (+57.6%) |
| Pedestrian Recall (SAHI) | 0.75 (từ 0.42, +78.6%) |
| Thời gian inference ảnh | 450ms avg (GPU) |
| Thời gian SAHI | 2.1 giây/ảnh |
| Thời gian xử lý video 30s | ~95 giây |
| Unit tests | 31/31 PASS |
| Functional tests | 9/9 PASS |
| API endpoints | ~80 routes |
| Số trang frontend | 8 trang (SPA) |
| Max concurrent video jobs | 2 |
| Tốc độ ngưỡng vi phạm | 70 km/h |
| Thời gian cooldown alert | 30 giây/track |
| Pixel/meter calibration | 8.0 |
| LoS thresholds | LOW: <0.5, MOD: <0.85, HIGH: ≥0.85 |

---

## THUẬT NGỮ KỸ THUẬT

| Tiếng Anh | Tiếng Việt | Giải thích ngắn |
|-----------|-----------|-----------------|
| Fisheye / Barrel distortion | Méo hình thùng | Đường thẳng → đường cong lồi |
| Bounding box (bbox) | Hộp bao | Hình chữ nhật bao quanh vật thể |
| Anchor-free | Không dùng neo | Dự đoán trực tiếp, không cần anchor box định sẵn |
| IoU | Giao/hợp | Tỷ lệ chồng lấp giữa 2 bbox |
| mAP | Trung bình AP | Metric chính đánh giá object detection |
| SAHI | Suy luận chia tile | Chia ảnh → inference từng phần → gộp |
| Fine-tuning | Tinh chỉnh | Train lại model pretrain trên data mới |
| Transfer learning | Học chuyển tiếp | Tận dụng kiến thức đã học từ task khác |
| Inference | Suy luận | Chạy model trên dữ liệu mới (không train) |
| Backbone | Xương sống | Phần extract features của mạng nơ-ron |
| Neck | Cổ | Phần kết hợp multi-scale features |
| Head | Đầu phát hiện | Phần dự đoán bbox và class |
| FPN | Mạng kim tự tháp đặc trưng | Multi-scale feature fusion top-down |
| PAN | Mạng tổng hợp đường dẫn | Multi-scale feature fusion bottom-up |
| Occupancy | Tỷ lệ chiếm dụng | % làn đường bị chiếm |
| LOS | Mức dịch vụ | Cấp độ lưu thông đường bộ |
| ALPR | Nhận dạng biển số tự động | Automatic License Plate Recognition |
| OCR | Nhận dạng ký tự quang học | Optical Character Recognition |
| CRNN | Mạng tích chập hồi quy | CNN + LSTM cho nhận dạng text |
| CTC | Phân loại thời gian kết nối | Decode sequence text từ CRNN |
| SPA | Ứng dụng một trang | Single-Page Application |
| REST API | API kiểu nghỉ ngơi | Representational State Transfer |
| WSGI | Giao diện cổng web Python | Web Server Gateway Interface |
| Docker | Công cụ container hóa | Đóng gói app + dependencies vào container |
| CI/CD | Tích hợp/Triển khai liên tục | Continuous Integration/Continuous Deployment |
| WAL | Ghi trước nhật ký | Write-Ahead Logging (SQLite concurrency) |
| WIF | Liên kết danh tính khối lượng | Workload Identity Federation (GCP auth) |

---

*Tài liệu được tổng hợp từ toàn bộ source code và documentation của project. Cập nhật: 18/06/2026.*
