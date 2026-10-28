"""
CLI script to fetch, cache, and inspect historical weather and air-quality data for NavosEdge.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulation.historical_data import HistoricalDataAcquisition, LOCATIONS


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and cache historical context for NavosEdge")
    parser.add_argument("--location", default="bhubaneswar", choices=list(LOCATIONS.keys()), help="Configured location")
    parser.add_argument("--latitude", type=float, help="Explicit latitude")
    parser.add_argument("--longitude", type=float, help="Explicit longitude")
    parser.add_argument("--start", default="2024-09-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-10-06", help="End date (YYYY-MM-DD, 35 days default)")
    parser.add_argument("--cache-dir", default="data/historical_cache", help="Directory to cache downloaded data")
    parser.add_argument("--station-csv", help="Optional CPCB station CSV file to import")
    parser.add_argument("--force", action="store_true", help="Force re-download even if cached")
    parser.add_argument("--summary", action="store_true", default=True, help="Print summary of acquired records")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("fetch-historical")

    acq = HistoricalDataAcquisition(
        cache_dir=args.cache_dir,
        location=args.location,
        latitude=args.latitude,
        longitude=args.longitude,
    )

    series = acq.build_context_series(args.start, args.end, station_csv=args.station_csv)
    logger.info("Successfully assembled %d hourly context records for %s (%s to %s)", len(series), acq.location_name, args.start, args.end)

    if args.summary and series:
        weather_provs = set(r.weather_provenance for r in series)
        pm_provs = set(r.pm_provenance for r in series)
        t_vals = [r.temperature_C for r in series if not r.is_missing]
        h_vals = [r.humidity_pct for r in series if not r.is_missing]
        pm25_vals = [r.pm25 for r in series if r.pm25 is not None]
        pm10_vals = [r.pm10 for r in series if r.pm10 is not None]

        summary = {
            "location": acq.location_name,
            "coordinates": f"{acq.latitude}, {acq.longitude}",
            "date_range": f"{args.start} to {args.end}",
            "total_hourly_records": len(series),
            "weather_provenance": list(weather_provs),
            "pm_provenance": list(pm_provs),
            "temperature_range_C": [round(min(t_vals), 1), round(max(t_vals), 1)] if t_vals else [],
            "humidity_range_pct": [round(min(h_vals), 1), round(max(h_vals), 1)] if h_vals else [],
            "pm25_range": [round(min(pm25_vals), 1), round(max(pm25_vals), 1)] if pm25_vals else [],
            "pm10_range": [round(min(pm10_vals), 1), round(max(pm10_vals), 1)] if pm10_vals else [],
            "missing_records": sum(1 for r in series if r.is_missing),
        }
        print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
