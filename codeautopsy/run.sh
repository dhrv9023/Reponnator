#!/usr/bin/env bash
# run.sh — CodeAutopsy Phase 1 quick-start script
#
# Usage:
#   ./run.sh https://github.com/pallets/flask
#   ./run.sh pallets/flask --branch 2.x
#   ./run.sh --list

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install dependencies if not already present
if ! python3 -c "import github" &>/dev/null; then
    echo "📦  Installing dependencies…"
    python3 -m pip install -r requirements.txt --break-system-packages --quiet
fi

# Copy env template if .env does not exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "📝  Created .env from .env.example — add your GITHUB_TOKEN for best results."
fi

python3 main.py "$@"
