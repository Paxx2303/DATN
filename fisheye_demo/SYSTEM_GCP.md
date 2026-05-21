# Hướng dẫn deploy hệ thống lên Google Cloud Platform (GCP)

Tài liệu này hướng dẫn chi tiết cách deploy hệ thống `fisheye_demo` lên Google Compute Engine (GCE) có hỗ trợ GPU NVIDIA L4 phục vụ xử lý YOLOv11 hiệu năng cao.

## 1. Chuẩn bị (Prerequisites)

1. **Google Cloud Account**: Đã kích hoạt liên kết thẻ thanh toán (Billing Account).
2. **GPU Quotas (Nếu chạy GPU)**:
   - Truy cập vào **IAM & Admin > Quotas & System Limits** trong Google Cloud Console.
   - Tìm kiếm `GPUS_ALL_REGIONS` hoặc `NVIDIA_L4_GPUS` để kiểm tra xem bạn có hạn mức quota tối thiểu là `1` hay không.
   - Nếu quota hiện tại bằng `0`, bạn cần gửi yêu cầu tăng hạn mức lên `1` (Request Increase) để có thể tạo được VM có GPU.
   - *Lưu ý*: Nếu không muốn mất phí GPU hoặc chưa được duyệt quota, bạn có thể chuyển cấu hình sang chạy CPU (xem mục cấu hình CPU ở dưới).

---

## 2. Deploy tự động qua Google Cloud Shell

Đây là phương thức deploy đơn giản nhất vì Google Cloud Shell đã cài đặt sẵn `gcloud` SDK, Git và Docker, giúp bạn không cần thiết lập gì tại máy tính cá nhân.

### Bước 1: Mở Google Cloud Shell
- Đăng nhập vào [Google Cloud Console](https://console.cloud.google.com/).
- Nhấp vào biểu tượng **Activate Cloud Shell** ở góc trên cùng bên phải thanh menu.

### Bước 2: Tải code lên Cloud Shell
Bạn có thể upload thư mục code hiện tại trực tiếp lên Cloud Shell:
- Trong thanh điều khiển của Cloud Shell, chọn nút menu ba chấm hoặc bánh răng và chọn **Upload**.
- Chọn file zip của dự án hoặc thư mục `fisheye_demo` để tải lên.
*(Hoặc clone repository của bạn từ Git)*

### Bước 3: Di chuyển vào thư mục dự án
```bash
cd fisheye_demo
```

### Bước 4: Chạy script deploy tự động
Đảm bảo script deploy có quyền thực thi và chạy nó:
```bash
chmod +x deploy/deploy_gcp.sh
./deploy/deploy_gcp.sh
```

Script sẽ thực hiện tự động các công việc sau:
1. Thiết lập GCP project (`project-ef8a8694-e33d-4954-ad1`).
2. Kích hoạt API Google Compute Engine.
3. Tạo máy ảo GCE VM (`fisheye-gpu-instance`) với hệ điều hành Ubuntu 22.04 LTS và 1 GPU NVIDIA L4.
4. Cấu hình script startup tự động cài đặt:
   - Docker & Docker Compose
   - Drivers GPU NVIDIA CUDA 535
   - NVIDIA Container Toolkit (để Docker có thể sử dụng GPU).
5. Mở cổng tường lửa port `5000` trên GCP.
6. Đóng gói mã nguồn & các weights model (`traffic.pt`, `yolo11_fisheye_v5_best.pt`, `sahi.pt`, `yolo11n.pt`) từ Cloud Shell để upload trực tiếp lên VM.
7. Chờ VM cài đặt xong các driver rồi khởi chạy Docker Compose production stack.
8. Trả về địa chỉ IP của VM.

---

## 3. Cấu hình chạy CPU (Nếu không dùng GPU)

Nếu bạn không được duyệt quota GPU hoặc muốn giảm chi phí tối đa (chạy CPU có giá ~25$/tháng so với ~700$/tháng khi có GPU):

1. **Sửa file `deploy/deploy_gcp.sh`**:
   - Đổi `MACHINE_TYPE` thành `e2-standard-2` hoặc `e2-medium`.
   - Xóa bỏ dòng tham số `--accelerator="${ACCELERATOR}" \`.
   - Sửa phần script startup: Có thể bỏ phần cài đặt NVIDIA drivers và NVIDIA Container Toolkit để tăng tốc khởi động VM.
2. **Sửa file `deploy/docker-compose.prod.yml`**:
   - Đổi `FISHEYE_DEVICE` từ `0` thành `cpu`.
   - Đổi `BASE_IMAGE` thành `python:3.10-slim`.
   - Xóa bỏ block `deploy.resources.reservations` liên quan đến GPU nvidia.

---

## 4. Quản lý hệ thống sau khi deploy

### Truy cập ứng dụng
Sau khi deploy thành công, bạn truy cập hệ thống qua địa chỉ:
```text
http://<VM_PUBLIC_IP>:5000
```

### Tiết kiệm chi phí (Quan trọng)
GPU NVIDIA L4 tính phí theo giờ chạy (~1.2$ - 1.5$/giờ). Để tiết kiệm chi phí khi không sử dụng/demo:
- **Tắt VM**: Khi không cần demo, hãy truy cập Compute Engine console hoặc chạy lệnh sau từ Cloud Shell để tắt VM:
  ```bash
  gcloud compute instances stop fisheye-gpu-instance --zone=asia-southeast1-b
  ```
- **Bật lại VM**: Khi cần sử dụng lại:
  ```bash
  gcloud compute instances start fisheye-gpu-instance --zone=asia-southeast1-b
  ```
  *(Lưu ý: Khi bật lại, các container Docker sẽ tự động khởi chạy lại nhờ chính sách `restart: unless-stopped` trong docker compose)*.

---

## 5. Troubleshooting (Sửa lỗi thường gặp)

### 1. Kiểm tra log cài đặt ban đầu của VM
Quá trình cài đặt driver NVIDIA và Docker diễn ra ngầm khi VM boot lần đầu và mất khoảng 3-5 phút. Bạn có thể xem tiến trình cài đặt bằng cách SSH vào VM và xem log:
```bash
gcloud compute ssh fisheye-gpu-instance --zone=asia-southeast1-b
tail -f /var/log/gce-startup.log
```
Nếu dòng cuối hiển thị `=== VM Initialization Finished successfully ===` thì quá trình cài đặt đã hoàn thành.

### 2. Kiểm tra container hoạt động
Sau khi SSH vào VM:
```bash
cd ~/fisheye_app
sudo docker compose -f deploy/docker-compose.prod.yml ps
sudo docker compose -f deploy/docker-compose.prod.yml logs -f fisheye-web
```

### 3. Kiểm tra GPU bên trong container
Để kiểm tra xem container đã nhận diện được GPU thành công chưa:
```bash
sudo docker exec -it $(sudo docker ps -qf "name=fisheye-web") nvidia-smi
```
Nếu lệnh trả ra bảng trạng thái NVIDIA L4 GPU thì hệ thống AI đang tăng tốc phần cứng cực kỳ hoàn hảo.
