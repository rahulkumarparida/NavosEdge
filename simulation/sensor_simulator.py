import math
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

try:
    from simulation.constants import (
        DEFAULT_SCENARIO,
        DEFAULT_SIM_NODE_ID,
        DEFAULT_SAMPLING_INTERVAL_SECONDS,
        ADC_VREF,
        ADC_MAX,
        SCENARIO_PROFILES,
        SCENARIO_ALIASES,
        SCENARIO_METADATA,
        DEFAULT_TIMELINE_START,
        SEASONAL_SEPT_TEMP_BASE,
        SEASONAL_NOV_TEMP_BASE,
        SEASONAL_SEPT_HUM_BASE,
        SEASONAL_NOV_HUM_BASE,
        SEASONAL_SEPT_PM25_BASE,
        SEASONAL_NOV_PM25_BASE,
        DIURNAL_TEMP_AMPLITUDE,
        DIURNAL_HUM_AMPLITUDE,
        DIURNAL_PEAK_SOLAR_HOUR,
        DIURNAL_LAG_HOURS,
        VALID_FAULT_TYPES,
        TEMP_MIN,
        TEMP_MAX,
        HUMIDITY_MIN,
        HUMIDITY_MAX,
        VOLTAGE_MIN,
        VOLTAGE_MAX,
    )
except ImportError:
    from constants import (
        DEFAULT_SCENARIO,
        DEFAULT_SIM_NODE_ID,
        DEFAULT_SAMPLING_INTERVAL_SECONDS,
        ADC_VREF,
        ADC_MAX,
        SCENARIO_PROFILES,
        SCENARIO_ALIASES,
        SCENARIO_METADATA,
        DEFAULT_TIMELINE_START,
        SEASONAL_SEPT_TEMP_BASE,
        SEASONAL_NOV_TEMP_BASE,
        SEASONAL_SEPT_HUM_BASE,
        SEASONAL_NOV_HUM_BASE,
        SEASONAL_SEPT_PM25_BASE,
        SEASONAL_NOV_PM25_BASE,
        DIURNAL_TEMP_AMPLITUDE,
        DIURNAL_HUM_AMPLITUDE,
        DIURNAL_PEAK_SOLAR_HOUR,
        DIURNAL_LAG_HOURS,
        VALID_FAULT_TYPES,
        TEMP_MIN,
        TEMP_MAX,
        HUMIDITY_MIN,
        HUMIDITY_MAX,
        VOLTAGE_MIN,
        VOLTAGE_MAX,
    )


class SensorSimulator:
    """
    Physically grounded, reproducible environmental sensor simulator.
    
    Generates telemetry for DHT22 (temperature, humidity), MPM10-CS (PM1.0, PM2.5, PM10),
    and MQ gas sensors (MQ2, MQ9, MQ135) with realistic diurnal cycles, seasonal trends
    (September through November), physical PM ratio constraints, and configurable faults.
    """

    def __init__(
        self,
        scenario: str = DEFAULT_SCENARIO,
        node_id: str = DEFAULT_SIM_NODE_ID,
        seed: Optional[int] = None,
        start_time: Optional[datetime] = None,
        sampling_interval_seconds: float = DEFAULT_SAMPLING_INTERVAL_SECONDS,
        enable_seasonal: bool = True,
        fault: Optional[str] = None,
        fault_target: Optional[str] = None,
        noise_scale: float = 1.0,
        custom_overrides: Optional[Dict[str, float]] = None,
    ):
        self.scenario = scenario
        self.node_id = node_id
        self.seed = seed
        self._rng = random.Random(seed)
        
        # Timeline configuration
        if start_time is not None:
            if start_time.tzinfo is None:
                self.current_time = start_time.replace(tzinfo=timezone.utc)
            else:
                self.current_time = start_time.astimezone(timezone.utc)
        else:
            self.current_time = datetime.now(timezone.utc)
            
        self.start_time = self.current_time
        self.interval = timedelta(seconds=max(0.1, sampling_interval_seconds))
        self.enable_seasonal = enable_seasonal
        
        # Fault injection setup
        if fault and fault not in VALID_FAULT_TYPES:
            raise ValueError(f"Unknown fault '{fault}'. Choose from: {sorted(VALID_FAULT_TYPES)}")
        self.fault = fault
        self.fault_target = fault_target
        self.noise_scale = max(0.0, noise_scale)
        self.custom_overrides = custom_overrides or {}
        
        # State tracking for multi-step continuity and faults
        self._step_count = 0
        self._previous_reading: Optional[Dict[str, Any]] = None
        self._warmup_steps = 10  # First 10 steps exhibit sensor warmup if enabled
        self._stuck_cache: Optional[Dict[str, Any]] = None
        self.last_fault_info: Dict[str, Any] = {"active": False, "type": "none", "target": None}

    def _resolve_scenario(self, name: str) -> str:
        canonical = SCENARIO_ALIASES.get(name, name)
        if canonical not in SCENARIO_PROFILES:
            return DEFAULT_SCENARIO
        return canonical

    def generate(self) -> Dict[str, Any]:
        """Generate the next timestamped, schema-valid sensor payload."""
        step = self._step_count
        self._step_count += 1
        
        scenario_key = self._resolve_scenario(self.scenario)
        profile = SCENARIO_PROFILES.get(scenario_key, SCENARIO_PROFILES[DEFAULT_SCENARIO])
        meta = SCENARIO_METADATA.get(scenario_key, SCENARIO_METADATA[DEFAULT_SCENARIO])
        
        pm25_range, pm10_range, mq2_range, mq9_range, mq135_range, temp_range, hum_range = profile
        
        # ── 1. Temporal & Seasonal Context ────────────────────────────────────
        cur = self.current_time
        solar_hour = cur.hour + cur.minute / 60.0 + cur.second / 3600.0
        
        # Seasonal progression spanning Sept 1 to Nov 30 (91 days)
        timeline_start = DEFAULT_TIMELINE_START
        total_seasonal_seconds = 91.0 * 86400.0
        elapsed_seasonal = (cur - timeline_start).total_seconds()
        seasonal_progress = min(1.0, max(0.0, elapsed_seasonal / total_seasonal_seconds)) if self.enable_seasonal else 0.5
        
        # Multi-day synoptic weather wave (period ~4.5 days)
        day_index = cur.timetuple().tm_yday
        synoptic_wave = math.sin((day_index + cur.hour / 24.0) * (2.0 * math.pi / 4.5))
        synoptic_temp_shift = synoptic_wave * 2.2
        synoptic_hum_shift = -synoptic_wave * 6.5
        
        # Diurnal solar cycle
        # Temperature peaks around 14:30 solar time, troughs around 05:30
        temp_diurnal = math.sin((solar_hour - 8.5) * (2.0 * math.pi / 24.0)) * DIURNAL_TEMP_AMPLITUDE
        # Relative humidity trough lags temperature peak by approx 1 hour
        hum_diurnal = -math.sin((solar_hour - 8.5 - DIURNAL_LAG_HOURS) * (2.0 * math.pi / 24.0)) * DIURNAL_HUM_AMPLITUDE

        # ── 2. Temperature & Relative Humidity ────────────────────────────────
        t_base = (temp_range[0] + temp_range[1]) / 2.0
        h_base = (hum_range[0] + hum_range[1]) / 2.0
        
        if self.enable_seasonal and scenario_key != 'stable':
            # Drift between September and November baselines
            t_base += (SEASONAL_SEPT_TEMP_BASE + (SEASONAL_NOV_TEMP_BASE - SEASONAL_SEPT_TEMP_BASE) * seasonal_progress) - 27.0
            h_base += (SEASONAL_SEPT_HUM_BASE + (SEASONAL_NOV_HUM_BASE - SEASONAL_SEPT_HUM_BASE) * seasonal_progress) - 67.0
            
        t_noise = self._rng.gauss(0.0, 0.25 * self.noise_scale) if scenario_key != 'stable' else 0.0
        h_noise = self._rng.gauss(0.0, 0.8 * self.noise_scale) if scenario_key != 'stable' else 0.0
        
        if scenario_key == 'stable':
            v_temp = t_base
            v_hum = h_base
        else:
            v_temp = t_base + temp_diurnal + synoptic_temp_shift + t_noise
            # Non-perfect inverse correlation: humidity has distinct moisture fluctuations
            v_hum = h_base + hum_diurnal + synoptic_hum_shift + h_noise
            
        v_temp = max(TEMP_MIN, min(TEMP_MAX, v_temp))
        v_hum = max(HUMIDITY_MIN, min(HUMIDITY_MAX, v_hum))
        if scenario_key == 'high_humidity':
            v_hum = max(80.0, v_hum)

        # ── 3. Particulate Matter (PM1.0, PM2.5, PM10) ────────────────────────
        # Seasonal winter inversion boost (November experiences higher baseline PM)
        pm_inversion_boost = (SEASONAL_NOV_PM25_BASE - SEASONAL_SEPT_PM25_BASE) * seasonal_progress * 0.4 if self.enable_seasonal else 0.0
        
        # Traffic rush hour diurnal peaks (08:30 and 18:30)
        rush_hour_boost = 0.0
        if scenario_key in ('traffic', 'mixed_pollution'):
            morning_rush = math.exp(-((solar_hour - 8.5) ** 2) / 2.5) * 22.0
            evening_rush = math.exp(-((solar_hour - 18.5) ** 2) / 3.0) * 28.0
            rush_hour_boost = morning_rush + evening_rush
            
        pm25_target = self._rng.uniform(pm25_range[0], pm25_range[1]) if scenario_key != 'stable' else pm25_range[0]
        pm25_noise = self._rng.gauss(0.0, max(0.5, pm25_target * 0.03 * self.noise_scale)) if scenario_key != 'stable' else 0.0
        
        v_pm25 = max(1.0, pm25_target + pm_inversion_boost + rush_hour_boost + pm25_noise)
        
        # Enforce physical coarse-to-fine ratio: PM10 / PM2.5
        coarse_min, coarse_max = meta.get('coarse_ratio_target', (1.4, 1.9))
        coarse_ratio = self._rng.uniform(coarse_min, coarse_max) if scenario_key != 'stable' else (coarse_min + coarse_max) / 2.0
        v_pm10 = v_pm25 * coarse_ratio
        
        # Enforce physical fine-to-ultrafine ratio: PM2.5 / PM1.0
        fine_min, fine_max = meta.get('fine_ratio_target', (1.6, 2.2))
        fine_ratio = self._rng.uniform(fine_min, fine_max) if scenario_key != 'stable' else (fine_min + fine_max) / 2.0
        v_pm1_0 = max(0.5, v_pm25 / fine_ratio)
        
        # Strict physical guarantee: PM1.0 <= PM2.5 <= PM10
        v_pm25 = max(v_pm1_0, v_pm25)
        v_pm10 = max(v_pm25, v_pm10)

        # ── 4. Metal Oxide Gas Sensors (MQ2, MQ9, MQ135) ──────────────────────
        mq2_base = self._rng.uniform(mq2_range[0], mq2_range[1]) if scenario_key != 'stable' else mq2_range[0]
        mq9_base = self._rng.uniform(mq9_range[0], mq9_range[1]) if scenario_key != 'stable' else mq9_range[0]
        mq135_base = self._rng.uniform(mq135_range[0], mq135_range[1]) if scenario_key != 'stable' else mq135_range[0]
        
        # Physical MOS environmental dependency: surface resistance shifts with humidity & temperature
        env_factor = 1.0 + 0.0012 * (v_hum - 50.0) + 0.0018 * (v_temp - 25.0)
        
        # Rush hour CO boost for MQ9 in traffic scenarios
        mq9_rush = (rush_hour_boost / 28.0) * 0.45 if scenario_key in ('traffic', 'mixed_pollution') else 0.0
        
        noise_mq = lambda: self._rng.gauss(0.0, 0.012 * self.noise_scale) if scenario_key != 'stable' else 0.0
        v_mq2 = max(VOLTAGE_MIN, min(VOLTAGE_MAX, mq2_base * env_factor + noise_mq()))
        v_mq9 = max(VOLTAGE_MIN, min(VOLTAGE_MAX, (mq9_base + mq9_rush) * env_factor + noise_mq()))
        v_mq135 = max(VOLTAGE_MIN, min(VOLTAGE_MAX, mq135_base * env_factor + noise_mq()))

        # ── 5. Apply Custom User Overrides ────────────────────────────────────
        if "temp" in self.custom_overrides: v_temp = self.custom_overrides["temp"]
        if "humidity" in self.custom_overrides: v_hum = self.custom_overrides["humidity"]
        if "pm1" in self.custom_overrides: v_pm1_0 = self.custom_overrides["pm1"]
        if "pm25" in self.custom_overrides: v_pm25 = self.custom_overrides["pm25"]
        if "pm10" in self.custom_overrides: v_pm10 = self.custom_overrides["pm10"]
        if "mq2" in self.custom_overrides: v_mq2 = self.custom_overrides["mq2"]
        if "mq9" in self.custom_overrides: v_mq9 = self.custom_overrides["mq9"]
        if "mq135" in self.custom_overrides: v_mq135 = self.custom_overrides["mq135"]
        
        # Re-enforce PM ordering after custom overrides
        v_pm25 = max(v_pm1_0, v_pm25)
        v_pm10 = max(v_pm25, v_pm10)

        # ── 6. Fault Injections & Sensor Non-Idealities ───────────────────────
        fault_mode = self.fault
        fault_tgt = self.fault_target
        
        # Backward compatibility for scenario='sensor_fault' without explicit fault arg
        if scenario_key == 'sensor_fault' and not fault_mode:
            fault_mode = 'rail_gnd'
            fault_tgt = self._rng.choice(['MQ2', 'MQ9', 'MQ135', 'PM2_5'])
            
        self.last_fault_info = {"active": bool(fault_mode and fault_mode != 'none'), "type": fault_mode or "none", "target": fault_tgt}
        
        is_missing_target = False
        
        if fault_mode == 'stuck':
            # Frozen bit-identical values across readings
            if self._stuck_cache is None:
                self._stuck_cache = {
                    "temp": v_temp, "hum": v_hum,
                    "pm1": v_pm1_0, "pm25": v_pm25, "pm10": v_pm10,
                    "mq2": v_mq2, "mq9": v_mq9, "mq135": v_mq135
                }
            if fault_tgt in ('MQ2', None): v_mq2 = self._stuck_cache["mq2"]
            if fault_tgt in ('MQ9', None): v_mq9 = self._stuck_cache["mq9"]
            if fault_tgt in ('MQ135', None): v_mq135 = self._stuck_cache["mq135"]
            if fault_tgt in ('PM2_5', None):
                v_pm1_0 = self._stuck_cache["pm1"]
                v_pm25 = self._stuck_cache["pm25"]
                v_pm10 = self._stuck_cache["pm10"]
            if fault_tgt in ('temperature', None): v_temp = self._stuck_cache["temp"]
            if fault_tgt in ('humidity', None): v_hum = self._stuck_cache["hum"]
            
        elif fault_mode == 'rail_gnd':
            # Short to ground (0V / ADC 0)
            if fault_tgt in ('MQ2', None): v_mq2 = 0.0
            if fault_tgt == 'MQ9': v_mq9 = 0.0
            if fault_tgt == 'MQ135': v_mq135 = 0.0
            if fault_tgt == 'PM2_5': v_pm1_0 = 0.0; v_pm25 = 0.0; v_pm10 = 0.0
            
        elif fault_mode == 'rail_vcc':
            # Short to VCC (5.0V / ADC 1023)
            if fault_tgt in ('MQ2', None): v_mq2 = 5.0
            if fault_tgt == 'MQ9': v_mq9 = 5.0
            if fault_tgt == 'MQ135': v_mq135 = 5.0
            
        elif fault_mode == 'warmup':
            # Sensor heater warming up: readings start high and decay over time
            decay = math.exp(-step / 4.0)
            warmup_offset = 2.5 * decay
            if fault_tgt in ('MQ2', None): v_mq2 = min(VOLTAGE_MAX, v_mq2 + warmup_offset)
            if fault_tgt in ('MQ9', None): v_mq9 = min(VOLTAGE_MAX, v_mq9 + warmup_offset)
            if fault_tgt in ('MQ135', None): v_mq135 = min(VOLTAGE_MAX, v_mq135 + warmup_offset)
            
        elif fault_mode == 'drift':
            # Gradual cumulative calibration drift
            drift_val = (step * 0.015) % 3.0
            if fault_tgt in ('MQ2', None): v_mq2 = min(VOLTAGE_MAX, v_mq2 + drift_val)
            if fault_tgt == 'MQ9': v_mq9 = min(VOLTAGE_MAX, v_mq9 + drift_val)
            if fault_tgt == 'MQ135': v_mq135 = min(VOLTAGE_MAX, v_mq135 + drift_val)
            if fault_tgt == 'temperature': v_temp = min(TEMP_MAX, v_temp + drift_val * 2.0)
            
        elif fault_mode == 'transient_spike':
            # 1-sample extreme jump outlier
            if step % 5 == 2:
                if fault_tgt in ('MQ2', None): v_mq2 = 4.85
                if fault_tgt == 'MQ9': v_mq9 = 4.85
                if fault_tgt == 'MQ135': v_mq135 = 4.85
                if fault_tgt == 'PM2_5': v_pm25 = 480.0; v_pm10 = 650.0
                
        elif fault_mode == 'missing':
            is_missing_target = True

        # ── 7. Construct Final Schema-Valid Payload ───────────────────────────
        def to_adc(volts: float) -> int:
            return int(max(0, min(ADC_MAX, round((volts / ADC_VREF) * ADC_MAX))))

        gas_sensors: Dict[str, Any] = {
            "MQ2": {
                "raw_adc": to_adc(v_mq2),
                "voltage_V": round(max(VOLTAGE_MIN, min(VOLTAGE_MAX, v_mq2)), 3)
            },
            "MQ9": {
                "raw_adc": to_adc(v_mq9),
                "voltage_V": round(max(VOLTAGE_MIN, min(VOLTAGE_MAX, v_mq9)), 3)
            },
            "MQ135": {
                "raw_adc": to_adc(v_mq135),
                "voltage_V": round(max(VOLTAGE_MIN, min(VOLTAGE_MAX, v_mq135)), 3)
            }
        }

        environment_block: Dict[str, Any] = {
            "temperature_C": round(v_temp, 2),
            "humidity_pct": round(v_hum, 2)
        }

        pm_block: Dict[str, Any] = {
            "PM1_0": round(v_pm1_0, 2),
            "PM2_5": round(v_pm25, 2),
            "PM10": round(v_pm10, 2)
        }

        # Apply missing-field fault if requested for testing fault detectors
        if is_missing_target:
            if fault_tgt in ('MQ2', 'MQ9', 'MQ135'):
                gas_sensors.pop(fault_tgt, None)
            elif fault_tgt == 'environment':
                environment_block = {}
            elif fault_tgt == 'particulate_matter':
                pm_block = {}

        payload: Dict[str, Any] = {
            "node_id": self.node_id,
            "timestamp": self.current_time.isoformat(),
            "environment": environment_block,
            "particulate_matter": pm_block,
            "gas_sensors": gas_sensors
        }

        self._previous_reading = payload
        self.current_time += self.interval
        return payload

    def generate_batch(self, count: int) -> List[Dict[str, Any]]:
        """Generate a consecutive sequence of simulated payloads."""
        return [self.generate() for _ in range(max(1, count))]

    def reset_timeline(self, start_time: Optional[datetime] = None) -> None:
        """Reset simulator clock and step count."""
        if start_time is not None:
            self.current_time = start_time.astimezone(timezone.utc) if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
        else:
            self.current_time = self.start_time
        self._step_count = 0
        self._stuck_cache = None
        self._previous_reading = None
