# 🗺️ AgriSmoke AI — Project Execution Plan & Roadmap

> This document tracks the development lifecycle of the **AgriSmoke AI** platform, detailing completed implementation phases, current status, and prioritized upcoming phases (To-Do).

---

## 📊 Phase Status Overview

| Phase | Description | Status | Completion Date |
| :---: | :--- | :---: | :---: |
| **Phase 1** | Foundation, Monorepo Architecture & Security Setup | **Completed** | Oct 2026 |
| **Phase 2** | Relational Database & Geospatial Persistence Layer (SQLite) | **Completed** | Oct 2026 |
| **Phase 3** | Atmospheric Physics & Machine Learning Dispersion Pipeline | **Completed** | Oct 2026 |
| **Phase 4** | FastAPI Backend Server & NASA FIRMS Satellite Integration | **Completed** | Oct 2026 |
| **Phase 5** | Frontend Geospatial Canvas & Interactive Vector Visualizations | **Completed** | Oct 2026 |
| **Phase 6** | End-to-End Automated Testing, Containerization & CI Scripts | **Completed** | Oct 2026 |
| **Phase 7** | Live Meteorological Data Integration & Automated Background Sync | **Completed** | Oct 2026 |
| **Phase 8** | Advanced Spatio-Temporal ML & Satellite AOD Ingestion | **Completed (Core Analytics)** | Oct 2026 |
| **Phase 9** | Real-Time Push Notifications, WebSockets & Policy Simulator | **Completed (Core Services)** | Oct 2026 |
| **Phase 10** | Cloud-Native Scale-Out (PostGIS + Redis + PWA) | **Completed (Production Ready)** | Oct 2026 |

---

## ✅ Completed Phases

### Phase 1: Foundation, Architecture & Security Setup
- [x] **Monorepo Directory Structure**: Clean separation of `ai-ml/`, `backend/`, `database/`, `deploy/`, `doc/`, `frontend/`, and `tests/`.
- [x] **Confidentiality & Gitignore Security**: Robust `.gitignore` preventing leakage of `.env`, API keys, private certificates, runtime `.db` files, and heavy compiled binary model weights (`*.joblib`).
- [x] **Environment Template**: Sanitized `.env.example` defining parameters for `NASA_FIRMS_MAP_KEY`, timeouts, and ports.
- [x] **System Documentation**: Comprehensive guides covering [Architecture](doc/ARCHITECTURE.md), [REST API Specifications](doc/API_SPECIFICATION.md), [Data Dictionary](doc/DATA_DICTIONARY.md), [ML Models](doc/ML_MODEL_DOC.md), and [Setup Guide](doc/SETUP_GUIDE.md).
- [x] **Agent Onboarding Protocol**: Published [`agent.md`](agent.md) with module patterns, conventions, and runtime gotchas for seamless multi-agent collaboration.

### Phase 2: Relational Database & Geospatial Persistence Layer
- [x] **SQLite Schema Design**: Created `database/schema.sql` defining 15 relational tables with 5 indexing strategies.
- [x] **Spatial Master Seeding**: Developed `database/init_db.py` to seed 33 district geographic boundaries, centroids, and land-use categories across Punjab, Haryana, Delhi-NCR, Rajasthan, and Western UP.
- [x] **Domain Entities**: Tables for CPCB monitoring stations, satellite fire hotspots, 7-day trend logs, GRAP action plan stages, and simulation history.
- [x] **Data Access Layer**: Built `backend/database.py` with thread-safe connection pooling and automatic mapping from `snake_case` DB columns to `camelCase` API JSON.

### Phase 3: Atmospheric Physics & Machine Learning Dispersion Pipeline
- [x] **Atmospheric Dataset Generator**: Built `ai-ml/dataset_generator.py` generating 6,500 physically calibrated records modeling Indo-Gangetic meteorology, boundary layer dynamics, and stubble fire loading.
- [x] **Model Benchmarking Pipeline**: Implemented `ai-ml/train_model.py` comparing Gradient Boosting, Random Forest, and Ridge regressors ($R^2 \approx 0.9886$).
- [x] **Inference Engine**: Developed `ai-ml/model_inference.py` featuring CPCB AQI breakpoint calculation, Gaussian plume dispersion fallback, and 24-hour diurnal curve generation.
- [x] **Self-Healing Loading**: Built automatic retraining and unpickling compatibility bridge to handle scikit-learn Cython version transitions seamlessly.

### Phase 4: FastAPI Backend Server & NASA FIRMS Satellite Integration
- [x] **REST API Server**: FastAPI application (`backend/main.py`) providing 22+ endpoints with CORS middleware and static asset delivery.
- [x] **NASA FIRMS Ingestion Client**: Implemented `backend/integrations/nasa_firms/` with HTTP connection pooling, exponential backoff retries, and rate-limit handling.
- [x] **Deduplication & Normalization**: SHA-256 fingerprinting for satellite thermal anomalies across VIIRS and MODIS instruments.
- [x] **Agricultural Fire Classifier**: Rule-based engine distinguishing agricultural crop residue burning from industrial refineries and forest fires.
- [x] **Spatiotemporal Clustering**: Single-linkage clustering grouping individual thermal pixels within 3.5 km into discrete fire events.
- [x] **Alert Lifecycle Management**: Structured state machine tracking alert lifecycle states (`NEW` → `ACKNOWLEDGED` → `INVESTIGATING` → `RESOLVED` → `DISMISSED`).

### Phase 5: Frontend Geospatial & Interactive Visualizations
- [x] **Zero-Dependency SPA**: High-performance dashboard (`frontend/index.html`) running with zero external CDN dependencies or Node.js build pipelines.
- [x] **Dark Glassmorphic UI**: Design system in `frontend/css/styles.css` using CSS custom properties, responsive grids, and accessible color tokens.
- [x] **Canvas Geospatial Map Engine**: Self-contained coordinate projection canvas (`map-engine.js`) rendering thermal hotspots, monitoring stations, and animated smoke plume particle flows.
- [x] **Vector Charting Engine**: Pure SVG/Canvas charting suite (`charts-engine.js`) generating diurnal AQI curves, 7-day trajectories, source apportionment donuts, and gauge dials.
- [x] **Client-Side Simulation Fallback**: Implemented `prediction-model.js` and `demo-data.js` to allow 100% full-fidelity offline operation via `file:///` protocol.
- [x] **Real-Time Interactive Controls**: Fluid parameter sliders with dynamic glow fills, debounced API synchronization, and cubic easing numeric animations.

### Phase 6: Automated Testing & Containerized Deployment
- [x] **Comprehensive Test Suite**: Orchestrated master test suite (`tests/run_all_tests.py`) covering DOM validation, SQLite CRUD, FIRMS ingestion, ML physics boundaries, and FastAPI routing (100% pass rate).
- [x] **Docker Containerization**: Multi-stage `deploy/Dockerfile` and `docker-compose.yml` for isolated deployment.
- [x] **Nginx Reverse Proxy**: Production-ready `deploy/nginx.conf` handling static compression and reverse proxying.
- [x] **1-Click Launchers**: Windows (`run_local.bat`) and POSIX (`run_local.sh`) scripts automating environment validation, database initialization, model training, and server startup.

---

## 📋 Upcoming Phases (To-Do)

### Phase 7: Live Meteorological API Integration & Automated Background Sync
- [x] **Real-Time Weather Integration**:
  - Connected Open-Meteo API to fetch real-time ambient temperature, relative humidity, surface pressure, wind speed, and wind direction for the Indo-Gangetic plain.
  - Implemented dynamic Planetary Boundary Layer (PBL) height extraction from hourly meteorological model data with ventilation index calculation.
  - Built calibrated seasonal fallback snapshot in `backend/integrations/weather/service.py` with in-memory TTL caching.
- [x] **Background Ingestion Scheduler**:
  - Implemented background task scheduler in `backend/scheduler.py` handling periodic NASA FIRMS satellite synchronization (every 3 hours) and live weather cache refreshes (every 15 minutes).
  - Added FastAPI lifespan events to launch the daemon thread safely on startup and gracefully shut down on exit.
- [x] **REST API Weather & Scheduler Endpoints**:
  - Added `/api/v1/weather/live` and `/api/v1/weather/refresh` for real-time airshed telemetry.
  - Added `/api/v1/scheduler/status`, `/api/v1/scheduler/trigger/firms`, and `/api/v1/scheduler/trigger/weather` for background job monitoring.
- [x] **Live Telemetry Controls in UI**:
  - Added "Live Meteorology & Satellite Telemetry Sync" toolbar on the prediction dashboard.
  - "🌤️ Sync Live Weather" button queries Open-Meteo via backend, dynamically populates sliders (wind speed, wind bearing, PBL height), and updates the live metric strip.
  - "🛰️ Sync Satellite Fires" button pulls live satellite active fire counts from NASA FIRMS.

### Phase 8: Advanced Spatio-Temporal ML & Satellite AOD Ingestion
- [x] **Uncertainty Quantification (90% Confidence Interval)**:
  - Formulated atmospheric dispersion error bounds accounting for nocturnal boundary layer compression and wind vector shear.
  - Implemented dynamic confidence margins: outputting `aqiLower`, `aqiUpper`, `aqiMargin`, `pm25Lower`, and `pm25Upper` with $z=1.645$ ($90\%$ CI).
- [x] **Satellite Aerosol Optical Depth (AOD) Proxy Validation**:
  - Implemented 550nm optical extinction proxy mapping surface $\text{PM}_{2.5}$ into total column aerosol mass ($\text{mg/m}^2$) and optical depth category (`VIIRS / Sentinel-5P TROPOMI Proxy`).
- [x] **Multi-Day 72-Hour Forward Atmospheric Outlook**:
  - Implemented `generate_multiday_forecast()` generating 72 sequential hourly predictions across Day 1, Day 2, and Day 3.
  - Generates day summaries with mean AQI, peak AQI hours, dominant GRAP stage, stubble share percentage, and synoptic weather annotations.
- [x] **Ground Monitor Benchmarking & Automated Drift Detection**:
  - Implemented `evaluate_ground_benchmark()` comparing real-time ML predictions against physical CPCB monitoring stations.
  - Automatically computes Mean Absolute Error (MAE), Mean Bias Error (MBE), and flags calibration drift when bias exceeds threshold limits.
- [x] **REST API Multiday & Drift Endpoints**:
  - Exposed `/api/v1/forecast/multiday` and `/api/v1/model/drift` in FastAPI backend.

### Phase 9: Real-Time Alerts, WebSockets & Policy Intervention Simulator
- [x] **Real-Time WebSocket Telemetry Stream**:
  - Implemented `ConnectionManager` and `/ws/telemetry` endpoint supporting persistent bi-directional streaming, initial state handshake, and heartbeat ping/pong.
- [x] **Multi-Channel Alert Evaluation & Dispatcher**:
  - Built `backend/alerts_dispatcher.py` evaluating predicted AQI and meteorology against CAQM GRAP Stage III/IV, nocturnal inversion, and corridor transport rules.
  - Automatically records alerts to SQLite and simulates multi-channel dispatch across CAQM Portal, KVK SMS Broadcast, CPCB Webhook, and Public Health Digest.
- [x] **Farm Intervention Economic & Agricultural Policy Simulator**:
  - Implemented `backend/policy_simulator.py` covering high-burn agricultural districts (Sangrur, Firozpur, Bathinda, Tarn Taran, Ludhiana, Kaithal, Fatehabad, Jind).
  - Models Pusa Bio-Decomposer spraying, Happy Seeder / Super SMS machinery, and ex-situ biomass pelletization.
  - Calculates fires prevented, biomass diverted (tonnes), avoided $\text{PM}_{2.5}$ emissions (tonnes), public health economic savings (₹ Crores), and Benefit-Cost Ratios (BCR).
- [x] **REST API Policy & Alert Endpoints**:
  - Exposed `/api/v1/policy/districts`, `/api/v1/policy/simulate`, `/api/v1/alerts/evaluate`, and `/api/v1/alerts/channels`.

### Phase 10: Enterprise Cloud-Native Scale-Out & PWA Offline Capabilities
- [x] **PostgreSQL + PostGIS Schema Migration**:
  - Created `database/schema_postgres_postgis.sql` featuring PostGIS spatial types (`GEOMETRY(Point, 4326)` for satellite anomaly coordinates and `GEOMETRY(Polygon, 4326)` for district boundaries).
  - Configured high-performance GiST spatial indexing (`USING GIST`) and automated coordinate-to-geometry trigger execution.
- [x] **Redis Distributed Caching Architecture**:
  - Created `backend/cache.py` providing an abstracted hybrid caching engine: zero-dependency in-memory TTL caching by default with transparent failover to Redis when `REDIS_URL` is configured.
- [x] **PWA (Progressive Web App) Offline Manifest & Service Worker**:
  - Created `frontend/manifest.json` defining standalone application metadata, themes, and icons.
  - Implemented `frontend/service-worker.js` with Cache-First strategy for static assets and Network-First with offline fallback for API requests.
  - Linked manifest and registered Service Worker in `frontend/index.html`.
- [x] **Cloud-Native Multi-Container Orchestration**:
  - Enhanced `deploy/docker-compose.yml` to define multi-container topologies including FastAPI (`agri-smoke-ai`), Redis (`redis:7-alpine`), and PostGIS (`postgis/postgis:16-3.4-alpine`).

---

## 📌 Maintenance & Contribution Protocol

1. When starting work on a new phase or feature, mark the item as in-progress.
2. Ensure any new environment variables or secret keys are added to [`.env.example`](.env.example) and documented in [`agent.md`](agent.md).
3. Always update automated test coverage in [`tests/`](tests/) and verify that `python tests/run_all_tests.py` passes 100% prior to closing any phase.

