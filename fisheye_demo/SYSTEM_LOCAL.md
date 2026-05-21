# System Local

## 1. Pham vi

Tai lieu nay mo ta he thong `fisheye_demo` khi chay o che do local:

- dev machine
- may demo
- may nghien cuu
- single-user hoac it user

Muc tieu la mo ta dung runtime hien tai cua codebase, khong mo ta kien truc production ly tuong.

## 2. Runtime local hien tai

He thong local hien tai chay theo mo hinh 1 process Flask:

- start bang `python app.py`
- phuc vu UI va API trong cung process
- model YOLO duoc load truc tiep trong app
- artifact duoc luu vao filesystem
- recent images duoc luu vao SQLite local
- live external camera duoc xu ly bang background thread trong process Flask

Entry point local:

- `app.py`

Frontend local:

- `templates/index.html`

## 3. Thanh phan chinh

### Backend local

- `app.py`
  - route API
  - config runtime
  - model registry
  - detect / convert orchestration
  - history, stats, recent images
  - external camera live state

### Media processing

- `fisheye.py`
  - fisheye transform
- `video_detect.py`
  - detect video theo frame
- `external_camera_detector.py`
  - parse nguon camera ngoai, tai snapshot, build overview

### Storage local

- `static/results/`
  - artifact detect / convert
- `static/uploads/`
  - file upload tam, nhat la video
- `recent_images.sqlite3`
  - gallery nhanh cho anh ket qua gan nhat

### Test local

- `tests/test_app.py`

## 4. Cau truc luu tru local

### 4.1 Artifact run

Moi request detect hoac convert thanh cong tao:

```text
static/results/<result_id>/
```

Trong do co the co:

- `metadata.json`
- `original.jpg`
- `preprocessed.jpg`
- `annotated.jpg`
- `fisheye.jpg`
- `annotated.mp4`
- `fisheye.mp4`
- `preview_annotated.jpg`
- `preview_fisheye.jpg`
- `overview_annotated.jpg`

### 4.2 Recent image store

File DB local:

```text
recent_images.sqlite3
```

Vai tro:

- giu gallery nhanh
- luu anh dai dien cho detect / convert / external camera
- prune theo `FISHEYE_RECENT_IMAGE_LIMIT`, mac dinh `100`

## 5. Workflow local

### 5.1 Detect image

1. Upload image vao UI hoac `POST /api/detect`.
2. App validate file.
3. Tuy option, app co the apply fisheye preprocess.
4. App load checkpoint da chon va infer.
5. App luu artifact + metadata.
6. App them anh dai dien vao recent image store.

### 5.2 Detect video

1. Upload video.
2. App luu file tam vao `static/uploads/`.
3. Kiem tra thoi luong video.
4. `video_detect.py` doc frame, preprocess neu can, infer tung frame.
5. Tao `annotated.mp4` + preview.
6. Luu metadata va update recent image store.
7. Xoa file tam.

### 5.3 Convert image / video

1. Client goi `POST /api/convert`.
2. App bat preprocessing bat buoc.
3. Neu la image, tao `fisheye.jpg`.
4. Neu la video, tao `fisheye.mp4`.
5. Luu metadata va preview neu co.

### 5.4 External camera detect

1. Client goi `POST /api/external-camera/detect`.
2. App parse source page de lay camera.
3. App tai snapshot.
4. App apply profile fisheye camera.
5. App infer tung camera.
6. App tao `overview_annotated.jpg`.
7. App luu metadata va recent image.

### 5.5 External camera live

1. Client goi `POST /api/external-camera/live/start`.
2. App tao background worker thread.
3. Worker loop:
   - tai snapshot
   - preprocess
   - infer
   - dong goi JPEG stream
   - cap nhat state trong RAM
4. UI doc status va stream qua API.

## 6. Checkpoint va model local

Hien tai local system cho phep chon checkpoint trong UI khi detect.

Nguon model:

- cac file `.pt` trong thu muc workspace goc
- cac file `.pt` trong thu muc `fisheye_demo`
- hoac duong dan chi dinh boi `FISHEYE_MODEL_PATH`

He thong co:

- danh sach checkpoint cho phep chon
- fallback noi bo sang `yolo11n.pt` neu can

Metadata cua moi run se ghi lai thong tin model da dung.

## 7. Config local quan trong

Thu tu uu tien config:

1. `SETTINGS_OVERRIDES`
2. environment variables
3. `.env`
4. default trong code

Bien moi truong local hay dung:

- `FISHEYE_UPLOAD_DIR`
- `FISHEYE_RESULTS_DIR`
- `FISHEYE_RECENT_IMAGE_DB`
- `FISHEYE_RECENT_IMAGE_LIMIT`
- `FISHEYE_DEFAULT_CONF`
- `FISHEYE_DEFAULT_IOU`
- `FISHEYE_DEVICE`
- `FISHEYE_MODEL_PATH`
- `FISHEYE_PRELOAD_MODEL`
- `FISHEYE_MAX_VIDEO_SECONDS`
- `FISHEYE_EXTERNAL_CAMERA_URL`

## 8. API local

Core API:

- `GET /`
- `GET /api/health`
- `GET /api/config`
- `GET /api/classes`
- `GET /api/history`
- `GET /api/history/<result_id>`
- `GET /api/stats`
- `GET /api/recent-images`
- `GET /api/recent-images/<image_id>`
- `GET /api/artifacts/<result_id>/<filename>`
- `POST /api/detect`
- `POST /api/convert`

External camera API:

- `GET /api/external-camera/source`
- `POST /api/external-camera/detect`
- `GET /api/external-camera/live/status`
- `GET /api/external-camera/live/stream`
- `POST /api/external-camera/live/start`
- `POST /api/external-camera/live/stop`

## 9. Cach chay local

### Python local

```powershell
cd C:\Using\NCKH\fisheye_demo
python app.py
```

Mo:

```text
http://127.0.0.1:5000
```

### Test local

```powershell
cd C:\Using\NCKH
py -3.10 -m unittest discover -s fisheye_demo\tests -t .
```

## 10. Gioi han local hien tai

1. `app.py` van la file lon, gom nhieu trach nhiem.
2. Detect video va convert video dang xu ly dong bo trong request.
3. Live external camera dung background thread noi bo.
4. History va stats van quet filesystem + `metadata.json`.
5. SQLite recent image store chi phu hop local hoac single-host.
6. Chua co auth, rate limit, queue, object storage, hay DB trung tam.
7. External camera phu thuoc vao nguon HTML/snapshot ben ngoai nen co the vo.

## 11. Khi nao nen dung local system

Dung local system khi:

- can code va debug nhanh
- can test checkpoint moi
- can demo workflow image / video
- can doi preprocess va so sanh ket qua
- can nghien cuu behavior truoc khi dong goi deploy

