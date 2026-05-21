# Các vấn đề còn tồn tại

File này tổng hợp các vấn đề còn tồn tại của `fisheye_demo` theo trạng thái code hiện tại, không dựa trên mục tiêu kỳ vọng.

## P0 - Live stream ngoài chưa phải live stream thật

- Trạng thái hiện tại:
  `External Camera Live` mới là polling snapshot theo chu kỳ, không phải decode video stream liên tục.
- Bằng chứng trong code:
  [external_camera_detector.py](external_camera_detector.py#L58) dùng `download_camera_snapshot()`.
  [app.py](app.py#L1229) trong `ExternalCameraLiveMonitor._worker_loop` gọi `run_external_camera_pipeline(... persist_result=False)`, mà pipeline này lấy ảnh snapshot rồi detect.
- Ảnh hưởng:
  Người dùng thấy “live” nhưng thực tế chỉ là ảnh tĩnh cập nhật theo chu kỳ vài giây.
  Không thể render video annotated liên tục theo frame.
- Hướng xử lý:
  Tách URL stream thật từ YouTube/live source.
  Dùng `yt-dlp` hoặc nguồn stream trực tiếp để lấy media URL.
  Dùng `ffmpeg`, OpenCV, hoặc pipeline HLS/WebRTC để đọc frame liên tục và xuất annotated stream.

## P0 - Phụ thuộc mạnh vào HTML của website ngoài

- Trạng thái hiện tại:
  Việc tách camera dựa vào regex quét `iframe` trong HTML của trang nguồn.
- Bằng chứng trong code:
  [external_camera_detector.py](external_camera_detector.py#L31) dùng regex `re.findall(...)` để lấy `iframe`.
- Ảnh hưởng:
  Chỉ cần website đổi DOM, đổi kiểu embed, lazy-load khác, hoặc thêm anti-bot thì toàn bộ pipeline camera ngoài sẽ hỏng.
- Hướng xử lý:
  Ưu tiên tích hợp từ nguồn stream ổn định hơn.
  Nếu vẫn phải scrape web, cần parser bền hơn và fallback logic rõ ràng.

## P0 - Không có endpoint stream video annotated thật

- Trạng thái hiện tại:
  Hệ thống chỉ trả ảnh base64, artifact ảnh/video file, và trạng thái in-memory.
  Không có endpoint như MJPEG, HLS, WebRTC để xem live detect ngay trong UI.
- Bằng chứng trong code:
  Hiện chỉ có `GET/POST /api/external-camera/live/*` và `POST /api/external-camera/detect` trong [app.py](app.py#L1454) trở đi, không có route streaming frame-by-frame.
- Ảnh hưởng:
  UI không thể hiển thị “camera live detect” đúng nghĩa.
- Hướng xử lý:
  Thêm `/stream/<camera_id>` kiểu MJPEG hoặc HLS output riêng cho mỗi camera.

## P1 - Distortion cho camera ngoài vẫn dùng preset chung, chưa hiệu chuẩn theo từng camera

- Trạng thái hiện tại:
  Đã có preset `traffic_camera`, tâm méo lệch và elip, nhưng vẫn là một bộ tham số mặc định dùng chung cho tất cả camera ngoài.
- Bằng chứng trong code:
  [fisheye.py](fisheye.py#L23) có mapping `traffic_camera`.
  [app.py](app.py#L249) đến [app.py](app.py#L285) chỉ có một nhóm config `FISHEYE_CAMERA_*` / `camera_fisheye_*` dùng chung.
- Ảnh hưởng:
  Các camera có góc đặt khác nhau sẽ bị warp chưa đúng, làm giảm chất lượng detect.
- Hướng xử lý:
  Tạo calibration profile riêng theo từng camera ID hoặc từng nguồn.
  Cho phép lưu `center_x`, `center_y`, `axis_scale_x`, `axis_scale_y`, `strength`, `radius`, `effect` theo camera.

## P1 - Live monitor chỉ giữ kết quả trong RAM

- Trạng thái hiện tại:
  Live monitor giữ `last_result` trong memory và không persist mỗi chu kỳ.
- Bằng chứng trong code:
  [app.py](app.py#L1148) `status_snapshot()` trả state in-memory.
  [app.py](app.py#L1239) cập nhật `last_result` sau mỗi vòng pipeline, nhưng không ghi artifact theo vòng lặp live.
- Ảnh hưởng:
  Restart server là mất toàn bộ trạng thái live.
  Không có lịch sử live để audit hoặc so sánh.
- Hướng xử lý:
  Lưu snapshot định kỳ, hoặc lưu sampling theo khoảng thời gian cấu hình được.
  Có thể thêm chế độ chỉ lưu khi vượt ngưỡng thay đổi số lượng object.

## P1 - Chạy background monitor theo thread trong Flask, chưa phù hợp để mở rộng

- Trạng thái hiện tại:
  Live monitor chạy bằng `threading.Thread` ngay trong process Flask.
- Bằng chứng trong code:
  [app.py](app.py#L1183) tạo thread `external-camera-live-monitor`.
- Ảnh hưởng:
  Khi deploy multi-worker hoặc restart process, trạng thái monitor có thể lệch.
  Không phù hợp cho scale-out hoặc quản lý job ổn định.
- Hướng xử lý:
  Tách live processing sang worker/service riêng.
  Dùng queue/job runner hoặc process manager riêng cho long-running tasks.

## P1 - Giao diện có thể gây hiểu nhầm giữa “live monitor” và “live stream”

- Trạng thái hiện tại:
  UI ghi `Start live`, `Stop live`, `Refresh live`, nhưng backend hiện chỉ là near-real-time snapshot polling.
- Bằng chứng trong code:
  [templates/index.html](templates/index.html#L936) đến [templates/index.html](templates/index.html#L938) dùng nhãn `Start live`, `Stop live`, `Refresh live`.
- Ảnh hưởng:
  Người dùng kỳ vọng xem video live thật, nhưng hệ thống chỉ cập nhật ảnh.
- Hướng xử lý:
  Đổi nhãn UI thành `Start live polling` hoặc `Start snapshot monitor` cho đến khi có stream thật.

## P1 - Tích hợp camera ngoài chưa có test end-to-end thật

- Trạng thái hiện tại:
  Test hiện tại chủ yếu mock `extract_camera_entries`, `download_camera_snapshot`, `run_inference` (và collage); luồng live start/stop mock trực tiếp `live_monitor.start` / `stop`.
- Bằng chứng trong code:
  [tests/test_app.py](tests/test_app.py#L175) trở đi (`test_external_camera_detect_returns_200`); live API xem [tests/test_app.py](tests/test_app.py#L233) trở đi.
- Ảnh hưởng:
  Test pass nhưng chưa đảm bảo website ngoài vẫn hoạt động thật, thumbnail vẫn tải được thật, hoặc model vẫn detect ổn trên dữ liệu thật.
- Hướng xử lý:
  Bổ sung smoke test tùy chọn cho môi trường có mạng.
  Tách integration test riêng, không chạy mặc định trong CI nếu nguồn ngoài không ổn định.

## P2 - Video detect và convert vẫn chạy đồng bộ trong request

- Trạng thái hiện tại:
  Detect video và convert video vẫn xử lý trong vòng đời request HTTP.
- Bằng chứng trong code:
  [app.py](app.py#L1570) `run_video_detect(...)` trong `POST /api/detect` khi upload video; [app.py](app.py#L1727) `convert_video_to_fisheye(...)` trong `POST /api/convert`.
- Ảnh hưởng:
  Video dài sẽ chiếm request lâu, dễ timeout, tốn tài nguyên và kém phù hợp khi có nhiều người dùng đồng thời.
- Hướng xử lý:
  Tách sang background job.
  Trả job id và polling trạng thái.

## P2 - Chưa có bảo vệ truy cập và rate limiting

- Trạng thái hiện tại:
  Các API detect, convert, live start/stop đều mở trực tiếp.
- Bằng chứng trong code:
  Các route công khai trong `create_app` (ví dụ [app.py](app.py#L1454) `/api/external-camera/...`, [app.py](app.py#L1537) `/api/detect`, [app.py](app.py#L1678) `/api/convert`) không có auth, API key, session gate, hay rate limit.
- Ảnh hưởng:
  Dễ bị lạm dụng tài nguyên inference hoặc bị gọi lặp gây nghẽn máy.
- Hướng xử lý:
  Thêm authentication tối thiểu và rate limit theo IP hoặc token.

## P2 - Tài liệu hiện có chưa phân biệt rõ các mức “snapshot”, “live polling”, và “true live stream”

- Trạng thái hiện tại:
  Hệ thống đã có nhiều chế độ camera ngoài, nhưng naming và giải thích chức năng chưa đủ sắc nét cho người dùng không kỹ thuật.
- Ảnh hưởng:
  Người dùng dễ hiểu nhầm khả năng hiện tại của hệ thống.
- Hướng xử lý:
  Cập nhật README, OVERVIEW, SYSTEM_OVERVIEW để phân biệt rõ:
  `single snapshot detect`
  `periodic live monitor`
  `true video live stream` (chưa có)

## Ưu tiên xử lý và đề xuất phát triển hệ thống

1. Làm rõ UI và tài liệu rằng live hiện tại là snapshot polling, không phải stream thật.
2. Xây pipeline stream thật cho camera ngoài.
3. Tách calibration distortion theo từng camera.
4. Chuyển live/video workload sang background worker riêng.
5. Bổ sung integration test và kiểm soát truy cập.
