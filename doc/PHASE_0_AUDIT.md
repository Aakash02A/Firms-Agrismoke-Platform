# 🛰️ AgriSmoke AI — Phase 0: Repository Audit & Integration Gap Analysis

> **Historical Architectural Baseline Document**  
> **Repository Root**: `A:\PROJECT\EVS\evs fine`  
> **Baseline Git Commit**: `c7f1a8c` (Baseline commit: AgriSmoke AI state before NASA FIRMS transformation)  
> **Active Test Status**: 4/4 Test Suites Passed (100%), Live Server Integration 100% Passed.  
> **Auditor Role**: Senior Software Architect, Geospatial Intelligence & Data Engineer.  

---

## 1. Repository Architecture Report

AgriSmoke AI was originally structured as a modular monolithic Python backend with a zero-build vanilla JavaScript single-page application (SPA) and a local SQLite relational store.

```
evs fine/
├── ai-ml/                   # Machine Learning & Physical Dispersion Engine
│   ├── dataset_generator.py # Synthesizes 6,500 physically calibrated observation records
│   ├── train_model.py       # Algorithmic benchmark & serialization pipeline
│   ├── model_inference.py   # Prediction engine, CPCB conversion & diurnal cycle
│   ├── training_data.csv    # 6,500 record training dataset
│   └── models/              # Serialized joblib models and metrics JSON
│
├── backend/                 # Python 3.13 FastAPI Backend
│   ├── main.py              # 13 REST API endpoints, CORS & static file mounting
│   ├── database.py          # SQLite CRUD query functions
│   ├── run.py               # Uvicorn 1-click startup server
│   └── requirements.txt     # Python backend dependencies
│
├── database/                # SQLite Relational Data Storage
│   ├── schema.sql           # 9 SQLite schema tables
│   ├── init_db.py           # Database seeder script
│   └── agri_smoke.db        # Active SQLite database file
│
├── frontend/                # Interactive User Interface (Zero-Build Vanilla JS/CSS)
│   ├── index.html           # SPA Dashboard & 6 Tab Panels
│   ├── css/styles.css       # Clean Light Enterprise Design System
│   └── js/                  # Visualization engines and client controllers
│       ├── app.js           # Client orchestrator & API debouncer
│       ├── charts-engine.js # Pure SVG vector charting engine
│       ├── demo-data.js     # Calibrated baseline reference data
│       ├── map-engine.js    # Canvas geospatial projection & particle flow
│       └── prediction-model.js # Deterministic client fallback model
│
├── deploy/                  # Containerization & Startup Scripts
│   ├── Dockerfile           # Multi-stage production container
│   ├── docker-compose.yml   # Compose service definition
│   ├── nginx.conf           # Reverse proxy configuration
│   └── run_local.bat/.sh    # Local launchers
│
├── doc/                     # Architecture & API Specifications
└── tests/                   # Automated Regression Test Suite
    ├── test_dom_elements.py # 90 DOM element IDs verification
    ├── test_database.py     # Database CRUD verification
    ├── test_ml_model.py     # ML regression & dispersion verification
    ├── test_backend_api.py  # REST API endpoint tests
    └── test_live_server.py  # End-to-end integration test
```

---

## 2. Existing Functionality Inventory

| Component | Technology | Working Status | Description |
| :--- | :--- | :---: | :--- |
| **REST API** | FastAPI 0.115, Uvicorn, Pydantic v2 | Operational | 13 endpoints providing stations, hotspots, trends, GRAP, alerts, predictions, diurnal forecasts, metrics, and CSV exports. |
| **Data Storage** | SQLite 3 (`agri_smoke.db`) | Operational | 9 tables (`monitoring_stations`, `fire_hotspots`, `hourly_forecasts`, `weekly_trends`, `district_fire_counts`, `grap_stages`, `early_warning_alerts`, `simulation_history`, `custom_thresholds`). |
| **ML Engine** | scikit-learn (`GradientBoostingRegressor`) | Operational | Predicts total $\text{PM}_{2.5}$ using 14 engineered physical features ($R^2 = 0.9886$, $\text{RMSE} = 17.67\,\mu\text{g/m}^3$). |
| **Geospatial Map** | HTML5 Canvas 2D Engine | Operational | Custom projection engine rendering coordinate grid, regional boundaries (Punjab, Haryana, Delhi, Western UP), wind vectors, animated smoke particles, and hotspots. |
| **Charts** | SVG Vector Chart Engine | Operational | 24h diurnal forecast curve, 7-day trend bars, source apportionment donut, district burning bars, and radial AQI speedometer. |
| **Dual-Mode** | Client/Server Architecture | Operational | Connects to FastAPI backend when available, falls back to client-side deterministic physics engine when offline. |

---

## 3. Technical Debt Report

1. **Synthetic / Mocked Data Ingestion**:
   - Active fire hotspots in `database/init_db.py` were static seeded rows (10 districts), not dynamically fetched from satellite telemetry.
   - The ML training data in `ai-ml/training_data.csv` was synthesized via mathematical dispersion formulas rather than real satellite and ground-sensor observations.

2. **Missing Configuration Management**:
   - No `.env` or structured configuration module for API keys, timeouts, or sensor parameters.

3. **No External Integration Pipeline**:
   - No HTTP client, rate limiter, or retry mechanism for external satellite providers (NASA FIRMS, CPCB, or Open-Meteo).

4. **Permissive CORS**:
   - `allow_origins=["*"]` was set across all methods and headers without origin segregation.

5. **Data Model Limitations**:
   - The initial `fire_hotspots` table only stored aggregate district numbers (`fire_count`, `avg_frp`), lacking individual satellite pixel-level observations (latitude, longitude, brightness, satellite sensor, scan, track, confidence, day/night).

---

## 4. NASA FIRMS Integration Gap Analysis

| Capability | Initial State | Required State for Real-World Operation |
| :--- | :--- | :--- |
| **NASA API Client** | None | Dedicated, authenticated HTTP client for `firms.modaps.eosdis.nasa.gov` Area API with timeout, retry, backoff, and caching. |
| **Authentication** | None | Secure `MAP_KEY` management via environment variables with zero credential leakage to client-side code. |
| **Supported Sensors** | None | Configurable multi-sensor support: VIIRS NOAA-20 NRT, VIIRS SNPP NRT, VIIRS NOAA-21 NRT, MODIS NRT. |
| **Data Ingestion** | Static database seeder | Automated & on-demand ingestion for the Indo-Gangetic bounding box (`73.5, 27.5, 78.5, 32.5`). |
| **Observation Storage** | Aggregated district counts | Pixel-level `fire_observations` table with unique observation hashes, deduplication, and full NASA telemetry fields. |
| **Fire Classification** | Assumed agricultural | Multi-class rules-based classification engine distinguishing agricultural burning, forest fires, industrial heat sources, and unclassified anomalies. |
| **District Aggregation** | Static ranking | Dynamic spatial boundary assignment aggregating pixel detections into district totals, FRP metrics, and confidence distributions. |
| **Event Clustering** | None | Spatiotemporal clustering grouping adjacent pixels into estimated fire events. |
| **Data Freshness & Sync** | Hardcoded timestamp | `data_sync_jobs` and `data_provider_status` tracking ingestion timestamps, record counts, duplicates skipped, and API errors. |
| **Interactive Map** | Static canvas markers | Real-time marker rendering, clustering, satellite/confidence/FRP/date filtering, and observation detail inspection. |
| **Predictor Integration** | Simulated fire counts | Live satellite fire metrics (active count, cumulative FRP, distance-weighted density) piped into the prediction pipeline. |

---

## 5. Phased Implementation Execution Strategy

- **Phase 1 — Architecture & Data Design**: Define database extensions (`fire_observations`, `data_sync_jobs`, `data_provider_status`), typed Pydantic schemas, and API contracts. *(Implemented)*
- **Phase 2 — NASA FIRMS Integration Module**: Implement `backend/integrations/nasa_firms/` (client, parser, normalizer, deduplicator, persistence service). *(Implemented)*
- **Phase 3 — Geospatial Intelligence & District Aggregation**: Implement spatial point-in-polygon mapping and spatiotemporal clustering. *(Implemented)*
- **Phase 4 — Fire Classification & Analytics Engine**: Multi-factor evidence-based fire classification and district analytics. *(Implemented)*
- **Phase 5 — Existing AI Prediction Integration**: Evaluate and connect satellite fire density and FRP into the prediction engine with temporal alignment. *(Implemented)*
- **Phase 6 — Frontend Integration**: Connect the command center UI to real NASA observation endpoints, interactive filters, provider status, and reports. *(Implemented)*
- **Phase 7 — Reliability, Scheduling & Live Weather**: Ingestion scheduler, live meteorological data, rate limiting, and health monitoring. *(Current Focus)*
- **Phase 8 — Complete Verification**: Comprehensive test suite covering NASA mock fixtures, parsing edge cases, API contracts, and regression. *(Implemented)*
- **Phase 9 — Documentation & Production Handover**: Update all system documentation, setup guides, and operational manuals. *(Implemented)*

