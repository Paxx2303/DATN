# Deployment Timeout Fix

## Problem
The deployment was failing with the error:
```
failed to receive status: rpc error: code = Unavailable desc = error reading from server: EOF
```

This occurred because the SSH connection was timing out during the long-running Docker build process (specifically during pip package installation which can take 5-10 minutes).

## Root Cause
- The deployment script was running `docker compose up --build` over SSH synchronously
- Long-running operations (especially pip installing ~30 packages with large dependencies like PyTorch, OpenCV, etc.) can exceed SSH timeout limits
- The connection was being terminated before the build completed

## Solution Implemented

### 1. Background Process Execution
Modified both deployment scripts (`deploy_gcp.sh` and `deploy_gcp_cpu.sh`) to:
- Create a deployment script (`deploy_app.sh`) on the VM
- Run the script in the background using `nohup` with output redirected to `~/deploy.log`
- This ensures the deployment continues even if the SSH connection drops
- Creates a completion flag file (`~/deployment_complete.flag`) when done

### 2. Monitoring Script
Created `check_deployment.sh` to monitor deployment progress:
- Checks for completion flag
- Shows last 50 lines of deployment logs
- Displays Docker container status
- Shows VM external IP and access URL

## How to Use

### Deploy the Application
```bash
# For CPU-only deployment
./deploy/deploy_gcp_cpu.sh

# For GPU deployment
./deploy/deploy_gcp.sh
```

The script will:
1. Upload code to VM
2. Start deployment in background
3. Wait 30 seconds and show initial status
4. Exit (deployment continues on VM)

### Check Deployment Status
```bash
# Check CPU instance
./deploy/check_deployment.sh cpu

# Check GPU instance
./deploy/check_deployment.sh gpu
```

### Watch Deployment Logs in Real-Time
```bash
# For CPU instance
gcloud compute ssh fisheye-cpu-instance --zone=asia-southeast1-b --command "tail -f ~/deploy.log"

# For GPU instance
gcloud compute ssh fisheye-gpu-instance --zone=asia-southeast1-b --command "tail -f ~/deploy.log"
```

### Check if Deployment is Complete
```bash
# For CPU instance
gcloud compute ssh fisheye-cpu-instance --zone=asia-southeast1-b --command "cat ~/deployment_complete.flag"

# For GPU instance
gcloud compute ssh fisheye-gpu-instance --zone=asia-southeast1-b --command "cat ~/deployment_complete.flag"
```

## Expected Timeline
- **VM Creation + Docker/NVIDIA Installation**: 3-5 minutes
- **Code Upload**: 30-60 seconds
- **Docker Build (Background)**: 8-12 minutes
  - Base image pull: 2-3 minutes
  - System packages: 1-2 minutes
  - Python dependencies: 5-7 minutes
  - Application copy: <1 minute
- **Total**: 12-18 minutes

## Benefits
1. **Resilient to Connection Issues**: Deployment continues even if SSH disconnects
2. **No Timeout Errors**: Background process isn't subject to SSH timeout limits
3. **Easy Monitoring**: Can check progress anytime with monitoring script
4. **Clean Logs**: All deployment output captured in `~/deploy.log`

## Files Modified
- `deploy/deploy_gcp.sh` - GPU deployment script
- `deploy/deploy_gcp_cpu.sh` - CPU deployment script
- `deploy/check_deployment.sh` - New monitoring script (created)

## Next Steps
After deployment completes:
1. Run `./deploy/check_deployment.sh [cpu|gpu]` to verify
2. Access the application at `http://<VM_IP>:5000`
3. Monitor application logs: `gcloud compute ssh <instance-name> --zone=asia-southeast1-b --command "cd ~/fisheye_app && sudo docker compose -f <compose-file> logs -f"`
