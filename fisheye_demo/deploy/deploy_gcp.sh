#!/bin/bash
# ==============================================================================
# Google Cloud Platform (GCP) Deployment Script for Fisheye Demo (GPU Mode)
# ==============================================================================
# This script automates Option A (GCE VM with GPU support) deployment.
# It provisions a VM, installs Docker/NVIDIA drivers, uploads code/weights,
# and starts the service using Docker Compose.
#
# Prerequisite: run "gcloud auth login" and ensure you are in the Google Cloud Shell
# or have the gcloud CLI installed.
# ==============================================================================

set -euo pipefail

# --- GCP Configuration ---
PROJECT_ID="project-ef8a8694-e33d-4954-ad1"
ZONE="asia-southeast1-b" # Singapore zone (close to Vietnam, supporting NVIDIA GPUs)
INSTANCE_NAME="fisheye-gpu-instance"
MACHINE_TYPE="g2-standard-4" # G2 instance includes 1x NVIDIA L4 GPU, 4 vCPUs, 16GB RAM
ACCELERATOR="type=nvidia-l4,count=1"
IMAGE_PROJECT="ubuntu-os-cloud"
IMAGE_FAMILY="ubuntu-2204-lts"
BOOT_DISK_SIZE="50GB"
BOOT_DISK_TYPE="pd-balanced"

echo "=== [1/5] Setting up GCP Project Context ==="
gcloud config set project "${PROJECT_ID}"

echo "=== [2/5] Enabling Google Cloud APIs ==="
gcloud services enable compute.googleapis.com

# Create startup script file for VM initialization
STARTUP_SCRIPT_PATH="deploy/gce_startup.sh"
echo "Creating VM startup script..."
cat << 'EOF' > "${STARTUP_SCRIPT_PATH}"
#!/bin/bash
exec > >(tee -i /var/log/gce-startup.log) 2>&1
echo "=== Beginning VM Initialization ==="

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

# 3. Install NVIDIA CUDA Drivers
apt-get install -y linux-headers-$(uname -r)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update -y
apt-get install -y nvidia-driver-535-server cuda-drivers-535

# 4. Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -y
apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA container runtime
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

echo "=== VM Initialization Finished successfully ==="
EOF

echo "=== [3/5] Creating GPU-Enabled VM Instance ==="
# Check if the VM already exists
if gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" >/dev/null 2>&1; then
  echo "VM instance ${INSTANCE_NAME} already exists."
else
  echo "Provisioning new GCE instance ${INSTANCE_NAME} (Machine: ${MACHINE_TYPE}, GPU: L4)..."
  gcloud compute instances create "${INSTANCE_NAME}" \
      --project="${PROJECT_ID}" \
      --zone="${ZONE}" \
      --machine-type="${MACHINE_TYPE}" \
      --accelerator="${ACCELERATOR}" \
      --maintenance-policy=TERMINATE \
      --restart-on-failure \
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
echo "Waiting for VM to initialize (Installing NVIDIA drivers & Docker takes 3-5 mins)..."
sleep 45

echo "=== [4/5] Preparing and Uploading Code to VM ==="
# Create temporary package of deployment files
TAR_FILE_NAME="fisheye_deploy.tar.gz"
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

echo "=== [5/5] Building and Running the App in GPU Mode ==="
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "
  cd ~/fisheye_app
  # Wait for startup script to finish installing NVIDIA and Docker
  echo 'Waiting for startup-script (drivers/docker) installation to complete...'
  while [ ! -f /var/log/gce-startup.log ] || ! grep -q 'VM Initialization Finished successfully' /var/log/gce-startup.log; do
    echo '...still waiting for installation packages...'
    sleep 15
  done
  echo 'Startup script finished installing dependencies.'

  # Verify GPU status on VM
  nvidia-smi

  # Run Production Compose
  echo 'Starting Docker Compose production stack...'
  sudo docker compose -f deploy/docker-compose.prod.yml down || true
  sudo docker compose -f deploy/docker-compose.prod.yml up --build -d
  
  echo 'Service status:'
  sudo docker compose -f deploy/docker-compose.prod.yml ps
"

# Retrieve VM External IP
VM_IP=$(gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
echo "=============================================================================="
echo "Deployment successful!"
echo "You can access the Fisheye app at: http://${VM_IP}:5000"
echo "=============================================================================="
