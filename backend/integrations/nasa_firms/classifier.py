"""
AgriSmoke AI - Agricultural Fire Classification Engine
Scientifically attributes satellite thermal anomalies to agricultural residue burning,
forest fires, industrial sources, or unclassified heat anomalies.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger("agri_smoke.firms.classifier")

# Known Industrial & Power Plant Clusters in NCR & Punjab (Lat, Lon, Radius_km, Name)
KNOWN_INDUSTRIAL_ZONES = [
    {"name": "Panipat Refinery & Petrochem", "lat": 29.46, "lon": 76.92, "radius_km": 6.0},
    {"name": "Guru Gobind Singh Refinery, Bathinda", "lat": 30.01, "lon": 74.88, "radius_km": 5.0},
    {"name": "NTPC Dadri Power Plant", "lat": 28.59, "lon": 77.60, "radius_km": 4.0},
    {"name": "Faridabad Industrial Sector", "lat": 28.38, "lon": 77.31, "radius_km": 5.0},
    {"name": "Ghaziabad Industrial Zone", "lat": 28.67, "lon": 77.44, "radius_km": 5.0},
    {"name": "Ludhiana Heavy Machinery & Steel", "lat": 30.88, "lon": 75.89, "radius_km": 4.0},
]

# Shivalik & Aravalli Forest Polygons (rough bounding boxes)
FOREST_BELTS = [
    # Shivalik foothills (North-East Punjab / HP border)
    {"name": "Shivalik Belt", "min_lat": 31.8, "max_lat": 32.5, "min_lon": 75.6, "max_lon": 76.5},
    # Aravalli Ridge (Rajasthan / Haryana border)
    {"name": "Aravalli Forest Ridge", "min_lat": 27.5, "max_lat": 28.2, "min_lon": 76.2, "max_lon": 77.0},
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates approximate distance between two GPS coordinates in kilometers."""
    import math
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def evaluate_crop_season(acq_date_str: str) -> Tuple[bool, str, float]:
    """
    Evaluates whether the observation date falls within standard Northern Indian crop stubble seasons.
    
    Returns:
        (is_in_season, season_name, season_weight)
    """
    try:
        dt = datetime.strptime(acq_date_str, "%Y-%m-%d")
        month = dt.month
        day = dt.day

        # Kharif (Paddy/Parali) Burning Window: Oct 1 - Nov 30 (Peak: Oct 15 - Nov 20)
        if month == 10 and day >= 10:
            return True, "Kharif Paddy Stubble (Early/Peak)", 0.95
        elif month == 11:
            return True, "Kharif Paddy Stubble (Peak/Late)", 0.95
        elif month == 10 and day < 10:
            return True, "Kharif Early Harvest", 0.70
        elif month == 12 and day <= 15:
            return True, "Kharif Post-Harvest Residual", 0.60

        # Rabi (Wheat) Burning Window: Apr 15 - May 25
        elif month == 4 and day >= 15:
            return True, "Rabi Wheat Residue", 0.85
        elif month == 5 and day <= 25:
            return True, "Rabi Wheat Residue", 0.85

        # Off-season (Monsoon / Deep Winter)
        elif month in (6, 7, 8, 9):
            return False, "Monsoon Growing Season (Non-Stubble)", 0.10
        else:
            return False, "Off-Season / Winter Fallow", 0.30
    except Exception:
        return False, "Unknown Date Format", 0.50


def classify_fire_observation(obs: Dict[str, Any], district_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Evaluates satellite observation attributes against spatial, temporal,
    spectral (FRP), and land-use criteria.
    
    Returns:
        {
            "classification": str,
            "classification_confidence": float,
            "classification_evidence": str (JSON string)
        }
    """
    lat = float(obs["latitude"])
    lon = float(obs["longitude"])
    frp = float(obs.get("frp", 0.0) or 0.0)
    conf_norm = float(obs.get("confidence_normalized", 0.5) or 0.5)
    acq_date = obs.get("acq_date", "")

    evidence: Dict[str, Any] = {
        "rules_version": "v2.0-spatial-temporal",
        "evaluations": []
    }

    # 1. Check Proximity to Known Industrial Heat Sources
    for ind in KNOWN_INDUSTRIAL_ZONES:
        dist = haversine_km(lat, lon, ind["lat"], ind["lon"])
        if dist <= ind["radius_km"]:
            evidence["evaluations"].append(f"Within {dist:.1f}km of {ind['name']}")
            evidence["category"] = "industrial_match"
            return {
                "classification": "industrial",
                "classification_confidence": 0.88,
                "classification_evidence": json.dumps(evidence)
            }

    # 2. Check Forest Belts
    for f in FOREST_BELTS:
        if f["min_lat"] <= lat <= f["max_lat"] and f["min_lon"] <= lon <= f["max_lon"]:
            evidence["evaluations"].append(f"Located inside designated {f['name']}")
            return {
                "classification": "forest_vegetation",
                "classification_confidence": 0.82,
                "classification_evidence": json.dumps(evidence)
            }

    # 3. Evaluate Seasonal Agricultural Window
    in_season, season_name, season_weight = evaluate_crop_season(acq_date)
    evidence["crop_calendar_window"] = season_name
    evidence["season_weight"] = season_weight

    # 4. District Agrarian Context
    is_agrarian_district = False
    dominant_crop = "Unknown"
    if district_meta:
        dominant_crop = district_meta.get("dominant_crop", "Agriculture")
        is_agrarian_district = bool(district_meta.get("stubble_risk_level") in ("HIGH", "CRITICAL", "MODERATE"))
        evidence["district_context"] = f"{district_meta.get('name')} ({dominant_crop}, Risk: {district_meta.get('stubble_risk_level')})"

    # 5. FRP and Confidence Scoring for Stubble Burning
    # Agricultural open burning characteristics:
    # - Moderate FRP: 5MW to 120MW (higher can be extreme field fires, lower can be faint smoldering)
    # - Occurs during crop harvest windows
    # - High or nominal satellite confidence
    score = 0.0
    reasons = []

    if in_season:
        score += 0.40 * season_weight
        reasons.append(f"Active harvesting season ({season_name})")
    else:
        score -= 0.25
        reasons.append("Outside documented crop burning season")

    if is_agrarian_district:
        score += 0.30
        reasons.append(f"Located in intense agricultural zone ({dominant_crop})")

    if 5.0 <= frp <= 150.0:
        score += 0.20
        reasons.append(f"FRP {frp:.1f} MW within typical open agricultural burning range (5-150 MW)")
    elif frp > 150.0:
        score += 0.10
        reasons.append(f"FRP {frp:.1f} MW indicates very intense thermal event")
    else:
        score += 0.05
        reasons.append(f"Low FRP {frp:.1f} MW indicates faint or smoldering anomaly")

    # Satellite confidence bonus
    score += (conf_norm * 0.10)
    reasons.append(f"Satellite detection confidence: {conf_norm:.2f}")

    evidence["evaluations"] = reasons

    final_confidence = max(0.10, min(0.98, round(score, 2)))

    if final_confidence >= 0.60:
        classification = "agricultural"
    elif final_confidence >= 0.40:
        classification = "requires_verification"
    elif not in_season and frp < 5.0:
        classification = "other_vegetation"
    else:
        classification = "unclassified"

    return {
        "classification": classification,
        "classification_confidence": final_confidence,
        "classification_evidence": json.dumps(evidence)
    }
