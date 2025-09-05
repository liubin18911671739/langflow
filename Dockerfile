# Production Dockerfile for Langflow
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r langflow && useradd -r -g langflow langflow

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
COPY README.md ./

# Install uv
RUN pip install uv

# Install Python dependencies
RUN uv pip install --system -e .

# Copy application code
COPY src/ ./src/
COPY Makefile ./
COPY .gitignore ./

# Create necessary directories
RUN mkdir -p /app/logs /app/uploads /app/temp && \
    chown -R langflow:langflow /app

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER langflow

# Expose port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/api/v1/health_check || exit 1

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command
CMD ["python", "-m", "langflow", "run", "--host", "0.0.0.0", "--port", "7860"]