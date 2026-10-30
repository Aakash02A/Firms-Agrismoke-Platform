"""
NASA FIRMS Schemas
Pydantic data models for raw input, normalized observations, and API responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class RawFireObservation(BaseModel):
    """Raw record directly parsed from NASA FIRMS Area CSV response."""
    latitude: float
    longitude: float
    brightness: Optional[float] = None
    bright_ti4: Optional[float] = None
    scan: Optional[float] = None
    track: Optional[float] = None
    acq_date: str
    acq_time: str
    satellite: str
    instrument: Optional[str] = None
    confidence: Optional[str] = None
    version: Optional[str] = None
    bright_ti5: Optional[float] = None
    bright_t31: Optional[float] = None
    frp: Optional[float] = None
    daynight: Optional[str] = None


class NormalizedFireObservation(BaseModel):
    """Clean, typed observation stored in SQLite and served to clients."""
    id: str
    source_provider: str = "nasa_firms"
    source_dataset: str
    source_version: Optional[str] = None
    latitude: float
    longitude: float
    brightness_temperature: Optional[float] = None
    scan: Optional[float] = None
    track: Optional[float] = None
    acquisition_timestamp: str
    acq_date: str
    acq_time: str
    satellite: str
    instrument: str
    confidence_raw: Optional[str] = None
    confidence_normalized: float = Field(ge=0.0, le=1.0)
    bright_ti5: Optional[float] = None
    frp: float = Field(ge=0.0)
    day_night: str
    district_id: Optional[str] = None
    state: Optional[str] = None
    classification: str = "unclassified"
    classification_confidence: float = 0.5
    classification_evidence: Optional[str] = None
    raw_payload: Optional[str] = None


class SyncRequest(BaseModel):
    sensor: Optional[str] = "VIIRS_NOAA20_NRT"
    region: Optional[str] = "indo_gangetic_airshed"
    day_range: Optional[int] = Field(default=3, ge=1, le=5)
    date: Optional[str] = None  # YYYY-MM-DD for historical queries


class SyncSummary(BaseModel):
    job_id: int
    status: str
    sensor: str
    region: str
    records_received: int
    records_inserted: int
    records_skipped: int
    records_rejected: int
    duration_ms: int
    message: str
    timestamp: str


class ProviderStatusResponse(BaseModel):
    provider_id: str
    provider_name: str
    is_healthy: bool
    status: str
    configured: bool
    masked_key: str
    default_sensor: str
    last_sync_timestamp: Optional[str] = None
    latest_data_timestamp: Optional[str] = None
    total_records_ingested: int = 0
    consecutive_failures: int = 0
    last_error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
