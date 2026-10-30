# AgriSmoke AI - Container Deployment
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
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

# Initialize SQLite database and ensure model artifacts exist
RUN python database/init_db.py
RUN python ai-ml/train_model.py

# Expose port
EXPOSE 8000

ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend:/app/ai-ml

# Start FastAPI server
CMD ["python", "backend/run.py"]

