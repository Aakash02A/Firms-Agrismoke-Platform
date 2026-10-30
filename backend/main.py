"""
AgriSmoke AI - FastAPI Backend Server
Integrates SQLite database, trained Machine Learning dispersion models,
real-time prediction API, and static frontend delivery.
"""

import sys
import io
import csv
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

from model_inference import predictor
import database as db
from backend.integrations.weather import weather_service, LiveWeatherSnapshot
from backend.scheduler import scheduler

app = FastAPI(
    title="AgriSmoke AI API",
    description="Backend API with SQLite & Atmospheric Machine Learning for Indo-Gangetic Airshed AQI Predictions",
    version="2.0.0"
)

# CORS Middleware (allows cross-origin requests from frontend on any port/file origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/api/status")
def get_system_status():
    """Returns current system health, metadata, and default status benchmark."""
    default_params = {
        "fireCount": 1684,
        "windSpeed": 11.5,
        "windDirectionDeg": 305,
        "pblHeight": 480,
        "urbanBaselineAqi": 180,
        "bioDecomposerAdoption": 25,
        "happySeederAdoption": 30
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
            "airshedRiskScore": pred["airshedScore"],
            "grapStage": pred["grapStage"]
        },
        "thresholds": thresholds
    }

@app.get("/api/stations")
def get_stations():
    """Retrieve all real-world monitoring stations from SQLite database."""
    return db.get_monitoring_stations()

@app.get("/api/hotspots")
def get_hotspots():
    """Retrieve active fire thermal anomalies in Punjab & Haryana from SQLite."""
    return db.get_fire_hotspots()

@app.get("/api/trends/weekly")
def get_weekly_trends():
    """Retrieve 7-day trend history from SQLite."""
    return db.get_weekly_trends()

@app.get("/api/districts")
def get_district_rankings():
    """Retrieve district-wise stubble burning comparison."""
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

    # Save to SQLite simulation history asynchronously/synchronously
    try:
        db.save_simulation_run(params, pred)
    except Exception as e:
        print(f"[Warning] Failed to record simulation to DB: {e}")

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
        return FileResponse(FRONTEND_DIR / "index.html")

# ----------------- Run Standalone -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

