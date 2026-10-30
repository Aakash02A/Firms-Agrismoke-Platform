"""
AgriSmoke AI - Live Server & End-to-End Comprehensive Test Suite
Validates static asset delivery, all 13 REST API endpoints, physical dispersion boundary cases,
response times, and database consistency.
"""

import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "ai-ml"))

from main import app
import database as db

client = TestClient(app)

def test_static_asset_delivery():
    print("\n--- 1. Testing Static File Delivery ---")
    
    # Root HTML
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "AgriSmoke AI" in res.text, "Title not found in HTML"
    assert "kpi-grid" in res.text, "kpi-grid not found in HTML"
    assert "geospatial-canvas" in res.text, "Canvas not found in HTML"
    print(" [PASS] Root HTML (index.html) successfully served.")

    # CSS stylesheet
    res_css = client.get("/css/styles.css")
    assert res_css.status_code == 200, f"Expected 200, got {res_css.status_code}"
    assert "--bg-primary: #f8fafc" in res_css.text, "Light theme background variable not found in styles.css"
    assert "--accent-green: #16a34a" in res_css.text, "Accent green variable not found in styles.css"
    print(f" [PASS] CSS stylesheet (/css/styles.css) served ({len(res_css.text)} bytes).")

    # JS files
    js_files = ["demo-data.js", "prediction-model.js", "charts-engine.js", "map-engine.js", "app.js"]
    for js in js_files:
        r = client.get(f"/js/{js}")
        assert r.status_code == 200, f"Failed serving /js/{js}"
        assert len(r.text) > 100, f"File /js/{js} is too short"
        print(f" [PASS] JS asset /js/{js} served ({len(r.text)} bytes).")

def test_api_system_status():
    print("\n--- 2. Testing System Status API ---")
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "GradientBoostingRegressor" in data["mlModel"]
    assert data["mlAccuracyR2"] > 0.95
    assert "currentBenchmark" in data
    bench = data["currentBenchmark"]
    assert bench["aqi"] > 0
    assert bench["dominantPollutant"] == "PM2.5"
    assert "thresholds" in data
    print(f" [PASS] /api/status -> Online, Model: {data['mlModel']}, R2: {data['mlAccuracyR2']}, Benchmark AQI: {bench['aqi']}")

def test_api_database_endpoints():
    print("\n--- 3. Testing Database Query Endpoints ---")
    
    # Stations
    res = client.get("/api/stations")
    assert res.status_code == 200
    stations = res.json()
    assert len(stations) >= 7, f"Expected >= 7 stations, got {len(stations)}"
    assert all("id" in s and "name" in s and "aqi" in s and "pm25" in s for s in stations)
    print(f" [PASS] /api/stations -> {len(stations)} stations retrieved.")

    # Hotspots
    res = client.get("/api/hotspots")
    assert res.status_code == 200
    hotspots = res.json()
    assert len(hotspots) >= 8
    assert all("district" in h and "fireCount" in h and "state" in h for h in hotspots)
    print(f" [PASS] /api/hotspots -> {len(hotspots)} thermal fire clusters retrieved.")

    # Weekly Trends
    res = client.get("/api/trends/weekly")
    assert res.status_code == 200
    trends = res.json()
    assert len(trends) == 7
    print(f" [PASS] /api/trends/weekly -> {len(trends)} days historical trend retrieved.")

    # Districts
    res = client.get("/api/districts")
    assert res.status_code == 200
    districts = res.json()
    assert len(districts) >= 8
    print(f" [PASS] /api/districts -> {len(districts)} district rankings retrieved.")

    # GRAP Stages
    res = client.get("/api/grap")
    assert res.status_code == 200
    grap = res.json()
    assert len(grap) == 4
    stage_ii = next((s for s in grap if s["stage"] == "Stage II"), None)
    assert stage_ii is not None and stage_ii["active"] == True
    print(f" [PASS] /api/grap -> 4 GRAP stages verified (Stage II active).")

    # Alerts
    res = client.get("/api/alerts")
    assert res.status_code == 200
    alerts = res.json()
    assert len(alerts) >= 3
    print(f" [PASS] /api/alerts -> {len(alerts)} early warning alerts retrieved.")

def test_api_threshold_management():
    print("\n--- 4. Testing Threshold Update & Persistence ---")
    # Initial read
    r_get = client.get("/api/thresholds")
    assert r_get.status_code == 200
    
    # Update to custom values
    new_aqi, new_fires = 425, 2250
    r_post = client.post("/api/thresholds", json={"aqi": new_aqi, "fires": new_fires})
    assert r_post.status_code == 200
    data = r_post.json()
    assert data["data"]["aqi"] == new_aqi
    assert data["data"]["fires"] == new_fires
    
    # Verify persistence
    r_verify = client.get("/api/thresholds")
    assert r_verify.json()["aqi"] == new_aqi
    assert r_verify.json()["fires"] == new_fires

    # Reset back to baseline
    client.post("/api/thresholds", json={"aqi": 400, "fires": 2000})
    print(f" [PASS] /api/thresholds -> Successfully updated and persisted to SQLite.")

def test_api_ml_prediction_scenarios():
    print("\n--- 5. Testing Machine Learning Prediction Scenarios ---")
    
    # 1. Baseline Scenario
    t0 = time.time()
    res = client.post("/api/predict", json={
        "fireCount": 1684,
        "windSpeed": 11.5,
        "windDirectionDeg": 305,
        "pblHeight": 480,
        "urbanBaselineAqi": 180,
        "bioDecomposerAdoption": 25,
        "happySeederAdoption": 30
    })
    elapsed = (time.time() - t0) * 1000
    assert res.status_code == 200
    base_data = res.json()
    pred = base_data["prediction"]
    assert 250 <= pred["predictedAqi"] <= 500, f"Unexpected baseline AQI: {pred['predictedAqi']}"
    assert pred["totalPm25"] > 100
    assert pred["stubblePm25"] > 20
    assert pred["paraliPct"] > 10
    assert len(base_data["hourlyForecast"]) == 24
    print(f" [PASS] Baseline Prediction: AQI = {pred['predictedAqi']} ({pred['category']}), PM2.5 = {pred['totalPm25']} ug/m3, Parali% = {pred['paraliPct']}% [Latency: {elapsed:.1f}ms]")

    # 2. Zero Fires Scenario (Physical lower bound check)
    res_zero = client.post("/api/predict", json={
        "fireCount": 0,
        "windSpeed": 11.5,
        "windDirectionDeg": 305,
        "pblHeight": 480,
        "urbanBaselineAqi": 180,
        "bioDecomposerAdoption": 50,
        "happySeederAdoption": 50
    })
    pred_zero = res_zero.json()["prediction"]
    assert pred_zero["stubblePm25"] == 0.0, f"Expected 0 stubble PM2.5, got {pred_zero['stubblePm25']}"
    assert pred_zero["paraliPct"] == 0.0, f"Expected 0% parali, got {pred_zero['paraliPct']}"
    assert pred_zero["predictedAqi"] < pred["predictedAqi"]
    print(f" [PASS] Zero Fires Scenario: Stubble PM2.5 = {pred_zero['stubblePm25']} ug/m3, Parali% = 0.0%, AQI = {pred_zero['predictedAqi']}")

    # 3. Severe Peak Burning & Thermal Inversion
    res_peak = client.post("/api/predict", json={
        "fireCount": 4800,
        "windSpeed": 14.0,
        "windDirectionDeg": 312,
        "pblHeight": 180, # Severe nocturnal inversion
        "urbanBaselineAqi": 240,
        "bioDecomposerAdoption": 0,
        "happySeederAdoption": 0
    })
    pred_peak = res_peak.json()["prediction"]
    assert pred_peak["predictedAqi"] >= 500 or pred_peak["category"] in ["Severe", "Severe+ / Emergency"]
    assert pred_peak["totalPm25"] > 350
    print(f" [PASS] Peak Burning & Nocturnal Inversion: AQI = {pred_peak['predictedAqi']} ({pred_peak['category']}), PM2.5 = {pred_peak['totalPm25']} ug/m3")

    # 4. Favorable Easterly Wind Shift (Plume deflected from Delhi)
    res_east = client.post("/api/predict", json={
        "fireCount": 2500,
        "windSpeed": 12.0,
        "windDirectionDeg": 90, # Due East (blows smoke away from Delhi)
        "pblHeight": 500,
        "urbanBaselineAqi": 150,
        "bioDecomposerAdoption": 20,
        "happySeederAdoption": 20
    })
    pred_east = res_east.json()["prediction"]
    assert pred_east["dirFactor"] <= 10, f"Expected low dir alignment, got {pred_east['dirFactor']}%"
    print(f" [PASS] Easterly Wind Shift Deflection: Dir Factor = {pred_east['dirFactor']}%, AQI = {pred_east['predictedAqi']}")

def test_api_forecast_and_export():
    print("\n--- 6. Testing 24h Diurnal Forecast & CSV Telemetry Export ---")
    
    # 24h Forecast
    res_fc = client.get("/api/forecast/diurnal?fireCount=1800&windSpeed=12.0")
    assert res_fc.status_code == 200
    hourly = res_fc.json()
    assert len(hourly) == 24
    assert all("time" in h and "aqi" in h and "pm25" in h and "pbl" in h for h in hourly)
    print(f" [PASS] /api/forecast/diurnal -> 24 hours of forecast points returned.")

    # Model metrics
    res_m = client.get("/api/model/metrics")
    assert res_m.status_code == 200
    metrics = res_m.json()
    assert "best_metrics" in metrics
    assert metrics["best_metrics"]["r2_score"] > 0.95
    print(f" [PASS] /api/model/metrics -> Validated model telemetry: R2 = {metrics['best_metrics']['r2_score']}")

    # CSV Export
    res_csv = client.get("/api/export/csv?fireCount=1684&windSpeed=11.5")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "Time,Predicted_AQI,PM25_ug_m3" in res_csv.text
    assert "# Model Telemetry Metadata" in res_csv.text
    print(f" [PASS] /api/export/csv -> Validated generated CSV telemetry report ({len(res_csv.text)} bytes).")

def test_api_nasa_firms_and_geospatial():
    print("\n--- 7. Testing NASA FIRMS & Geospatial Intelligence Endpoints ---")

    # Status
    res_status = client.get("/api/v1/firms/status")
    assert res_status.status_code == 200
    s_data = res_status.json()
    assert s_data["provider_id"] == "nasa_firms"
    assert "status" in s_data
    print(f" [PASS] /api/v1/firms/status -> Provider: {s_data['provider_name']}, Health: {s_data['is_healthy']}")

    # Config
    res_cfg = client.get("/api/v1/firms/config")
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert "masked_map_key" in cfg_data
    assert "supported_sensors" in cfg_data
    print(f" [PASS] /api/v1/firms/config -> Safe config retrieved, Masked Key: {cfg_data['masked_map_key']}")

    # Observations
    res_obs = client.get("/api/v1/firms/observations?limit=20")
    assert res_obs.status_code == 200
    obs_list = res_obs.json()
    assert isinstance(obs_list, list)
    print(f" [PASS] /api/v1/firms/observations -> Retrieved {len(obs_list)} normalized observations")

    # Summary
    res_sum = client.get("/api/v1/firms/summary?days=7")
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert "stats" in sum_data and "provider" in sum_data
    print(f" [PASS] /api/v1/firms/summary -> Total Observations: {sum_data['stats'].get('total_observations', 0)}")

    # Geospatial Districts
    res_dist = client.get("/api/v1/geospatial/districts?days=7")
    assert res_dist.status_code == 200
    dist_list = res_dist.json()
    assert len(dist_list) >= 10
    print(f" [PASS] /api/v1/geospatial/districts -> {len(dist_list)} dynamic district summaries retrieved")

    # Geospatial Events
    res_evt = client.get("/api/v1/geospatial/events?limit=20")
    assert res_evt.status_code == 200
    evt_list = res_evt.json()
    assert isinstance(evt_list, list)
    print(f" [PASS] /api/v1/geospatial/events -> {len(evt_list)} clustered fire events retrieved")

    # Live Satellite Prediction
    res_live = client.get("/api/v1/predict/live")
    assert res_live.status_code == 200
    live_data = res_live.json()
    assert "prediction" in live_data
    assert 50 <= live_data["prediction"]["predictedAqi"] <= 999
    print(f" [PASS] /api/v1/predict/live -> Source: {live_data['source']}, Predicted AQI: {live_data['prediction']['predictedAqi']}")

    # Real-World Lifecycle Alerts
    res_alt = client.get("/api/v1/alerts")
    assert res_alt.status_code == 200
    alt_list = res_alt.json()
    assert isinstance(alt_list, list)
    print(f" [PASS] /api/v1/alerts -> {len(alt_list)} lifecycle alerts retrieved")

if __name__ == "__main__":
    print("======================================================================")
    print(">> AgriSmoke AI - Comprehensive Live Server Test Suite")
    print("======================================================================")
    
    try:
        test_static_asset_delivery()
        test_api_system_status()
        test_api_database_endpoints()
        test_api_threshold_management()
        test_api_ml_prediction_scenarios()
        test_api_forecast_and_export()
        test_api_nasa_firms_and_geospatial()
        print("\n======================================================================")
        print(">> ALL INTEGRATION & APPLICATION TESTS PASSED (100% SUCCESS)!")
        print("======================================================================")
    except AssertionError as e:
        print(f"\n[FAIL] Test assertion failed: {e}")
        sys.exit(1)
    except Exception as ex:
        print(f"\n[ERROR] Unexpected error during test run: {ex}")
        sys.exit(1)

