# System Report

## 1. Tong quan

`fisheye_demo` la he thong Flask phuc vu detect object giao thong tren:

- anh fisheye
- anh giao thong thuong sau khi be cong fisheye
- video
- external camera

He thong hien tai co 2 nhom van hanh chinh:

- `local`: chay bang `python app.py`
- `deploy`: chay bang Docker + `gunicorn`

## 2. Chuc nang hien tai

He thong hien dang ho tro:

1. Detect tren anh fisheye.
2. Detect tren anh thuong sau khi preprocess sang fisheye.
3. Detect tren video va xuat `annotated.mp4`.
4. Convert anh/video sang fisheye.
5. Detect external camera one-shot.
6. Live detect external camera.

## 3. Thanh phan chinh

- `app.py`
  - Flask app chinh
  - route API
  - model registry
  - orchestration detect / convert / external camera
- `fisheye.py`
  - xu ly fisheye transform
- `video_detect.py`
  - detect video theo frame
- `external_camera_detector.py`
  - xu ly external camera snapshot / stream
- `recent_image_store.py`
  - SQLite recent image store
- `templates/index.html`
  - giao dien web

## 4. Model hien tai

He thong da duoc dieu chinh de chi giu checkpoint chinh:

- `traffic.pt`

Checkpoint nay la model duoc expose de detect.
Fallback noi bo van co the dung `yolo11n.pt` neu can de tranh vo app khi thieu file model chinh.

## 5. Storage hien tai

He thong hien tai dung:

- `static/results/`
  - artifact detect / convert
- `static/uploads/`
  - file upload tam
- `recent_images.sqlite3`
  - gallery nhanh cho anh ket qua gan nhat

Moi run thanh cong thuong tao:

- `metadata.json`
- artifact image/video tuong ung

## 6. Runtime local

Che do local hien tai:

- 1 Flask process
- model load truc tiep trong app
- artifact luu local disk
- recent image luu SQLite local
- external live chay bang background thread

Phu hop cho:

- dev
- debug
- demo
- nghien cuu

## 7. Runtime deploy

Che do deploy hien tai:

- Docker image tu `deploy/Dockerfile`
- chay qua `wsgi:app`
- serve bang `gunicorn`
- ho tro `docker-compose.local.yml`
- ho tro `docker-compose.prod.yml`

Production baseline hien tai da ho tro external camera `stream mode`.

## 8. External camera

He thong hien tai ho tro 2 che do external camera:

- `snapshot mode`
  - phu hop local / page camera kieu cu
- `stream mode`
  - phu hop deploy
  - mo stream truc tiep bang OpenCV
  - live detect infer tren frame moi thay vi polling snapshot JPEG

Bien moi truong deploy lien quan:

- `FISHEYE_EXTERNAL_CAMERA_SOURCE_MODE`
- `FISHEYE_EXTERNAL_CAMERA_STREAM_URL`

## 9. API chinh

- `GET /api/health`
- `GET /api/config`
- `GET /api/history`
- `GET /api/stats`
- `POST /api/detect`
- `POST /api/convert`
- `POST /api/external-camera/detect`
- `POST /api/external-camera/live/start`
- `POST /api/external-camera/live/stop`
- `GET /api/external-camera/live/stream`

## 10. Danh gia hien trang

Diem manh:

- workflow image / video / external camera da day du
- co UI web
- co artifact history
- co local mode va deploy mode
- deploy da ho tro stream cho external camera

Han che:

- app van theo huong monolithic
- detect video van synchronous
- live monitor van nam trong process web
- filesystem + SQLite van la state chinh
- chua co queue, Postgres, Redis, object storage, auth

## 11. Tai lieu lien quan

- `README.md`
- `SYSTEM_OVERVIEW.md`
- `SYSTEM_LOCAL.md`
- `SYSTEM_DEPLOY.md`
- `SYSTEM_ARCHITECH.md`

