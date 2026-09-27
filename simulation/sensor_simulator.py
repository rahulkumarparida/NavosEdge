import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

class SensorSimulator:
    def __init__(self, scenario: str = 'clean_indoor', node_id: str = "sim_node_01", seed: int = None):
        self.scenario = scenario
        self.node_id = node_id
        if seed is not None:
            random.seed(seed)
        self.current_time = datetime.now(timezone.utc)
        self.interval = timedelta(seconds=60)

    def generate(self) -> Dict[str, Any]:
        scenario = self.scenario
        
        # Base values
        if scenario == 'clean_indoor':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (5, 15), (10, 25), (0.8, 1.2), (0.6, 1.0), (0.7, 1.1), (22, 26), (40, 55)
        elif scenario == 'traffic':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (35, 80), (60, 120), (1.3, 2.0), (1.5, 2.5), (1.2, 1.8), (28, 35), (30, 50)
        elif scenario == 'dust_construction':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (50, 120), (150, 400), (0.9, 1.3), (0.7, 1.1), (0.8, 1.2), (30, 38), (25, 40)
        elif scenario == 'combustion_smoke':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (80, 200), (100, 250), (2.5, 4.0), (2.0, 3.5), (2.0, 3.5), (32, 40), (30, 50)
        elif scenario == 'high_humidity':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (10, 25), (15, 35), (0.9, 1.3), (0.7, 1.1), (0.8, 1.2), (24, 30), (85, 98)
        elif scenario == 'pm_spike':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (200, 500), (300, 700), (1.0, 1.5), (0.8, 1.2), (0.9, 1.3), (25, 32), (40, 60)
        elif scenario == 'gas_spike':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (10, 30), (15, 40), (3.0, 4.5), (2.5, 4.0), (3.0, 4.5), (25, 35), (35, 55)
        elif scenario == 'mixed_pollution':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (60, 150), (100, 250), (1.8, 3.0), (1.5, 2.8), (1.5, 2.8), (28, 35), (40, 60)
        elif scenario == 'stable':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (12, 12), (20, 20), (1.0, 1.0), (0.8, 0.8), (0.9, 0.9), (25, 25), (50, 50)
        elif scenario == 'sensor_fault':
            pm25, pm10, mq2, mq9, mq135, temp, hum = (5, 15), (10, 25), (0.8, 1.2), (0.6, 1.0), (0.7, 1.1), (22, 26), (40, 55)
        else:
            pm25, pm10, mq2, mq9, mq135, temp, hum = (5, 15), (10, 25), (0.8, 1.2), (0.6, 1.0), (0.7, 1.1), (22, 26), (40, 55)
            
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
            return int(max(0, min(1023, (volts / 5.0) * 1023)))

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
