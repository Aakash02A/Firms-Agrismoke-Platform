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
| **Phase 7** | Live Meteorological Data Integration & Automated Background Sync | **In Progress (Backend Complete)** | Oct 2026 |
| **Phase 8** | Advanced Spatio-Temporal ML & Satellite AOD Ingestion | **To-Do (Planned)** | Q1 2027 |
| **Phase 9** | Real-Time Push Notifications, WebSockets & Policy Simulator | **To-Do (Planned)** | Q1 2027 |
| **Phase 10** | Cloud-Native Scale-Out (PostGIS + Redis + Kubernetes) | **To-Do (Future)** | Q2 2027 |

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
> **Status**: Completed (Backend & Ingestion Engine) | **Updated**: Oct 2026

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
- [ ] **Live Telemetry Toggle in UI**:
  - Add a "Use Live Weather" toggle on the frontend dashboard to auto-populate sliders with real-time readings.

### Phase 8: Advanced Spatio-Temporal ML & Satellite AOD Ingestion
> **Target**: Q1 2027 | **Priority**: Medium

- [ ] **TROPOMI / Sentinel-5P Satellite Ingestion**:
  - Ingest satellite Aerosol Optical Depth (AOD) and Carbon Monoxide (CO) tropospheric column densities to validate surface PM2.5 estimates.
- [ ] **Spatio-Temporal Graph Neural Network (ST-GNN)**:
  - Prototype a graph-based deep learning architecture modeling inter-district smoke transport and dispersion over 72-hour forward windows.
- [ ] **MLOps & Model Governance**:
  - Integrate MLflow / Weights & Biases for experiment tracking, automated drift detection, and daily performance benchmarking against physical CPCB monitors.
- [ ] **Uncertainty Quantification**:
  - Output prediction confidence intervals (e.g., 90% confidence bands) alongside deterministic AQI values.

### Phase 9: Real-Time Alerts, WebSockets & Policy Intervention Simulator
> **Target**: Q1 2027 | **Priority**: Medium

- [ ] **WebSocket Telemetry Stream**:
  - Establish a persistent WebSocket endpoint (`/ws/telemetry`) broadcasting live fire detections and plume updates directly to connected dashboard clients.
- [ ] **Multi-Channel Alert Dispatcher**:
  - Add email (SMTP), SMS, and Webhook dispatchers triggered when predicted AQI crosses CAQM GRAP Stage III/IV thresholds.
- [ ] **Farm Intervention Economic Simulator**:
  - Build an interactive policy simulation tab allowing state agricultural planners to calculate cost-benefit metrics for distributing Happy Seeders, CRM subsidies, and bio-decomposer solutions across specific high-fire districts.
- [ ] **Role-Based Access Control (RBAC)**:
  - Add JWT authentication distinguishing between Public Viewers, Research Analysts, and Government Enforcement Officers.

### Phase 10: Enterprise Cloud-Native Scale-Out
> **Target**: Q2 2027 | **Priority**: Low / Long-term

- [ ] **PostgreSQL + PostGIS Migration**:
  - Transition persistence layer from SQLite to PostgreSQL with PostGIS extension for high-performance spatial queries, bounding box intersections, and spatial indexing.
- [ ] **Redis Distributed Caching**:
  - Add Redis caching layer for heavy spatial aggregation queries, satellite downloads, and inference results.
- [ ] **Kubernetes Helm Charts**:
  - Package AgriSmoke AI into cloud-native Helm charts for high-availability multi-replica Kubernetes clusters.
- [ ] **Offline PWA Support**:
  - Convert frontend into an installable Progressive Web App (PWA) with Service Worker caching for field monitoring officers in rural areas with limited connectivity.

---

## 📌 Maintenance & Contribution Protocol

1. When starting work on a new phase or feature, mark the item as in-progress.
2. Ensure any new environment variables or secret keys are added to [`.env.example`](.env.example) and documented in [`agent.md`](agent.md).
3. Always update automated test coverage in [`tests/`](tests/) and verify that `python tests/run_all_tests.py` passes 100% prior to closing any phase.

