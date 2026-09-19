import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from app.schemas.sensor import SensorPayload
from app.schemas.inference import InferenceResult
from app.schemas.pipeline import (
    SensorHealth,
    AnomalyResult,
    ForecastResult,
    AdvisoryResult,
    PipelineResults,
)

logger = logging.getLogger(__name__)

class ModularPipeline:
    def __init__(self):
        # Bounded-memory state per node for EMA anomaly detection and forecasting
        # dict structure: node_id -> {"ema": {...}, "ema_var": {...}, "last_pm": {...}, "count": int}
        self.node_states: Dict[str, dict] = {}
        self.ema_alpha = 0.1

    def _get_or_create_state(self, node_id: str) -> dict:
        if node_id not in self.node_states:
            self.node_states[node_id] = {
                "ema": {},
                "ema_var": {},
                "last_pm": None,
                "count": 0
            }
        return self.node_states[node_id]

    def check_health(self, payload: SensorPayload) -> SensorHealth:
        """
        Evaluate payload quality and sensor health without inferring exact gas identities.
        """
        issues = []
        status = "ok"

        # 1. Stale check
        now = datetime.now(timezone.utc)
        payload_time = payload.timestamp.astimezone(timezone.utc) if payload.timestamp.tzinfo else payload.timestamp.replace(tzinfo=timezone.utc)
        delta = (now - payload_time).total_seconds()
        if delta > 3600:  # > 1 hour
            issues.append("Reading is stale (> 1 hour old)")
            status = "stale"

        # 2. Out of bounds / Railed checks
        # MQ sensors are typically 0-5V. Exactly 0 or exactly 5 often means disconnected/shorted.
        for sensor_name in ["MQ2", "MQ9", "MQ135"]:
            v = getattr(payload.gas_sensors, sensor_name).voltage_V
            if v <= 0.01:
                issues.append(f"{sensor_name} voltage suspiciously low (railed to GND)")
            elif v >= 4.99:
                issues.append(f"{sensor_name} voltage suspiciously high (railed to VCC)")

        # Temperature / Humidity limits
        t = payload.environment.temperature_C
        h = payload.environment.humidity_pct
        if t <= -35.0 or t >= 80.0:
            issues.append("Temperature near extreme hardware limits")
        if h <= 1.0 or h >= 99.0:
            issues.append("Humidity near extreme hardware limits")

        if issues and status == "ok":
            status = "degraded"

        return SensorHealth(status=status, issues=issues)

    def extract_features(self, payload: SensorPayload) -> dict:
        """
        Extract features with clear separation between raw and derived values.
        """
        return {
            "mq2_v": payload.gas_sensors.MQ2.voltage_V,
            "mq9_v": payload.gas_sensors.MQ9.voltage_V,
            "mq135_v": payload.gas_sensors.MQ135.voltage_V,
            "temp_c": payload.environment.temperature_C,
            "hum_pct": payload.environment.humidity_pct,
            "pm1_0": payload.particulate_matter.PM1_0,
            "pm2_5": payload.particulate_matter.PM2_5,
            "pm10": payload.particulate_matter.PM10,
        }

    def detect_anomalies(self, node_id: str, features: dict) -> AnomalyResult:
        """
        Lightweight online baseline and anomaly detector using EMA.
        Tracks PM and MQ voltages.
        """
        state = self._get_or_create_state(node_id)
        deviations = []

        track_keys = ["mq2_v", "mq9_v", "mq135_v", "pm2_5"]
        
        # If very first reading, initialize EMA and return normal
        if state["count"] == 0:
            for k in track_keys:
                state["ema"][k] = features[k]
                state["ema_var"][k] = 0.0
            return AnomalyResult(is_anomalous=False, deviations=[])

        alpha = self.ema_alpha
        for k in track_keys:
            val = features[k]
            ema = state["ema"][k]
            ema_var = state["ema_var"][k]
            
            # Check deviation before updating
            # We use a minimum standard deviation to avoid infinite sensitivity
            min_std = 0.1 if "mq" in k else 5.0
            std = max((ema_var) ** 0.5, min_std)
            
            # Anomaly if > 3 std deviations away
            if abs(val - ema) > 3 * std:
                deviations.append(f"{k} significantly deviated from baseline (val: {val:.2f}, base: {ema:.2f})")
                # Dampen the update during an anomaly so baseline doesn't jump too fast
                update_alpha = alpha * 0.1
            else:
                update_alpha = alpha

            # Update EMA
            diff = val - ema
            state["ema"][k] = ema + update_alpha * diff
            state["ema_var"][k] = (1 - update_alpha) * (ema_var + update_alpha * diff**2)

        return AnomalyResult(is_anomalous=len(deviations) > 0, deviations=deviations)

    def forecast_pm(self, node_id: str, features: dict, health: SensorHealth) -> ForecastResult:
        """
        Persistence-based PM forecast baseline.
        Only valid if sufficient history exists (count > 0) and sensor is not stale/invalid.
        """
        state = self._get_or_create_state(node_id)
        
        forecast = ForecastResult(pm2_5_persistence=None, pm10_persistence=None)
        
        # Only forecast if sensor is currently reasonably healthy
        if health.status in ["ok", "degraded"] and state["last_pm"] is not None:
            # We use the previous reading as the baseline prediction for the next period
            forecast.pm2_5_persistence = state["last_pm"]["pm2_5"]
            forecast.pm10_persistence = state["last_pm"]["pm10"]

        # Update last_pm for the next round
        state["last_pm"] = {
            "pm2_5": features["pm2_5"],
            "pm10": features["pm10"]
        }
        
        state["count"] += 1
        return forecast

    def generate_advisory(self, health: SensorHealth, anomaly: AnomalyResult, inference: InferenceResult, features: dict) -> AdvisoryResult:
        """
        Deterministic advisory engine combining verified measurements, sensor health, model outputs, and uncertainty.
        Avoids claiming regulatory AQI or exact gas identities.
        """
        messages = []
        level = "NORMAL"

        if health.status in ["stale", "invalid"]:
            return AdvisoryResult(level="MAINTENANCE", messages=["Sensor is offline, stale, or returning invalid data. Check hardware."])
        
        if health.status == "degraded":
            messages.extend(health.issues)
            level = "MAINTENANCE"
            
        # Add anomaly information
        if anomaly.is_anomalous:
            messages.append("Unusual environmental baseline shift detected.")
            if level == "NORMAL":
                level = "CAUTION"

        # Particulate matter advisory (using general qualitative terms, avoiding strict AQI)
        pm25 = features["pm2_5"]
        if pm25 > 150.0:
            messages.append("Elevated particulate matter (PM2.5) measured. Air quality may be significantly reduced.")
            level = "WARNING"
        elif pm25 > 50.0:
            messages.append("Moderate particulate matter (PM2.5) measured.")
            if level == "NORMAL":
                level = "CAUTION"

        # Model inference advisory
        if inference.status == "success" and inference.safety_status == "unsafe":
            # Determine if we trust the inference based on uncertainty
            # A highly uncertain "unsafe" prediction should not trigger a full warning.
            if inference.uncertainty and inference.uncertainty > 0.6:
                messages.append("Unusual gas profile detected, but classification confidence is low. Monitor conditions.")
                if level != "WARNING":
                    level = "CAUTION"
            else:
                messages.append("Hazardous environmental gas profile detected based on sensor models.")
                level = "WARNING"
                
        if level == "NORMAL" and not messages:
            messages.append("Environmental conditions appear normal and stable.")

        return AdvisoryResult(level=level, messages=messages)

    def process(self, payload: SensorPayload, inference: InferenceResult) -> PipelineResults:
        """
        Runs the full modular pipeline on a given payload.
        """
        node_id = payload.node_id
        
        health = self.check_health(payload)
        features = self.extract_features(payload)
        anomaly = self.detect_anomalies(node_id, features)
        forecast = self.forecast_pm(node_id, features, health)
        advisory = self.generate_advisory(health, anomaly, inference, features)

        return PipelineResults(
            health=health,
            anomaly=anomaly,
            forecast=forecast,
            advisory=advisory
        )
