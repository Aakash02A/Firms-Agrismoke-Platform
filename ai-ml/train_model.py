"""
AgriSmoke AI - Machine Learning Model Trainer
Trains, benchmarks, and serializes atmospheric dispersion ML regressors
for predicting fine particulate (PM2.5) concentrations and urban air quality.
"""

import sys
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

# Scikit-learn unpickling compatibility bridge
if "_loss" not in sys.modules:
    try:
        import sklearn._loss._loss as _cyloss
        sys.modules["_loss"] = _cyloss
    except Exception:
        try:
            import sklearn._loss as _skloss
            sys.modules["_loss"] = _skloss
        except Exception:
            pass

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, root_mean_squared_error, mean_absolute_error
from sklearn.preprocessing import StandardScaler

# Import local dataset generator if data does not exist
from dataset_generator import generate_atmospheric_dataset, DATA_PATH

MODELS_DIR = Path(__file__).resolve().parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_OUTPUT_PATH = MODELS_DIR / "aqi_dispersion_model.joblib"
SCALER_OUTPUT_PATH = MODELS_DIR / "scaler.joblib"
METRICS_OUTPUT_PATH = MODELS_DIR / "metrics.json"

FEATURE_COLS = [
    "fire_count",
    "wind_speed",
    "wind_direction_deg",
    "pbl_height",
    "urban_baseline_aqi",
    "bio_decomposer_adoption",
    "happy_seeder_adoption",
    "temperature",
    "humidity",
    "effective_fires",
    "dir_alignment",
    "wind_coeff",
    "inversion_multiplier",
    "ventilation_index"
]

TARGET_COL = "total_pm25"

def train_and_evaluate():
    print("=== AgriSmoke AI &bull; Model Training Pipeline ===")
    
    if not DATA_PATH.exists():
        generate_atmospheric_dataset()

    df = pd.read_csv(DATA_PATH)
    print(f"Loaded dataset: {df.shape[0]} records, {df.shape[1]} features.")

    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    # Train / Test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    print(f"Train set: {X_train.shape[0]} | Test set: {X_test.shape[0]}")

    # Standard Scaler
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Candidate Algorithms
    candidates = {
        "GradientBoostingRegressor": GradientBoostingRegressor(
            n_estimators=180, learning_rate=0.08, max_depth=5, random_state=42
        ),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=150, max_depth=12, n_jobs=-1, random_state=42
        ),
        "RidgeRegression": Ridge(alpha=1.0)
    }

    # Add XGBoost if available
    try:
        import xgboost as xgb
        candidates["XGBoostRegressor"] = xgb.XGBRegressor(
            n_estimators=180, learning_rate=0.07, max_depth=5, random_state=42, n_jobs=-1
        )
    except ImportError:
        pass

    results = {}
    best_name = None
    best_score = -float("inf")
    best_model = None

    print("\nEvaluating Candidate Regressors...")
    for name, model in candidates.items():
        t0 = time.time()
        # Scale for Ridge, raw for tree-based
        if "Ridge" in name:
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
        elapsed = time.time() - t0

        r2 = r2_score(y_test, y_pred)
        rmse = root_mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)

        results[name] = {
            "r2_score": round(float(r2), 4),
            "rmse": round(float(rmse), 3),
            "mae": round(float(mae), 3),
            "training_time_sec": round(elapsed, 2)
        }
        print(f" -> {name:26}: R2 = {r2:.4f} | RMSE = {rmse:.3f} ug/m3 | MAE = {mae:.3f} ug/m3 ({elapsed:.2f}s)")

        if r2 > best_score:
            best_score = r2
            best_name = name
            best_model = model

    print(f"\nOptimal Model Selected: {best_name} (R2 = {best_score:.4f})")

    # Feature Importances
    feature_importances = {}
    if hasattr(best_model, "feature_importances_"):
        for col, imp in zip(FEATURE_COLS, best_model.feature_importances_):
            feature_importances[col] = round(float(imp), 4)
        # Sort desc
        feature_importances = dict(sorted(feature_importances.items(), key=lambda item: item[1], reverse=True))

    # Serialize Best Model and Scaler
    print(f"Serializing best model to: {MODEL_OUTPUT_PATH}")
    joblib.dump(best_model, MODEL_OUTPUT_PATH)
    joblib.dump(scaler, SCALER_OUTPUT_PATH)

    metrics_data = {
        "model_name": best_name,
        "selected_at": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "target_variable": TARGET_COL,
        "features": FEATURE_COLS,
        "best_metrics": results[best_name],
        "all_candidate_metrics": results,
        "feature_importances": feature_importances,
        "dataset_summary": {
            "total_samples": int(df.shape[0]),
            "pm25_min": float(df[TARGET_COL].min()),
            "pm25_max": float(df[TARGET_COL].max()),
            "pm25_mean": round(float(df[TARGET_COL].mean()), 2)
        }
    }

    with open(METRICS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    print(f"Training metrics and feature weights saved to: {METRICS_OUTPUT_PATH}")
    return metrics_data

if __name__ == "__main__":
    train_and_evaluate()

