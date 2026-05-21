# Huong dan cai dat va su dung `fisheye_demo`

## Muc luc

1. [Yeu cau he thong](#1-yeu-cau-he-thong)
2. [Cai dat](#2-cai-dat)
3. [Cau hinh](#3-cau-hinh)
4. [Khoi dong server](#4-khoi-dong-server)
5. [Su dung giao dien web](#5-su-dung-giao-dien-web)
6. [API Reference](#6-api-reference)
7. [Chay tests](#7-chay-tests)
8. [Chay Streamlit demo tuy chon](#8-chay-streamlit-demo-tuy-chon)
9. [Cau truc artifact dau ra](#9-cau-truc-artifact-dau-ra)
10. [Xu ly loi thuong gap](#10-xu-ly-loi-thuong-gap)

---

## 1. Yeu cau he thong

| Thanh phan | Muc toi thieu |
|---|---|
| Python | 3.10+ |
| pip | 23.0+ |
| RAM | 4 GB |
| GPU tuy chon | CUDA neu muon tang toc YOLO |

---

## 2. Cai dat

### Buoc 1 - Di chuyen vao project

```powershell
cd C:\Using\NCKH\fisheye_demo
```

### Buoc 2 - Tao virtual environment

```powershell
python -m venv venv

# Windows
venv\Scripts\activate
```

### Buoc 3 - Cai dependencies

```powershell
pip install -r requirements.txt
```

Neu may co GPU NVIDIA va muon cai PyTorch CUDA truoc:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
```

### Buoc 4 - Chuan bi model

Dat checkpoint `.pt` vao thu muc goc cua project. He thong uu tien model theo ten file:

1. chua `fisheye`
2. chua `best`
3. chua `yolo11`
4. fallback sang `yolo11n.pt`

Vi du:

```text
fisheye_demo/
|-- phase2_fisheye_best.pt
|-- yolo11n.pt
`-- ...
```

---

## 3. Cau hinh

He thong ho tro file `.env` tai thu muc goc `fisheye_demo/`.

Ban co the tao file dua tren [`.env.example`](C:/Using/NCKH/fisheye_demo/.env.example).

He thong hien chap nhan ca ten bien moi va alias de de dung:

```env
# Inference defaults
FISHEYE_DEFAULT_CONF=0.25
FISHEYE_DEFAULT_IOU=0.45

# Alias tuong thich
CONFIDENCE_THRESHOLD=0.25
IOU_THRESHOLD=0.45

# Device
FISHEYE_DEVICE=cpu
# hoac
DEVICE=cpu

# Storage
FISHEYE_RESULTS_DIR=static/results
# hoac
ARTIFACT_DIR=static/results

# Fisheye defaults
FISHEYE_DEFAULT_STRENGTH=0.70
FISHEYE_DEFAULT_RADIUS=0.85
FISHEYE_DEFAULT_EFFECT=standard

# Alias tuong thich
FISHEYE_STRENGTH=0.70
FISHEYE_RADIUS=0.85
FISHEYE_EFFECT=standard

# Model
FISHEYE_MODEL_PATH=
FISHEYE_PRELOAD_MODEL=1
```

Luu y:

- `radius` hien tai duoc gioi han trong khoang `0.0 - 1.0`.
- Gia tri mac dinh trong code hien tai la `strength=0.70`, `radius=0.85`, `effect=standard`.

---

## 4. Khoi dong server

```powershell
python app.py
```

Server Flask mac dinh chay tai:

```text
http://127.0.0.1:5000
```

Ban cung co the chay bang Flask CLI:

```powershell
flask run --host=0.0.0.0 --port=5000
```

---

## 5. Su dung giao dien web

Mo trinh duyet tai `http://127.0.0.1:5000`.

### 5.1 Detect anh fisheye

1. Chon `Input layout = Already fisheye`.
2. Upload anh.
3. Dieu chinh `Confidence threshold` va `IoU threshold` neu can.
4. Nhan `Detect image`.

### 5.2 Detect anh thuong va tu dong be cong fisheye

1. Chon `Input layout = Normal traffic view`.
2. Upload anh giao thong thuong.
3. Dieu chinh:
   - `Fisheye strength`
   - `Fisheye radius`
   - `Fisheye effect`
4. Nhan `Detect image`.

He thong se luu:

- `original.jpg`
- `preprocessed.jpg`
- `annotated.jpg`
- `metadata.json`

### 5.3 Convert anh hoac video sang fisheye

1. Upload anh hoac video.
2. Chon `Input layout = Normal traffic view` neu dau vao la camera thuong.
3. Cau hinh fisheye.
4. Nhan `Convert to fisheye`.

Ket qua:

- Anh convert: artifact `fisheye.jpg`
- Video convert: artifact `fisheye.mp4`

### 5.4 Detect video

1. Upload video.
2. Chon `Input layout = Already fisheye` neu video da la fisheye, hoac `Normal traffic view` neu can be cong truoc.
3. Dieu chinh `confidence`, `IoU` va cac thong so fisheye neu can.
4. Nhan `Detect objects`.

He thong se luu:

- `annotated.mp4`
- `preview_annotated.jpg`
- `metadata.json`

### 5.5 Xem lich su

Cuon xuong phan `Recent runs` de xem:

- task `detect` hoac `convert`
- media type `image` hoac `video`
- cac link artifact tuong ung

---

## 6. API Reference

### `GET /api/health`

Kiem tra trang thai server.

```powershell
curl.exe http://127.0.0.1:5000/api/health
```

Response thuc te se co dang gan nhu:

```json
{
  "status": "ok",
  "server_time": "2026-05-11T12:00:00Z",
  "device": "cpu",
  "model": {
    "loaded": true,
    "source": "custom",
    "loaded_from_name": "phase2_fisheye_best.pt"
  },
  "storage": {
    "results_dir": "C:\\Using\\NCKH\\fisheye_demo\\static\\results",
    "recent_runs": 3
  }
}
```

### `GET /api/config`

Tra ve:

- class names
- class color map
- default threshold
- fisheye defaults
- source layouts
- media types duoc ho tro

### `GET /api/history`

Danh sach cac run da luu.

```powershell
curl.exe http://127.0.0.1:5000/api/history
```

### `GET /api/history/<result_id>`

Chi tiet mot run.

```powershell
curl.exe http://127.0.0.1:5000/api/history/abc123
```

### `POST /api/detect`

Detect doi tuong tren anh hoac video.

Route nay chap nhan ca field `image` va alias `file`.
Thong so confidence chap nhan ca `conf` va alias `confidence`.

```powershell
curl.exe -X POST ^
  -F "file=@C:\path\to\image.jpg" ^
  -F "source_layout=fisheye" ^
  -F "confidence=0.25" ^
  -F "iou=0.45" ^
  http://127.0.0.1:5000/api/detect
```

Neu detect tren anh thuong:

```powershell
curl.exe -X POST ^
  -F "file=@C:\path\to\traffic.jpg" ^
  -F "source_layout=normal" ^
  -F "apply_fisheye=true" ^
  -F "fisheye_strength=0.75" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  -F "confidence=0.25" ^
  -F "iou=0.45" ^
  http://127.0.0.1:5000/api/detect
```

| Tham so | Kieu | Bat buoc | Mo ta |
|---|---|---|---|
| `image` hoac `file` | file | co | Anh hoac video dau vao |
| `source_layout` | string | khong | `fisheye` hoac `normal` |
| `conf` hoac `confidence` | float | khong | Nguong confidence |
| `iou` | float | khong | Nguong IoU |
| `apply_fisheye` | bool | khong | Bat/tat preprocessing |
| `fisheye_strength` | float | khong | Cuong do be cong |
| `fisheye_radius` | float | khong | Ban kinh be cong |
| `fisheye_effect` | string | khong | `standard`, `extreme`, `subtle` |

Neu detect tren video:

```powershell
curl.exe -X POST ^
  -F "file=@C:\path\to\traffic.mp4" ^
  -F "source_layout=normal" ^
  -F "apply_fisheye=true" ^
  -F "fisheye_strength=0.70" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  -F "confidence=0.25" ^
  -F "iou=0.45" ^
  http://127.0.0.1:5000/api/detect
```

Luu y:

- Route nay hien nhan ca anh va video.
- Video detect duoc xu ly dong bo tung frame.
- He thong gioi han do dai video de tranh timeout khi demo.

### `POST /api/convert`

Convert anh hoac video sang fisheye.

Route nay chap nhan:

- `media`
- `file`
- `image`
- `video`

Convert anh:

```powershell
curl.exe -X POST ^
  -F "file=@C:\path\to\traffic.jpg" ^
  -F "source_layout=normal" ^
  -F "fisheye_strength=0.70" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  http://127.0.0.1:5000/api/convert
```

Convert video:

```powershell
curl.exe -X POST ^
  -F "file=@C:\path\to\traffic.mp4" ^
  -F "source_layout=normal" ^
  -F "fisheye_strength=0.70" ^
  -F "fisheye_radius=0.85" ^
  -F "fisheye_effect=standard" ^
  http://127.0.0.1:5000/api/convert
```

### `GET /api/artifacts/<result_id>/<filename>`

Tai artifact cua mot run.

```powershell
curl.exe http://127.0.0.1:5000/api/artifacts/abc123/annotated.jpg --output result.jpg
```

---

## 7. Chay tests

He thong hien co the chay bang `unittest` va van tuong thich voi `pytest`.

### Cach 1 - unittest

```powershell
cd C:\Using\NCKH
python -m unittest discover -s fisheye_demo\tests -t .
```

### Cach 2 - pytest

```powershell
pytest fisheye_demo\tests -v
```

Co the chay mot test cu the:

```powershell
pytest fisheye_demo\tests\test_app.py -k detect -v
```

---

## 8. Chay Streamlit demo tuy chon

`demo.py` la giao dien Streamlit cu.

```powershell
streamlit run demo.py
```

Mo:

```text
http://127.0.0.1:8501
```

Luu y:

- `app.py` moi la entry point chinh cua he thong Flask.
- `demo.py` la demo phu, khong phai luong chinh.

---

## 9. Cau truc artifact dau ra

Moi request thanh cong tao mot thu muc:

```text
static/results/<result_id>/
```

Cac file co the duoc tao:

- `original.jpg`
- `preprocessed.jpg`
- `annotated.jpg`
- `annotated.mp4`
- `fisheye.jpg`
- `original.mp4`
- `fisheye.mp4`
- `preview_original.jpg`
- `preview_fisheye.jpg`
- `preview_annotated.jpg`
- `metadata.json`

Noi dung `metadata.json` phan anh dung cau truc record cua he thong, vi du:

```json
{
  "id": "20260511123000-abcd1234",
  "task": "detect",
  "media_type": "image",
  "filename": "traffic.jpg",
  "source_layout": "normal",
  "preprocessing": {
    "source_layout": "normal",
    "enabled": true,
    "strength": 0.7,
    "radius": 0.85,
    "effect": "standard"
  },
  "parameters": {
    "confidence_threshold": 0.25,
    "iou_threshold": 0.45
  },
  "summary": {
    "total_objects": 7,
    "inference_ms": 42.6,
    "class_counts": {
      "Car": 4,
      "Bus": 0,
      "Truck": 1,
      "Pedestrian": 2,
      "Motorbike": 0
    }
  },
  "artifacts": {
    "original": "original.jpg",
    "preprocessed": "preprocessed.jpg",
    "annotated": "annotated.jpg",
    "metadata": "metadata.json"
  }
}
```

---

## 10. Xu ly loi thuong gap

### Khong tim thay model

Neu he thong khong thay checkpoint custom, no se fallback sang `yolo11n.pt`.

Giai phap:

- Dat file `.pt` vao thu muc goc project.
- Dat ten co chua `fisheye` hoac `best` de duoc uu tien.

### CUDA out of memory

Giai phap:

- dat `FISHEYE_DEVICE=cpu` hoac `DEVICE=cpu` trong `.env`
- giam kich thuoc anh dau vao

### Convert video cham

Giai phap:

- test voi video ngan
- tranh video qua lon
- neu can video dai, nen tach sang background job trong lan nang cap sau

### Port 5000 dang bi chiem

Giai phap:

```powershell
flask run --port=5001
```

### Loi `ModuleNotFoundError: ultralytics`

Giai phap:

- kich hoat dung virtual environment
- chay lai:

```powershell
pip install -r requirements.txt
```
