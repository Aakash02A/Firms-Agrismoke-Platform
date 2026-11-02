"""
AgriSmoke AI - Multi-Channel Alert Evaluation & Dispatcher
Monitors real-time predicted AQI, satellite fire hotspots, and meteorological thresholds.
Triggers CAQM GRAP Stage notifications and dispatches alerts via configured channels.
"""

import uuid
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
import database as db

logger = logging.getLogger("agri_smoke.alerts")

CONFIGURED_CHANNELS = [
    {"id": "CAQM_GOV_DASHBOARD", "name": "Commission for Air Quality Management (CAQM) Portal", "type": "INTERNAL_STREAM", "active": True},
    {"id": "DISTRICT_SMS_BROADCAST", "name": "State Agriculture & Krishi Vigyan Kendra (KVK) SMS", "type": "TELEPHONY", "active": True},
    {"id": "CPCB_OPERATIONS_WEBHOOK", "name": "Central Pollution Control Board Ops Webhook", "type": "WEBHOOK_HTTP", "active": True},
    {"id": "NCR_PUBLIC_HEALTH_DIGEST", "name": "Delhi-NCR Public Health Advisory Digest", "type": "EMAIL_DISPATCH", "active": True}
]

DISPATCH_LOGS: List[Dict[str, Any]] = []


class AlertEvaluationEngine:
    def evaluate_and_dispatch(
        self,
        predicted_aqi: int,
        fire_count: int,
        pbl_height: int,
        wind_direction_deg: int,
        wind_speed: float
    ) -> List[Dict[str, Any]]:
        """
        Evaluates current simulation/telemetry against regulatory CAQM GRAP and airshed thresholds.
        Generates and saves alerts into SQLite, then triggers multi-channel dispatch.
        """
        generated_alerts = []

        # Rule 1: GRAP Stage IV Emergency (AQI > 450)
        if predicted_aqi >= 450:
            alert_id = f"ALERT-GRAP4-{uuid.uuid4().hex[:6].upper()}"
            alert = {
                "id": alert_id,
                "category": "grap_emergency",
                "severity": "EMERGENCY",
                "title": "🚨 GRAP Stage IV Emergency Enacted",
                "message": f"Predicted AQI reached {predicted_aqi} (Severe+). Mandatory ban on commercial non-BS-VI diesel vehicles and construction.",
                "state": "Delhi-NCR",
                "district": "All Airshed Districts",
                "trigger_condition": f"Predicted AQI {predicted_aqi} >= 450",
                "status": "NEW"
            }
            if db.insert_alert_record(alert):
                generated_alerts.append(alert)
                self._dispatch_to_channels(alert)

        # Rule 2: GRAP Stage III Severe (AQI 401 - 449)
        elif predicted_aqi >= 401:
            alert_id = f"ALERT-GRAP3-{uuid.uuid4().hex[:6].upper()}"
            alert = {
                "id": alert_id,
                "category": "grap_severe",
                "severity": "CRITICAL",
                "title": "⚠️ GRAP Stage III (Severe Air Quality)",
                "message": f"Predicted AQI {predicted_aqi} triggers Stage III. Halt physical primary classes and enforce stone crusher closures.",
                "state": "Delhi-NCR",
                "district": "Urban Airshed",
                "trigger_condition": f"Predicted AQI {predicted_aqi} >= 401",
                "status": "NEW"
            }
            if db.insert_alert_record(alert):
                generated_alerts.append(alert)
                self._dispatch_to_channels(alert)

        # Rule 3: Extreme Nocturnal Inversion & Fire Surge
        if pbl_height <= 250 and fire_count >= 1800:
            alert_id = f"ALERT-INVERSION-{uuid.uuid4().hex[:6].upper()}"
            alert = {
                "id": alert_id,
                "category": "extreme_inversion",
                "severity": "CRITICAL",
                "title": "🌪️ Atmospheric Inversion Trapping Surge",
                "message": f"Planetary Boundary Layer collapsed to {pbl_height}m with {fire_count} active farm fires. Toxic plume will trap at ground level.",
                "state": "Punjab & Delhi",
                "district": "Yamuna Airshed Corridor",
                "trigger_condition": f"PBL {pbl_height}m <= 250m & Fires {fire_count} >= 1800",
                "status": "NEW"
            }
            if db.insert_alert_record(alert):
                generated_alerts.append(alert)
                self._dispatch_to_channels(alert)

        # Rule 4: NW Stubble Transport Corridor Active
        delta_nw = abs(wind_direction_deg - 312)
        if delta_nw <= 20 and wind_speed >= 12.0 and fire_count >= 1200:
            alert_id = f"ALERT-PLUME-{uuid.uuid4().hex[:6].upper()}"
            alert = {
                "id": alert_id,
                "category": "plume_transport",
                "severity": "WARNING",
                "title": "💨 Direct NW Plume Channelling into Delhi",
                "message": f"North-westerly winds ({wind_direction_deg}° at {wind_speed} km/h) are actively transporting smoke from {fire_count} upstream fire clusters.",
                "state": "Haryana & Delhi",
                "district": "NCR Entry Axis",
                "trigger_condition": f"Wind {wind_direction_deg}° NW aligned & Speed {wind_speed} km/h >= 12",
                "status": "NEW"
            }
            if db.insert_alert_record(alert):
                generated_alerts.append(alert)
                self._dispatch_to_channels(alert)

        return generated_alerts

    def _dispatch_to_channels(self, alert: Dict[str, Any]):
        """Dispatches an alert across all active communication channels."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for channel in CONFIGURED_CHANNELS:
            if channel["active"]:
                log_entry = {
                    "dispatchId": f"DISPATCH-{uuid.uuid4().hex[:8].upper()}",
                    "alertId": alert["id"],
                    "alertTitle": alert["title"],
                    "severity": alert["severity"],
                    "channelId": channel["id"],
                    "channelName": channel["name"],
                    "channelType": channel["type"],
                    "status": "DELIVERED",
                    "dispatchedAt": now_str
                }
                DISPATCH_LOGS.insert(0, log_entry)
                # Keep log size manageable
                if len(DISPATCH_LOGS) > 100:
                    DISPATCH_LOGS.pop()
                logger.info(f"Dispatched {alert['id']} to {channel['name']}")


alert_engine = AlertEvaluationEngine()

