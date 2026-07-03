"""
api/middleware/error_handler.py — Global exception handling

Custom exceptions and handlers for clean JSON error responses.
"""

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================

class CodeAutopsyAPIError(Exception):
    """Base exception for CodeAutopsy API errors."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class RepoNotFoundError(CodeAutopsyAPIError):
    """Repository not found (404)."""
    def __init__(self, repo_key: str):
        super().__init__(
            message=f"Repository '{repo_key}' has not been ingested yet. Run /api/repos/ingest first.",
            status_code=status.HTTP_404_NOT_FOUND
        )


class PhaseNotCompleteError(CodeAutopsyAPIError):
    """Required phase not complete (409)."""
    def __init__(self, phase: str, required_phase: str):
        super().__init__(
            message=f"Phase {required_phase} output not found. Run /api/{required_phase} first before {phase}.",
            status_code=status.HTTP_409_CONFLICT
        )


class JobAlreadyRunningError(CodeAutopsyAPIError):
    """Job already running for this repo (409)."""
    def __init__(self, phase: str, repo_key: str, job_id: str):
        super().__init__(
            message=f"Job already running for {phase} on {repo_key}. Job ID: {job_id}",
            status_code=status.HTTP_409_CONFLICT
        )


class ExternalAPIError(CodeAutopsyAPIError):
    """External API failed (502)."""
    def __init__(self, service: str, details: str):
        super().__init__(
            message=f"{service} API error: {details}",
            status_code=status.HTTP_502_BAD_GATEWAY
        )


# ============================================================================
# Exception Handlers
# ============================================================================

async def codeautopsy_error_handler(request: Request, exc: CodeAutopsyAPIError):
    """Handle custom CodeAutopsy exceptions."""
    logger.error(f"{exc.__class__.__name__}: {exc.message}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "status_code": exc.status_code
        }
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors (422)."""
    logger.warning(f"Validation error: {exc.errors()}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "message": "Request validation failed",
            "status_code": 422,
            "details": exc.errors()
        }
    )


async def generic_error_handler(request: Request, exc: Exception):
    """Handle all other unhandled exceptions (500)."""
    logger.exception(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred. Please try again later.",
            "status_code": 500
        }
    )


def setup_exception_handlers(app: FastAPI):
    """
    Register all exception handlers with the FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    # Custom exceptions
    app.add_exception_handler(CodeAutopsyAPIError, codeautopsy_error_handler)
    
    # Validation errors
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    
    # Generic fallback
    app.add_exception_handler(Exception, generic_error_handler)
    
    logger.info("Exception handlers registered")
