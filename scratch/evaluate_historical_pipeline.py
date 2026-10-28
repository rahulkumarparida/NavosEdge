"""
Benchmark and evaluation script for NavosEdge historical replay and pipeline verification.
Replays the generated 35-day dataset (10,056 records) through ProcessingService,
evaluating retention, daily aggregates, forecast accuracy vs. persistence,
anomaly detection, and advisory transitions.
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from Simulator.session import load_dataset
from Simulator.client import IntelligenceClient
from app.schemas.sensor import SensorPayload
from app.services.processing import ProcessingService
from app.services.inference import TinyGasNetAdapter
from app.services.node_registry import NodeRegistry
from app.storage.jsonl_store import JsonlStorageService
from app.storage.daily_aggregates import DailyAggregateService
from app.storage.local_dataset_logger import LocalDatasetLogger
from app.services.events import EventService
from app.anomaly.engine import AnomalyEngine
from app.forecast.plugin import ForecastPlugin
from app.forecast.config import ForecastSettings
from app.forecast.model import _fit_ar, _ar_predict
from app.aqi.service import AQIService
from unittest.mock import AsyncMock


class DirectClient(IntelligenceClient):
    def __init__(self, service: ProcessingService) -> None:
        super().__init__("http://localtest", 10.0)
        self.service = service
        self.results = []

    async def submit(self, payload: dict) -> dict:
        parsed = SensorPayload.model_validate(payload)
        res = await self.service.process_reading(parsed)
        self.results.append(res)
        return {"status": "accepted"}


async def run_benchmark():
    dataset_path = Path("test_data/historical_35d.jsonl")
    if not dataset_path.exists():
        print(f"Error: dataset not found at {dataset_path}")
        return

    records = load_dataset(dataset_path)
    print(f"Loaded {len(records)} records from {dataset_path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="navos_hist_bench_"))
    try:
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        inference_adapter = TinyGasNetAdapter(artifacts_dir=artifacts_dir)
        inference_adapter.load()
        node_registry = NodeRegistry()
        storage = JsonlStorageService(data_dir=temp_dir, max_files_per_node=60)
        event_service = EventService()
        anomaly_engine = AnomalyEngine()
        forecast_settings = ForecastSettings(
            STORAGE_DIR=temp_dir / "forecast",
            RETENTION_HOURS=72,
            DEFAULT_HORIZON_MINUTES=60,
            DEFAULT_SAMPLING_INTERVAL_MINUTES=5,
            MIN_HISTORY_POINTS=12,
        )
        forecast_plugin = ForecastPlugin()
        forecast_plugin.initialize(settings=forecast_settings)
        aqi_service = AQIService(storage_path=temp_dir / "aqi", standard="CPCB")
        local_logger = LocalDatasetLogger(dataset_dir=temp_dir / "local_dataset")

        service = ProcessingService(
            inference_adapter=inference_adapter,
            node_registry=node_registry,
            storage=storage,
            event_service=event_service,
            anomaly_engine=anomaly_engine,
            forecast_plugin=forecast_plugin,
            aqi_service=aqi_service,
            local_dataset_logger=local_logger,
        )
        service._forward_to_manager = AsyncMock()

        client = DirectClient(service)

        print("\n--- Starting 35-Day Accelerated Replay ---")
        start_time = time.perf_counter()

        # Batch submission without artificial sleep to test peak ingestion throughput
        advisories = {"NORMAL": 0, "MODERATE": 0, "HIGH": 0, "SEVERE": 0, "CRITICAL": 0}
        anomalies_detected = 0

        for idx, rec in enumerate(records):
            await client.submit(rec)
            res = client.results[-1]
            sev = res.advisory.severity if res.advisory else "NORMAL"
            advisories[sev] = advisories.get(sev, 0) + 1
            if getattr(res, "anomaly", None) and res.anomaly.is_anomaly:
                anomalies_detected += 1

        end_time = time.perf_counter()
        elapsed_sec = end_time - start_time
        rate = len(records) / elapsed_sec if elapsed_sec > 0 else 0.0

        print(f"Replay completed in {elapsed_sec:.2f} seconds ({rate:.1f} records/sec)")
        print(f"Simulated time span: 35 days (50,400 minutes) replayed in {elapsed_sec:.2f}s (Acceleration: {50400*60/elapsed_sec:.0f}x)")

        # Retention and partition files
        node_dir = temp_dir / "readings" / "hist-node-01"
        partition_files = list(node_dir.glob("*.jsonl"))
        print(f"\nStorage partitions: {len(partition_files)} daily files created")

        # Daily aggregates evaluation
        print("\n--- Daily Aggregates Evaluation ---")
        daily_service = DailyAggregateService(storage)
        days = sorted(list({rec["timestamp"][:10] for rec in records}))
        daily_summaries = []
        sufficient_days = 0
        for d in days:
            agg = await daily_service.get_or_compute_daily_aggregate("hist-node-01", d)
            if agg:
                daily_summaries.append(agg)
                if agg.get("data_sufficiency_pct", 0) >= 66.7:
                    sufficient_days += 1

        print(f"Total days processed: {len(daily_summaries)}")
        print(f"CPCB sufficient days (>=66.7% / 16h data): {sufficient_days}/{len(daily_summaries)}")
        first_day = daily_summaries[0]
        mid_day = daily_summaries[len(daily_summaries)//2]
        print(f"Sample Day 1 ({first_day['date']}): Samples={first_day['sample_count']}, Coverage={first_day['data_sufficiency_pct']}%, CPCB 24h AQI={first_day['aqi']['cpcb_24h_aqi']}")
        print(f"Sample Day 18 ({mid_day['date']}): Samples={mid_day['sample_count']}, Coverage={mid_day['data_sufficiency_pct']}%, CPCB 24h AQI={mid_day['aqi']['cpcb_24h_aqi']}")

        # Forecast Evaluation vs. Persistence (No future leakage, chronological split)
        print("\n--- Forecasting vs. Persistence Baseline Evaluation ---")
        pm25_series = [r["particulate_matter"]["PM2_5"] for r in records if "particulate_matter" in r]
        pm10_series = [r["particulate_matter"]["PM10"] for r in records if "particulate_matter" in r]

        # 80/20 chronological split (28 days train, 7 days test)
        split_idx = int(len(pm25_series) * 0.8)
        horizon_steps = 12  # 60 minutes = 12 * 5-min intervals

        def evaluate_forecast(series, name):
            train = series[:split_idx]
            test = series[split_idx:]
            res = _fit_ar(train, order=3)
            coeffs, intercept = res if res else ([1.0, 0.0, 0.0], 0.0)

            p_preds = []
            ar_preds = []
            actuals = []

            for step in range(len(test) - horizon_steps):
                hist = list(train) + list(test[:step])
                # Persistence: y_{t+h} = y_t
                p_preds.append(hist[-1])
                # AR forecast
                ar_pred_seq = _ar_predict(coeffs, intercept, hist, horizon_steps)
                ar_preds.append(ar_pred_seq[-1])
                actuals.append(test[step + horizon_steps])

            p_mae = sum(abs(p - a) for p, a in zip(p_preds, actuals)) / len(actuals)
            p_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(p_preds, actuals)) / len(actuals))
            ar_mae = sum(abs(p - a) for p, a in zip(ar_preds, actuals)) / len(actuals)
            ar_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(ar_preds, actuals)) / len(actuals))

            return {
                "name": name,
                "persistence_mae": p_mae,
                "persistence_rmse": p_rmse,
                "ar_mae": ar_mae,
                "ar_rmse": ar_rmse,
                "eval_points": len(actuals),
            }

        pm25_eval = evaluate_forecast(pm25_series, "PM2.5")
        pm10_eval = evaluate_forecast(pm10_series, "PM10")

        print(f"PM2.5 (1-hr horizon, {pm25_eval['eval_points']} evaluation points):")
        print(f"  Persistence: MAE = {pm25_eval['persistence_mae']:.2f} µg/m³, RMSE = {pm25_eval['persistence_rmse']:.2f} µg/m³")
        print(f"  AR Model:    MAE = {pm25_eval['ar_mae']:.2f} µg/m³, RMSE = {pm25_eval['ar_rmse']:.2f} µg/m³")
        print(f"PM10 (1-hr horizon, {pm10_eval['eval_points']} evaluation points):")
        print(f"  Persistence: MAE = {pm10_eval['persistence_mae']:.2f} µg/m³, RMSE = {pm10_eval['persistence_rmse']:.2f} µg/m³")
        print(f"  AR Model:    MAE = {pm10_eval['ar_mae']:.2f} µg/m³, RMSE = {pm10_eval['ar_rmse']:.2f} µg/m³")

        print("\n--- Advisory & Anomaly Distribution ---")
        print(f"Anomalies detected: {anomalies_detected}")
        for sev, cnt in advisories.items():
            print(f"  {sev}: {cnt} ({cnt/len(records)*100:.1f}%)")

        # Save summary JSON for report
        summary_out = {
            "elapsed_seconds": elapsed_sec,
            "records_replayed": len(records),
            "records_per_second": rate,
            "acceleration_factor": 50400*60/elapsed_sec,
            "storage_partitions": len(partition_files),
            "sufficient_days": sufficient_days,
            "total_days": len(daily_summaries),
            "anomalies_detected": anomalies_detected,
            "advisories": advisories,
            "pm25_eval": pm25_eval,
            "pm10_eval": pm10_eval,
        }
        with open("test_data/benchmark_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary_out, f, indent=2)
        print("\nBenchmark summary saved to test_data/benchmark_summary.json")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
