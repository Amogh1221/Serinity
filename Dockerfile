# Use a lightweight Python 3.11 base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/tmp/hf_home \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies (ffmpeg is required by FunASR/torchaudio for webm/ogg audio decoding)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user (Hugging Face requirement)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Install dependencies first (to leverage Docker caching)
COPY --chown=user:user Requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r Requirements.txt

# Copy the rest of the application code
COPY --chown=user:user . /app/

# Expose port 7860 (Hugging Face requirement)
EXPOSE 7860

# Start the FastAPI application with 2 workers.
# Each worker loads ~1.5GB of ML models (SenseVoice + BERT + VAD).
# With 16GB RAM this is safe (~3GB total), and 2 workers provides real
# concurrency benefit for CPU-bound STT when multiple users transcribe simultaneously.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2", "--timeout-keep-alive", "75"]
