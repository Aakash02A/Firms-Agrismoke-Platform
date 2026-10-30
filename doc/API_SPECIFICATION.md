# 📡 AgriSmoke AI &bull; REST API Specification

The AgriSmoke AI backend is powered by **FastAPI (Python 3.13)** and provides a high-throughput, asynchronous JSON API documented via OpenAPI (Swagger).

- **Base URL**: `http://127.0.0.1:8000`
- **Interactive Swagger Documentation**: `http://127.0.0.1:8000/docs`
- **ReDoc Interactive Reference**: `http://127.0.0.1:8000/redoc`

---

## Endpoint Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/status` | System health, model accuracy, and default benchmark status |
| `GET` | `/api/stations` | Real-world Delhi-NCR air monitoring stations (CPCB CAAQMS) |
| `GET` | `/api/hotspots` | Active fire clusters in Punjab & Haryana with FRP |
| `GET` | `/api/trends/weekly` | 7-day trend history of fires vs. Delhi AQI |
| `GET` | `/api/districts` | District-wise stubble burning rankings |
| `POST` | `/api/predict` | **Core ML Endpoint**: Run ML regressor on custom scenario |
| `GET` | `/api/forecast/diurnal` | Generate 24-hour diurnal AQI & $\text{PM}_{2.5}$ forecast |
| `GET` | `/api/grap` | CAQM Graded Response Action Plan (GRAP) guidelines |
| `GET` | `/api/alerts` | Live automated early warning alert feed |
| `GET` | `/api/thresholds` | Retrieve user-configured emergency thresholds |
| `POST` | `/api/thresholds` | Update emergency trigger thresholds in SQLite |
| `GET` | `/api/model/metrics` | Retrieve model training metrics, $R^2$, and feature importances |
| `GET` | `/api/export/csv` | Download 24h ML prediction report as CSV |

---

## Detailed Endpoint Documentation

### 1. System Status (`GET /api/status`)
Retrieves runtime configuration, ML model metadata, and current Delhi-NCR composite baseline.

#### Response `200 OK`
```json
{
  "status": "online",
  "system": "AgriSmoke AI Indo-Gangetic Air Quality Platform",
  "backend": "Python 3.13 + FastAPI + SQLite",
  "mlModel": "GradientBoostingRegressor",
  "mlAccuracyR2": 0.9886,
  "currentBenchmark": {
    "aqi": 382,
    "category": "Very Poor",
    "categoryColor": "#ff3d00",
    "dominantPollutant": "PM2.5",
    "pm25": 236.4,
    "pm10": 388.2,
    "paraliContributionPct": 34.6,
    "activeFires": 1684,
    "windSpeed": 11.5,
    "windDirectionDeg": 305,
    "pblHeight": 480,
    "airshedRiskScore": 84,
    "grapStage": "Stage III"
  },
  "thresholds": {
    "aqi": 400,
    "fires": 2000
  }
}
```

---

### 2. Predict Scenario (`POST /api/predict`)
Executes the serialized Machine Learning regressor (`GradientBoostingRegressor`) using user-provided meteorological and intervention variables.

#### Request Body
```json
{
  "fireCount": 2450,
  "windSpeed": 12.0,
  "windDirectionDeg": 310,
  "pblHeight": 320,
  "urbanBaselineAqi": 180,
  "bioDecomposerAdoption": 35,
  "happySeederAdoption": 40,
  "temperature": 22.5,
  "humidity": 65.0
}
```

#### Response `200 OK`
```json
{
  "prediction": {
    "predictedAqi": 415,
    "category": "Severe",
    "categoryColor": "#d50000",
    "grapStage": "Stage III",
    "riskLevel": "Critical",
    "totalPm25": 268.4,
    "totalPm10": 450.9,
    "stubblePm25": 148.4,
    "urbanBasePm25": 120.0,
    "paraliPct": 55.3,
    "transportHours": 22.9,
    "airshedScore": 92,
    "dirFactor": 98,
    "pblTrappingFactor": 1.98,
    "effectiveFires": 1592,
    "mitigationSavings": {
      "pm25Avoidable": 77.2,
      "aqiDrop": 64,
      "biomassAvoidedTonnes": 3821
    },
    "mlModelMetadata": {
      "modelType": "GradientBoostingRegressor",
      "r2Score": 0.9886,
      "rmse": 17.672
    }
  },
  "hourlyForecast": [
    {
      "time": "11:00",
      "hourNum": 11,
      "aqi": 415,
      "pm25": 268.4,
      "stubblePct": 55.3,
      "pbl": 320,
      "windSpeed": 12.0,
      "category": "Severe",
      "color": "#d50000"
    }
  ]
}
```

---

### 3. Monitoring Stations (`GET /api/stations`)
Fetches all real-world representative monitoring stations stored in SQLite.

#### Response `200 OK`
```json
[
  {
    "id": "del_bawana",
    "name": "Bawana, North-West Delhi",
    "type": "Industrial / Upwind Inflow",
    "lat": 28.7762,
    "lng": 77.0511,
    "aqi": 468,
    "category": "Severe",
    "pm25": 345.0,
    "pm10": 512.0,
    "parali_pct": 44.0,
    "trend": "up"
  }
]
```

---

### 4. Machine Learning Model Metrics (`GET /api/model/metrics`)
Returns benchmark comparisons across all trained models, loss metrics, and feature weights.

#### Response `200 OK`
```json
{
  "model_name": "GradientBoostingRegressor",
  "selected_at": "2026-10-29 03:20:25 UTC",
  "target_variable": "total_pm25",
  "best_metrics": {
    "r2_score": 0.9886,
    "rmse": 17.672,
    "mae": 9.509,
    "training_time_sec": 9.86
  },
  "all_candidate_metrics": {
    "GradientBoostingRegressor": { "r2_score": 0.9886, "rmse": 17.672, "mae": 9.509 },
    "XGBoostRegressor": { "r2_score": 0.9878, "rmse": 18.310, "mae": 9.551 },
    "RandomForestRegressor": { "r2_score": 0.9834, "rmse": 21.381, "mae": 11.037 },
    "RidgeRegression": { "r2_score": 0.6586, "rmse": 96.896, "mae": 60.172 }
  },
  "feature_importances": {
    "effective_fires": 0.4125,
    "urban_baseline_aqi": 0.2841,
    "inversion_multiplier": 0.1412,
    "dir_alignment": 0.0892,
    "wind_coeff": 0.0435
  }
}
```

