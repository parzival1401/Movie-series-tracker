#!/bin/bash
# Run on the Pi from the project directory.
# First time only: chmod +x deploy.sh
set -e
echo "Pulling latest code..."
git pull origin main
echo "Building Docker image..."
docker compose build
echo "Restarting container..."
docker compose up -d
echo ""
echo "✓ Deployed. Access at: http://100.77.67.90:8000"
