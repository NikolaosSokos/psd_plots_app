import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).parent.absolute()

# Application Settings
HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
PORT = int(os.environ.get("FLASK_PORT", 5000))

# Data Directories
# Default to /darrays/qc-working/images, but allow overriding via environment variables
PLOTS_DIR = os.environ.get("PLOTS_DIR", "/darrays/qc-working/images")

# Gunicorn Settings (optional, for reference/custom usage)
GUNICORN_WORKERS = int(os.environ.get("GUNICORN_WORKERS", 4))
GUNICORN_TIMEOUT = int(os.environ.get("GUNICORN_TIMEOUT", 120))
