"""
NASA FIRMS Ingestion Service
Coordinates data retrieval, parsing, spatial association, classification,
deduplication, event clustering, and status telemetry.
"""

import time
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .config import FirmsConfig
from .client import NasaFirmsClient
from .parser import parse_firms_csv
from .normalizer import normalize_observation
from .classifier import classify_fire_observation, haversine_km
from .schemas import SyncSummary, ProviderStatusResponse
from .exceptions import FirmsAuthenticationError

from backend import database

try:
    from backend.security import redact_secrets
except ImportError:  # pragma: no cover - supports flat/direct imports
    from security import redact_secrets

logger = logging.getLogger("agri_smoke.firms.service")


class FirmsIngestionService:
    def __init__(self, config: Optional[FirmsConfig] = None):
        self.config = config or FirmsConfig()
        self.client = NasaFirmsClient(self.config)

    def _find_matching_district(self, lat: float, lon: float, districts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Matches coordinates to nearest district within a 35 km proximity threshold.
        """
        best_match = None
        min_distance = 35.0  # km threshold

        for d in districts:
            c_lat = d.get("center_lat")
            c_lon = d.get("center_lon")
            if c_lat is None or c_lon is None:
                continue

            dist = haversine_km(lat, lon, float(c_lat), float(c_lon))
            if dist < min_distance:
                min_distance = dist
                best_match = d

        return best_match

    def cluster_events(self, observations: List[Dict[str, Any]], radius_km: float = 3.5) -> List[Dict[str, Any]]:
        """
        Simple spatiotemporal single-linkage clustering.
        Clusters observations occurring close in space (<= radius_km) and time (same date).
        """
        if not observations:
            return []

        clusters: List[List[Dict[str, Any]]] = []

        for obs in observations:
            lat = obs["latitude"]
            lon = obs["longitude"]
            acq_date = obs["acq_date"]

            matched_cluster = None
            for cl in clusters:
                # Compare to first item or centroid
                first = cl[0]
                if first["acq_date"] == acq_date:
                    d = haversine_km(lat, lon, first["latitude"], first["longitude"])
                    if d <= radius_km:
                        matched_cluster = cl
                        break

            if matched_cluster is not None:
                matched_cluster.append(obs)
            else:
                clusters.append([obs])

        events = []
        for idx, cl in enumerate(clusters):
            count = len(cl)
            total_frp = sum(float(o.get("frp", 0.0) or 0.0) for o in cl)
            max_frp = max(float(o.get("frp", 0.0) or 0.0) for o in cl)
            avg_lat = sum(o["latitude"] for o in cl) / count
            avg_lon = sum(o["longitude"] for o in cl) / count

            times = sorted(o["acquisition_timestamp"] for o in cl)
            first_seen = times[0]
            last_seen = times[-1]

            # Approximate duration
            duration = 1.0
            try:
                t1 = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                duration = max(0.5, (t2 - t1).total_seconds() / 3600.0)
            except Exception:
                pass

            # Primary classification
            agri_count = sum(1 for o in cl if o.get("classification") == "agricultural")
            dominant_class = "agricultural" if agri_count >= count / 2 else cl[0].get("classification", "unclassified")
            district_id = cl[0].get("district_id")
            state = cl[0].get("state")

            # Estimated smoke emission: approx 0.02 tons PM2.5 per MW-hour of FRP
            smoke_tons = round(total_frp * duration * 0.02, 2)

            event_id = f"EVT-{cl[0]['acq_date'].replace('-', '')}-{idx+1:04d}"
            events.append({
                "id": event_id,
                "cluster_label": f"Cluster-{district_id or 'NCR'}-{idx+1}",
                "state": state or "Punjab",
                "district": district_id or "Regional",
                "district_id": district_id or "Regional",
                "centroid_lat": round(avg_lat, 4),
                "centroid_lon": round(avg_lon, 4),
                "observation_count": count,
                "total_frp": round(total_frp, 2),
                "max_frp": round(max_frp, 2),
                "first_seen": first_seen,
                "last_seen": last_seen,
                "duration_hours": round(duration, 1),
                "classification": dominant_class,
                "classification_confidence": 0.85 if dominant_class == "agricultural" else 0.60,
                "estimated_smoke_emission_tons": smoke_tons
            })

        return events

    def ingest_observations(
        self,
        sensor: Optional[str] = None,
        region_name: str = "indo_gangetic_airshed",
        day_range: Optional[int] = None,
        date: Optional[str] = None,
        raw_csv_override: Optional[str] = None
    ) -> SyncSummary:
        """
        Executes a full ingestion cycle from NASA FIRMS Area API into SQLite.
        """
        start_time = time.time()
        active_sensor = sensor or self.config.default_sensor
        target_coords = self.config.get_bounding_box(region_name)
        active_day_range = day_range or self.config.day_range

        logger.info(f"Starting NASA FIRMS ingestion: sensor={active_sensor}, region={region_name}, range={active_day_range}")

        try:
            # 1. Fetch CSV
            if raw_csv_override is not None:
                csv_data = raw_csv_override
            else:
                csv_data = self.client.get_area_observations_csv(
                    sensor=active_sensor,
                    coords=target_coords,
                    day_range=active_day_range,
                    date=date
                )

            # 2. Parse CSV
            raw_rows, rejected_count = parse_firms_csv(csv_data)
            records_received = len(raw_rows)

            # 3. Load District Metadata for Spatial Context
            districts = database.get_districts()

            # 4. Normalize & Classify Each Row
            normalized_list: List[Dict[str, Any]] = []
            for row in raw_rows:
                obs = normalize_observation(row, source_dataset=active_sensor)
                
                # Spatial matching
                dist = self._find_matching_district(obs["latitude"], obs["longitude"], districts)
                if dist:
                    obs["district"] = dist["name"]
                    obs["district_id"] = dist["name"]
                    obs["state"] = dist["state"]
                else:
                    obs["district"] = "Regional Airshed"
                    obs["district_id"] = "Regional Airshed"
                    obs["state"] = "North India"

                # Agricultural classification
                clf_result = classify_fire_observation(obs, dist)
                obs["classification"] = clf_result["classification"]
                obs["classification_confidence"] = clf_result["classification_confidence"]
                obs["classification_evidence"] = clf_result["classification_evidence"]

                normalized_list.append(obs)

            # 5. Persist Observations with Deduplication
            db_res = database.insert_fire_observations(normalized_list)
            records_inserted = db_res["inserted"]
            records_skipped = db_res["skipped"]

            # 6. Spatiotemporal Clustering
            if normalized_list:
                events = self.cluster_events(normalized_list)
                database.save_fire_events(events)

                # Generate automated alerts for intense thermal clusters
                for ev in events:
                    if float(ev.get("total_frp", 0.0)) >= 100.0:
                        database.insert_alert_record({
                            "id": f"ALT-{ev['id']}",
                            "category": "extreme_frp_cluster",
                            "severity": "CRITICAL" if float(ev.get("total_frp", 0.0)) >= 200.0 else "WARNING",
                            "title": f"High-Intensity Fire Cluster in {ev.get('district')}",
                            "message": f"Thermal cluster of {ev.get('observation_count')} fires generating {ev.get('total_frp')} MW total FRP detected by {active_sensor}.",
                            "state": ev.get("state"),
                            "district": ev.get("district"),
                            "trigger_condition": f"total_frp >= 100 MW (detected: {ev.get('total_frp')} MW)"
                        })

            duration_ms = int((time.time() - start_time) * 1000)

            # Determine latest acquisition timestamp
            latest_ts = None
            if normalized_list:
                latest_ts = max(o["acquisition_timestamp"] for o in normalized_list)

            # 7. Record Sync Job
            job_id = database.record_sync_job(
                provider_id="nasa_firms",
                status="SUCCESS",
                records_received=records_received,
                records_inserted=records_inserted,
                records_skipped=records_skipped,
                records_rejected=rejected_count,
                execution_duration_ms=duration_ms,
                request_params=f"sensor={active_sensor};region={region_name};range={active_day_range};date={date or 'latest'}"
            )

            # 8. Update Provider Status
            database.update_data_provider_status(
                provider_id="nasa_firms",
                status="ONLINE",
                is_healthy=True,
                records_ingested_delta=records_inserted,
                latest_data_timestamp=latest_ts,
                details={
                    "last_sensor": active_sensor,
                    "last_region": region_name,
                    "records_received": records_received,
                    "records_inserted": records_inserted,
                    "records_skipped": records_skipped,
                    "last_sync_duration_ms": duration_ms
                }
            )

            msg = f"Synced {records_received} records ({records_inserted} new, {records_skipped} duplicate) in {duration_ms}ms"
            logger.info(msg)

            return SyncSummary(
                job_id=job_id,
                status="SUCCESS",
                sensor=active_sensor,
                region=region_name,
                records_received=records_received,
                records_inserted=records_inserted,
                records_skipped=records_skipped,
                records_rejected=rejected_count,
                duration_ms=duration_ms,
                message=msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            # Redact the MAP_KEY / any credential-bearing URL from BOTH the message
            # we persist and the traceback we log. The underlying requests exception
            # can echo the full FIRMS URL (which contains the key in its path).
            err_msg = redact_secrets(str(e), [self.config.map_key])
            logger.error(
                "NASA FIRMS ingestion failed:\n%s",
                redact_secrets(traceback.format_exc(), [self.config.map_key]),
            )

            job_id = database.record_sync_job(
                provider_id="nasa_firms",
                status="FAILED",
                records_received=0,
                records_inserted=0,
                records_skipped=0,
                records_rejected=0,
                execution_duration_ms=duration_ms,
                request_params=f"sensor={active_sensor};region={region_name}",
                error_message=err_msg
            )

            status_str = "UNCONFIGURED" if isinstance(e, FirmsAuthenticationError) else "ERROR"
            database.update_data_provider_status(
                provider_id="nasa_firms",
                status=status_str,
                is_healthy=False,
                error_message=err_msg
            )

            return SyncSummary(
                job_id=job_id,
                status="FAILED",
                sensor=active_sensor,
                region=region_name,
                records_received=0,
                records_inserted=0,
                records_skipped=0,
                records_rejected=0,
                duration_ms=duration_ms,
                message=err_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

    def get_provider_status(self) -> ProviderStatusResponse:
        """Retrieves unified status of NASA FIRMS provider."""
        raw_status = database.get_data_provider_status("nasa_firms")
        return ProviderStatusResponse(
            provider_id="nasa_firms",
            provider_name="NASA FIRMS (Earthdata)",
            is_healthy=bool(raw_status.get("is_healthy", 0)),
            status=raw_status.get("status", "UNCONFIGURED"),
            configured=self.config.is_configured,
            masked_key=self.config.masked_map_key,
            default_sensor=self.config.default_sensor,
            last_sync_timestamp=raw_status.get("last_sync_timestamp"),
            latest_data_timestamp=raw_status.get("latest_data_timestamp"),
            total_records_ingested=raw_status.get("total_records_ingested", 0),
            consecutive_failures=raw_status.get("consecutive_failures", 0),
            last_error_message=redact_secrets(raw_status.get("last_error_message"), [self.config.map_key]),
            details=raw_status.get("details")
        )
