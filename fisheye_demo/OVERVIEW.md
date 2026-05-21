# Full System Overview

## 1. Muc tieu

`fisheye_demo` la mot he thong web nho cho bai toan giao thong, tap trung vao 3 kha nang:

- detect doi tuong tren anh fisheye,
- detect doi tuong tren anh hoac video thuong sau khi bien dang sang fisheye,
- convert anh hoac video thuong sang fisheye de dung cho pipeline khac.

He thong hien tai khong can database va khong can queue job. Toan bo du lieu duoc luu bang artifact file va `metadata.json`.

## 2. He thong gom nhung gi

He thong gom 6 khoi chinh:

1. Flask backend
   - route API
   - runtime config
   - model registry
   - artifact management

2. Frontend 1 trang
   - upload media
   - detect / convert
   - dashboard stats
   - history

3. Fisheye transformation
   - inverse mapping
   - bilinear interpolation
   - cac profile distortion

4. YOLO inference runtime
   - nap checkpoint
   - infer tren image
   - infer tren tung frame video

5. Artifact storage
   - luu image/video output
   - luu preview
   - luu metadata

6. Test layer
   - test route
   - test alias field
   - test video detect
   - test dashboard stats

## 3. Cau truc thu muc

```text
fisheye_demo/
|-- app.py
|-- fisheye.py
|-- video_detect.py
|-- demo.py
|-- README.md
|-- OVERVIEW.md
|-- SYSTEM_OVERVIEW.md
|-- INSTALLATION_AND_USAGE.md
|-- .env.example
|-- requirements.txt
|-- yolo11n.pt
|-- __init__.py
|-- .streamlit/
|   `-- config.toml
|-- templates/
|   `-- index.html
|-- static/
|   |-- uploads/
|   `-- results/
`-- tests/
    |-- __init__.py
    `-- test_app.py
```

## 4. Vai tro tung file quan trong

### `app.py`

Entry point chinh cua he thong Flask.

Trach nhiem:

- tao app,
- doc `.env`,
- tao `AppSettings`,
- nap model qua `ModelRegistry`,
- xu ly request detect / convert,
- sinh JSON response,
- luu artifact va metadata,
- tong hop dashboard stats.

Route chinh hien co:

- `GET /`
- `GET /api/config`
- `GET /api/health`
- `GET /api/classes`
- `GET /api/history`
- `GET /api/history/<result_id>`
- `GET /api/stats`
- `GET /api/artifacts/<result_id>/<filename>`
- `POST /api/detect`
- `POST /api/convert`
- `POST /detect`

### `fisheye.py`

Mo dun bien dang image sang fisheye.

Trach nhiem:

- dinh nghia cac mode `standard`, `extreme`, `subtle`,
- noi suy bilinear,
- ap dung barrel distortion tren anh PIL.

Ham trung tam:

- `apply_fisheye(image, strength, radius, effect)`

### `video_detect.py`

Mo dun detect tren video.

Trach nhiem:

- doc frame bang OpenCV,
- tuy chon be cong fisheye moi frame,
- goi model YOLO moi frame,
- ve bbox,
- xuat `annotated.mp4`,
- luu `preview_annotated.jpg`,
- tra summary tong hop.

Ham trung tam:

- `run_video_detect(...)`

### `templates/index.html`

Frontend cua he thong.

Trach nhiem:

- upload image/video,
- detect image/video,
- convert image/video,
- hien thi ket qua,
- render dashboard stats bang Canvas API,
- hien thi recent runs,
- refresh health / history / stats.

### `tests/test_app.py`

Bo test route chinh.

Bao phu:

- health
- config
- history
- stats
- detect image
- detect video
- convert image
- alias `file`
- alias `confidence`

### `demo.py`

Streamlit demo cu.

Hien tai:

- van co the chay rieng,
- khong phai entry point chinh,
- chi nen xem la giao dien phu hoac tai nguyen demo cu.

## 5. Runtime configuration

He thong ho tro 2 nhom config:

### 5.1 Bien moi truong chinh

- `FISHEYE_DEFAULT_CONF`
- `FISHEYE_DEFAULT_IOU`
- `FISHEYE_DEVICE`
- `FISHEYE_RESULTS_DIR`
- `FISHEYE_MODEL_PATH`
- `FISHEYE_DEFAULT_STRENGTH`
- `FISHEYE_DEFAULT_RADIUS`
- `FISHEYE_DEFAULT_EFFECT`
- `FISHEYE_PRELOAD_MODEL`
- `FISHEYE_MAX_VIDEO_SECONDS`

### 5.2 Alias de tuong thich

- `CONFIDENCE_THRESHOLD`
- `IOU_THRESHOLD`
- `DEVICE`
- `ARTIFACT_DIR`
- `FISHEYE_STRENGTH`
- `FISHEYE_RADIUS`
- `FISHEYE_EFFECT`

### 5.3 Thu tu uu tien config

1. `SETTINGS_OVERRIDES` khi tao app
2. environment variables hien co
3. file `.env`
4. gia tri mac dinh trong code

## 6. Cach chon model

`ModelRegistry` tim checkpoint trong:

- thu muc project goc,
- thu muc `fisheye_demo`,
- hoac duong dan do `FISHEYE_MODEL_PATH` chi dinh.

Uu tien model theo ten:

- chua `fisheye`
- chua `best`
- chua `resume`
- chua `yolo11`

Neu khong co model custom:

- fallback sang `yolo11n.pt`

## 7. Luong nghiep vu chinh

### 7.1 Detect image fisheye

1. upload anh
2. `POST /api/detect`
3. backend doc anh
4. bo qua preprocessing neu `source_layout=fisheye`
5. YOLO infer
6. luu `original.jpg`, `annotated.jpg`, `metadata.json`
7. tra JSON ket qua cho UI

### 7.2 Detect image thuong sau khi be cong

1. upload anh thuong
2. `POST /api/detect`
3. tinh preprocessing options
4. ap dung `apply_fisheye(...)`
5. YOLO infer tren anh da bien dang
6. luu `original.jpg`, `preprocessed.jpg`, `annotated.jpg`, `metadata.json`
7. tra JSON ket qua cho UI

### 7.3 Convert image sang fisheye

1. upload anh
2. `POST /api/convert`
3. ep preprocessing bat
4. ap dung fisheye
5. luu `original.jpg`, `fisheye.jpg`, `metadata.json`
6. tra preview va artifact link

### 7.4 Convert video sang fisheye

1. upload video
2. `POST /api/convert`
3. luu file tam vao `static/uploads`
4. doc frame bang OpenCV
5. ap dung fisheye tung frame
6. ghi `fisheye.mp4`
7. luu preview frame dau
8. copy artifact vao `static/results/<result_id>/`
9. xoa file tam

### 7.5 Detect video

1. upload video
2. `POST /api/detect`
3. luu file tam vao `static/uploads`
4. kiem tra do dai video
5. nap model
6. doc tung frame
7. tuy chon be cong fisheye moi frame
8. infer YOLO tung frame
9. ve bbox va ghi `annotated.mp4`
10. luu `preview_annotated.jpg`
11. sinh `metadata.json`
12. xoa file tam

## 8. API behavior

### `GET /api/health`

Tra ve:

- status server
- model status
- device
- results dir
- so run gan day

### `GET /api/config`

Tra ve:

- class names
- class colors
- default thresholds
- default fisheye config
- supported source layouts
- supported media extensions
- limit config

### `GET /api/history`

Tra ve danh sach run da luu.

Moi run thuong co:

- `id`
- `task`
- `media_type`
- `summary`
- `artifacts`
- `artifact_urls`

### `GET /api/stats`

Tong hop thong ke tu `metadata.json`:

- tong run
- tong detect run
- tong convert run
- class distribution
- avg inference

### `POST /api/detect`

Chap nhan:

- image file
- video file
- field `image` hoac `file`
- `conf` hoac `confidence`
- `iou`
- `source_layout`
- `apply_fisheye`
- `fisheye_strength`
- `fisheye_radius`
- `fisheye_effect`

### `POST /api/convert`

Chap nhan:

- `media`
- `file`
- `image`
- `video`

Route nay chi convert, khong detect.

## 9. Artifact storage

Moi run tao mot thu muc:

```text
static/results/<result_id>/
```

Tuy loai task, artifact co the gom:

- `original.jpg`
- `preprocessed.jpg`
- `annotated.jpg`
- `fisheye.jpg`
- `annotated.mp4`
- `original.mp4`
- `fisheye.mp4`
- `preview_original.jpg`
- `preview_fisheye.jpg`
- `preview_annotated.jpg`
- `metadata.json`

## 10. Metadata structure

`metadata.json` la nguon su that cua moi run.

No thuong gom:

- `id`
- `task`
- `media_type`
- `filename`
- `created_at`
- `source_layout`
- `preprocessing`
- `parameters`
- `summary`
- `model`
- `detections` neu la detect image
- `artifacts`

## 11. Dashboard stats

Dashboard tren trang chu hien lay du lieu tu `GET /api/stats`.

No khong can:

- database
- chart library
- frontend framework

No su dung:

- `metadata.json` tu `static/results`
- Canvas API thuần

Dashboard hien hien thi:

- tong so run
- tong detect run
- tong convert run
- avg inference
- bar chart phan bo class detect

## 12. Frontend behavior

Frontend hien theo kieu single-page dashboard.

No co cac nhom chuc nang:

- upload va preview media
- dieu chinh threshold va fisheye params
- detect
- convert
- summary ket qua hien tai
- dashboard thong ke he thong
- recent runs

Sau moi detect hoac convert thanh cong, frontend tu load lai:

- `loadHistory()`
- `loadHealth()`
- `loadStats()`

## 13. Gioi han hien tai

- Video detect va video convert dang xu ly dong bo trong request.
- Chua co queue job hoac background worker.
- Chua co database.
- Chua co auth.
- Frontend van la 1 file HTML/JS lon.
- `demo.py` va `app.py` cung ton tai song song.

## 14. Tradeoff hien tai

### Don gian

He thong de chay, de copy, de demo, de debug.

### De mo rong vua phai

Code dang o muc co the mo rong tiep, nhung chua tach thanh package nho.

### Khong toi uu cho production lon

Video dai van co nguy co timeout va su dung CPU/GPU lon trong 1 request.

## 15. Huong mo rong hop ly tiep theo

1. Background jobs cho video dai
2. Video detect + annotated tracking info nang hon
3. Tach `app.py` thanh `routes`, `services`, `storage`, `config`
4. Tach JS/CSS ra khoi `index.html`
5. Dong bo hoac retire `demo.py`
6. Them auth neu can chia se ra ngoai

## 16. Thu tu nen doc neu moi vao du an

1. `README.md`
2. `OVERVIEW.md`
3. `INSTALLATION_AND_USAGE.md`
4. `SYSTEM_OVERVIEW.md`
5. `app.py`
6. `fisheye.py`
7. `video_detect.py`
8. `templates/index.html`
9. `tests/test_app.py`

## 17. File overview nay dung de lam gi

File nay dung lam diem vao tong hop cho nguoi moi:

- hieu he thong dang co gi,
- route nao quan trong,
- data luu o dau,
- detect va convert khac nhau the nao,
- dashboard thong ke lay du lieu tu dau,
- va he thong dang manh / yeu o diem nao.
