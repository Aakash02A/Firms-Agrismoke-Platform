"""
AgriSmoke AI - FastAPI Backend Server
Integrates SQLite database, trained Machine Learning dispersion models,
real-time prediction API, and static frontend delivery.
"""

import sys
import io
import csv
import time
import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Ensure root and ai-ml paths are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
AI_ML_DIR = ROOT_DIR / "ai-ml"
FRONTEND_DIR = ROOT_DIR / "frontend"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(AI_ML_DIR) not in sys.path:
    sys.path.insert(0, str(AI_ML_DIR))
if str(ROOT_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "backend"))

# Load project-root .env so os.getenv() calls (NASA_FIRMS_MAP_KEY, PORT, REDIS_URL,
# etc.) pick up values from the file. Graceful: if python-dotenv is not installed,
# we simply rely on variables exported in the OS environment.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

from model_inference import predictor
import database as db
from app_config import config
from backend.integrations.weather import weather_service, LiveWeatherSnapshot
from backend.integrations.air_quality import air_quality_service
from backend.scheduler import scheduler
from backend.policy_simulator import (
    PolicySimulationRequest,
    PolicySimulationResult,
    simulate_policy_intervention,
    get_available_districts
)
from backend.alerts_dispatcher import alert_engine, CONFIGURED_CHANNELS, DISPATCH_LOGS

logger = logging.getLogger("agri_smoke.api")

# Interactive docs (Swagger/ReDoc) are exposed only outside production, or when
# explicitly re-enabled via DOCS_ENABLED=true. In prod the API surface stays closed.
app = FastAPI(
    title="AgriSmoke AI API",
    description="Backend API with SQLite & Atmospheric Machine Learning for Indo-Gangetic Airshed AQI Predictions",
    version="2.0.0",
    docs_url="/docs" if config.docs_enabled else None,
    redoc_url="/redoc" if config.docs_enabled else None,
    openapi_url="/openapi.json" if config.docs_enabled else None,
)

# CORS: locked to explicit origins from config. We never combine a wildcard
# origin with credentials (invalid + unsafe). Same-origin hosting needs no CORS.
if config.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

# ----------------- Security Middleware -----------------

# Content-Security-Policy tuned for this vanilla-JS app: only self-hosted scripts
# (no inline <script>, no third-party JS), Google Fonts for styles/fonts, and
# same-origin data/API/WebSocket connections. Inline style *attributes* are used
# across the markup, hence style-src 'unsafe-inline'.
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'"
)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Stateless compute allowed through read-only mode (does not write to the DB).
READ_ONLY_ALLOWED_POST_PATHS = {"/api/predict"}
# Expensive ML/report endpoints subject to per-client rate limiting.
RATE_LIMITED_PREFIXES = ("/api/predict", "/api/forecast", "/api/v1/forecast", "/api/v1/predict", "/api/export")
_rate_buckets: Dict[tuple, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(ip: str, path: str) -> bool:
    window = 60.0
    limit = max(1, config.rate_limit_per_minute)
    key = (ip, path)
    now = time.time()
    bucket = _rate_buckets[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


@app.middleware("http")
async def security_and_guard_middleware(request: Request, call_next):
    path = request.url.path

    # 1. Read-only gate: reject state-changing calls to non-compute endpoints.
    if config.read_only and request.method in MUTATING_METHODS and path not in READ_ONLY_ALLOWED_POST_PATHS:
        if path.startswith("/api"):
            return JSONResponse(
                status_code=405,
                content={"error": "This deployment is read-only. Write operations are disabled."},
                headers={"Content-Security-Policy": CSP_POLICY},
            )

    # 2. Rate limit expensive endpoints.
    if config.rate_limit_enabled and path.startswith(RATE_LIMITED_PREFIXES) and _is_rate_limited(_client_ip(request), path):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please slow down."},
            headers={"Retry-After": "60", "Content-Security-Policy": CSP_POLICY},
        )

    response = await call_next(request)

    # 3. Baseline security headers on every response.
    response.headers["Content-Security-Policy"] = CSP_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if config.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the real traceback server-side; never leak internals to clients in prod."""
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    detail = "Internal server error" if config.is_production else f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"error": detail})

# ----------------- Request / Response Models -----------------

class PredictionRequest(BaseModel):
    fireCount: int = Field(default=1684, ge=0, le=10000, description="Active thermal farm fires")
    windSpeed: float = Field(default=11.5, ge=0.5, le=60.0, description="Wind speed in km/h")
    windDirectionDeg: int = Field(default=305, ge=0, le=360, description="Wind direction degrees")
    pblHeight: int = Field(default=480, ge=100, le=2500, description="Planetary Boundary Layer height in meters")
    urbanBaselineAqi: int = Field(default=180, ge=30, le=450, description="Urban baseline AQI")
    bioDecomposerAdoption: int = Field(default=25, ge=0, le=100, description="% Bio-decomposer adoption")
    happySeederAdoption: int = Field(default=30, ge=0, le=100, description="% In-situ Happy Seeder adoption")
    temperature: Optional[float] = Field(default=24.2, description="Ambient temperature in °C")
    humidity: Optional[float] = Field(default=62.0, description="Relative humidity %")

class ThresholdUpdateRequest(BaseModel):
    aqi: int = Field(ge=50, le=999)
    fires: int = Field(ge=50, le=10000)

# ----------------- API Endpoints -----------------

@app.get("/api/health")
def health_check():
    """Lightweight liveness probe for PaaS/load balancers (no external calls)."""
    return {"status": "ok", "environment": config.environment}


@app.get("/api/status")
def get_system_status():
    """Returns current system health, metadata, and a LIVE-driven status benchmark."""
    # Pull real-time meteorology (Open-Meteo, key-free) and live Delhi baseline AQI
    # so the benchmark reflects actual conditions rather than fixed mock defaults.
    live_wx = weather_service.get_live_weather("delhi_ncr")
    live_aq = air_quality_service.get_live_reading(28.6139, 77.2090)

    default_params = {
        "fireCount": 1684,
        "windSpeed": live_wx.windSpeed,
        "windDirectionDeg": live_wx.windDirectionDeg,
        "pblHeight": live_wx.pblHeight,
        "urbanBaselineAqi": (live_aq["aqi"] if live_aq else 180),
        "bioDecomposerAdoption": 25,
        "happySeederAdoption": 30,
        "temperature": live_wx.temperature,
        "humidity": live_wx.humidity
    }
    pred = predictor.predict(default_params)
    thresholds = db.get_custom_thresholds()
    
    return {
        "status": "online",
        "system": "AgriSmoke AI Indo-Gangetic Air Quality Platform",
        "backend": "Python 3.13 + FastAPI + SQLite",
        "mlModel": predictor.metrics.get("model_name", "GradientBoostingRegressor"),
        "mlAccuracyR2": predictor.metrics.get("best_metrics", {}).get("r2_score", 0.9886),
        "currentBenchmark": {
            "aqi": pred["predictedAqi"],
            "category": pred["category"],
            "categoryColor": pred["categoryColor"],
            "dominantPollutant": "PM2.5",
            "pm25": pred["totalPm25"],
            "pm10": pred["totalPm10"],
            "paraliContributionPct": pred["paraliPct"],
            "activeFires": default_params["fireCount"],
            "windSpeed": default_params["windSpeed"],
            "windDirectionDeg": default_params["windDirectionDeg"],
            "pblHeight": default_params["pblHeight"],
            "isWeatherLive": live_wx.isLive,
            "isAirQualityLive": bool(live_aq),
            "airshedRiskScore": pred["airshedScore"],
            "grapStage": pred["grapStage"]
        },
        "thresholds": thresholds
    }

@app.get("/api/stations")
def get_stations():
    """Retrieve monitoring stations enriched with LIVE PM2.5/PM10/AQI from the
    Open-Meteo Air Quality API (key-free). Falls back to stored values when the
    live feed is unreachable, marking each record with a `live` flag."""
    stations = db.get_monitoring_stations()
    air_quality_service.enrich_stations(stations)
    return stations

@app.get("/api/air-quality/forecast")
def get_air_quality_forecast(lat: float, lng: float, hours: int = 72):
    """Real per-location hourly PM2.5/AQI forecast for the next `hours` (from the
    current IST hour) via the Open-Meteo Air Quality API. Used by the station
    detail modal to show each place's own time series. isLive=false when the
    upstream feed is unreachable (hourly is then empty)."""
    hours = max(1, min(72, int(hours)))
    data = air_quality_service.get_forecast_hours(lat, lng, hours)
    return {
        "isLive": bool(data),
        "source": "OPEN_METEO_AIR_QUALITY_LIVE" if data else "UNAVAILABLE",
        "count": len(data),
        "hourly": data,
    }

@app.get("/api/hotspots")
def get_hotspots():
    """Return active fire hotspots. Prefers LIVE NASA FIRMS satellite detections
    aggregated by district; falls back to seeded reference hotspots when no live
    observations have been synced yet (e.g. MAP key not configured)."""
    live = db.get_live_fire_hotspots()
    if live:
        return live
    return db.get_fire_hotspots()

@app.get("/api/trends/weekly")
def get_weekly_trends():
    """Retrieve 7-day trend history from SQLite."""
    return db.get_weekly_trends()

@app.get("/api/districts")
def get_district_rankings():
    """District-wise stubble burning counts. Uses LIVE NASA FIRMS aggregates when
    available, otherwise the seeded district counts."""
    live = db.get_live_district_fire_counts()
    if live:
        return live
    return db.get_district_fire_counts()

@app.get("/api/grap")
def get_grap_guidelines():
    """Retrieve CAQM Graded Response Action Plan (GRAP) guidelines."""
    return db.get_grap_stages()

@app.get("/api/alerts")
def get_alerts():
    """Retrieve active early warning alert dispatch stream."""
    return db.get_early_warning_alerts()

@app.get("/api/thresholds")
def get_thresholds():
    """Get active safety trigger thresholds."""
    return db.get_custom_thresholds()

@app.post("/api/thresholds")
def update_thresholds(req: ThresholdUpdateRequest):
    """Update custom alert thresholds in SQLite."""
    updated = db.update_custom_thresholds(req.aqi, req.fires)
    return {"message": "Thresholds updated successfully", "data": updated}

@app.post("/api/predict")
def run_prediction(req: PredictionRequest):
    """
    Core ML Prediction Endpoint:
    Accepts scenario parameters, executes the trained Machine Learning regressor,
    logs the run into SQLite history, and returns predicted AQI and 24h diurnal forecast.
    """
    params = req.model_dump()
    pred = predictor.predict(params)
    hourly = predictor.generate_hourly_forecast(params)

    # Persist simulation history only when writes are permitted (read-only
    # production skips this and just returns the stateless prediction).
    if not config.read_only:
        try:
            db.save_simulation_run(params, pred)
        except Exception as e:
            logger.warning("Failed to record simulation to DB: %s", e)

    return {
        "prediction": pred,
        "hourlyForecast": hourly,
        "inputs": params
    }

@app.get("/api/forecast/diurnal")
def get_diurnal_forecast(
    fireCount: int = 1684,
    windSpeed: float = 11.5,
    windDirectionDeg: int = 305,
    pblHeight: int = 480,
    urbanBaselineAqi: int = 180,
    bioDecomposerAdoption: int = 25,
    happySeederAdoption: int = 30
):
    """Generate dynamic 24-hour diurnal forecast using the ML model."""
    params = {
        "fireCount": fireCount,
        "windSpeed": windSpeed,
        "windDirectionDeg": windDirectionDeg,
        "pblHeight": pblHeight,
        "urbanBaselineAqi": urbanBaselineAqi,
        "bioDecomposerAdoption": bioDecomposerAdoption,
        "happySeederAdoption": happySeederAdoption
    }
    return predictor.generate_hourly_forecast(params)


@app.get("/api/v1/forecast/multiday")
def get_multiday_forecast(
    fireCount: int = 1684,
    windSpeed: float = 11.5,
    windDirectionDeg: int = 305,
    pblHeight: int = 480,
    urbanBaselineAqi: int = 180,
    bioDecomposerAdoption: int = 25,
    happySeederAdoption: int = 30,
    location: str = "delhi_ncr",
    useLive: bool = True
):
    """Generate multi-day 72-hour forward atmospheric dispersion outlook with uncertainty bounds.

    By default the outlook is driven by REAL Open-Meteo forecast meteorology
    (hourly wind speed/direction and boundary-layer height) for the next 72h; fire
    emissions are held at the current level. Set useLive=false to force the
    deterministic heuristic trend (offline / what-if mode).
    """
    params = {
        "fireCount": fireCount,
        "windSpeed": windSpeed,
        "windDirectionDeg": windDirectionDeg,
        "pblHeight": pblHeight,
        "urbanBaselineAqi": urbanBaselineAqi,
        "bioDecomposerAdoption": bioDecomposerAdoption,
        "happySeederAdoption": happySeederAdoption
    }
    met_forecast = weather_service.get_forecast_hours(location_key=location, hours=72) if useLive else []
    return predictor.generate_multiday_forecast(params, met_forecast=met_forecast)


@app.get("/api/v1/model/drift")
def get_model_drift_evaluation():
    """Evaluate model prediction accuracy and drift against current ground monitoring stations."""
    stations = db.get_monitoring_stations()
    return predictor.evaluate_ground_benchmark(stations)

@app.get("/api/model/metrics")
def get_model_metrics():
    """Returns Machine Learning model validation metrics, R2 score, RMSE, and feature importances."""
    return predictor.metrics

@app.get("/api/export/csv")
def export_csv(
    fireCount: int = 1684,
    windSpeed: float = 11.5,
    windDirectionDeg: int = 305,
    pblHeight: int = 480,
    urbanBaselineAqi: int = 180,
    bioDecomposerAdoption: int = 25,
    happySeederAdoption: int = 30
):
    """Generates on-the-fly downloadable diagnostic CSV containing 24h predictions."""
    params = {
        "fireCount": fireCount,
        "windSpeed": windSpeed,
        "windDirectionDeg": windDirectionDeg,
        "pblHeight": pblHeight,
        "urbanBaselineAqi": urbanBaselineAqi,
        "bioDecomposerAdoption": bioDecomposerAdoption,
        "happySeederAdoption": happySeederAdoption
    }
    pred = predictor.predict(params)
    hourly = predictor.generate_hourly_forecast(params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Time", "Predicted_AQI", "PM25_ug_m3", "Stubble_Smoke_Contribution_Pct", "PBL_Height_m", "Wind_Speed_kmh", "Category"])
    for row in hourly:
        writer.writerow([row["time"], row["aqi"], row["pm25"], row["stubblePct"], row["pbl"], row["windSpeed"], row["category"]])

    writer.writerow([])
    writer.writerow(["# Model Telemetry Metadata"])
    writer.writerow(["Model Type", predictor.metrics.get("model_name", "GradientBoostingRegressor")])
    writer.writerow(["Model R2 Score", predictor.metrics.get("best_metrics", {}).get("r2_score", 0.9886)])
    writer.writerow(["Active Farm Fires", fireCount])
    writer.writerow(["Predicted 24h AQI", pred["predictedAqi"]])
    writer.writerow(["GRAP Stage", pred["grapStage"]])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=AgriSmoke_ML_Prediction_Report.csv"}
    )


# ----------------- NASA FIRMS & Geospatial Intelligence API -----------------

from backend.integrations.nasa_firms import FirmsConfig, FirmsIngestionService
from backend.integrations.nasa_firms.schemas import SyncRequest, SyncSummary, ProviderStatusResponse

firms_config = FirmsConfig()
firms_service = FirmsIngestionService(firms_config)


class AlertStatusUpdateRequest(BaseModel):
    status: str = Field(description="New status: NEW, ACKNOWLEDGED, RESOLVED, DISMISSED")
    notes: Optional[str] = None


@app.get("/api/v1/firms/status", response_model=ProviderStatusResponse)
def get_firms_provider_status():
    """Retrieve operational health, dataset status, and metrics for NASA FIRMS."""
    return firms_service.get_provider_status()


@app.get("/api/v1/firms/config")
def get_firms_config():
    """Retrieve safe configuration metadata for NASA FIRMS (masked key)."""
    return firms_config.to_safe_dict()


@app.get("/api/v1/firms/observations")
def get_firms_observations(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    satellite: Optional[str] = None,
    min_confidence: Optional[float] = None,
    min_frp: Optional[float] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    classification: Optional[str] = None,
    limit: int = 500,
    offset: int = 0
):
    """
    Query real satellite thermal anomaly observations from SQLite.
    Supports filtering by acquisition date, satellite, confidence score, FRP, state, and classification.
    """
    clamped_limit = max(1, min(2000, limit))
    return db.get_fire_observations(
        start_date=start_date,
        end_date=end_date,
        satellite=satellite,
        min_confidence=min_confidence,
        min_frp=min_frp,
        state=state,
        district_id=district,
        classification=classification,
        limit=clamped_limit,
        offset=offset
    )


@app.get("/api/v1/firms/summary")
def get_firms_summary(days: int = 3):
    """Retrieve aggregate telemetry and environmental impact of recent fire observations."""
    clamped_days = max(1, min(30, days))
    stats = db.get_fire_observation_stats(days=clamped_days)
    provider_status = firms_service.get_provider_status()
    return {
        "periodDays": clamped_days,
        "stats": stats,
        "provider": {
            "status": provider_status.status,
            "isHealthy": provider_status.is_healthy,
            "configured": provider_status.configured,
            "maskedKey": provider_status.masked_key,
            "defaultSensor": provider_status.default_sensor,
            "latestDataTimestamp": provider_status.latest_data_timestamp
        }
    }


@app.post("/api/v1/firms/sync", response_model=SyncSummary)
def sync_firms_data(req: SyncRequest):
    """
    Trigger on-demand synchronization with NASA FIRMS Area API.
    Retrieves satellite CSV, normalizes, applies agricultural classification,
    deduplicates with SHA-256, and stores in SQLite.
    """
    return firms_service.ingest_observations(
        sensor=req.sensor,
        region_name=req.region or "indo_gangetic_airshed",
        day_range=req.day_range,
        date=req.date
    )


@app.get("/api/v1/geospatial/districts")
def get_geospatial_districts(days: int = 3):
    """
    Live dynamic district-level intelligence aggregated from actual NASA satellite detections.
    Combines master district boundaries with live fire metrics (total fires, agricultural count, FRP).
    """
    return db.get_district_fire_summary(days=days)


@app.get("/api/v1/geospatial/events")
def get_geospatial_events(limit: int = 100):
    """Retrieve spatiotemporally clustered fire events with estimated PM2.5 smoke emissions."""
    return db.get_fire_events(limit=limit)


@app.get("/api/v1/predict/live")
def get_live_satellite_prediction(
    windSpeed: float = 11.5,
    windDirectionDeg: int = 305,
    pblHeight: int = 480,
    urbanBaselineAqi: int = 180,
    bioDecomposerAdoption: int = 25,
    happySeederAdoption: int = 30
):
    """
    Generates real-time AQI prediction driven by ACTUAL live NASA FIRMS fire counts.
    Pulls agricultural fires detected within the last 48 hours to feed into the ML model.
    """
    stats = db.get_fire_observation_stats(days=2)
    # Use real agricultural fire count if available; fallback to baseline if zero records ingested yet
    detected_fires = stats.get("agricultural_count", 0) or stats.get("total_observations", 0)
    effective_fire_count = detected_fires if detected_fires > 0 else 1684

    params = {
        "fireCount": effective_fire_count,
        "windSpeed": windSpeed,
        "windDirectionDeg": windDirectionDeg,
        "pblHeight": pblHeight,
        "urbanBaselineAqi": urbanBaselineAqi,
        "bioDecomposerAdoption": bioDecomposerAdoption,
        "happySeederAdoption": happySeederAdoption
    }
    pred = predictor.predict(params)
    hourly = predictor.generate_hourly_forecast(params)

    return {
        "source": "NASA_FIRMS_LIVE_SATELLITE" if detected_fires > 0 else "BASELINE_DEFAULT",
        "liveFiresDetected": detected_fires,
        "aggregateFrpMw": stats.get("total_frp", 0.0),
        "prediction": pred,
        "hourlyForecast": hourly,
        "inputs": params
    }


@app.get("/api/v1/alerts")
def get_alert_stream(status: Optional[str] = None, limit: int = 50):
    """Retrieve alert records with formal lifecycle status filter (NEW, ACKNOWLEDGED, RESOLVED)."""
    return db.get_alert_records(status=status, limit=limit)


@app.patch("/api/v1/alerts/{alert_id}")
def update_alert(alert_id: str, req: AlertStatusUpdateRequest):
    """Update alert lifecycle status."""
    valid_statuses = {"NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "DISMISSED"}
    if req.status.upper() not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{req.status}'. Must be one of {valid_statuses}")
    
    success = db.update_alert_record_status(alert_id, req.status.upper(), req.notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return {"message": f"Alert {alert_id} status updated to {req.status.upper()}"}


# ----------------- Weather & Meteorology Endpoints -----------------

@app.get("/api/v1/weather/live", response_model=LiveWeatherSnapshot)
def get_live_meteorology(location: str = "delhi_ncr"):
    """Fetch real-time atmospheric weather and boundary layer height."""
    return weather_service.get_live_weather(location_key=location)


@app.post("/api/v1/weather/refresh", response_model=LiveWeatherSnapshot)
def refresh_live_meteorology(location: str = "delhi_ncr"):
    """Force fresh fetch of real-time weather from Open-Meteo."""
    return weather_service.refresh_cache(location_key=location)


# ----------------- Scheduler Telemetry Endpoints -----------------

@app.get("/api/v1/scheduler/status")
def get_scheduler_status():
    """Retrieve background telemetry scheduler status and job logs."""
    return scheduler.get_status()


@app.post("/api/v1/scheduler/trigger/firms")
def trigger_firms_sync_job():
    """Immediately trigger background NASA FIRMS sync job."""
    return scheduler.trigger_firms_sync_now()


@app.post("/api/v1/scheduler/trigger/weather")
def trigger_weather_sync_job():
    """Immediately trigger background weather sync job."""
    return scheduler.trigger_weather_refresh_now()


# ----------------- Real-Time WebSocket Telemetry Stream -----------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_json(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()


@app.websocket("/ws/telemetry")
async def websocket_telemetry_stream(websocket: WebSocket):
    """Real-time bi-directional WebSocket telemetry stream for connected dashboards."""
    await ws_manager.connect(websocket)
    try:
        weather = weather_service.get_live_weather()
        weather_dict = weather.model_dump() if hasattr(weather, "model_dump") else weather.dict()
        await websocket.send_json({
            "type": "HANDSHAKE_INIT",
            "message": "Connected to AgriSmoke AI Real-Time Telemetry Stream",
            "activeClients": len(ws_manager.active_connections),
            "liveWeather": weather_dict
        })
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({
                "type": "HEARTBEAT_ACK",
                "clientPayload": data
            })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ----------------- Agricultural & Policy Simulation Endpoints -----------------

@app.get("/api/v1/policy/districts")
def get_policy_districts():
    """Retrieve list of priority agricultural districts with baseline stubble metrics."""
    return get_available_districts()


@app.post("/api/v1/policy/simulate", response_model=PolicySimulationResult)
def run_policy_simulation(req: PolicySimulationRequest):
    """
    Simulate Crop Residue Management (CRM) interventions:
    calculates avoided emissions, public health economic savings, and Benefit-Cost Ratios (BCR).
    """
    return simulate_policy_intervention(req)


# ----------------- Multi-Channel Alert Evaluation & Dispatch Endpoints -----------------

class AlertEvaluationRequest(BaseModel):
    predictedAqi: int = Field(default=412, ge=0, le=1000)
    fireCount: int = Field(default=1850, ge=0)
    pblHeight: int = Field(default=240, ge=50)
    windDirectionDeg: int = Field(default=310, ge=0, le=360)
    windSpeed: float = Field(default=13.5, ge=0.0)


@app.post("/api/v1/alerts/evaluate")
def evaluate_and_dispatch_alerts(req: AlertEvaluationRequest):
    """
    Evaluate telemetry against CAQM GRAP and airshed safety rules.
    Persists triggered alerts to SQLite and dispatches to configured notification channels.
    """
    alerts = alert_engine.evaluate_and_dispatch(
        predicted_aqi=req.predictedAqi,
        fire_count=req.fireCount,
        pbl_height=req.pblHeight,
        wind_direction_deg=req.windDirectionDeg,
        wind_speed=req.windSpeed
    )
    return {
        "status": "EVALUATED",
        "alertsTriggered": len(alerts),
        "alerts": alerts,
        "dispatchesActive": len(CONFIGURED_CHANNELS)
    }


@app.get("/api/v1/alerts/channels")
def get_alert_channels_and_logs(limit: int = 20):
    """Retrieve configured communication channels and recent dispatch audit logs."""
    return {
        "channels": CONFIGURED_CHANNELS,
        "recentDispatches": DISPATCH_LOGS[:limit]
    }


@app.on_event("startup")
def startup_event():
    """Initialize background ingestion scheduler on server boot."""
    scheduler.start()


@app.on_event("shutdown")
def shutdown_event():
    """Safely terminate background threads on server shutdown."""
    scheduler.stop()

# ----------------- Serve Frontend Static Files -----------------

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

    @app.get("/")
    def serve_frontend():
        # no-cache so HTML edits (and the SW cache-version bump) take effect on the
        # next reload instead of being served from a stale browser/service-worker cache.
        return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache, must-revalidate"})

# ----------------- Run Standalone -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.reload_enabled,
        proxy_headers=config.proxy_headers,
        forwarded_allow_ips=config.forwarded_allow_ips,
    )

