import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

try:
    from simulation.constants import (
        DEFAULT_SCENARIO,
        DEFAULT_SIM_NODE_ID,
        DEFAULT_SAMPLING_INTERVAL_SECONDS,
        ADC_VREF,
        ADC_MAX,
        SCENARIO_PROFILES,
    )
except ImportError:
    from constants import (
        DEFAULT_SCENARIO,
        DEFAULT_SIM_NODE_ID,
        DEFAULT_SAMPLING_INTERVAL_SECONDS,
        ADC_VREF,
        ADC_MAX,
        SCENARIO_PROFILES,
    )

class SensorSimulator:
    def __init__(self, scenario: str = DEFAULT_SCENARIO, node_id: str = DEFAULT_SIM_NODE_ID, seed: int = None):
        self.scenario = scenario
        self.node_id = node_id
        if seed is not None:
            random.seed(seed)
        self.current_time = datetime.now(timezone.utc)
        self.interval = timedelta(seconds=DEFAULT_SAMPLING_INTERVAL_SECONDS)

    def generate(self) -> Dict[str, Any]:
        scenario = self.scenario
        
        # Base values from centralized SCENARIO_PROFILES
        profile = SCENARIO_PROFILES.get(scenario, SCENARIO_PROFILES['clean_indoor'])
        pm25, pm10, mq2, mq9, mq135, temp, hum = profile
            
        def r(r_tuple):
            val = random.uniform(r_tuple[0], r_tuple[1])
            if scenario == 'stable':
                # add +/- 0.5% noise
                noise = random.uniform(-0.005, 0.005)
                val = val * (1 + noise)
            else:
                # add slight random noise for realism (e.g. +/- 2%)
                noise = random.uniform(-0.02, 0.02)
                val = val * (1 + noise)
            return val

        v_pm25 = r(pm25)
        v_pm10 = r(pm10)
        
        if v_pm10 < v_pm25:
            v_pm10 = v_pm25 + random.uniform(1, 5)
            
        v_pm1_0 = v_pm25 * 0.5

        v_mq2 = r(mq2)
        v_mq9 = r(mq9)
        v_mq135 = r(mq135)
        
        if scenario == 'sensor_fault':
            fault = random.choice(['mq2', 'mq9', 'mq135', 'pm25'])
            fault_val = random.choice([0.0, 5.0]) if fault != 'pm25' else 0.0
            if fault == 'mq2': v_mq2 = fault_val
            elif fault == 'mq9': v_mq9 = fault_val
            elif fault == 'mq135': v_mq135 = fault_val
            elif fault == 'pm25': v_pm25 = fault_val; v_pm10 = fault_val
            
        v_temp = r(temp)
        v_hum = r(hum)
        
        def to_adc(volts):
            return int(max(0, min(ADC_MAX, (volts / ADC_VREF) * ADC_MAX)))

        payload = {
            "node_id": self.node_id,
            "timestamp": self.current_time.isoformat(),
            "environment": {
                "temperature_C": round(v_temp, 2),
                "humidity_pct": round(v_hum, 2)
            },
            "particulate_matter": {
                "PM1_0": round(v_pm1_0, 2),
                "PM2_5": round(v_pm25, 2),
                "PM10": round(v_pm10, 2)
            },
            "gas_sensors": {
                "MQ2": {
                    "raw_adc": to_adc(v_mq2),
                    "voltage_V": round(max(0.0, min(5.0, v_mq2)), 3)
                },
                "MQ9": {
                    "raw_adc": to_adc(v_mq9),
                    "voltage_V": round(max(0.0, min(5.0, v_mq9)), 3)
                },
                "MQ135": {
                    "raw_adc": to_adc(v_mq135),
                    "voltage_V": round(max(0.0, min(5.0, v_mq135)), 3)
                }
            }
        }
        
        self.current_time += self.interval
        return payload
