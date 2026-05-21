# System Overview

## 1. Muc dich

Bo tai lieu he thong da duoc tach thanh 2 phan ro rang:

1. `local`: mo ta he thong khi chay tren may dev, may demo, hoac nghien cuu.
2. `deploy`: mo ta he thong khi dong goi va chay bang Docker / Gunicorn cho moi truong deploy.

File nay dong vai tro trang tong quan de dinh huong nguoi doc.

## 2. Nen doc file nao

### Neu ban dang chay local

Doc:

1. `README.md`
2. `INSTALLATION_AND_USAGE.md`
3. `SYSTEM_LOCAL.md`

`SYSTEM_LOCAL.md` tap trung vao:

- runtime Flask local
- artifact filesystem
- recent image SQLite
- detect / convert / external camera workflow
- config, checkpoint, test va gioi han local

### Neu ban dang chuan bi deploy

Doc:

1. `README.md`
2. `deploy/Dockerfile`
3. `deploy/docker-compose.local.yml`
4. `deploy/docker-compose.prod.yml`
5. `SYSTEM_DEPLOY.md`

`SYSTEM_DEPLOY.md` tap trung vao:

- Docker image va entrypoint
- cach web app duoc chay qua `gunicorn`
- volume, env, artifact va SQLite trong container
- local compose vs production baseline compose
- gioi han kien truc deploy hien tai

## 3. So do tach he thong

```text
fisheye_demo/
|-- SYSTEM_OVERVIEW.md   -> trang tong quan
|-- SYSTEM_LOCAL.md      -> he thong local/dev/demo
|-- SYSTEM_DEPLOY.md     -> he thong deploy/docker/runtime
`-- SYSTEM_ARCHITECH.md  -> huong kien truc/refactor sau nay
```

## 4. Dinh nghia 2 phan

### Local system

La phan he thong dang chay theo mo hinh:

- `python app.py`
- 1 Flask process
- model load truc tiep trong app
- artifact luu local disk
- recent images luu SQLite local
- live external camera chay bang background thread

Day la phan phu hop de:

- code va debug
- test nhanh
- demo tinh nang
- nghien cuu model / checkpoint

### Deploy system

La phan he thong dang chay theo mo hinh:

- build image bang `deploy/Dockerfile`
- expose app qua `wsgi:app`
- chay Flask qua `gunicorn`
- mount volume cho `static/results`, `static/uploads`, data va model
- dieu khien bang `docker compose`

Day la phan phu hop de:

- demo on dinh hon local script
- chay detached
- dong goi thanh moi truong reproducible

## 5. Luu y quan trong

- `SYSTEM_LOCAL.md` mo ta trang thai "as-is" khi dev va su dung app tren may local.
- `SYSTEM_DEPLOY.md` mo ta trang thai "as-is" khi dong goi va chay bang Docker hien tai.
- `SYSTEM_ARCHITECH.md` la tai lieu muc tieu kien truc va refactor, khong phai runtime hien tai.

## 6. Thu tu doc de hieu nhanh

Neu moi vao project, thu tu hop ly la:

1. `README.md`
2. `SYSTEM_OVERVIEW.md`
3. `SYSTEM_LOCAL.md`
4. `SYSTEM_DEPLOY.md`
5. `SYSTEM_ARCHITECH.md`

