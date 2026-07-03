#!/bin/bash

# CodeAutopsy × Repponator — Quick Start Script
# Starts both backend and frontend in development mode

set -e

echo "🚀 CodeAutopsy × Repponator — Starting..."
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from correct directory
if [ ! -f "RUN_GUIDE.md" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Function to start backend
start_backend() {
    echo -e "${BLUE}Starting FastAPI backend...${NC}"
    cd codeautopsy
    
    # Check if venv exists
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate venv
    source venv/bin/activate
    
    # Install dependencies if needed
    if ! python3 -c "import fastapi" 2>/dev/null; then
        echo "Installing dependencies..."
        pip install -r requirements.txt
    fi
    
    # Start backend
    echo -e "${GREEN}✓ Backend starting on http://localhost:8000${NC}"
    echo "  API Docs: http://localhost:8000/docs"
    echo ""
    python3 -m uvicorn api.main:app --reload --port 8000
}

# Function to start frontend
start_frontend() {
    echo -e "${BLUE}Starting React frontend...${NC}"
    cd codeautopsy-web
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo "Installing dependencies..."
        npm install
    fi
    
    # Start frontend
    echo -e "${GREEN}✓ Frontend starting on http://localhost:5173${NC}"
    echo ""
    npm run dev
}

# Check if we should start both or just one
if [ "$1" == "backend" ]; then
    start_backend
elif [ "$1" == "frontend" ]; then
    start_frontend
else
    # Start backend in background
    start_backend &
    BACKEND_PID=$!
    
    sleep 3
    
    # Start frontend in foreground
    start_frontend
    
    # Cleanup on exit
    trap "kill $BACKEND_PID" EXIT
fi
