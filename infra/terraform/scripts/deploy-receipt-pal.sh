#!/bin/bash
set -euo pipefail

# Usage: deploy-receipt-pal.sh [TAG]
#   TAG  Git tag or branch to deploy (default: latest tag on main)
REQUESTED_TAG="${1:-}"

echo "=== Starting Receipt Pal deployment $(date) ==="

APP_DIR="${APP_INSTALL_PATH:-/opt/receipt-pal}"

cd "$APP_DIR"

if [ ! -f "$APP_DIR/backend/.env" ]; then
  echo "ERROR: backend/.env not found at $APP_DIR/backend/.env" >&2
  exit 1
fi

echo "Fetching latest changes from origin..."
git fetch --tags origin main

if [ -n "$REQUESTED_TAG" ]; then
  DEPLOY_REF="$REQUESTED_TAG"
else
  # Default: latest semver tag reachable from main
  DEPLOY_REF="$(git tag --merged origin/main --sort=-version:refname | head -n1)"
  if [ -z "$DEPLOY_REF" ]; then
    echo "No tags found on main — deploying tip of main instead."
    DEPLOY_REF="origin/main"
  fi
fi

echo "Checking out: $DEPLOY_REF"
git checkout "$DEPLOY_REF"

echo "Using docker compose file at $APP_DIR/docker-compose.yml"

echo "Stopping existing services (if any)..."
docker compose down || true

echo "Building images..."
docker compose build

echo "Running database migrations..."
docker compose run --rm db-migrate

echo "Starting bot service..."
docker compose up -d bot

echo "=== Deployment complete $(date) ==="
docker compose ps
echo "--- Recent logs (tail 50) ---"
docker compose logs --tail=50
