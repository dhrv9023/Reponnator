#!/usr/bin/env bash

# CodeAutopsy × Repponator — Development Startup Script
# Starts both FastAPI backend and React (Vite) frontend simultaneously.

set -euo pipefail

# ANSI color codes for pretty output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}🚀 CodeAutopsy × Repponator — Startup Console${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. Enforce running from the correct workspace root
if [ ! -d "codeautopsy" ] || [ ! -d "codeautopsy-web" ]; then
    echo -e "${RED}❌ Error: Please run this script from the workspace root directory.${NC}"
    echo -e "Directory must contain both ${YELLOW}codeautopsy/${NC} and ${YELLOW}codeautopsy-web/${NC} folders."
    exit 1
fi

# Store root directory path
ROOT_DIR=$(pwd)
BACKEND_PID=0

# Clean up background tasks on interrupt / exit
cleanup() {
    if [ "$BACKEND_PID" -ne 0 ]; then
        echo -e "\n${YELLOW}🛑 Shutting down backend server (PID: $BACKEND_PID)...${NC}"
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}✨ Cleanup complete. Goodbye!${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 2. Start Backend Function
start_backend() {
    echo -e "${BLUE}📡 Initialising FastAPI Backend...${NC}"
    cd "${ROOT_DIR}/codeautopsy"
    
    # Setup virtual environment if missing
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}📦 Creating Python virtual environment (venv)...${NC}"
        python3 -m venv venv
    fi
    
    # Activate venv
    source venv/bin/activate
    
    # Install/Verify requirements
    echo -e "${BLUE}📦 Checking Python dependencies...${NC}"
    pip install --quiet -r requirements.txt
    
    # Launch Uvicorn server in background
    echo -e "${GREEN}✓ FastAPI Backend starting on port 8000...${NC}"
    python3 -m uvicorn api.main:app --port 8000 &
    BACKEND_PID=$!
    
    # Let backend spin up
    sleep 3
}

# 3. Start Frontend Function
start_frontend() {
    echo -e "${BLUE}🌐 Initialising React Frontend...${NC}"
    cd "${ROOT_DIR}/codeautopsy-web"
    
    # Install node_modules if missing
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}📦 Installing frontend dependencies (this may take a moment)...${NC}"
        npm install --quiet
    fi
    
    # Launch Vite in foreground (so logs and hot-reloads show here)
    echo -e "${GREEN}✓ Vite Dev Server launching...${NC}"
    echo -e "--------------------------------------------------"
    echo -e "  Backend API:  ${YELLOW}http://localhost:8000${NC}"
    echo -e "  API Docs:     ${YELLOW}http://localhost:8000/docs${NC}"
    echo -e "  Frontend UI:  ${YELLOW}http://localhost:5173${NC}"
    echo -e "--------------------------------------------------"
    echo -e "${YELLOW}Press Ctrl+C to terminate both servers.${NC}"
    echo -e "--------------------------------------------------"
    npm run dev
}

# Route commands
if [ "${1:-}" = "backend" ]; then
    start_backend
    # If running backend only in foreground, wait for it
    wait "$BACKEND_PID"
elif [ "${1:-}" = "frontend" ]; then
    # Disable trap cleanup since we didn't spin up background backend
    trap - SIGINT SIGTERM EXIT
    start_frontend
else
    # Spin up backend in background, then run frontend in foreground
    start_backend
    start_frontend
fi
