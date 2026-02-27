FROM python:3.11-slim

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first
COPY pyproject.toml uv.lock ./

# Install dependencies (this uses uv's pip compatibility to install globally in the container)
RUN uv pip install --system -r pyproject.toml

# Copy application files (ignoring data directories via .dockerignore usually)
COPY . .

# Expose standard port
EXPOSE 5000

# Set environment variables (can be overridden at runtime)
ENV PLOTS_DIR=/darrays/qc-working/images
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000
ENV GUNICORN_WORKERS=4
ENV GUNICORN_TIMEOUT=120

# Run gunicorn by default
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]
