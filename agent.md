# 🤖 Agent Configuration — Firms-Agrismoke-Platform

> This file provides any AI coding agent (Copilot, Cursor, Antigravity, Claude, ChatGPT, Gemini, etc.) with the full project context needed to contribute effectively. Read this first before making changes.

---

## 📌 Project Identity

| Field | Value |
| :--- | :--- |
| **Name** | AgriSmoke AI — Crop-Burning & Urban Air Quality Prediction System |
| **Domain** | Environmental Science / Atmospheric Modelling / Indo-Gangetic Airshed |
| **Region** | Northern India (Punjab, Haryana, Delhi-NCR, Western UP) |
| **Stack** | Python 3.13 + FastAPI backend, SQLite, scikit-learn/XGBoost ML, vanilla JS frontend |
| **License** | MIT |
| **API Version** | `2.0.0` |

---

## 🗂 Repository Structure

```
Firms-Agrismoke-Platform/
├── ai-ml/                         # Machine Learning & atmospheric science
│   ├── dataset_generator.py       # Synthetic atmospheric training data generator
│   ├── train_model.py             # Model selection pipeline (GB, RF, XGBoost)
│   ├── model_inference.py         # Inference engine + CPCB AQI calculation + diurnal forecasts
│   ├── training_data.csv          # Generated training dataset (~7k rows)
│   └── models/                    # Serialized model artifacts (gitignored)
│       ├── aqi_dispersion_model.joblib
│       ├── scaler.joblib
│       ├── test_rf.joblib
│       └── metrics.json           # Training performance metrics (tracked)
│
├── backend/                       # FastAPI REST API server
│   ├── main.py                    # All API route definitions + CORS + static serving
│   ├── database.py                # SQLite CRUD data access layer
│   ├── run.py                     # Uvicorn server entrypoint
│   ├── requirements.txt           # Python dependencies
│   └── integrations/
│       └── nasa_firms/            # NASA FIRMS satellite data integration package
│           ├── __init__.py        # Exports: FirmsConfig, NasaFirmsClient, FirmsIngestionService
│           ├── config.py          # Environment-driven configuration (NASA_FIRMS_MAP_KEY, etc.)
│           ├── client.py          # HTTP client for NASA FIRMS Area API
│           ├── service.py         # Orchestration: fetch → parse → normalize → classify → persist
│           ├── parser.py          # CSV response parser
│           ├── normalizer.py      # Raw → NormalizedFireObservation transformation
│           ├── classifier.py      # Agricultural fire classification (rule-based)
│           ├── schemas.py         # Pydantic data models
│           └── exceptions.py      # Custom exception hierarchy
│
├── database/                      # Database layer
│   ├── schema.sql                 # Full SQLite schema (15 tables, 5 indexes)
│   └── init_db.py                 # Database initialization + seeding script
│
├── frontend/                      # Browser-based dashboard (zero-dependency vanilla JS)
│   ├── index.html                 # Single-page application (all sections)
│   ├── README.md                  # Frontend architecture documentation
│   ├── css/styles.css             # Design system with CSS custom properties
│   └── js/
│       ├── app.js                 # Main controller (tabs, sliders, API connectivity)
│       ├── map-engine.js          # Canvas-based geospatial map with plume animation
│       ├── charts-engine.js       # SVG/Canvas chart rendering (5 chart types)
│       ├── prediction-model.js    # Client-side atmospheric model (offline fallback)
│       └── demo-data.js           # Calibrated demonstration dataset
│
├── deploy/                        # Deployment configurations
│   ├── Dockerfile                 # Python 3.13-slim container
│   ├── docker-compose.yml         # Single-service compose
│   ├── nginx.conf                 # Reverse proxy config
│   ├── run_local.bat              # Windows 1-click launcher
│   └── run_local.sh               # Linux/macOS 1-click launcher
│
├── doc/                           # Technical documentation
│   ├── ARCHITECTURE.md            # System architecture overview
│   ├── API_SPECIFICATION.md       # Full REST API specification
│   ├── DATA_DICTIONARY.md         # Database field definitions
│   ├── ML_MODEL_DOC.md            # ML model design & performance
│   └── SETUP_GUIDE.md             # Installation instructions
│
├── tests/                         # Automated test suite
│   ├── run_all_tests.py           # Master test runner (5 suites)
│   ├── test_dom_elements.py       # Frontend DOM element verification
│   ├── test_database.py           # SQLite CRUD tests
│   ├── test_nasa_firms.py         # NASA FIRMS integration tests
│   ├── test_ml_model.py           # ML inference & physics validation
│   ├── test_backend_api.py        # FastAPI endpoint tests
│   ├── test_live_server.py        # Live server integration tests
│   └── inspect_ui.py              # UI inspection utility
│
├── .gitignore                     # Comprehensive ignore rules
├── .env.example                   # Environment variable template
├── index.html                     # Root redirect → frontend/index.html
├── run.bat                        # Quick launcher (Windows)
├── README.md                      # Project overview
└── LICENSE                        # MIT License
```

---

## ⚙️ Tech Stack & Dependencies

### Backend (Python)
| Package | Version | Purpose |
| :--- | :--- | :--- |
| `fastapi` | ≥0.115.0 | REST API framework |
| `uvicorn` | ≥0.30.0 | ASGI server |
| `pydantic` | ≥2.8.0 | Request/response validation |
| `scikit-learn` | ≥1.5.0 | ML models (GradientBoosting, RandomForest) |
| `pandas` | ≥2.2.0 | Data manipulation |
| `numpy` | ≥1.26.0 | Numerical computations |
| `joblib` | ≥1.4.0 | Model serialization |
| `xgboost` | ≥2.1.0 | XGBoost regressor candidate |

### Frontend (Browser)
- **Zero external dependencies** — no npm, no CDN, no build step
- Pure vanilla JavaScript ES6+ classes
- Custom Canvas 2D geospatial map engine (no Leaflet/Mapbox)
- Custom SVG chart engine (no Chart.js/D3)
- CSS custom properties design system (`:root` tokens in `styles.css`)

### Database
- **SQLite 3** via Python `sqlite3` stdlib — no ORM
- Database file: `database/agri_smoke.db` (gitignored, auto-created by `init_db.py`)

---

## 🏗 Architecture & Key Patterns

### Module Import Strategy
The project uses `sys.path` manipulation instead of a package manager:
```python
# Both main.py and run.py do this:
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "ai-ml"))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from model_inference import predictor   # ai-ml/model_inference.py
import database as db                    # backend/database.py
```

> **Important**: When adding new modules, ensure they are importable through the existing `sys.path` entries. There is no `setup.py`, `pyproject.toml`, or `pip install -e .`.

### API Response Convention: camelCase
The backend database uses **snake_case** columns, but the API always returns **camelCase** JSON keys to the frontend:

```python
# database.py pattern — manual snake_case → camelCase mapping:
d["fireCount"] = row["fire_count"]
d["avgFRP"] = row["avg_frp"]
d["harvestProgress"] = row["harvest_progress"]
d["smokeIntensity"] = row["smoke_intensity"]
d["paraliPct"] = row["parali_pct"]
d["stubblePct"] = row["stubble_pct"]
d["grapStage"] = row["grap_stage"]
d["aqiRange"] = row["aqi_range"]
d["actionRequired"] = row["action_required"]
```

> **Rule**: All new API responses MUST use camelCase keys. All new DB columns MUST use snake_case. Add explicit mapping in `database.py` helper functions.

### Pydantic Models
- Request models use camelCase fields matching frontend JSON: `fireCount`, `windSpeed`, `windDirectionDeg`, `pblHeight`
- NASA FIRMS schemas in `backend/integrations/nasa_firms/schemas.py` use snake_case (raw data models)
- Response construction is done inline in `main.py` endpoint functions (dict construction, not response models)

### Error Handling
- Backend uses `HTTPException` from FastAPI with status codes 400, 404, 500
- NASA FIRMS has a custom exception hierarchy: `FirmsError` → `FirmsAuthenticationError`, `FirmsDataError`, `FirmsNetworkError`
- ML engine has a self-healing pattern: if model loading fails, it auto-retrains from `train_model.py`
- Frontend gracefully degrades to offline client-side prediction model when backend is unreachable

### Configuration
All secrets and tunable parameters use **environment variables** with sensible defaults:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `NASA_FIRMS_MAP_KEY` | `""` (empty) | NASA Earthdata MAP key for FIRMS API |
| `NASA_FIRMS_BASE_URL` | `https://firms.modaps.eosdis.nasa.gov` | FIRMS API base URL |
| `NASA_FIRMS_DEFAULT_SENSOR` | `VIIRS_NOAA20_NRT` | Default satellite sensor |
| `NASA_FIRMS_DAY_RANGE` | `3` | Day range for data queries (1–5) |
| `NASA_FIRMS_REQUEST_TIMEOUT` | `30` | HTTP request timeout (seconds) |
| `NASA_FIRMS_CACHE_TTL` | `900` | Cache time-to-live (seconds) |
| `PORT` | `8000` | Server port |

> **Never hardcode secrets.** Use `os.getenv()` with safe defaults. See `backend/integrations/nasa_firms/config.py` for the pattern.

---

## 🛤 API Endpoints Reference

### Core Data Endpoints (v1 legacy style)
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/status` | System health + ML model metrics |
| `GET` | `/api/stations` | Air quality monitoring stations (9 stations) |
| `GET` | `/api/hotspots` | Active fire hotspots (thermal anomalies) |
| `GET` | `/api/trends/weekly` | 7-day air quality & fire trend history |
| `GET` | `/api/districts` | District-level fire count rankings |
| `GET` | `/api/grap` | GRAP action plan stages (I–IV) |
| `GET` | `/api/alerts` | Early warning alert feed |
| `POST` | `/api/predict` | ML-powered AQI dispersion prediction |
| `GET` | `/api/forecast/diurnal` | 24-hour diurnal AQI forecast curve |
| `GET` | `/api/thresholds` | Get custom safety thresholds |
| `POST` | `/api/thresholds` | Update custom safety thresholds |
| `GET` | `/api/model/metrics` | Trained ML model accuracy metrics |
| `GET` | `/api/export/csv` | Export simulation telemetry as CSV |

### NASA FIRMS Satellite Integration Endpoints (v1 structured)
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/firms/status` | FIRMS provider health status |
| `POST` | `/api/v1/firms/sync` | Trigger satellite data synchronization |
| `GET` | `/api/v1/firms/observations` | Query normalized fire observations |
| `GET` | `/api/v1/firms/events` | Clustered fire event summaries |
| `GET` | `/api/v1/geospatial/districts` | District geospatial data + fire overlay |
| `POST` | `/api/v1/predict/live` | Prediction with live satellite data augmentation |
| `GET` | `/api/v1/alerts` | Formal lifecycle alert records (NEW→RESOLVED) |
| `PATCH` | `/api/v1/alerts/{alert_id}` | Update alert lifecycle status |

### Static Content
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves `frontend/index.html` |
| `GET` | `/css/*` | Static CSS files |
| `GET` | `/js/*` | Static JS files |

---

## 🗄 Database Schema (15 Tables)

| # | Table | Purpose | Key Columns |
| :--- | :--- | :--- | :--- |
| 1 | `monitoring_stations` | CPCB air quality stations | `id`, `name`, `lat`, `lng`, `aqi`, `pm25`, `parali_pct` |
| 2 | `fire_hotspots` | Active thermal anomaly clusters | `district`, `state`, `fire_count`, `avg_frp`, `smoke_intensity` |
| 3 | `hourly_forecasts` | Diurnal cycle projections | `hour_num`, `aqi`, `pm25`, `pbl_height` |
| 4 | `weekly_trends` | 7-day historical trends | `day_label`, `aqi`, `fires`, `stubble_pct`, `grap_stage` |
| 5 | `district_fire_counts` | District fire rankings | `district`, `fires`, `state` |
| 6 | `grap_stages` | GRAP action plan (I–IV) | `stage`, `aqi_range`, `is_active`, `actions_json` |
| 7 | `early_warning_alerts` | Alert feed entries | `level`, `alert_type`, `title`, `detail`, `action_required` |
| 8 | `simulation_history` | User/engine scenario runs | `fire_count`, `predicted_aqi`, `predicted_pm25`, `parali_pct` |
| 9 | `custom_thresholds` | Safety threshold settings | `aqi_threshold`, `fires_threshold` |
| 10 | `fire_observations` | Normalized NASA FIRMS records | `latitude`, `longitude`, `frp`, `confidence_score`, `classification` |
| 11 | `fire_events` | Spatiotemporal fire clusters | `centroid_lat`, `centroid_lng`, `total_frp`, `observation_count` |
| 12 | `districts` | Geographic district master data | `name`, `state`, `centroid_lat`, `centroid_lng`, bounds |
| 13 | `data_sync_jobs` | Synchronization job tracking | `status`, `records_fetched`, `records_inserted`, `error_message` |
| 14 | `data_provider_status` | External provider health | `provider_id`, `status`, `last_success`, `records_count` |
| 15 | `alert_records` | Lifecycle-managed alerts | `category`, `severity`, `status` (NEW→RESOLVED) |

---

## 🧪 Testing

### Running Tests
```bash
# Run the full automated test suite (5 suites, ~30 checks):
python tests/run_all_tests.py

# Individual suite:
python tests/test_database.py
python tests/test_ml_model.py
python tests/test_backend_api.py
python tests/test_nasa_firms.py
python tests/test_dom_elements.py
```

### Test Architecture
- Tests use **no external testing framework** (no pytest/unittest) — they are self-contained scripts with direct assertions
- `run_all_tests.py` orchestrates sequential execution via `subprocess` and reports pass/fail per suite
- Tests import project modules directly using the same `sys.path` manipulation pattern
- `test_backend_api.py` tests endpoints using FastAPI's `TestClient` (from `starlette.testclient`)
- `test_ml_model.py` validates model loading, prediction ranges, physics constraints (inversion sensitivity, wind direction, diurnal cycle)

### When Adding Tests
- Add new test files as `tests/test_<module>.py`
- Register them in `run_all_tests.py`'s `TESTS` list
- Use the same self-contained assertion pattern (print PASS/FAIL, exit code 0/1)

---

## 🧠 ML Model Details

### Training Pipeline
1. `dataset_generator.py` generates synthetic atmospheric training data with physics-informed features
2. `train_model.py` benchmarks GradientBoosting, RandomForest, and XGBoost — selects best by R² score
3. Best model serialized to `ai-ml/models/aqi_dispersion_model.joblib`
4. Performance metrics saved to `ai-ml/models/metrics.json`

### Input Features (8 primary)
`fire_count`, `wind_speed`, `wind_direction_deg`, `pbl_height`, `urban_baseline_aqi`, `bio_decomposer_pct`, `happy_seeder_pct`, `temperature`

### Output
Predicted PM2.5 concentration → converted to Indian CPCB AQI (0–999 scale) via breakpoint interpolation

### Key Physics
- **Wind Direction Factor**: Maximum smoke transport at 305–315° (NW → SE corridor, Punjab to Delhi)
- **PBL Height**: Lower boundary layer = stronger trapping = higher AQI (inversely proportional)
- **Diurnal Cycle**: PBL collapses at night (04:00 minimum ~180m) → peak AQI; expands by afternoon (~800m) → lower AQI
- **Mitigation**: Bio-decomposer and Happy Seeder adoption reduce fire count proportionally

### Self-Healing Model Loading
If the serialized `.joblib` fails to load (sklearn version mismatch), `model_inference.py` automatically retrains by calling `train_model.py`. If that also fails, it falls back to a calibrated physics-based dispersion calculation.

---

## 🌐 Frontend Architecture

### Class Structure
| Class | File | Purpose |
| :--- | :--- | :--- |
| — (IIFE) | `app.js` | Main controller: tabs, sliders, API fetch, state management |
| `AgriSmokeMapEngine` | `map-engine.js` | Canvas 2D geospatial rendering, plume particle system |
| `AgriSmokeChartsEngine` | `charts-engine.js` | SVG/Canvas chart rendering (5 chart types) |
| `AgriSmokePredictionModel` | `prediction-model.js` | Client-side atmospheric model (offline fallback) |
| `DEMO_DATA` (const) | `demo-data.js` | Static demonstration dataset |

### Backend Connectivity
```javascript
// Frontend auto-detects backend availability:
const isLocalBackend = window.location.protocol.startsWith('http') && (window.location.port === '8000');
const API_BASE = isLocalBackend ? '' : 'http://127.0.0.1:8000';

// All API calls use fetch() with this pattern:
const response = await fetch(`${API_BASE}/api/endpoint`);
```

### Offline Fallback
When the backend is unreachable, the frontend seamlessly switches to:
- `AgriSmokePredictionModel` for client-side AQI predictions
- `DEMO_DATA` for station, hotspot, and trend data
- Full functionality maintained (the app works via `file:///` protocol)

---

## 🚀 Running the Project

### Quick Start (Windows)
```batch
run.bat
:: OR
deploy\run_local.bat
```

### Quick Start (Linux/macOS)
```bash
chmod +x deploy/run_local.sh
./deploy/run_local.sh
```

### Manual Start
```bash
pip install -r backend/requirements.txt
python database/init_db.py
python ai-ml/train_model.py
python backend/run.py
# Open http://127.0.0.1:8000
```

### Docker
```bash
cd deploy && docker compose up --build
```

### Offline Mode (No Python Required)
Open `frontend/index.html` directly in a browser — the app auto-switches to demo/offline mode.

---

## 📏 Coding Conventions

### Python
- **Style**: PEP 8 with 4-space indentation
- **Type hints**: Used in function signatures (`-> List[Dict[str, Any]]`, `Optional[float]`)
- **Docstrings**: Triple-quoted module and function docstrings
- **Imports**: stdlib → third-party → local, with `sys.path` setup before local imports
- **DB columns**: `snake_case` (e.g., `fire_count`, `avg_frp`, `parali_pct`)
- **API response keys**: `camelCase` (e.g., `fireCount`, `avgFRP`, `paraliPct`)
- **No ORM**: Raw `sqlite3` with `conn.row_factory = sqlite3.Row`

### JavaScript
- **ES6+ classes**: `AgriSmokeMapEngine`, `AgriSmokeChartsEngine`, `AgriSmokePredictionModel`
- **DOM**: Direct `document.getElementById()` — no virtual DOM or framework
- **Style**: 4-space indentation, semicolons, single quotes for strings
- **Naming**: camelCase variables and functions, PascalCase classes
- **No build step**: No bundler, no transpiler — files load via `<script>` tags

### SQL
- `snake_case` for all table and column names
- Tables use `TEXT PRIMARY KEY` for domain identifiers, `INTEGER PRIMARY KEY AUTOINCREMENT` for sequence IDs
- `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` for audit columns
- `JSON` stored as `TEXT` columns (e.g., `actions_json`, `evidence_json`, `raw_payload`)

---

## 🔒 Security & Secrets

### Environment Variables
- **Never commit** `.env` files — the `.gitignore` blocks them
- Copy `.env.example` → `.env` and fill in your NASA FIRMS MAP key
- The `FirmsConfig` class provides `.masked_map_key` for safe logging

### Gitignored Confidential Data
```
.env, .env.*, *.env         → API keys, secrets, credentials
*.db, *.sqlite              → Runtime databases with user/telemetry data
*.joblib, *.pkl, *.h5       → Large binary model artifacts
__pycache__/                → Compiled bytecode
credentials/, secrets/      → Credential directories
*.pem, *.key, *.cert        → Cryptographic material
```

---

## 🔄 Common Agent Tasks

### Adding a New API Endpoint
1. Define the route in `backend/main.py` following the existing pattern
2. If it needs data, add a helper function in `backend/database.py` (snake→camelCase mapping)
3. If it needs a new table, add the schema in `database/schema.sql` and seeding in `database/init_db.py`
4. Add a test in `tests/test_backend_api.py`
5. Connect from frontend in `app.js` using `fetch(\`\${API_BASE}/api/...\`)`

### Adding a New ML Feature
1. Add the feature column to `ai-ml/dataset_generator.py`
2. Include it in the feature list in `ai-ml/train_model.py`
3. Add the input to `model_inference.py`'s `predict()` method
4. Retrain: `python ai-ml/train_model.py`
5. Update the `PredictionRequest` Pydantic model in `backend/main.py`

### Adding a New Frontend Section
1. Add HTML section in `frontend/index.html` with a unique `id`
2. Add tab button if needed (follow existing `tab-btn` pattern)
3. Implement logic in `frontend/js/app.js` within the `DOMContentLoaded` IIFE
4. Add verification in `tests/test_dom_elements.py`

### Modifying the Database Schema
1. Update `database/schema.sql`
2. Update `database/init_db.py` seeding logic
3. Update `backend/database.py` CRUD helpers with camelCase mapping
4. Delete `database/agri_smoke.db` and re-run `python database/init_db.py`
5. Run `python tests/test_database.py` to verify

---

## ⚠️ Known Constraints & Gotchas

1. **sys.path manipulation**: The project does NOT use standard Python packaging. Imports rely on runtime `sys.path.insert()` calls. Always run scripts from the project root or via the provided launchers.

2. **SQLite concurrency**: SQLite is single-writer. The backend uses short-lived connections via `get_connection()` context manager. Do not hold connections open across async operations.

3. **Model version coupling**: The `.joblib` model is tightly coupled to the sklearn version that trained it. If you upgrade scikit-learn, delete `ai-ml/models/*.joblib` and retrain. The inference engine handles this automatically.

4. **No package.json**: The frontend has zero Node.js dependencies. Do not add npm/yarn. All JavaScript is vanilla ES6+.

5. **CORS is fully open**: `allow_origins=["*"]` is set for development. Restrict this before production deployment.

6. **AQI scale**: The app uses Indian CPCB PM2.5 breakpoints, NOT US EPA AQI. Values above 500 are extrapolated up to 999 using a custom overflow formula.

7. **Wind direction convention**: 305° means wind blowing FROM the NW (Punjab) TOWARD the SE (Delhi). The `source_bearing_deg = 312.0` in `model_inference.py` represents the Punjab→Delhi transport corridor.

8. **Frontend offline mode**: The frontend must function identically whether loaded from the FastAPI server (`http://`) or directly from disk (`file:///`). Always test both modes.

---

## 📚 Further Reading

- [Architecture Overview](doc/ARCHITECTURE.md)
- [API Specification](doc/API_SPECIFICATION.md)
- [Data Dictionary](doc/DATA_DICTIONARY.md)
- [ML Model Documentation](doc/ML_MODEL_DOC.md)
- [Setup Guide](doc/SETUP_GUIDE.md)
- [Frontend README](frontend/README.md)
