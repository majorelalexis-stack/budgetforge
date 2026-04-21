#!/usr/bin/env bash
# BudgetForge — deploy script (run as ubuntu on VPS)
# Usage: ./deploy.sh
set -euo pipefail

DEPLOY_DIR="/opt/budgetforge"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Syncing files..."
rsync -a --exclude='.git' --exclude='node_modules' --exclude='venv' --exclude='__pycache__' \
  "$REPO_DIR/" "$DEPLOY_DIR/"

echo "==> Backend: installing deps..."
cd "$DEPLOY_DIR/backend"
python3 -m venv venv
venv/bin/pip install -q -r requirements.txt

echo "==> Backend: running migrations..."
venv/bin/alembic upgrade head

echo "==> Dashboard: installing deps & building..."
cd "$DEPLOY_DIR/dashboard"
npm ci --silent
npm run build

echo "==> Restarting services..."
sudo systemctl daemon-reload
sudo systemctl enable budgetforge-backend budgetforge-dashboard
sudo systemctl restart budgetforge-backend budgetforge-dashboard

echo "==> Status:"
sudo systemctl is-active budgetforge-backend
sudo systemctl is-active budgetforge-dashboard

echo ""
echo "Deploy complete."
echo "  Backend : http://localhost:8011/health"
echo "  Dashboard: http://localhost:3011"
