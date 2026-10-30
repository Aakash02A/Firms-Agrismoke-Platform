# 🚀 AgriSmoke AI &bull; Installation & Setup Guide

This guide walks you through setting up and running the AgriSmoke AI full-stack application (Python FastAPI backend, SQLite database, Machine Learning model, and frontend).

---

## 📋 Prerequisites
- **Python 3.10+** (Python 3.13 recommended)
- **Modern Web Browser** (Microsoft Edge, Google Chrome, Mozilla Firefox)
- *(Optional)* Docker and Docker Compose

---

## ⚡ Option 1: 1-Click Launch (Windows)

1. Open File Explorer to `evs fine/`.
2. Double-click [deploy/run_local.bat](file:///a:/CHROME%20-EDGE%20DOWNLOADS/evs%20fine/deploy/run_local.bat).
3. The script will automatically:
   - Check your Python environment.
   - Initialize and seed the SQLite database (`database/agri_smoke.db`).
   - Train/verify the Machine Learning model (`ai-ml/models/aqi_dispersion_model.joblib`).
   - Launch the FastAPI server at `http://127.0.0.1:8000`.
4. Open `http://127.0.0.1:8000` in your web browser.

---

## 🐧 Option 2: 1-Click Launch (Linux & macOS)

1. Open a terminal in the project root:
   ```bash
   chmod +x deploy/run_local.sh
   ./deploy/run_local.sh
   ```
2. Navigate to `http://127.0.0.1:8000`.

---

## 🛠️ Option 3: Manual Step-by-Step Setup

### Step 1: Install Python Dependencies
```bash
python -m pip install -r backend/requirements.txt
```

### Step 2: Initialize the SQLite Database
```bash
python database/init_db.py
```
*Creates `database/agri_smoke.db` and populates tables with calibrated stations, hotspots, weekly trends, and GRAP guidelines.*

### Step 3: Train the Machine Learning Model
```bash
python ai-ml/train_model.py
```
*Generates the atmospheric training dataset, benchmarks candidate algorithms (Gradient Boosting, Random Forest, XGBoost), and serializes the optimal regressor into `ai-ml/models/`.*

### Step 4: Start the Backend Server
```bash
python backend/run.py
```
The server will start listening at `http://127.0.0.1:8000`.
- **Web User Interface**: `http://127.0.0.1:8000`
- **Interactive Swagger Documentation**: `http://127.0.0.1:8000/docs`

---

## 🐳 Option 4: Docker & Docker Compose

To deploy inside an isolated container:
```bash
cd deploy
docker compose up --build
```
Access the application at `http://localhost:8000`.

---

## 🌐 Option 5: Standalone Offline Mode (Zero Installation)

If you don't have Python or want to run entirely offline without a backend:
1. Navigate to `frontend/`.
2. Double-click [frontend/index.html](file:///a:/CHROME%20-EDGE%20DOWNLOADS/evs%20fine/frontend/index.html).
3. The application will detect that the backend is offline and seamlessly engage its built-in client-side simulation engine!

---

## 🔍 Verification & Testing

To test that all backend endpoints and ML inference functions are operating properly:

```bash
# Test System Status
curl http://127.0.0.1:8000/api/status

# Test ML Prediction Endpoint
curl -X POST http://127.0.0.1:8000/api/predict \
     -H "Content-Type: application/json" \
     -d '{"fireCount": 2000, "windSpeed": 12.5, "windDirectionDeg": 310, "pblHeight": 400}'
```

