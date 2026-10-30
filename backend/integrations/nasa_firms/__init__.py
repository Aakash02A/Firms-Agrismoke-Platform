"""
AgriSmoke AI - NASA FIRMS Integration Package
Production-grade ingestion, normalization, agricultural classification,
and persistence of NASA satellite thermal anomaly observations.
"""

from .config import FirmsConfig
from .client import NasaFirmsClient
from .service import FirmsIngestionService

__all__ = ["FirmsConfig", "NasaFirmsClient", "FirmsIngestionService"]
