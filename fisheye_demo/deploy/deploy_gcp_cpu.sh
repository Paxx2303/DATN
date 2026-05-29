#!/bin/bash
# ==============================================================================
# Google Cloud Platform (GCP) Deployment Script for Fisheye Demo (CPU Mode)
# ==============================================================================
# This script automates Option B (GCE VM with CPU-only support) deployment.
# It provisions a cost-effective VM, installs Docker, uploads code/weights,
# and starts the service using Docker Compose in CPU mode.
#
# Prerequisite: run "gcloud auth login" and ensure you are in the Google Cloud Shell
# or have the gcloud CLI installed.
# ==============================================================================

set -euo pipefail

# --- GCP Configuration ---
PROJECT_ID="project-ef8a8694-e33d-4954-ad1"
ZONE="asia-southeast1-b" # Singapore zone (close to Vietnam)
INSTANCE_NAME="fisheye-cpu-instance"
MACHINE_TYPE="e2-standard-2" # 2 vCPUs, 8GB RAM (~$50/month)
IMAGE_PROJECT="ubuntu-os-cloud"
IMAGE_FAMILY="ubuntu-2204-lts"
BOOT_DISK_SIZE="30GB"
BOOT_DISK_TYPE="pd-balanced"

echo "=== [1/5] Setting up GCP Project Context ==="
gcloud config set project "${PROJECT_ID}"

echo "=== [2/5] Enabling Google Cloud APIs ==="
gcloud services enable compute.googleapis.com

# Create startup script file for VM initialization (CPU-only version)
STARTUP_SCRIPT_PATH="deploy/gce_startup_cpu.sh"
echo "Creating VM CPU startup script..."
cat << 'EOF' > "${STARTUP_SCRIPT_PATH}"
#!/bin/bash
exec > >(tee -i /var/log/gce-startup.log) 2>&1
echo "=== Beginning VM Initialization (CPU Mode) ==="

# 1. Update Apt Repositories
apt-get update -y
apt-get upgrade -y

# 2. Install Docker
apt-get install -y apt-transport-https ca-certificates curl software-properties-common gnupg lsb-release
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl restart docker

echo "=== VM Initialization Finished successfully ==="
EOF

echo "=== [3/5] Creating CPU-Enabled VM Instance ==="
# Check if the VM already exists
if gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" >/dev/null 2>&1; then
  echo "VM instance ${INSTANCE_NAME} already exists."
else
  echo "Provisioning new GCE instance ${INSTANCE_NAME} (Machine: ${MACHINE_TYPE}, CPU-only)..."
  gcloud compute instances create "${INSTANCE_NAME}" \
      --project="${PROJECT_ID}" \
      --zone="${ZONE}" \
      --machine-type="${MACHINE_TYPE}" \
      --image-project="${IMAGE_PROJECT}" \
      --image-family="${IMAGE_FAMILY}" \
      --boot-disk-size="${BOOT_DISK_SIZE}" \
      --boot-disk-type="${BOOT_DISK_TYPE}" \
      --metadata-from-file=startup-script="${STARTUP_SCRIPT_PATH}" \
      --tags=http-server,fisheye-port
fi

# Configure firewall to allow traffic to port 5000 (Fisheye web interface)
echo "Configuring firewall rules..."
if ! gcloud compute firewall-rules describe allow-fisheye >/dev/null 2>&1; then
  gcloud compute firewall-rules create allow-fisheye \
      --allow tcp:5000 \
      --target-tags=fisheye-port \
      --description="Allow port 5000 access for Fisheye Demo"
fi

# Wait for VM to boot and startup script to complete
echo "Waiting for VM to initialize (Installing Docker takes ~1 min)..."
sleep 20

echo "=== [4/5] Preparing and Uploading Code to VM ==="
# Create temporary package of deployment files
TAR_FILE_NAME="fisheye_deploy_cpu.tar.gz"
TAR_FILE="/tmp/${TAR_FILE_NAME}"
echo "Packaging source files and model weights..."
tar --exclude='venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='tests' \
    --exclude='.pytest_cache' \
    --exclude='recent_images.sqlite3' \
    --exclude='static/results/*' \
    --exclude='static/uploads/*' \
    -czf "${TAR_FILE}" -C . .

echo "Uploading deployment package to VM..."
gcloud compute scp "${TAR_FILE}" "${INSTANCE_NAME}:~/${TAR_FILE_NAME}" --zone="${ZONE}"

echo "Extracting code on VM..."
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "
  mkdir -p ~/fisheye_app
  tar -xzf ~/${TAR_FILE_NAME} -C ~/fisheye_app
  rm ~/${TAR_FILE_NAME}
"
# Clean up local archive
rm "${TAR_FILE}"

echo "=== [5/5] Building and Running the App in CPU Mode ==="
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "
  cd ~/fisheye_app
  # Wait for startup script to finish installing Docker
  echo 'Waiting for startup-script (docker) installation to complete...'
  while [ ! -f /var/log/gce-startup.log ] || ! grep -q 'VM Initialization Finished successfully' /var/log/gce-startup.log; do
    echo '...still waiting for installation packages...'
    sleep 10
  done
  echo 'Startup script finished installing dependencies.'

  # Run Production Compose
  echo 'Starting Docker Compose production stack (CPU Mode)...'
  sudo docker compose -f deploy/docker-compose.prod-cpu.yml down || true
  sudo docker compose -f deploy/docker-compose.prod-cpu.yml up --build -d
  
  echo 'Service status:'
  sudo docker compose -f deploy/docker-compose.prod-cpu.yml ps
"

# Retrieve VM External IP
VM_IP=$(gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
echo "=============================================================================="
echo "Deployment successful in CPU mode!"
echo "You can access the Fisheye app at: http://${VM_IP}:5000"
echo "=============================================================================="
