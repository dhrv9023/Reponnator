"""
api/main.py — FastAPI application entry point

Phase 8: Production-grade REST API for CodeAutopsy × Repponator
"""

import logging
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] [%(name)s] — %(message)s'
)

logger = logging.getLogger(__name__)

# Import routers
from api.routers import repos, parse, chunk, qa, diagram, story, jobs
from api.middleware import setup_exception_handlers
from api.models import HealthResponse

# Create FastAPI app
app = FastAPI(
    title="CodeAutopsy API",
    description="REST API for the CodeAutopsy × Repponator pipeline",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup exception handlers
setup_exception_handlers(app)

# Include routers
app.include_router(repos.router, prefix="/api/repos", tags=["Repositories"])
app.include_router(parse.router, prefix="/api/parse", tags=["Parsing"])
app.include_router(chunk.router, prefix="/api/chunk", tags=["Chunking"])
app.include_router(qa.router, prefix="/api/qa", tags=["Q&A"])
app.include_router(diagram.router, prefix="/api/diagram", tags=["Diagram"])
app.include_router(story.router, prefix="/api/story", tags=["Story"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])

# Health check endpoint
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    groq_key = os.getenv("GROQ_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")
    
    return HealthResponse(
        status="ok",
        version="1.0.0",
        groq_configured=bool(groq_key),
        github_token_configured=bool(github_token)
    )


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "CodeAutopsy API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
