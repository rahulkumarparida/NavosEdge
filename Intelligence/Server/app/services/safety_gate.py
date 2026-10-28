"""
Sensor Safety Gate — Pre-Inference Validation for TinyGasNet.

Validates raw sensor telemetry against documented electrical, physical,
and operational bounds before invoking neural network inference.

Hardware Specifications & Electrical Constraints:
1. Microcontroller / ADC Specs (Arduino UNO Q):
   - Architecture: 32-bit ARM Cortex-M33 (STM32U5) MCU + Qualcomm Linux MPU.
   - ADC: 10-bit successive approximation register (SAR) ADC.
   - Input voltage range: 0.0 V to 5.0 V mapped to raw ADC 0 to 1023 (1 LSB ~ 4.887 mV).
   - Absolute rails: GND (0.0 V / ADC 0) and VCC (5.0 V / ADC 1023).

2. Metal Oxide Semiconductor (MOS) Gas Sensors (MQ-2, MQ-9, MQ-135):
   - Circuit topology: Supply voltage Vc = 5.0 V ± 0.1 V across sensing element Rs
     in series with load resistor RL = 10.0 kΩ to GND.
   - Output voltage: V_out = Vc * (RL / (Rs + RL)).
   - In clean air: Rs is at maximum baseline resistance (5 kΩ - 30 kΩ),
     yielding physical baseline voltages typically in 0.50 V - 1.20 V.
   - In high gas concentration: Rs decreases towards 100 Ω - 300 Ω,
     yielding output voltages up to 4.20 V - 4.60 V.
   - Electrical failure limits:
     * Lower electrical limit: 0.100 V (ADC ~ 20). Output < 0.10 V physically requires
       Rs > 490 kΩ, which cannot occur in functional sensors. A reading < 0.10 V
       definitively indicates a ground short (GND rail), open circuit, or unpowered heater.
     * Upper electrical limit: 4.900 V (ADC ~ 1003). Output > 4.90 V requires Rs < 204 Ω.
       A reading > 4.90 V indicates a supply rail short (VCC short).
   - Valid electrical operating window: [0.100 V, 4.900 V].

3. Environmental Sensor (DHT22 / AM2302):
   - Operating temperature range: -40.0 °C to +80.0 °C (datasheet).
   - Verified accuracy limit for gas compensation: -20.0 °C to +65.0 °C (±0.5 °C).
   - Outside [-20.0 °C, 65.0 °C]: thermal drift compromises MOS baseline compensation.
   - Relative humidity range: 0.0 % to 100.0 % RH.

Abstention Policy:
- When any input violates validated limits or is non-finite / missing,
  TinyGasNet inference is NOT called.
- Returns an explicit SENSOR_FAULT InferenceResult with uncertainty = 1.0,
  gas_class = "SENSOR_FAULT", safety_status = "unknown".
- Downstream advisory cannot interpret the reading as CleanAir or safe.
- Detailed diagnostic evidence is preserved in error_message.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.inference import InferenceResult, InferenceStatus

# ------------------------------------------------------------------
# Documented Sensor-Specific Electrical and Physical Bounds
# ------------------------------------------------------------------

# MQ Gas Sensors (MQ2, MQ9, MQ135): 5V supply, RL = 10 kΩ
MQ_VOLTAGE_MIN: float = 0.100  # Volts. < 0.10V = GND short / open circuit
MQ_VOLTAGE_MAX: float = 4.900  # Volts. > 4.90V = VCC power rail short

# DHT22 Temperature & Humidity Limits
TEMP_MIN_C: float = -20.0      # °C. Verified environmental operating range
TEMP_MAX_C: float = 65.0       # °C. Verified environmental operating range
HUMIDITY_MIN_PCT: float = 0.0  # % RH
HUMIDITY_MAX_PCT: float = 100.0  # % RH

SENSOR_LIMITS: Dict[str, Tuple[float, float, str]] = {
    "MQ2_V": (MQ_VOLTAGE_MIN, MQ_VOLTAGE_MAX, "V"),
    "MQ9_V": (MQ_VOLTAGE_MIN, MQ_VOLTAGE_MAX, "V"),
    "MQ135_V": (MQ_VOLTAGE_MIN, MQ_VOLTAGE_MAX, "V"),
    "temperature_C": (TEMP_MIN_C, TEMP_MAX_C, "°C"),
    "humidity_pct": (HUMIDITY_MIN_PCT, HUMIDITY_MAX_PCT, "%"),
}


@dataclass
class GateResult:
    """Result of the pre-inference sensor safety validation."""

    is_valid: bool
    violations: List[str] = field(default_factory=list)
    faulty_sensors: List[str] = field(default_factory=list)
    has_hardware_fault: bool = False
    has_environmental_out_of_bounds: bool = False
    reason: str = ""

    def to_inference_result(self, inference_time_ms: float = 0.0) -> InferenceResult:
        """Construct an explicit SENSOR_FAULT or ABSTAIN inference result."""
        if self.has_hardware_fault or (not self.has_environmental_out_of_bounds):
            return InferenceResult.from_sensor_fault(
                message=self.reason,
                uncertainty=1.0,
                inference_time_ms=inference_time_ms,
            )
        return InferenceResult.from_abstain(
            message=self.reason,
            uncertainty=1.0,
            inference_time_ms=inference_time_ms,
        )


class SensorSafetyGate:
    """
    Validates sensor inputs prior to invoking neural network inference.
    Prevents electrical rail shorts or malformed readings from producing
    bogus high-confidence classifications.
    """

    @staticmethod
    def validate(
        mq2_v: Any,
        mq9_v: Any,
        mq135_v: Any,
        temperature_c: Any,
        humidity_pct: Any,
    ) -> GateResult:
        """
        Validate all 5 input channels against physical/electrical boundaries.

        Checks:
        1. Non-null and non-missing check.
        2. Finite numeric check (rejects NaN, +Inf, -Inf, non-numeric).
        3. Electrical bounds for MQ gas channels [0.100V, 4.900V].
        4. Environmental bounds for temperature [-20.0°C, 65.0°C] and humidity [0.0%, 100.0%].

        Returns GateResult with detailed diagnostic violations.
        """
        violations: List[str] = []
        faulty_sensors: List[str] = []
        has_hw_fault = False
        has_env_oob = False

        channels: Dict[str, Tuple[Any, float, float, str]] = {
            "MQ2_V": (mq2_v, MQ_VOLTAGE_MIN, MQ_VOLTAGE_MAX, "V"),
            "MQ9_V": (mq9_v, MQ_VOLTAGE_MIN, MQ_VOLTAGE_MAX, "V"),
            "MQ135_V": (mq135_v, MQ_VOLTAGE_MIN, MQ_VOLTAGE_MAX, "V"),
            "temperature_C": (temperature_c, TEMP_MIN_C, TEMP_MAX_C, "°C"),
            "humidity_pct": (humidity_pct, HUMIDITY_MIN_PCT, HUMIDITY_MAX_PCT, "%"),
        }

        for name, (val, min_bound, max_bound, unit) in channels.items():
            # 1. Null / Missing check
            if val is None:
                violations.append(f"{name} is missing (null/None)")
                faulty_sensors.append(name)
                has_hw_fault = True
                continue

            # 2. Non-numeric / Non-finite check
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                violations.append(f"{name} has non-numeric value: {repr(val)}")
                faulty_sensors.append(name)
                has_hw_fault = True
                continue

            v_float = float(val)
            if not math.isfinite(v_float):
                violations.append(f"{name} is non-finite ({repr(val)})")
                faulty_sensors.append(name)
                has_hw_fault = True
                continue

            # 3. Electrical / Physical bounds check
            if v_float < min_bound:
                if "MQ" in name:
                    violations.append(
                        f"{name} voltage {v_float:.3f}V below lower electrical limit "
                        f"{min_bound:.3f}V (railed to GND or open circuit)"
                    )
                    has_hw_fault = True
                else:
                    violations.append(
                        f"{name} value {v_float:.1f}{unit} below physical operating limit "
                        f"{min_bound:.1f}{unit}"
                    )
                    has_env_oob = True
                faulty_sensors.append(name)

            elif v_float > max_bound:
                if "MQ" in name:
                    violations.append(
                        f"{name} voltage {v_float:.3f}V above upper electrical limit "
                        f"{max_bound:.3f}V (railed to VCC supply)"
                    )
                    has_hw_fault = True
                else:
                    violations.append(
                        f"{name} value {v_float:.1f}{unit} above physical operating limit "
                        f"{max_bound:.1f}{unit}"
                    )
                    has_env_oob = True
                faulty_sensors.append(name)

        if violations:
            reason = "Pre-inference safety gate tripped: " + "; ".join(violations)
            return GateResult(
                is_valid=False,
                violations=violations,
                faulty_sensors=faulty_sensors,
                has_hardware_fault=has_hw_fault,
                has_environmental_out_of_bounds=has_env_oob,
                reason=reason,
            )

        return GateResult(is_valid=True)
