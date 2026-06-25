#!/usr/bin/env bash
# Run this ON the EC2 instance, in the folder that holds:
#   lolsuit-images.tar, docker-compose.prod.yml, .env
# It loads the uploaded images and (re)starts the stack. No source build here.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Loading images from lolsuit-images.tar"
docker load -i lolsuit-images.tar

echo "==> Starting stack"
docker compose -f docker-compose.prod.yml up -d

docker compose -f docker-compose.prod.yml ps
