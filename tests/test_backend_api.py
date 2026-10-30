"""
Diagnostic Test: Backend API Endpoint Functions
Directly tests all FastAPI endpoint logic, return models, CSV formatting, and static files.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "ai-ml"))

import main
from main import PredictionRequest, ThresholdUpdateRequest

def test_api_endpoints():
    print("=== Test 4: Backend API Endpoint Logic & Data Validation ===")

    # 1. Test /api/status
    status = main.get_system_status()
    assert status["status"] == "online"
    assert "currentBenchmark" in status
    assert status["mlModel"] == "GradientBoostingRegressor"
    print(f"[PASS] /api/status -> Model: {status['mlModel']}, R2: {status['mlAccuracyR2']}, Baseline AQI: {status['currentBenchmark']['aqi']}")

    # 2. Test /api/stations
    stations = main.get_stations()
    assert len(stations) == 9
    assert all("name" in s and "aqi" in s and "paraliPct" in s for s in stations)
    print(f"[PASS] /api/stations -> Retrieved {len(stations)} stations (Top: {stations[0]['name']} - {stations[0]['aqi']} AQI)")

    # 3. Test /api/hotspots
    hotspots = main.get_hotspots()
    assert len(hotspots) == 10
    assert all("district" in h and "fireCount" in h and "avgFRP" in h for h in hotspots)
    print(f"[PASS] /api/hotspots -> Retrieved {len(hotspots)} fire hotspots (Top: {hotspots[0]['district']} - {hotspots[0]['fireCount']} fires)")

    # 4. Test /api/trends/weekly
    trends = main.get_weekly_trends()
    assert len(trends) == 7
    print(f"[PASS] /api/trends/weekly -> Retrieved {len(trends)} historical records")

    # 5. Test /api/districts
    districts = main.get_district_rankings()
    assert len(districts) == 10
    print(f"[PASS] /api/districts -> Retrieved {len(districts)} district rankings")

    # 6. Test /api/grap
    grap = main.get_grap_guidelines()
    assert len(grap) == 4
    assert any(g["active"] for g in grap)
    print(f"[PASS] /api/grap -> Retrieved {len(grap)} GRAP stages")

    # 7. Test /api/alerts
    alerts = main.get_alerts()
    assert len(alerts) >= 3
    print(f"[PASS] /api/alerts -> Retrieved {len(alerts)} alerts")

    # 8. Test /api/predict (Core ML inference)
    req = PredictionRequest(
        fireCount=2500,
        windSpeed=12.5,
        windDirectionDeg=310,
        pblHeight=350,
        urbanBaselineAqi=180,
        bioDecomposerAdoption=20,
        happySeederAdoption=25
    )
    pred_res = main.run_prediction(req)
    assert "prediction" in pred_res
    assert "hourlyForecast" in pred_res
    p = pred_res["prediction"]
    h = pred_res["hourlyForecast"]
    assert 200 <= p["predictedAqi"] <= 999
    assert len(h) == 24
    print(f"[PASS] /api/predict -> Predicted AQI: {p['predictedAqi']} ({p['category']}), PM2.5: {p['totalPm25']} ug/m3, 24h Hourly Points: {len(h)}")

    # 9. Test /api/forecast/diurnal
    hourly = main.get_diurnal_forecast(fireCount=1800, windSpeed=10.0)
    assert len(hourly) == 24
    print(f"[PASS] /api/forecast/diurnal -> Generated {len(hourly)} hourly diurnal forecast points")

    # 10. Test /api/thresholds
    up_req = ThresholdUpdateRequest(aqi=425, fires=2200)
    main.update_thresholds(up_req)
    current_th = main.get_thresholds()
    assert current_th["aqi"] == 425 and current_th["fires"] == 2200
    # Reset
    main.update_thresholds(ThresholdUpdateRequest(aqi=400, fires=2000))
    print("[PASS] /api/thresholds -> Successfully updated and verified in SQLite")

    # 11. Test /api/model/metrics
    metrics = main.get_model_metrics()
    assert "best_metrics" in metrics
    assert metrics["best_metrics"]["r2_score"] > 0.95
    print(f"[PASS] /api/model/metrics -> Validated ML accuracy metrics (R2 = {metrics['best_metrics']['r2_score']})")

    # 12. Test /api/export/csv
    csv_resp = main.export_csv(fireCount=1684, windSpeed=11.5)
    assert csv_resp.media_type == "text/csv"
    assert b"Time,Predicted_AQI" in csv_resp.body
    print(f"[PASS] /api/export/csv -> Generated telemetry CSV ({len(csv_resp.body)} bytes)")

    # 13. Test Frontend file resolution
    frontend_resp = main.serve_frontend()
    assert Path(frontend_resp.path).exists()
    assert "index.html" in str(frontend_resp.path)
    print(f"[PASS] serve_frontend() -> Resolved valid file: {frontend_resp.path}")

    # 14. Test /api/v1/firms/status & config
    firms_status = main.get_firms_provider_status()
    assert firms_status.provider_id == "nasa_firms"
    firms_cfg = main.get_firms_config()
    assert "masked_map_key" in firms_cfg
    print(f"[PASS] /api/v1/firms/status -> Provider: {firms_status.provider_name}, Status: {firms_status.status}")

    # 15. Test /api/v1/firms/observations & summary
    obs = main.get_firms_observations(limit=50)
    assert isinstance(obs, list)
    summary = main.get_firms_summary(days=7)
    assert "stats" in summary
    print(f"[PASS] /api/v1/firms/observations -> Retrieved {len(obs)} records, Summary Total: {summary['stats'].get('total_observations', 0)}")

    # 16. Test /api/v1/geospatial/districts & events
    geo_districts = main.get_geospatial_districts(days=7)
    assert len(geo_districts) >= 10
    geo_events = main.get_geospatial_events(limit=20)
    assert isinstance(geo_events, list)
    print(f"[PASS] /api/v1/geospatial/districts -> Retrieved {len(geo_districts)} districts, Events: {len(geo_events)}")

    # 17. Test /api/v1/predict/live
    live_pred = main.get_live_satellite_prediction()
    assert "prediction" in live_pred
    assert "source" in live_pred
    print(f"[PASS] /api/v1/predict/live -> Source: {live_pred['source']}, AQI: {live_pred['prediction']['predictedAqi']}")

    # 18. Test /api/v1/alerts
    alerts_v1 = main.get_alert_stream()
    assert isinstance(alerts_v1, list)
    print(f"[PASS] /api/v1/alerts -> Retrieved {len(alerts_v1)} lifecycle alert records")

    # 19. Test /api/v1/weather/live
    weather_live = main.get_live_meteorology()
    assert weather_live.temperature > -20.0 and weather_live.temperature < 60.0
    assert weather_live.pblHeight >= 100
    assert weather_live.ventilationIndex > 0
    print(f"[PASS] /api/v1/weather/live -> Location: {weather_live.location}, Temp: {weather_live.temperature}C, Wind: {weather_live.windSpeed} km/h, PBL: {weather_live.pblHeight}m")

    # 20. Test /api/v1/scheduler/status
    sched_status = main.get_scheduler_status()
    assert "isRunning" in sched_status
    assert "firmsIntervalHours" in sched_status
    print(f"[PASS] /api/v1/scheduler/status -> Running: {sched_status['isRunning']}, FIRMS Interval: {sched_status['firmsIntervalHours']}h, Weather Refreshes: {sched_status['totalWeatherRefreshes']}")

    # 21. Test /api/v1/forecast/multiday
    multiday = main.get_multiday_forecast()
    assert multiday["horizonHours"] == 72
    assert len(multiday["hourly"]) == 72
    assert len(multiday["daySummaries"]) == 3
    print(f"[PASS] /api/v1/forecast/multiday -> Horizon: 72h, Day 1 AQI: {multiday['daySummaries'][0]['meanAqi']}, Day 2 AQI: {multiday['daySummaries'][1]['meanAqi']}, Day 3 AQI: {multiday['daySummaries'][2]['meanAqi']}")

    # 22. Test /api/v1/model/drift
    drift = main.get_model_drift_evaluation()
    assert "status" in drift
    assert "meanAbsoluteError" in drift
    print(f"[PASS] /api/v1/model/drift -> Status: {drift['status']}, Evaluated Stations: {drift['evaluatedStationCount']}, MAE: {drift['meanAbsoluteError']} AQI")

    # 23. Test /api/v1/policy/districts
    districts = main.get_policy_districts()
    assert len(districts) >= 8
    assert all("id" in d and "annualFiresBaseline" in d for d in districts)
    print(f"[PASS] /api/v1/policy/districts -> Retrieved {len(districts)} agricultural districts (Top: {districts[0]['name']})")

    # 24. Test /api/v1/policy/simulate
    policy_res = main.run_policy_simulation(main.PolicySimulationRequest(
        districtId="PB_SANGRUR",
        bioDecomposerAdoptionPct=40.0,
        happySeederAdoptionPct=45.0,
        subsidyBudgetCrores=20.0
    ))
    assert policy_res.firesPrevented > 0
    assert policy_res.pm25AvoidedTonnes > 0
    assert policy_res.benefitCostRatio > 1.0
    print(f"[PASS] /api/v1/policy/simulate -> District: {policy_res.districtName}, Prevented Fires: {policy_res.firesPrevented} (-{policy_res.fireReductionPct}%), PM2.5 Avoided: {policy_res.pm25AvoidedTonnes}t, BCR: {policy_res.benefitCostRatio}x")

    # 25. Test /api/v1/alerts/evaluate
    eval_res = main.evaluate_and_dispatch_alerts(main.AlertEvaluationRequest(
        predictedAqi=465,
        fireCount=2100,
        pblHeight=220,
        windDirectionDeg=312,
        windSpeed=14.0
    ))
    assert eval_res["status"] == "EVALUATED"
    assert eval_res["alertsTriggered"] >= 1
    print(f"[PASS] /api/v1/alerts/evaluate -> Triggered {eval_res['alertsTriggered']} emergency alerts across {eval_res['dispatchesActive']} channels")

    # 26. Test /api/v1/alerts/channels
    channels_res = main.get_alert_channels_and_logs()
    assert len(channels_res["channels"]) >= 4
    assert len(channels_res["recentDispatches"]) >= 1
    print(f"[PASS] /api/v1/alerts/channels -> {len(channels_res['channels'])} active channels, {len(channels_res['recentDispatches'])} delivered dispatch logs")

    print("=== Backend API & Data Delivery: ALL 26 ENDPOINTS & ENGINES PASSED! ===")

if __name__ == "__main__":
    test_api_endpoints()
