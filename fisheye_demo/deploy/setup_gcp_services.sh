#!/bin/bash
# ==============================================================================
# setup_gcp_services.sh — Tạo Cloud SQL (PostgreSQL) + GCS Bucket cho fisheye_demo
# Chạy từ Google Cloud Shell hoặc máy có gcloud CLI đã auth
# ==============================================================================
set -euo pipefail

# ── Cấu hình — THAY ĐỔI CÁC GIÁ TRỊ NÀY ─────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-project-ef8a8694-e33d-4954-ad1}"
REGION="asia-southeast1"
ZONE="${REGION}-b"

# Cloud SQL
DB_INSTANCE_NAME="fisheye-db"
DB_NAME="fisheye_db"
DB_USER="fisheye_user"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 16 | tr -d '/+=' | head -c 20)}"
DB_TIER="db-f1-micro"   # Free tier equivalent, đủ cho demo

# GCS
BUCKET_NAME="fisheye-snapshots-${PROJECT_ID}"
SNAPSHOT_TTL_HOURS=6

# Service Account
SA_NAME="fisheye-app"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "============================================================"
echo "FishEye8K — GCP Services Setup"
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "============================================================"

# ── 1. Set project ────────────────────────────────────────────────────────────
gcloud config set project "${PROJECT_ID}"

# ── 2. Enable APIs ────────────────────────────────────────────────────────────
echo ""
echo "[1/6] Enabling GCP APIs..."
gcloud services enable \
    sqladmin.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com \
    cloudresourcemanager.googleapis.com \
    --quiet

echo "✓ APIs enabled"

# ── 3. Tạo Cloud SQL PostgreSQL instance ─────────────────────────────────────
echo ""
echo "[2/6] Creating Cloud SQL PostgreSQL instance: ${DB_INSTANCE_NAME}..."

if gcloud sql instances describe "${DB_INSTANCE_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  ✓ Instance ${DB_INSTANCE_NAME} already exists, skipping creation"
else
    gcloud sql instances create "${DB_INSTANCE_NAME}" \
        --project="${PROJECT_ID}" \
        --database-version=POSTGRES_15 \
        --tier="${DB_TIER}" \
        --region="${REGION}" \
        --storage-type=SSD \
        --storage-size=10GB \
        --backup-start-time=03:00 \
        --no-assign-ip \
        --quiet

    echo "  ✓ Cloud SQL instance created"
fi

# Tạo database
echo "  Creating database ${DB_NAME}..."
gcloud sql databases create "${DB_NAME}" \
    --instance="${DB_INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --quiet 2>/dev/null || echo "  (database already exists)"

# Tạo user
echo "  Creating user ${DB_USER}..."
gcloud sql users create "${DB_USER}" \
    --instance="${DB_INSTANCE_NAME}" \
    --password="${DB_PASSWORD}" \
    --project="${PROJECT_ID}" \
    --quiet 2>/dev/null || echo "  (user already exists)"

# Lấy connection name
INSTANCE_CONNECTION_NAME=$(gcloud sql instances describe "${DB_INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --format="value(connectionName)")

echo "  ✓ Cloud SQL ready"
echo "  Connection name: ${INSTANCE_CONNECTION_NAME}"

# ── 4. Tạo GCS Bucket ────────────────────────────────────────────────────────
echo ""
echo "[3/6] Creating GCS bucket: ${BUCKET_NAME}..."

if gsutil ls -b "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "  ✓ Bucket ${BUCKET_NAME} already exists"
else
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" -b on "gs://${BUCKET_NAME}"
    echo "  ✓ Bucket created"
fi

# Đặt lifecycle rule: xóa object sau TTL_HOURS giờ
echo "  Setting lifecycle rule (delete after ${SNAPSHOT_TTL_HOURS}h)..."
cat > /tmp/lifecycle.json << EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 1,
        "matchesPrefix": ["snapshots/"]
      }
    }
  ]
}
EOF
# age=1 day là minimum của GCS lifecycle, app sẽ tự xóa theo TTL_HOURS
gsutil lifecycle set /tmp/lifecycle.json "gs://${BUCKET_NAME}"
echo "  ✓ Lifecycle rule set (GCS minimum: 1 day; app-level cleanup: ${SNAPSHOT_TTL_HOURS}h)"

# Bật CORS cho bucket (để frontend có thể load ảnh trực tiếp)
cat > /tmp/cors.json << EOF
[
  {
    "origin": ["*"],
    "method": ["GET"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
EOF
gsutil cors set /tmp/cors.json "gs://${BUCKET_NAME}"
echo "  ✓ CORS configured"

# ── 5. Tạo Service Account ────────────────────────────────────────────────────
echo ""
echo "[4/6] Creating Service Account: ${SA_NAME}..."

if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  ✓ Service account already exists"
else
    gcloud iam service-accounts create "${SA_NAME}" \
        --display-name="FishEye App Service Account" \
        --project="${PROJECT_ID}" \
        --quiet
    echo "  ✓ Service account created"
fi

# Gán roles
echo "  Granting roles..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/cloudsql.client" \
    --quiet

gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin" "gs://${BUCKET_NAME}"

echo "  ✓ Roles granted (Cloud SQL Client + GCS Object Admin)"

# Tạo key file
SA_KEY_FILE="gcp-sa-key.json"
gcloud iam service-accounts keys create "${SA_KEY_FILE}" \
    --iam-account="${SA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --quiet
echo "  ✓ Service account key saved: ${SA_KEY_FILE}"

# ── 6. Tạo .env.production ───────────────────────────────────────────────────
echo ""
echo "[5/6] Generating .env.production..."

cat > .env.production << EOF
# Auto-generated by setup_gcp_services.sh
# $(date -u +"%Y-%m-%dT%H:%M:%SZ")

FISHEYE_DEFAULT_CONF=0.25
FISHEYE_DEFAULT_IOU=0.45
FISHEYE_DEVICE=0
FISHEYE_PRELOAD_MODEL=1
FISHEYE_MAX_UPLOAD_MB=256
FISHEYE_MAX_VIDEO_SECONDS=180

FISHEYE_UPLOAD_DIR=/app/static/uploads
FISHEYE_RESULTS_DIR=/app/static/results
FISHEYE_RECENT_IMAGE_DB=/app/data/recent_images.sqlite3

# Cloud SQL (Unix socket via Cloud SQL Auth Proxy)
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@/fisheye_db?host=/cloudsql/${INSTANCE_CONNECTION_NAME}
CLOUD_SQL_INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME}

# Google Cloud Storage
FISHEYE_CLOUD_STORAGE=1
GCS_BUCKET_NAME=${BUCKET_NAME}
GCS_PROJECT_ID=${PROJECT_ID}
FISHEYE_SNAPSHOT_TTL_HOURS=${SNAPSHOT_TTL_HOURS}

# Alert thresholds
ALERT_THRESHOLD_TOTAL=15
ALERT_THRESHOLD_CAR=10
ALERT_THRESHOLD_BUS=3
ALERT_THRESHOLD_TRUCK=3
ALERT_THRESHOLD_PEDESTRIAN=8
ALERT_THRESHOLD_MOTORBIKE=12
ALERT_COOLDOWN_SECONDS=60

FISHEYE_EXTERNAL_CAMERA_SOURCE_MODE=stream
FISHEYE_EXTERNAL_CAMERA_LIVE_INTERVAL=1.0

WEB_CONCURRENCY=1
WEB_THREADS=4
WEB_TIMEOUT=300
EOF

echo "  ✓ .env.production generated"

# ── 7. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "[6/6] Setup complete!"
echo ""
echo "============================================================"
echo "SUMMARY"
echo "============================================================"
echo "Cloud SQL instance : ${INSTANCE_CONNECTION_NAME}"
echo "Database           : ${DB_NAME}"
echo "DB User            : ${DB_USER}"
echo "DB Password        : ${DB_PASSWORD}"
echo "GCS Bucket         : gs://${BUCKET_NAME}"
echo "Service Account    : ${SA_EMAIL}"
echo "SA Key file        : ${SA_KEY_FILE}"
echo ""
echo "NEXT STEPS:"
echo "  1. Copy ${SA_KEY_FILE} vào VM:"
echo "     gcloud compute scp ${SA_KEY_FILE} fisheye-gpu-instance:~/fisheye_app/ --zone=${ZONE}"
echo ""
echo "  2. Copy .env.production vào VM:"
echo "     gcloud compute scp .env.production fisheye-gpu-instance:~/fisheye_app/.env --zone=${ZONE}"
echo ""
echo "  3. SSH vào VM và chạy:"
echo "     gcloud compute ssh fisheye-gpu-instance --zone=${ZONE}"
echo "     cd ~/fisheye_app"
echo "     sudo docker compose -f deploy/docker-compose.prod.yml up --build -d"
echo ""
echo "  4. Truy cập app:"
VM_IP=$(gcloud compute instances describe fisheye-gpu-instance --zone="${ZONE}" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || echo "N/A")
echo "     http://${VM_IP}:5000"
echo "============================================================"
echo ""
echo "⚠️  QUAN TRỌNG: Lưu DB_PASSWORD vào nơi an toàn!"
echo "   DB_PASSWORD=${DB_PASSWORD}"
