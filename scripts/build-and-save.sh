#!/usr/bin/env bash
# Build both images on THIS machine and pack them into a single tarball
# that you upload to the EC2 instance. No registry needed.
#
#   bash scripts/build-and-save.sh
#   -> produces lolsuit-images.tar
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Building backend image (lolsuit-server:latest)"
docker build -t lolsuit-server:latest -f server/Dockerfile .

echo "==> Building frontend image (lolsuit-web:latest)"
docker build -t lolsuit-web:latest ./client

echo "==> Saving both images to lolsuit-images.tar"
docker save lolsuit-server:latest lolsuit-web:latest -o lolsuit-images.tar

echo "Done. Upload lolsuit-images.tar to the EC2 box, then run scripts/deploy-on-ec2.sh"
