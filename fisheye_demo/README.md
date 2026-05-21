# FishEye8K Detection System

Ung dung nay da duoc mo rong theo 2 luong dau vao:

- Anh fisheye: detect truc tiep bang YOLO.
- Anh giao thong thong thuong: be cong sang fisheye truoc roi detect.
- Video giao thong: co the convert sang fisheye hoac detect truc tiep tung frame de xuat `annotated.mp4`.

## Thanh phan chinh

- `app.py`: Flask app, API, detect image, convert image/video sang fisheye.
- `fisheye.py`: thuat toan barrel distortion bang inverse mapping + bilinear interpolation.
- `templates/index.html`: giao dien web.
- `static/results/`: artifact cua detect va convert.
- `recent_images.sqlite3`: SQLite luu 100 anh dau ra gan nhat de lam gallery/history nhe.
- `tests/test_app.py`: test route co ban.
- `SYSTEM_OVERVIEW.md`: tai lieu tong quan kien truc, luong xu ly va vai tro tung thanh phan.
- `SYSTEM_LOCAL.md`: mo ta he thong khi chay local/dev/demo.
- `SYSTEM_DEPLOY.md`: mo ta he thong khi dong goi va chay deploy/Docker.
- `SYSTEM_ARCHITECH.md`: tai lieu kien truc chi tiet cho design, refactor va deployment.
- `refactor.md`: ke hoach refactor theo 2 huong local test va production deploy.
- `deploy/`: Dockerfile va docker-compose cho local / production baseline.
- `INSTALLATION_AND_USAGE.md`: huong dan cai dat, cau hinh, API, artifact va troubleshooting.
- `.env.example`: mau cau hinh moi truong.

## Chay ung dung

```powershell
cd C:\Using\NCKH\fisheye_demo
python app.py
```

Mo:

```text
http://127.0.0.1:5000
```

## Tai lieu he thong

- `SYSTEM_OVERVIEW.md`: trang tong quan va dieu huong tai lieu.
- `SYSTEM_LOCAL.md`: runtime local, storage local, workflow local.
- `SYSTEM_DEPLOY.md`: runtime deploy, Docker, Gunicorn, compose, volume va gioi han deploy.
- `SYSTEM_ARCHITECH.md`: huong kien truc / refactor xa hon.

## Luong xu ly

### 1. Detect anh fisheye

- Upload anh.
- Chon `Input layout = Already fisheye`.
- Bam `Detect image`.

### 2. Detect anh thuong sau khi be cong fisheye

- Upload anh giao thong binh thuong.
- Chon `Input layout = Normal traffic view`.
- Dieu chinh `strength`, `radius`, `effect`.
- Bam `Detect image`.

Backend se:

- Tao anh fisheye trung gian.
- Chay detect tren anh da be cong.
- Luu `original`, `preprocessed`, `annotated`, `metadata`.

### 3. Detect video

- Upload video.
- Chon `Input layout = Already fisheye` neu video da la fisheye, hoac `Normal traffic view` neu can be cong truoc.
- Bam `Detect objects`.

Backend se:

- Doc tung frame.
- Tuy chon be cong fisheye truoc khi infer.
- Detect tung frame bang YOLO.
- Xuat `annotated.mp4` va `preview_annotated.jpg`.

### 4. Chuyen video thuong sang fisheye

- Upload video.
- Chon `Input layout = Normal traffic view`.
- Bam `Convert to fisheye`.

Backend se:

- Doc tung frame.
- Ap dung `apply_fisheye(...)`.
- Ghi video moi `fisheye.mp4`.
- Luu preview frame va metadata.

## API chinh

- `GET /api/health`: trang thai he thong.
- `GET /api/config`: config, media support, fisheye options.
- `GET /api/history`: lich su artifact.
- `GET /api/history/<result_id>`: chi tiet mot run.
- `GET /api/recent-images`: 100 anh dau ra gan nhat duoc luu trong SQLite.
- `GET /api/recent-images/<image_id>`: doc 1 anh tu recent image store.
- `GET /api/artifacts/<result_id>/<filename>`: mo artifact.
- `POST /api/detect`: detect anh hoac video.
- `POST /api/convert`: convert anh hoac video sang fisheye.

## Vi du API

Detect anh thuong va tu dong be cong:

```powershell
curl.exe -X POST ^
  -F "image=@C:\path\to\street.jpg" ^
  -F "source_layout=normal" ^
  -F "apply_fisheye=true" ^
  -F "fisheye_strength=0.75" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  -F "conf=0.25" ^
  -F "iou=0.45" ^
  http://127.0.0.1:5000/api/detect
```

Detect video:

```powershell
curl.exe -X POST ^
  -F "file=@C:\path\to\traffic.mp4" ^
  -F "source_layout=normal" ^
  -F "apply_fisheye=true" ^
  -F "fisheye_strength=0.75" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  -F "confidence=0.25" ^
  -F "iou=0.45" ^
  http://127.0.0.1:5000/api/detect
```

Convert video thuong sang fisheye:

```powershell
curl.exe -X POST ^
  -F "media=@C:\path\to\traffic.mp4" ^
  -F "source_layout=normal" ^
  -F "fisheye_strength=0.75" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  http://127.0.0.1:5000/api/convert
```

## Kiem tra

```powershell
cd C:\Using\NCKH
python -m unittest discover -s fisheye_demo\tests -t .
```

## Chay bang Docker

Local test:

```powershell
cd C:\Using\NCKH\fisheye_demo
docker compose -f deploy\docker-compose.local.yml up --build
```

Production baseline / Runpod demo:

```powershell
cd C:\Using\NCKH\fisheye_demo
docker compose -f deploy\docker-compose.prod.yml up --build -d
```

Production baseline chay Flask qua `gunicorn`, dung CUDA/PyTorch base image mac dinh cho GPU, va luu artifact/recent image DB trong Docker volumes.
Neu can override cau hinh production, tao `.env` tu `.env.production.example` truoc khi chay compose.

## Ghi chu

- He thong van uu tien checkpoint co ten chua `fisheye`, `best`, `yolo11`.
- Neu khong tim thay model custom, no fallback sang `yolo11n.pt`.
- Detect video dang chay dong bo trong request va mac dinh gioi han do dai video de tranh timeout.
- Recent image store mac dinh giu `100` anh; co the doi qua `FISHEYE_RECENT_IMAGE_LIMIT`.
- Deploy production hien tai la single-node baseline; refactor worker/Postgres/Redis nam trong `refactor.md`.
