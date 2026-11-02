"""
NASA FIRMS Normalizer
Standardizes VIIRS/MODIS observations into normalized database records with SHA-256 IDs.
"""

import hashlib
import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("agri_smoke.firms.normalizer")


def generate_observation_id(source_dataset: str, lat: float, lon: float, acq_date: str, acq_time: str) -> str:
    """
    Creates a deterministic 24-character SHA-256 hash representing a unique fire observation.
    Prevents duplicates even across repeated sync requests.
    """
    raw_key = f"{source_dataset}:{lat:.4f}:{lon:.4f}:{acq_date}:{acq_time.zfill(4)}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]


def parse_acquisition_timestamp(acq_date: str, acq_time: str) -> str:
    """
    Combines NASA acq_date (YYYY-MM-DD) and acq_time (HHMM or HMM) into ISO-8601 UTC string.
    Example: '2026-10-29', '815' -> '2026-10-29T08:15:00Z'
    """
    time_clean = acq_time.strip().zfill(4)
    hour = int(time_clean[:2])
    minute = int(time_clean[2:4])
    # Safeguard hour and minute bounds
    hour = min(23, max(0, hour))
    minute = min(59, max(0, minute))
    
    return f"{acq_date}T{hour:02d}:{minute:02d}:00Z"


def normalize_confidence(conf_raw: Optional[str], instrument: str) -> Tuple[Optional[str], float]:
    """
    Normalizes confidence to a float between 0.0 and 1.0.
    VIIRS uses: 'l' (low), 'n' (nominal), 'h' (high).
    MODIS uses integer 0-100.
    """
    if not conf_raw:
        return None, 0.5

    conf_clean = str(conf_raw).strip().lower()

    if conf_clean in ('l', 'low'):
        return conf_raw, 0.35
    elif conf_clean in ('n', 'nominal'):
        return conf_raw, 0.65
    elif conf_clean in ('h', 'high'):
        return conf_raw, 0.95
    else:
        try:
            val = float(conf_clean)
            normalized = max(0.0, min(1.0, val / 100.0 if val > 1.0 else val))
            return conf_raw, round(normalized, 3)
        except ValueError:
            return conf_raw, 0.5


def normalize_observation(raw_row: Dict[str, Any], source_dataset: str) -> Dict[str, Any]:
    """
    Transforms a raw parsed CSV row into a standardized observation dict ready for SQLite.
    """
    lat = float(raw_row["latitude"])
    lon = float(raw_row["longitude"])
    acq_date = raw_row["acq_date"]
    acq_time = str(raw_row["acq_time"]).strip().zfill(4)

    obs_id = generate_observation_id(source_dataset, lat, lon, acq_date, acq_time)
    acq_timestamp = parse_acquisition_timestamp(acq_date, acq_time)

    # Instrument detection
    instrument = raw_row.get("instrument") or ("VIIRS" if "VIIRS" in source_dataset else "MODIS")
    satellite = raw_row.get("satellite", "Unknown")

    # Confidence
    conf_raw, conf_norm = normalize_confidence(raw_row.get("confidence"), instrument)

    # Brightness temperature (VIIRS: bright_ti4, MODIS: brightness)
    brightness = None
    for key in ("bright_ti4", "brightness"):
        if raw_row.get(key):
            try:
                brightness = float(raw_row[key])
                break
            except (ValueError, TypeError):
                pass

    # Secondary brightness (VIIRS: bright_ti5, MODIS: bright_t31)
    bright_secondary = None
    for key in ("bright_ti5", "bright_t31"):
        if raw_row.get(key):
            try:
                bright_secondary = float(raw_row[key])
                break
            except (ValueError, TypeError):
                pass

    # Fire Radiative Power (FRP)
    frp = 0.0
    if raw_row.get("frp"):
        try:
            frp = max(0.0, float(raw_row["frp"]))
        except (ValueError, TypeError):
            frp = 0.0

    # Scan and Track
    scan = None
    if raw_row.get("scan"):
        try:
            scan = float(raw_row["scan"])
        except (ValueError, TypeError):
            pass

    track = None
    if raw_row.get("track"):
        try:
            track = float(raw_row["track"])
        except (ValueError, TypeError):
            pass

    day_night = raw_row.get("daynight", "D").upper()
    if day_night not in ("D", "N"):
        day_night = "D"

    version = raw_row.get("version")

    return {
        "id": obs_id,
        "source_provider": "nasa_firms",
        "source_dataset": source_dataset,
        "source_version": version,
        "latitude": lat,
        "longitude": lon,
        "brightness_temperature": brightness,
        "scan": scan,
        "track": track,
        "acquisition_timestamp": acq_timestamp,
        "acq_date": acq_date,
        "acq_time": acq_time,
        "satellite": satellite,
        "instrument": instrument,
        "confidence_raw": conf_raw,
        "confidence_normalized": conf_norm,
        "bright_ti5": bright_secondary,
        "frp": frp,
        "day_night": day_night,
        "district_id": None,
        "state": None,
        "classification": "unclassified",
        "classification_confidence": 0.5,
        "classification_evidence": None,
        "raw_payload": json.dumps(raw_row)
    }
