"""
Diagnostic Test: AI/ML Inference & Edge Case Verification
Validates model artifacts, physical sensitivity to parameters, and 24h forecasting.
"""

import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "ai-ml"))
from model_inference import predictor

def test_ml_model():
    print("=== Test 3: AI/ML Model & Forecasting Verification ===")
    
    # 1. Model artifact check
    assert predictor.model is not None, "ML model failed to load!"
    assert predictor.metrics, "Model metrics JSON not loaded!"
    r2 = predictor.metrics.get("best_metrics", {}).get("r2_score", 0)
    print(f"[PASS] Serialized model loaded: {predictor.metrics.get('model_name')} (R2 = {r2})")
    assert r2 > 0.95, f"R2 score too low: {r2}"

    # 2. Baseline scenario
    baseline = predictor.predict({
        "fireCount": 1684, "windSpeed": 11.5, "windDirectionDeg": 305,
        "pblHeight": 480, "urbanBaselineAqi": 180,
        "bioDecomposerAdoption": 25, "happySeederAdoption": 30
    })
    print(f"[PASS] Baseline prediction: AQI = {baseline['predictedAqi']} ({baseline['category']}), PM2.5 = {baseline['totalPm25']} ug/m3, Parali% = {baseline['paraliPct']}%")
    assert 250 <= baseline["predictedAqi"] <= 450, f"Unexpected baseline AQI: {baseline['predictedAqi']}"
    assert baseline["stubblePm25"] > 0
    assert baseline["category"] in ["Poor", "Very Poor", "Severe", "Severe+ / Emergency"]

    # 3. Zero fires edge case (Clean agricultural scenario)
    zero_fires = predictor.predict({
        "fireCount": 0, "windSpeed": 12.0, "windDirectionDeg": 310,
        "pblHeight": 500, "urbanBaselineAqi": 150
    })
    print(f"[PASS] Zero fires scenario: AQI = {zero_fires['predictedAqi']}, Stubble PM2.5 = {zero_fires['stubblePm25']} ug/m3, Parali% = {zero_fires['paraliPct']}%")
    assert zero_fires["stubblePm25"] == 0.0 or zero_fires["paraliPct"] <= 2.0
    assert zero_fires["predictedAqi"] < baseline["predictedAqi"]

    # 4. Peak fire surge edge case (5,000 fires)
    peak_fires = predictor.predict({
        "fireCount": 5000, "windSpeed": 12.0, "windDirectionDeg": 312,
        "pblHeight": 250, "urbanBaselineAqi": 200,
        "bioDecomposerAdoption": 0, "happySeederAdoption": 0
    })
    print(f"[PASS] Peak fires scenario: AQI = {peak_fires['predictedAqi']} ({peak_fires['category']}), PM2.5 = {peak_fires['totalPm25']} ug/m3")
    assert peak_fires["predictedAqi"] >= 400, "Peak fires should trigger Severe or Emergency AQI"
    assert peak_fires["grapStage"] in ["Stage III", "Stage IV"]

    # 5. Favorable Easterly wind shift (Plume directed away from Delhi)
    easterly_wind = predictor.predict({
        "fireCount": 3000, "windSpeed": 15.0, "windDirectionDeg": 90, # Easterly
        "pblHeight": 500, "urbanBaselineAqi": 180
    })
    print(f"[PASS] Easterly wind shift: AQI = {easterly_wind['predictedAqi']}, Dir Factor = {easterly_wind['dirFactor']}%")
    assert easterly_wind["dirFactor"] <= 10, "Easterly wind alignment should drop significantly"
    assert easterly_wind["predictedAqi"] < peak_fires["predictedAqi"]

    # 6. Nocturnal boundary layer inversion compression
    low_pbl = predictor.predict({
        "fireCount": 2000, "windSpeed": 10.0, "windDirectionDeg": 310,
        "pblHeight": 180, "urbanBaselineAqi": 180
    })
    high_pbl = predictor.predict({
        "fireCount": 2000, "windSpeed": 10.0, "windDirectionDeg": 310,
        "pblHeight": 800, "urbanBaselineAqi": 180
    })
    print(f"[PASS] Inversion sensitivity: Low PBL (180m) AQI = {low_pbl['predictedAqi']} vs High PBL (800m) AQI = {high_pbl['predictedAqi']}")
    assert low_pbl["predictedAqi"] > high_pbl["predictedAqi"]
    assert low_pbl["pblTrappingFactor"] > high_pbl["pblTrappingFactor"]

    # 7. Diurnal 24-hour hourly progression test
    hourly = predictor.generate_hourly_forecast({
        "fireCount": 1684, "windSpeed": 11.5, "windDirectionDeg": 305, "pblHeight": 480
    }, start_hour=0)
    assert len(hourly) == 24, f"Expected 24 forecast hours, got {len(hourly)}"
    
    # Verify diurnal night vs afternoon dynamics
    # Hour 4 (04:00 night inversion) vs Hour 14 (14:00 solar mixing)
    hour_4 = next(h for h in hourly if h["hourNum"] == 4)
    hour_14 = next(h for h in hourly if h["hourNum"] == 14)
    print(f"[PASS] Diurnal cycle: 04:00 AQI = {hour_4['aqi']} (PBL: {hour_4['pbl']}m) vs 14:00 AQI = {hour_14['aqi']} (PBL: {hour_14['pbl']}m)")
    assert hour_4["aqi"] > hour_14["aqi"], "Nocturnal AQI should exceed midday convective AQI"
    assert hour_4["pbl"] < hour_14["pbl"], "Nocturnal PBL should be compressed relative to midday"

    print("=== AI/ML Model & Forecasting: ALL TESTS PASSED! ===")

if __name__ == "__main__":
    test_ml_model()

