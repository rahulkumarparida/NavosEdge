"""
Daily Aggregates Service for NavosEdge.

Computes, updates, and persists long-lived daily summary statistics per node
from raw partitioned JSONL readings or local dataset records.

Ensures safe idempotence and correct handling of late-arriving readings.
Calculates 24-hour CPCB PM averages, data sufficiency, and coverage percentage.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.aqi.calculator import AQICalculator

logger = logging.getLogger("navos-daily-aggregates")


@dataclass
class DailyAggregate:
    date: str  # YYYY-MM-DD
    node_id: str
    count: int
    first_timestamp: Optional[str]
    last_timestamp: Optional[str]
    coverage_hours: float
    coverage_pct: float
    pm25: Dict[str, float]  # min, max, mean
    pm10: Dict[str, float]  # min, max, mean
    temperature_C: Dict[str, float]  # min, max, mean
    humidity_pct: Dict[str, float]   # min, max, mean
    cpcb_aqi: Optional[float]
    aqi_category: Optional[str]
    data_sufficiency: str  # "VALID" (>= 16h coverage) or "INSUFFICIENT_DATA"
    updated_at: str


class DailyAggregateService:
    """Manages computation and persistence of daily aggregates per node."""

    def __init__(self, data_dir: Path | str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.aggregates_dir = self.data_dir / "daily_aggregates"
        self.aggregates_dir.mkdir(parents=True, exist_ok=True)
        self.readings_dir = self.data_dir / "readings"
        self.calculator = AQICalculator(standard="CPCB")
        self._lock = threading.Lock()

    def _node_file(self, node_id: str) -> Path:
        return self.aggregates_dir / f"{node_id}.jsonl"

    def compute_for_date(self, node_id: str, target_date: Union[date, str]) -> Optional[DailyAggregate]:
        """
        Compute daily aggregate statistics from the raw JSONL file for that date.
        """
        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        raw_file = self.readings_dir / node_id / f"{date_str}.jsonl"
        if not raw_file.exists():
            return None

        records: List[Dict[str, Any]] = []
        with raw_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not records:
            return None

        # Sort chronologically
        def parse_dt(r: dict) -> datetime:
            ts_str = r.get("timestamp") or ""
            dt = datetime.fromisoformat(ts_str)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        records.sort(key=parse_dt)
        timestamps = [parse_dt(r) for r in records]

        first_ts = timestamps[0]
        last_ts = timestamps[-1]
        coverage_hours = max(0.0, (last_ts - first_ts).total_seconds() / 3600.0)
        # Expected readings at 5-min intervals is 288
        coverage_pct = round(min(100.0, (coverage_hours / 24.0) * 100.0), 1)

        # Extract values
        pm25_vals = [
            float(r["particulate_matter"]["PM2_5"])
            for r in records
            if "particulate_matter" in r and "PM2_5" in r["particulate_matter"]
        ]
        pm10_vals = [
            float(r["particulate_matter"]["PM10"])
            for r in records
            if "particulate_matter" in r and "PM10" in r["particulate_matter"]
        ]
        temp_vals = [
            float(r["environment"]["temperature_C"])
            for r in records
            if "environment" in r and "temperature_C" in r["environment"]
        ]
        hum_vals = [
            float(r["environment"]["humidity_pct"])
            for r in records
            if "environment" in r and "humidity_pct" in r["environment"]
        ]

        def stats_dict(vals: List[float]) -> Dict[str, float]:
            if not vals:
                return {"min": 0.0, "max": 0.0, "mean": 0.0}
            return {
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "mean": round(sum(vals) / len(vals), 2),
            }

        pm25_stats = stats_dict(pm25_vals)
        pm10_stats = stats_dict(pm10_vals)
        temp_stats = stats_dict(temp_vals)
        hum_stats = stats_dict(hum_vals)

        # CPCB 24-hour PM data sufficiency (>= 16 hours)
        data_sufficiency = "VALID" if coverage_hours >= 16.0 else "INSUFFICIENT_DATA"

        # Compute 24h AQI
        aqi_val: Optional[float] = None
        aqi_cat: Optional[str] = None
        if pm25_stats["mean"] > 0 or pm10_stats["mean"] > 0:
            calc_result = self.calculator.calculate(
                pm1_0=0.0,
                pm2_5=pm25_stats["mean"],
                pm10=pm10_stats["mean"],
                timestamp=last_ts,
                node_id=node_id,
                data_sufficiency=data_sufficiency,
                averaging_window_hours=24.0,
                data_coverage_hours=coverage_hours,
            )
            aqi_val = calc_result.aqi
            aqi_cat = calc_result.category

        return DailyAggregate(
            date=date_str,
            node_id=node_id,
            count=len(records),
            first_timestamp=first_ts.isoformat(),
            last_timestamp=last_ts.isoformat(),
            coverage_hours=round(coverage_hours, 2),
            coverage_pct=coverage_pct,
            pm25=pm25_stats,
            pm10=pm10_stats,
            temperature_C=temp_stats,
            humidity_pct=hum_stats,
            cpcb_aqi=aqi_val,
            aqi_category=aqi_cat,
            data_sufficiency=data_sufficiency,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def update_or_recompute(self, node_id: str, target_date: Union[date, str]) -> Optional[DailyAggregate]:
        """
        Compute daily aggregate and update the node's JSONL aggregate store.
        Idempotent: if an aggregate for target_date already exists, it is replaced (handling late records).
        """
        agg = self.compute_for_date(node_id, target_date)
        if agg is None:
            return None

        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        node_file = self._node_file(node_id)

        with self._lock:
            existing: Dict[str, dict] = {}
            if node_file.exists():
                with node_file.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            d = item.get("date")
                            if d:
                                existing[d] = item
                        except json.JSONDecodeError:
                            continue

            # Update or insert
            existing[date_str] = asdict(agg)

            # Rewrite sorted by date
            with node_file.open("w", encoding="utf-8") as fh:
                for d in sorted(existing.keys()):
                    fh.write(json.dumps(existing[d], separators=(",", ":")) + "\n")

        return agg

    def get_aggregates(
        self,
        node_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve stored daily aggregates for a node, optionally filtered by date range."""
        node_file = self._node_file(node_id)
        if not node_file.exists():
            return []

        results: List[Dict[str, Any]] = []
        with self._lock:
            with node_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        d = rec.get("date", "")
                        if start_date and d < start_date:
                            continue
                        if end_date and d > end_date:
                            continue
                        results.append(rec)
                    except json.JSONDecodeError:
                        continue

        results.sort(key=lambda x: x.get("date", ""))
        return results

    def compute_all_dates(self, node_id: str) -> List[DailyAggregate]:
        """Compute/recompute aggregates for all date files present for this node."""
        node_raw_dir = self.readings_dir / node_id
        if not node_raw_dir.exists():
            return []

        date_files = [f for f in node_raw_dir.iterdir() if f.is_file() and f.suffix == ".jsonl"]
        date_files.sort(key=lambda f: f.name)

        aggregates: List[DailyAggregate] = []
        for f in date_files:
            # stem is YYYY-MM-DD
            target_date = f.stem
            agg = self.update_or_recompute(node_id, target_date)
            if agg is not None:
                aggregates.append(agg)

        return aggregates
