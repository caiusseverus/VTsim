#!/bin/bash
# VTsim Web — production startup script.
# Requires: uv, Node.js + npm (for frontend build).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FRONTEND_DIR="webapp/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

# Build frontend if dist/ doesn't exist or --build flag given.
if [ ! -d "$DIST_DIR" ] || [ "${1}" = "--build" ]; then
  echo "Building frontend..."
  cd "$FRONTEND_DIR"
  npm install
  npm run build
  cd "$SCRIPT_DIR"
fi

echo "Starting VTsim backend at http://localhost:8000"
UV_CACHE_DIR=/tmp/uv-cache uv run uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000
