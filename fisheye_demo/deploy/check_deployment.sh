#!/bin/bash
# ==============================================================================
# Check Deployment Status on GCP VM
# ==============================================================================
# This script checks the status of a running deployment on the GCP VM instance.
# Usage: ./check_deployment.sh [cpu|gpu]
# Default: cpu
# ==============================================================================

set -euo pipefail

# --- GCP Configuration ---
PROJECT_ID="project-ef8a8694-e33d-4954-ad1"
ZONE="asia-southeast1-b"

# Determine instance name based on argument
MODE="${1:-cpu}"
if [ "$MODE" = "gpu" ]; then
    INSTANCE_NAME="fisheye-gpu-instance"
    COMPOSE_FILE="deploy/docker-compose.prod.yml"
else
    INSTANCE_NAME="fisheye-cpu-instance"
    COMPOSE_FILE="deploy/docker-compose.prod-cpu.yml"
fi

echo "=== Checking Deployment Status on ${INSTANCE_NAME} ==="
echo ""

# Check if deployment is complete
echo "Checking deployment completion flag..."
if gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "test -f ~/deployment_complete.flag" 2>/dev/null; then
    echo "✓ Deployment completed successfully!"
    echo ""
    
    # Get the completion timestamp
    gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "cat ~/deployment_complete.flag"
    echo ""
else
    echo "⚠ Deployment still in progress or not started yet."
    echo ""
fi

# Show last 50 lines of deployment log
echo "=== Last 50 lines of deployment log ==="
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "tail -n 50 ~/deploy.log 2>/dev/null || echo 'No deployment log found'"
echo ""

# Check Docker container status
echo "=== Docker Container Status ==="
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE}" --command "
    cd ~/fisheye_app 2>/dev/null && \
    sudo docker compose -f ${COMPOSE_FILE} ps 2>/dev/null || \
    echo 'Docker containers not yet running or compose file not found'
"
echo ""

# Get VM External IP
VM_IP=$(gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || echo "Unable to get IP")
echo "=============================================================================="
echo "VM External IP: ${VM_IP}"
echo "If deployment is complete, access the app at: http://${VM_IP}:5000"
echo "=============================================================================="
echo ""
echo "To watch deployment logs in real-time, run:"
echo "  gcloud compute ssh ${INSTANCE_NAME} --zone=${ZONE} --command 'tail -f ~/deploy.log'"
