# 🌾 AgriSmoke AI &bull; Full-Stack Air Quality Prediction Platform
### *Indo-Gangetic Airshed (Punjab, Haryana & Delhi-NCR)*

A production-grade, end-to-end atmospheric simulation, machine learning inference, and air quality prediction platform designed to analyze the transboundary transport of agricultural crop-burning smoke and predict urban air quality in Delhi-NCR.

---

## 📁 Repository Structure

```
.
├── frontend/                # Interactive HTML5 Canvas & SVG Dashboard
│   ├── index.html           # Single-page web application
│   ├── css/styles.css       # Dark theme & glassmorphic UI
│   └── js/                  # Map engine, SVG charts, and app controller
│
├── backend/                 # Python 3.13 FastAPI Backend
│   ├── main.py              # REST API & static file delivery
│   ├── database.py          # SQLite database connection & CRUD
│   ├── run.py               # 1-Click server launcher
│   └── requirements.txt     # Python backend dependencies
│
├── database/                # SQLite Relational Database
│   ├── schema.sql           # Database schema & tables
│   ├── init_db.py           # Database seeder & initializer
│   └── agri_smoke.db        # SQLite database
│
├── ai-ml/                   # Machine Learning & Dispersion Modeling
│   ├── dataset_generator.py # Atmospheric dataset synthesizer
│   ├── train_model.py       # ML trainer & algorithm benchmarker
│   ├── model_inference.py   # Prediction engine & CPCB conversion
│   └── models/              # Serialized ML model artifacts & metrics
│
├── deploy/                  # Deployment & Automation
│   ├── Dockerfile           # Multi-stage Docker container
│   ├── docker-compose.yml   # Compose service definition
│   ├── run_local.bat        # Windows 1-click startup batch script
│   ├── run_local.sh         # Linux/macOS startup shell script
│   └── nginx.conf           # Reverse proxy configuration
│
└── doc/                     # System Documentation
    ├── ARCHITECTURE.md      # Full architecture & ER diagram
    ├── API_SPECIFICATION.md # Complete REST API documentation
    ├── ML_MODEL_DOC.md      # Model benchmarks & physics formulations
    └── SETUP_GUIDE.md       # Installation & deployment instructions
```

---

## 🚀 Quickstart

### 1-Click Windows Launcher:
Double-click `deploy/run_local.bat`.

### Manual Launch:
```bash
# 1. Install dependencies
python -m pip install -r backend/requirements.txt

# 2. Initialize database
python database/init_db.py

# 3. Train Machine Learning Model
python ai-ml/train_model.py

# 4. Start backend server
python backend/run.py
```

Open your browser to:
- **Web Dashboard**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

