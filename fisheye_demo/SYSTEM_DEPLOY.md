# System Deploy

## 1. Pham vi

Tai lieu nay mo ta he thong `fisheye_demo` khi dong goi va chay o che do deploy hien tai.

Deploy o day duoc hieu la:

- build image Docker
- chay app qua `gunicorn`
- dung `docker compose` de khoi dong
- luu artifact va data qua volume / bind mount

Day la deploy baseline hien tai cua repo, chua phai production scale hoan chinh.

## 2. Thanh phan deploy hien co

### File deploy

- `deploy/Dockerfile`
- `deploy/docker-compose.local.yml`
- `deploy/docker-compose.prod.yml`
- `wsgi.py`
- `requirements-prod.txt`

### Runtime deploy

- Python 3.10 base image
- `gunicorn` lam web server process manager
- Flask app duoc import tu `wsgi:app`
- `ffmpeg`, `libgl1`, `libglib2.0-0` phuc vu video va OpenCV runtime

## 3. Entry point deploy

Docker image chay voi command:

```text
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 300 wsgi:app
```

Vai tro tung thanh phan:

- `wsgi.py`
  - expose object `app`
- `gunicorn`
  - chay Flask app ben trong container
- port `5000`
  - port service mac dinh trong image

## 4. Docker image hien tai

### Build flow

1. Lay `python:3.10-slim` lam base image mac dinh.
2. Cai packages he thong:
   - `ffmpeg`
   - `libgl1`
   - `libglib2.0-0`
3. Copy `requirements.txt` va `requirements-prod.txt`.
4. Cai dependency Python.
5. Copy source code vao `/app`.
6. Tao san cac thu muc:
   - `/app/static/uploads`
   - `/app/static/results`
   - `/app/data`
   - `/app/models`

### Package Python

Deploy runtime dung:

- `flask`
- `ultralytics`
- `opencv-python`
- `pillow`
- `numpy`
- `gunicorn`

## 5. 2 che do deploy hien co

### 5.1 Local Docker mode

File:

```text
deploy/docker-compose.local.yml
```

Muc dich:

- chay local bang Docker thay vi `python app.py`
- de test image runtime
- de kiem tra env, mount, artifact, dependency OS

Phu hop khi:

- muon mo phong deployment tren may ca nhan
- muon test reproducible environment
- muon demo ma khong cai tay dependency local

### 5.2 Production baseline mode

File:

```text
deploy/docker-compose.prod.yml
```

Muc dich:

- chay detached
- dung `gunicorn`
- de lam baseline cho may demo / server don

Phu hop khi:

- can dong goi de deploy nhanh
- muon chay service on dinh hon local script
- can mount volume artifact va data ro rang

## 6. Data va storage trong deploy

Deploy hien tai van dung storage giong local system, chi khac o cach dong goi:

### Artifact

- `static/results/`

Vai tro:

- luu output image / video
- luu `metadata.json`
- duoc map qua volume hoac bind mount tuy compose file

### Upload tam

- `static/uploads/`

Vai tro:

- giu file upload trong qua trinh xu ly
- dac biet quan trong voi video

### SQLite recent image

- `recent_images.sqlite3`

Vai tro:

- giu gallery nhanh trong runtime deploy hien tai
- van la local file DB, khong phai DB phan tan

## 7. Config deploy

Bien moi truong deploy quan trong:

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
- `FISHEYE_EXTERNAL_CAMERA_SOURCE_MODE`
- `FISHEYE_EXTERNAL_CAMERA_STREAM_URL`
- `FISHEYE_EXTERNAL_CAMERA_URL`

Trong deploy, nhung bien nay nen duoc dat ro rang qua:

- compose env
- `.env`
- runtime override

Cho deploy streaming, cau hinh khuyen nghi la:

- `FISHEYE_EXTERNAL_CAMERA_SOURCE_MODE=stream`
- `FISHEYE_EXTERNAL_CAMERA_STREAM_URL=<rtsp|http-hls|mjpeg-url>`

## 8. Checkpoint trong deploy

Deploy system hien tai van su dung cung `ModelRegistry` voi local system.

Dieu nay co nghia la:

- app co the tim model `.pt` trong workspace / app dir
- co the chi dinh qua `FISHEYE_MODEL_PATH`
- detect image, video, external camera co the chon checkpoint qua `model_key`

Neu deploy bang container, can dam bao:

- file checkpoint da ton tai trong image
  hoac
- checkpoint duoc mount vao container

Neu khong, app se fallback sang `yolo11n.pt` neu model nay co san.

## 8.1 External camera stream mode trong deploy

Trong production compose, external camera da co the chay o `stream mode` thay vi `snapshot mode`.

Khi `stream mode` duoc bat:

- backend mo stream truc tiep bang OpenCV
- live monitor giu ket noi stream thay vi tai lai JPEG snapshot moi chu ky
- moi chu ky lay frame moi tu stream va infer bang GPU/CPU runtime hien tai
- one-shot detect cung co the chup 1 frame truc tiep tu stream

Snapshot mode van con de tuong thich voi local va voi nguon camera page kieu cu.

## 9. Luong khoi dong deploy

### Deploy local Docker

```powershell
cd C:\Using\NCKH\fisheye_demo
docker compose -f deploy\docker-compose.local.yml up --build
```

### Deploy production baseline

```powershell
cd C:\Using\NCKH\fisheye_demo
docker compose -f deploy\docker-compose.prod.yml up --build -d
```

Sau khi service len, app se expose tren port da map tu compose.

## 10. Hanh vi runtime khi deploy

Mac du chay trong Docker / Gunicorn, logic xu ly van giong local:

- detect video van la synchronous request
- convert video van synchronous
- external live van la background thread trong app process
- history va stats van scan filesystem
- recent image van la SQLite file local

Noi cach khac, deploy mode hien tai thay doi packaging va web serving, nhung chua tach logic thanh web/worker/doc lap.

## 11. Muc tieu phu hop cua deploy hien tai

Deploy hien tai phu hop cho:

- single-host demo
- server nho
- lab / noi bo
- baseline reproducible environment

Deploy hien tai chua phu hop hoan toan cho:

- nhieu worker GPU/CPU doc lap
- queue background job
- object storage rieng
- Postgres lam source of truth
- multi-instance scale out

## 12. Gioi han deploy hien tai

1. Van la monolithic Flask app.
2. Video workload nang co the chiem request rat lau.
3. Live monitor nam trong process web, khong phai service rieng.
4. SQLite va filesystem van la state chinh.
5. Chua co reverse proxy, TLS, auth, rate limit, hay central DB ngay trong baseline nay.
6. Chua co queue worker, retry, dead-letter, monitoring stack day du.

## 13. De xuat su dung dung cach

### Dung deploy baseline khi

- can dong goi app de demo
- can mot moi truong chay on dinh hon local script
- can test artifact va env trong container
- can tai su dung setup tren may khac nhanh

### Khong nen xem deploy baseline la production hoan chinh khi

- can scale nhieu request video song song
- can uptime cao
- can auth va quan tri user
- can worker tach rieng
- can object storage / Postgres / Redis

## 14. Nen doc gi tiep theo

Neu can nang cap tu deploy baseline len he thong hoan chinh, doc tiep:

1. `SYSTEM_ARCHITECH.md`
2. `refactor.md`
