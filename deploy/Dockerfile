# AgriSmoke AI - Container Deployment
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (curl used for the container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project modules
COPY backend/ ./backend/
COPY database/ ./database/
COPY ai-ml/ ./ai-ml/
COPY frontend/ ./frontend/

# Create a non-root user and hand it ownership of the writable data dirs,
# then run init + model training as that user so the artifacts are not root-owned.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/database \
    && chown -R appuser:appuser /app
USER appuser

# Runtime configuration is declared BEFORE the seeding step so the database
# created at build time lands on the SAME path the server opens at runtime.
# HOST must be 0.0.0.0 so the PaaS/container port mapping is reachable
# (loopback-only binding would make the service appear down).
#
# DB_PATH is intentionally env-overridable:
#   * docker-compose bind-mounts the host ./database dir here (persistent);
#   * Render's blueprint overrides DB_PATH to /var/data + a diskMount (see render.yaml);
#   * backend/database.py.ensure_ready() also creates/seeds the target dir at boot,
#     so a fresh empty volume self-heals without this build-time step.
ENV PORT=8000
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend:/app/ai-ml
ENV DB_PATH=/app/database/agri_smoke.db

# Initialize SQLite database and ensure model artifacts exist (as non-root)
RUN python database/init_db.py
RUN python ai-ml/train_model.py

EXPOSE 8000

# Liveness probe against the lightweight health endpoint.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# Start FastAPI server
CMD ["python", "backend/run.py"]
