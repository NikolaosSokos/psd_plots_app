# PSD Plots App

Web application for visualizing Power Spectral Density (PSD) plots from seismic data.

## Deployment & Execution

There are multiple ways to run this application.

### Option 1: Docker (Recommended)
You can run the app in the background permanently using Docker Compose. The `docker-compose.yml` is configured to automatically restart the application (`unless-stopped`), ensuring it stays alive.

1. Install Docker & Docker Compose if not already installed.
2. Edit `docker-compose.yml` if necessary, especially the volume mount path `/darrays/qc-working/images` if it differs on your machine.
3. Start the application:
```bash
docker compose up -d
```
It will run in the background. If the container or machine restarts, Docker will automatically spin it back up.

### Option 2: Systemd Service (Native Background Service)
If you prefer running it natively without Docker, you can install it as a `systemd` service. This will also keep it alive permanently.

1. Open `plots-app.service` and verify the `User`, `Group`, and `WorkingDirectory` paths.
2. Copy the service file to the systemd directory:
```bash
sudo cp plots-app.service /etc/systemd/system/
```
3. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable plots-app
sudo systemctl start plots-app
```

### Option 3: Local Development
To run the server locally for development:

```bash
uv run python app.py
```

## Configuration (Environment Variables)

This repository includes a `config.py` that reads from environment variables, making it highly portable. You can configure:

* `PLOTS_DIR`: Directory where images are located (default: `/darrays/qc-working/images`)
* `FLASK_HOST`: Address to bind to (default: `0.0.0.0`)
* `FLASK_PORT`: Port to run the application on (default: `5000`)
* `GUNICORN_WORKERS`: Number of workers (used by Docker and systemd, default: `4`)

To override, either set them inside `docker-compose.yml`, or pass them via command line:
```bash
PLOTS_DIR=/my/custom/path uv run python app.py
```
