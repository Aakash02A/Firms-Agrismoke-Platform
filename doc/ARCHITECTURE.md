# 🏗️ AgriSmoke AI &bull; System Architecture & Technical Design

The **AgriSmoke AI** platform is an end-to-end atmospheric dispersion, machine learning inference, and air quality simulation system for the **Indo-Gangetic Airshed** (Punjab, Haryana, Delhi-NCR, and Western UP).

---

## 1. System Architecture Overview

```mermaid
graph TD
    subgraph Client["Frontend Presentation Layer (Browser)"]
        UI["Single Page Application (index.html)"]
        Canvas["Interactive Geospatial Canvas (map-engine.js)"]
        Charts["SVG Visualization Engine (charts-engine.js)"]
        Controller["UI Controller & Client Model (app.js)"]
    end

    subgraph Server["Backend Application Layer (FastAPI)"]
        API["FastAPI REST Endpoints (backend/main.py)"]
        CORS["CORS & Static Files Middleware"]
        DBAccess["Database Layer (backend/database.py)"]
    end

    subgraph Data["Persistence Layer (SQLite)"]
        DB[("agri_smoke.db")]
        StationsTbl["monitoring_stations"]
        HotspotsTbl["fire_hotspots"]
        WeeklyTbl["weekly_trends"]
        DistrictsTbl["district_fire_counts"]
        AlertsTbl["early_warning_alerts"]
        HistoryTbl["simulation_history"]
    end

    subgraph AIML["Machine Learning & Physics Engine (ai-ml/)"]
        Gen["Dataset Generator (dataset_generator.py)"]
        Train["Model Trainer & Benchmarker (train_model.py)"]
        ModelArtifact["Trained Regressor (aqi_dispersion_model.joblib)"]
        Inference["Inference Engine (model_inference.py)"]
    end

    UI --> Controller
    Canvas --> Controller
    Charts --> Controller

    Controller -->|REST JSON Requests| API
    API --> DBAccess
    DBAccess --> DB

    DB --> StationsTbl
    DB --> HotspotsTbl
    DB --> WeeklyTbl
    DB --> DistrictsTbl
    DB --> AlertsTbl
    DB --> HistoryTbl

    API --> Inference
    Inference --> ModelArtifact
    Train --> ModelArtifact
    Gen --> Train
```

---

## 2. Directory Hierarchy

```
evs fine/
├── frontend/                # Interactive Web User Interface
│   ├── index.html           # Semantic Single-Page Dashboard & Tab panels
│   ├── css/
│   │   └── styles.css       # Glassmorphism, CSS variables, dark theme
│   └── js/
│       ├── app.js           # Client orchestrator, live API connector & debouncer
│       ├── charts-engine.js # Pure SVG vector charting engine
│       ├── demo-data.js     # Calibrated baseline reference data
│       ├── map-engine.js    # Canvas geospatial projection & particle flow
│       └── prediction-model.js # Deterministic client fallback model
│
├── backend/                 # Python 3.13 FastAPI Backend
│   ├── main.py              # REST API routes & static file delivery
│   ├── database.py          # SQLite database connection & CRUD queries
│   ├── run.py               # 1-Click backend launcher
│   └── requirements.txt     # Python backend dependencies
│
├── database/                # Relational Data Storage
│   ├── schema.sql           # SQLite database schema
│   ├── init_db.py           # Seeder script for monitoring stations & hotspots
│   └── agri_smoke.db        # Production SQLite database file
│
├── ai-ml/                   # Machine Learning Training & Inference
│   ├── dataset_generator.py # Synthesizes calibrated atmospheric dataset
│   ├── train_model.py       # Trains Gradient Boosting, RF & XGBoost regressors
│   ├── model_inference.py   # Loads serialized model & computes CPCB AQI
│   ├── training_data.csv    # 6,500 observation atmospheric dataset
│   └── models/
│       ├── aqi_dispersion_model.joblib # Serialized optimal ML model
│       ├── scaler.joblib    # Feature standardizer
│       └── metrics.json     # Model validation scores & feature importances
│
├── deploy/                  # Production & Local Deployment
│   ├── Dockerfile           # Multi-stage production container
│   ├── docker-compose.yml   # Docker Compose service definition
│   ├── run_local.bat        # Windows 1-click startup batch script
│   ├── run_local.sh         # Linux/macOS startup shell script
│   └── nginx.conf           # Reverse proxy configuration
│
└── doc/                     # System Documentation
    ├── ARCHITECTURE.md      # System architecture & data flow
    ├── API_SPECIFICATION.md # REST API endpoint schemas & curl examples
    ├── ML_MODEL_DOC.md      # Model benchmarks, physics equations & features
    └── SETUP_GUIDE.md       # Step-by-step setup and deployment guide
```

---

## 3. Database Entity Relationship (ER)

```mermaid
erDiagram
    MONITORING_STATIONS {
        string id PK
        string name
        string type
        float lat
        float lng
        int aqi
        string category
        float pm25
        float pm10
        float parali_pct
        string trend
    }

    FIRE_HOTSPOTS {
        string id PK
        string district
        string state
        float lat
        float lng
        int fire_count
        float avg_frp
        string status
        string harvest_progress
        string confidence
        string smoke_intensity
    }

    WEEKLY_TRENDS {
        int id PK
        string day_label
        int aqi
        int fires
        float pm25
        float stubble_pct
        string grap_stage
    }

    DISTRICT_FIRE_COUNTS {
        string district PK
        int fires
        string state
    }

    SIMULATION_HISTORY {
        int id PK
        datetime created_at
        int fire_count
        float wind_speed
        int wind_dir
        int pbl_height
        int baseline_aqi
        int bio_dec_pct
        int happy_seeder_pct
        int predicted_aqi
        float predicted_pm25
        float predicted_pm10
        float parali_pct
        string grap_stage
        int mitigation_drop
    }

    CUSTOM_THRESHOLDS {
        int id PK
        int aqi_threshold
        int fires_threshold
        datetime updated_at
    }
```

---

## 4. Dual-Mode Operation (Live API + Offline Fallback)

The architecture guarantees high availability and zero-installation usage through a **Dual-Mode System**:
1. **Live Backend Mode (Connected to FastAPI & SQLite)**:
   - When `python backend/run.py` is active, the frontend connects to `http://127.0.0.1:8000`.
   - Real-time ML predictions use the trained `GradientBoostingRegressor` model ($R^2 = 0.9886$).
   - Stations, hotspots, weekly trends, and alerts hydrate dynamically from the SQLite database.
   - Simulation runs are logged to SQLite for historical audits.
2. **Standalone Local Mode (Zero Installation)**:
   - If the backend is offline or the user opens `index.html` directly via `file:///`, the frontend smoothly falls back to the embedded deterministic physics dispersion engine in `prediction-model.js`.
   - The user is notified gracefully via the status badge without console errors or interrupted functionality.

