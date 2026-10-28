# Base image: PyTorch runtime with CUDA/cuDNN support (works on CPU too)
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Environment variables for Python runtime optimizations and custom model/data cache paths
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/models/ultralytics \
    MODEL_DIR=/models \
    DATA_DIR=/data \
    TORCH_HOME=/models/torch

# Install system dependencies for computer vision and health checking, then clean up apt cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Leverage layer caching: install Python dependencies before copying source code
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application source code
COPY app/ /app/app

# Create mount points and declare persistent volumes for weights and datasets
RUN mkdir -p /models /data
VOLUME ["/models", "/data"]

# Expose backend service port
EXPOSE 8000

# Container healthcheck targeting the API endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fs http://localhost:8000/api/health || exit 1

# Start Uvicorn with a single worker to preserve dedicated GPU job scheduling
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
