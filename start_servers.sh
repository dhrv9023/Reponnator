#!/bin/bash

echo "🚀 Starting CodeAutopsy Servers"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -d "codeautopsy" ] || [ ! -d "codeautopsy-web" ]; then
    echo "❌ Error: Must run from /home/ag2/Desktop/github_prj/"
    exit 1
fi

echo "📡 Starting Backend Server (Python)..."
cd codeautopsy
python3 -m uvicorn api.main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

echo "⏳ Waiting for backend to start..."
sleep 5

echo "🌐 Starting Frontend Server (React)..."
cd codeautopsy-web
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Servers starting!"
echo "================================"
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "API Docs: http://localhost:8000/docs"
echo "================================"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
