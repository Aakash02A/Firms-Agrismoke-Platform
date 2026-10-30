"""
NASA FIRMS CSV Parser
Robust parsing of VIIRS and MODIS CSV responses with schema flexibility and validation.
"""

import csv
import io
import logging
from typing import List, Dict, Any, Tuple
from .exceptions import FirmsParseError

logger = logging.getLogger("agri_smoke.firms.parser")


def parse_firms_csv(csv_content: str) -> Tuple[List[Dict[str, Any]], int]:
    """
    Parses NASA FIRMS Area API CSV output into a list of row dictionaries.
    
    Returns:
        (valid_rows, rejected_count)
    
    Raises:
        FirmsParseError: If the content is an error message, HTML, or completely unparseable.
    """
    if not csv_content or not csv_content.strip():
        return [], 0

    stripped = csv_content.strip()

    # Detect NASA plain text error messages
    if "Invalid MAP_KEY" in stripped or "Bad MAP_KEY" in stripped:
        raise FirmsParseError("NASA FIRMS returned: Invalid MAP_KEY")
    if "No data available" in stripped:
        return [], 0
    if stripped.startswith("<!DOCTYPE html") or stripped.startswith("<html"):
        raise FirmsParseError("NASA FIRMS returned an HTML error page instead of CSV data")

    # Clean BOM if present
    if stripped.startswith("\ufeff"):
        stripped = stripped[1:]

    reader = csv.DictReader(io.StringIO(stripped))
    if not reader.fieldnames:
        raise FirmsParseError("CSV contains no valid header")

    # Normalize header fieldnames (strip whitespace, lowercase)
    clean_fieldnames = [f.strip().lower() for f in reader.fieldnames if f]
    
    # Must have latitude, longitude, acq_date, acq_time
    required_cols = {"latitude", "longitude", "acq_date", "acq_time"}
    if not required_cols.issubset(clean_fieldnames):
        raise FirmsParseError(
            f"Missing required columns in CSV header. Required: {required_cols}, Found: {clean_fieldnames}"
        )

    valid_rows: List[Dict[str, Any]] = []
    rejected_count = 0

    for row_idx, row in enumerate(reader):
        try:
            # Map clean lowercase keys
            clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}

            lat_str = clean_row.get("latitude")
            lon_str = clean_row.get("longitude")
            if not lat_str or not lon_str:
                rejected_count += 1
                continue

            lat = float(lat_str)
            lon = float(lon_str)

            # Sanity check lat/lon
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                rejected_count += 1
                continue

            acq_date = clean_row.get("acq_date", "")
            acq_time = clean_row.get("acq_time", "")
            if not acq_date or not acq_time:
                rejected_count += 1
                continue

            valid_rows.append(clean_row)
        except (ValueError, TypeError) as ex:
            rejected_count += 1
            logger.debug(f"Row {row_idx} rejected during parsing: {ex}")

    return valid_rows, rejected_count
