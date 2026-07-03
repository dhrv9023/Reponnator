#!/bin/bash
# Test the full pipeline via API

echo "🚀 Testing Full Pipeline via API"
echo "=================================="
echo ""

cd /home/ag2/Desktop/github_prj/codeautopsy

# Start backend
echo "📡 Starting backend server..."
python3 -m uvicorn api.main:app --port 8000 &
API_PID=$!
sleep 5

# Health check
echo "🏥 Health check..."
curl -s http://localhost:8000/api/health | jq
echo ""

# Test ingest (full pipeline)
echo "📥 Starting ingestion (full pipeline)..."
RESPONSE=$(curl -s -X POST http://localhost:8000/api/repos/ingest \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/pallets/itsdangerous", "force": true}')

echo "$RESPONSE" | jq
JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')
echo ""
echo "Job ID: $JOB_ID"
echo ""

# Poll job status
echo "⏳ Polling job status..."
for i in {1..60}; do
    STATUS=$(curl -s http://localhost:8000/api/jobs/$JOB_ID | jq -r '.status')
    PROGRESS=$(curl -s http://localhost:8000/api/jobs/$JOB_ID | jq -r '.progress')
    MESSAGE=$(curl -s http://localhost:8000/api/jobs/$JOB_ID | jq -r '.message')
    
    echo "[$i] Status: $STATUS | Progress: $PROGRESS% | Message: $MESSAGE"
    
    if [ "$STATUS" == "completed" ] || [ "$STATUS" == "failed" ]; then
        break
    fi
    
    sleep 2
done

echo ""
echo "✅ Final status:"
curl -s http://localhost:8000/api/jobs/$JOB_ID | jq
echo ""

# Check outputs
echo "📊 Checking outputs..."
echo ""

echo "Diagram:"
if [ -f "data/repos/pallets__itsdangerous/diagram/mermaid_diagram.mmd" ]; then
    echo "✅ Diagram generated"
    cat data/repos/pallets__itsdangerous/diagram/diagram_metadata.json | jq '{nodes: .total_nodes, edges: .total_edges}'
else
    echo "❌ Diagram not found"
fi
echo ""

echo "Story:"
if [ -f "data/repos/pallets__itsdangerous/story/story_output.json" ]; then
    echo "✅ Story generated"
    cat data/repos/pallets__itsdangerous/story/story_output.json | jq '{title: .title, sections: (.sections | length)}'
else
    echo "❌ Story not found"
fi
echo ""

# Kill server
echo "🛑 Stopping backend server..."
kill $API_PID

echo ""
echo "🎉 Test complete!"
