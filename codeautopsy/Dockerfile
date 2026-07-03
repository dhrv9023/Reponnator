FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (build-essential for tree-sitter parsing, git to clone repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend files
COPY . .

# Expose port 8000
EXPOSE 8000

# Run FastAPI app with uvicorn in production mode
CMD ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
