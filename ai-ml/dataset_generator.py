"""
AgriSmoke AI - Atmospheric Dataset Generator
Generates physically calibrated synthetic-empirical observations representing
the Indo-Gangetic airshed post-monsoon crop-burning seasons (Punjab/Haryana to Delhi-NCR).
"""

import numpy as np
import pandas as pd
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "training_data.csv"

def generate_atmospheric_dataset(n_samples=6500, random_seed=42):
    np.random.seed(random_seed)
    
    print(f"Generating {n_samples} calibrated atmospheric & stubble observation samples...")
    
    # 1. Base independent variables
    # Farm fires (peak burning season reaches 3,000-5,000; early/late season is low)
    fire_count = np.random.choice([
        np.random.randint(0, 300),      # Low / pre-harvest
        np.random.randint(300, 1500),   # Moderate burning
        np.random.randint(1500, 3500),  # Heavy burning
        np.random.randint(3500, 5200)   # Severe peak burning
    ], size=n_samples)

    # Wind speed in km/h (typical winter post-monsoon: 4 to 22 km/h)
    wind_speed = np.random.uniform(2.0, 32.0, size=n_samples)

    # Wind direction in degrees (0-360)
    # Higher probability around 290-330 deg (prevailing North-Westerly winter regime)
    is_prevailing_nw = np.random.rand(n_samples) < 0.65
    wind_dir = np.where(
        is_prevailing_nw,
        np.random.normal(312, 22, size=n_samples) % 360,
        np.random.uniform(0, 360, size=n_samples)
    )

    # Planetary Boundary Layer (PBL) mixing height in meters (150m night inversion to 1400m afternoon)
    pbl_height = np.random.choice([
        np.random.randint(150, 350),   # Severe nocturnal inversion
        np.random.randint(350, 650),   # Normal autumn mixing
        np.random.randint(650, 1300)   # Convective afternoon mixing
    ], size=n_samples)

    # Urban internal baseline AQI (Delhi's internal vehicular/industrial load)
    urban_baseline_aqi = np.random.uniform(50.0, 260.0, size=n_samples)

    # Policy mitigation variables (0 to 100%)
    bio_decomposer_adoption = np.random.uniform(0.0, 100.0, size=n_samples)
    happy_seeder_adoption = np.random.uniform(0.0, 100.0, size=n_samples)

    # Meteorological covariates
    temperature = np.random.uniform(14.0, 32.0, size=n_samples)
    humidity = np.random.uniform(30.0, 85.0, size=n_samples)

    # 2. Physics-inspired engineered features
    # Mitigation efficiency
    mitigation_factor = np.clip((bio_decomposer_adoption * 0.45 + happy_seeder_adoption * 0.55) / 100.0, 0.0, 0.92)
    effective_fires = fire_count * (1.0 - mitigation_factor)

    # Directional alignment to Delhi (Bearing 312 deg NW)
    delta_deg = np.abs(wind_dir - 312.0)
    delta_deg = np.where(delta_deg > 180.0, 360.0 - delta_deg, delta_deg)
    rad = np.radians(delta_deg)
    cos_val = np.cos(rad)
    dir_alignment = np.where(cos_val < 0, np.maximum(0.04, 0.05 + cos_val * 0.03), np.maximum(0.05, np.power(cos_val, 1.8)))

    # Wind transport & dilution coefficient
    wind_coeff = np.where(
        wind_speed < 5.0,
        0.55 + (wind_speed / 5.0) * 0.25,
        np.where(
            wind_speed <= 18.0,
            0.80 + ((wind_speed - 5.0) / 13.0) * 0.35,
            np.maximum(0.40, 1.15 - ((wind_speed - 18.0) / 25.0) * 0.70)
        )
    )

    # Atmospheric Inversion Trapping Multiplier
    inversion_multiplier = np.power(800.0 / np.maximum(100.0, pbl_height), 0.75)

    # Ventilation index (wind_speed * pbl_height)
    ventilation_index = (wind_speed * 1000.0 / 3600.0) * pbl_height # m^2/s

    # 3. Ground Truth Target Generation with Realistic Atmospheric Stochastic Noise
    stubble_pm25 = (effective_fires * 0.082) * dir_alignment * wind_coeff * inversion_multiplier
    # Natural observational variance (+- 7%)
    stubble_pm25 += np.random.normal(0, np.maximum(1.0, stubble_pm25 * 0.07))
    stubble_pm25 = np.maximum(0.0, np.round(stubble_pm25, 2))

    # Approximate baseline PM2.5 from baseline AQI
    urban_baseline_pm25 = np.where(
        urban_baseline_aqi <= 50, urban_baseline_aqi * 0.6,
        np.where(
            urban_baseline_aqi <= 100, 30.0 + (urban_baseline_aqi - 50.0) * 0.6,
            np.where(
                urban_baseline_aqi <= 200, 60.0 + (urban_baseline_aqi - 100.0) * 0.3,
                np.where(
                    urban_baseline_aqi <= 300, 90.0 + (urban_baseline_aqi - 200.0) * 0.3,
                    120.0 + (urban_baseline_aqi - 300.0) * 0.85
                )
            )
        )
    )
    urban_baseline_pm25 += np.random.normal(0, 3.5, size=n_samples)
    urban_baseline_pm25 = np.maximum(15.0, np.round(urban_baseline_pm25, 2))

    total_pm25 = np.round(urban_baseline_pm25 + stubble_pm25, 2)
    total_pm10 = np.round(total_pm25 * 1.68 + np.random.normal(0, 8.0, size=n_samples), 2)
    parali_pct = np.where(total_pm25 > 0, np.clip(np.round((stubble_pm25 / total_pm25) * 100.0, 1), 0.0, 85.0), 0.0)

    # Construct DataFrame
    df = pd.DataFrame({
        "fire_count": fire_count,
        "wind_speed": np.round(wind_speed, 2),
        "wind_direction_deg": np.round(wind_dir, 1),
        "pbl_height": pbl_height,
        "urban_baseline_aqi": np.round(urban_baseline_aqi, 1),
        "bio_decomposer_adoption": np.round(bio_decomposer_adoption, 1),
        "happy_seeder_adoption": np.round(happy_seeder_adoption, 1),
        "temperature": np.round(temperature, 1),
        "humidity": np.round(humidity, 1),
        # Engineered features
        "effective_fires": np.round(effective_fires, 1),
        "dir_alignment": np.round(dir_alignment, 4),
        "wind_coeff": np.round(wind_coeff, 4),
        "inversion_multiplier": np.round(inversion_multiplier, 3),
        "ventilation_index": np.round(ventilation_index, 2),
        # Target variables
        "stubble_pm25": stubble_pm25,
        "urban_baseline_pm25": urban_baseline_pm25,
        "total_pm25": total_pm25,
        "total_pm10": total_pm10,
        "parali_pct": parali_pct
    })

    df.to_csv(DATA_PATH, index=False)
    print(f"Dataset successfully created and saved to: {DATA_PATH}")
    print(f"Dataset Shape: {df.shape}")
    print(df.head(3))
    return df

if __name__ == "__main__":
    generate_atmospheric_dataset()

