#!/usr/bin/env bash
# AgriSmoke AI - Full Stack Platform Launcher (Linux & macOS)

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=============================================================================="
echo "                [ AgriSmoke AI Platform Launcher ]"
echo "      Crop-Burning & Urban Air Quality Prediction System (Delhi-NCR)"
echo "=============================================================================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    exit 1
fi

echo "[1/4] Checking Python environment..."
python3 --version

# Initialize Database
echo ""
echo "[2/4] Verifying and Initializing SQLite Database..."
python3 database/init_db.py

# Check / Train Machine Learning Model
echo ""
echo "[3/4] Checking Machine Learning Model Artifacts..."
if [ ! -f "ai-ml/models/aqi_dispersion_model.joblib" ]; then
    echo "Training Machine Learning Model..."
    python3 ai-ml/train_model.py
else
    echo "ML model artifacts found in ai-ml/models/."
fi

# Launch Backend Server
echo ""
echo "[4/4] Starting FastAPI Backend on http://127.0.0.1:8000 ..."
echo "- Web Dashboard: http://127.0.0.1:8000"
echo "- Interactive Swagger Docs: http://127.0.0.1:8000/docs"
echo ""
python3 backend/run.py
