"""
Historical environmental data acquisition and caching for NavosEdge.

Fetches and caches hourly historical weather (Open-Meteo Historical Weather API)
and atmospheric PM reanalysis (Open-Meteo Air Quality API) for configured locations
(e.g., Bhubaneswar, Dhenkanal, Odisha, India), or imports documented station CSVs.

Strictly records provenance:
- OBSERVED: Ground truth measurements from documented station CSVs
- REANALYSIS: Reanalysis atmospheric weather / CAMS data
- SYNTHETIC: Generated fallback profiles
- DERIVED: Resampled or interpolated values
"""

from __future__ import annotations

import csv
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("navos-historical-data")

# Known deployment coordinates in Odisha, India
LOCATIONS: Dict[str, Tuple[float, float]] = {
    "bhubaneswar": (20.2961, 85.8245),
    "dhenkanal": (20.6558, 85.5976),
    "cuttack": (20.4625, 85.8830),
    "angul": (20.8398, 85.1012),
}

CACHE_DIR_DEFAULT = Path("data/historical_cache")


@dataclass
class HourlyContextRecord:
    timestamp: str  # ISO-8601 UTC
    temperature_C: float
    humidity_pct: float
    pm25: Optional[float]
    pm10: Optional[float]
    weather_provenance: str  # "REANALYSIS", "OBSERVED", "SYNTHETIC"
    pm_provenance: str       # "REANALYSIS", "OBSERVED", "SYNTHETIC"
    source: str
    station_or_coords: str
    is_missing: bool = False


class HistoricalDataAcquisition:
    """Acquires, caches, and parses historical weather and air-quality context."""

    def __init__(
        self,
        cache_dir: Path | str = CACHE_DIR_DEFAULT,
        location: str = "bhubaneswar",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        timeout: float = 10.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        
        loc_key = location.lower().strip()
        if latitude is not None and longitude is not None:
            self.latitude = latitude
            self.longitude = longitude
            self.location_name = f"{latitude:.4f},{longitude:.4f}"
        elif loc_key in LOCATIONS:
            self.latitude, self.longitude = LOCATIONS[loc_key]
            self.location_name = loc_key
        else:
            self.latitude, self.longitude = LOCATIONS["bhubaneswar"]
            self.location_name = "bhubaneswar"

    def fetch_weather(
        self,
        start_date: str,
        end_date: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch historical hourly weather from Open-Meteo Historical Weather API.
        Cached locally in `data/historical_cache/weather_{location}_{start}_{end}.json`.
        """
        cache_file = self.cache_dir / f"weather_{self.location_name}_{start_date}_{end_date}.json"
        if not force_refresh and cache_file.exists():
            try:
                logger.info("Loading cached weather from %s", cache_file)
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed reading cache %s: %s; refetching", cache_file, e)

        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={self.latitude}&longitude={self.longitude}&"
            f"start_date={start_date}&end_date={end_date}&"
            f"hourly=temperature_2m,relative_humidity_2m"
        )
        logger.info("Fetching historical weather from Open-Meteo: %s", url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NavosEdge-HistoricalAcquisition/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        except Exception as exc:
            logger.warning("Open-Meteo weather request failed (%s). Checking offline fallback.", exc)
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))
            return self._generate_synthetic_weather_fallback(start_date, end_date)

    def fetch_air_quality(
        self,
        start_date: str,
        end_date: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch historical hourly PM2.5 and PM10 from Open-Meteo Air Quality API.
        Cached locally in `data/historical_cache/airquality_{location}_{start}_{end}.json`.
        """
        cache_file = self.cache_dir / f"airquality_{self.location_name}_{start_date}_{end_date}.json"
        if not force_refresh and cache_file.exists():
            try:
                logger.info("Loading cached air quality from %s", cache_file)
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed reading cache %s: %s; refetching", cache_file, e)

        url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={self.latitude}&longitude={self.longitude}&"
            f"start_date={start_date}&end_date={end_date}&"
            f"hourly=pm10,pm2_5"
        )
        logger.info("Fetching historical air quality from Open-Meteo: %s", url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NavosEdge-HistoricalAcquisition/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        except Exception as exc:
            logger.warning("Open-Meteo air quality request failed (%s). Checking offline fallback.", exc)
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))
            return self._generate_synthetic_pm_fallback(start_date, end_date)

    def load_cpcb_station_csv(self, csv_path: Path | str) -> Dict[str, Tuple[float, float]]:
        """
        Import documented CPCB station CSV with columns:
        Timestamp (or Date/Time), PM2.5, PM10.
        Returns dict mapping ISO timestamp -> (pm2.5, pm10).
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CPCB station CSV not found: {path}")

        records: Dict[str, Tuple[float, float]] = {}
        with path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts_raw = row.get("Timestamp") or row.get("From Date") or row.get("Date")
                pm25_raw = row.get("PM2.5") or row.get("pm2_5") or row.get("PM25")
                pm10_raw = row.get("PM10") or row.get("pm10")
                if not ts_raw or pm25_raw is None or pm10_raw is None:
                    continue
                try:
                    # Support formats like YYYY-MM-DD HH:MM:SS or ISO
                    ts = datetime.fromisoformat(ts_raw.strip().replace(" ", "T"))
                    if ts.tzinfo is None:
                        # CPCB stations report IST (+05:30)
                        ist = timezone(timedelta(hours=5, minutes=30))
                        ts = ts.replace(tzinfo=ist).astimezone(timezone.utc)
                    else:
                        ts = ts.astimezone(timezone.utc)
                    records[ts.isoformat()] = (float(pm25_raw), float(pm10_raw))
                except (ValueError, TypeError):
                    continue
        logger.info("Imported %d records from CPCB station CSV %s", len(records), path)
        return records

    def build_context_series(
        self,
        start_date: str,
        end_date: str,
        station_csv: Optional[Path | str] = None,
    ) -> List[HourlyContextRecord]:
        """
        Merge weather and PM reanalysis/observations into an aligned hourly context series.
        """
        weather_data = self.fetch_weather(start_date, end_date)
        aq_data = self.fetch_air_quality(start_date, end_date)
        
        station_obs: Dict[str, Tuple[float, float]] = {}
        if station_csv:
            station_obs = self.load_cpcb_station_csv(station_csv)

        weather_hourly = weather_data.get("hourly", {})
        weather_times = weather_hourly.get("time", [])
        temperatures = weather_hourly.get("temperature_2m", [])
        humidities = weather_hourly.get("relative_humidity_2m", [])
        weather_prov = weather_data.get("_navos_provenance", "REANALYSIS")

        aq_hourly = aq_data.get("hourly", {})
        aq_times = aq_hourly.get("time", [])
        pm25_vals = aq_hourly.get("pm2_5", [])
        pm10_vals = aq_hourly.get("pm10", [])
        aq_prov = aq_data.get("_navos_provenance", "REANALYSIS")

        # Map AQ by ISO time
        aq_map: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
        for t, p25, p10 in zip(aq_times, pm25_vals, pm10_vals):
            # Open-Meteo returns YYYY-MM-DDTHH:MM
            try:
                dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
                aq_map[dt.isoformat()] = (p25, p10)
            except ValueError:
                pass

        results: List[HourlyContextRecord] = []
        for i, t_str in enumerate(weather_times):
            try:
                dt = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)
                iso_ts = dt.isoformat()
            except ValueError:
                continue

            temp = temperatures[i] if i < len(temperatures) else 28.0
            hum = humidities[i] if i < len(humidities) else 65.0
            is_missing = (temp is None or hum is None)
            temp = float(temp) if temp is not None else 28.0
            hum = float(hum) if hum is not None else 65.0

            # Prefer observed station data if available for this timestamp
            if iso_ts in station_obs:
                p25, p10 = station_obs[iso_ts]
                pm_p = "OBSERVED"
                source_label = f"CPCB Station ({station_csv})"
            elif iso_ts in aq_map:
                p25, p10 = aq_map[iso_ts]
                pm_p = aq_prov
                source_label = f"Open-Meteo Air Quality ({self.location_name})"
            else:
                p25, p10 = None, None
                pm_p = "SYNTHETIC"
                source_label = f"Synthetic Baseline ({self.location_name})"

            results.append(
                HourlyContextRecord(
                    timestamp=iso_ts,
                    temperature_C=temp,
                    humidity_pct=hum,
                    pm25=float(p25) if p25 is not None else None,
                    pm10=float(p10) if p10 is not None else None,
                    weather_provenance=weather_prov,
                    pm_provenance=pm_p,
                    source=source_label,
                    station_or_coords=f"{self.latitude:.4f},{self.longitude:.4f}",
                    is_missing=is_missing,
                )
            )

        return results

    def _generate_synthetic_weather_fallback(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Deterministic offline synthetic fallback for weather when network is offline."""
        logger.info("Using offline synthetic weather fallback for %s to %s", start_date, end_date)
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
        hours = int((end_dt - start_dt).total_seconds() / 3600)
        
        times = []
        temps = []
        hums = []
        import math
        for h in range(hours):
            cur = start_dt + timedelta(hours=h)
            times.append(cur.strftime("%Y-%m-%dT%H:%M"))
            solar_hour = cur.hour
            temp = 28.0 + 4.0 * math.sin((solar_hour - 8.5) * (2.0 * math.pi / 24.0))
            hum = 65.0 - 12.0 * math.sin((solar_hour - 9.5) * (2.0 * math.pi / 24.0))
            temps.append(round(temp, 1))
            hums.append(round(hum, 1))
            
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": {"time": times, "temperature_2m": temps, "relative_humidity_2m": hums},
            "_navos_provenance": "SYNTHETIC",
        }

    def _generate_synthetic_pm_fallback(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Deterministic offline synthetic fallback for PM when network is offline."""
        logger.info("Using offline synthetic PM fallback for %s to %s", start_date, end_date)
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
        hours = int((end_dt - start_dt).total_seconds() / 3600)
        
        times = []
        p25 = []
        p10 = []
        import math
        for h in range(hours):
            cur = start_dt + timedelta(hours=h)
            times.append(cur.strftime("%Y-%m-%dT%H:%M"))
            solar_hour = cur.hour
            rush = math.exp(-((solar_hour - 8.5) ** 2) / 2.5) * 15.0 + math.exp(-((solar_hour - 18.5) ** 2) / 3.0) * 20.0
            val25 = 35.0 + rush
            val10 = val25 * 1.6
            p25.append(round(val25, 1))
            p10.append(round(val10, 1))
            
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": {"time": times, "pm2_5": p25, "pm10": p10},
            "_navos_provenance": "SYNTHETIC",
        }
