"""
Processing pipeline — orchestrates validation, inference, storage and events.
"""

import asyncio
import logging
import uuid

from app.schemas.sensor import SensorPayload
from app.schemas.responses import ReadingAccepted
from app.schemas.anomaly import AnomalyReport
from app.schemas.source_classification import SourceClassificationResult
from app.services.events import EventService
from app.services.inference import InferenceAdapter
from app.services.node_registry import NodeRegistry
from app.storage.jsonl_store import JsonlStorageService
from app.services.pipeline import ModularPipeline
from app.anomaly.engine import AnomalyEngine
from app.source_classifier.classifier import SourceClassifier
from app.forecast.plugin import ForecastPlugin
from app.schemas.forecast import ForecastReadingInput

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(
        self,
        inference_adapter: InferenceAdapter,
        node_registry: NodeRegistry,
        storage: JsonlStorageService,
        event_service: EventService,
        anomaly_engine: AnomalyEngine,
        source_classifier: SourceClassifier | None = None,
        forecast_plugin: ForecastPlugin | None = None,
    ) -> None:
        self.inference_adapter = inference_adapter
        self.node_registry = node_registry
        self.storage = storage
        self.event_service = event_service
        self.anomaly_engine = anomaly_engine
        self.source_classifier = source_classifier
        self.forecast_plugin = forecast_plugin
        self.pipeline = ModularPipeline()
        # Track which nodes have been history-primed
        self._primed_nodes: set = set()

    async def _ensure_history_loaded(self, node_id: str) -> None:
        """
        On first encounter with a node, load recent history from JSONL
        into the anomaly engine's rolling window.
        """
        if node_id in self._primed_nodes:
            return

        try:
            history = await self.storage.get_recent_readings(node_id, hours=24)
            if history:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, self.anomaly_engine.load_history, node_id, history
                )
                logger.info(
                    "Loaded %d historical records for node %s anomaly baseline",
                    len(history),
                    node_id,
                )
        except Exception as e:
            logger.warning(
                "Failed to load history for node %s: %s", node_id, e
            )

        self._primed_nodes.add(node_id)

    async def process_reading(self, payload: SensorPayload) -> ReadingAccepted:
        reading_id = uuid.uuid4().hex[:12]
        node_id = payload.node_id
        timestamp = payload.timestamp

        # Register with the node registry
        self.node_registry.register_reading(node_id, timestamp)

        # Extract model input features
        mq2_v = payload.gas_sensors.MQ2.voltage_V
        mq9_v = payload.gas_sensors.MQ9.voltage_V
        mq135_v = payload.gas_sensors.MQ135.voltage_V
        temperature_c = payload.environment.temperature_C
        humidity_pct = payload.environment.humidity_pct

        # Run inference
        inference_result = await self.inference_adapter.predict(
            mq2_v=mq2_v,
            mq9_v=mq9_v,
            mq135_v=mq135_v,
            temperature_c=temperature_c,
            humidity_pct=humidity_pct,
        )

        # Run the modular extended pipeline
        pipeline_results = self.pipeline.process(payload, inference_result)

        # Build storage record
        payload_dict = payload.model_dump(mode="json")
        record = {
            "reading_id": reading_id,
            "node_id": node_id,
            "timestamp": payload_dict["timestamp"],
            "environment": payload_dict["environment"],
            "particulate_matter": payload_dict["particulate_matter"],
            "gas_sensors": payload_dict["gas_sensors"],
            "inference": inference_result.model_dump(mode="json"),
            "pipeline": pipeline_results.model_dump(mode="json"),
        }

        # Persist to JSONL (must happen BEFORE anomaly analysis so history is on disk)
        await self.storage.append_reading(node_id, record)

        # --- Anomaly detection ---
        await self._ensure_history_loaded(node_id)

        try:
            loop = asyncio.get_event_loop()
            anomaly_dict = await loop.run_in_executor(
                None, self.anomaly_engine.analyse, node_id, record
            )
            anomaly_report = AnomalyReport.from_engine_dict(anomaly_dict)
            pipeline_results.anomaly_report = anomaly_report
        except Exception as e:
            logger.error(
                "Anomaly engine error for node %s: %s", node_id, e, exc_info=True
            )
            # Pipeline continues without anomaly report

        # --- Source classification (Phase 3) ---
        if self.source_classifier is not None and self.source_classifier.is_loaded:
            try:
                loop = asyncio.get_event_loop()
                sc_dict = await loop.run_in_executor(
                    None, self.source_classifier.classify, payload
                )
                sc_result = SourceClassificationResult.from_classifier_dict(sc_dict)
                pipeline_results.source_classification = sc_result
            except Exception as e:
                logger.error(
                    "Source classifier error for node %s: %s", node_id, e, exc_info=True
                )
                # Pipeline continues without source classification

        # --- Phase 4: Forward to forecast plugin ---
        if self.forecast_plugin is not None and self.forecast_plugin.is_initialized:
            try:
                forecast_reading = ForecastReadingInput(
                    node_id=node_id,
                    timestamp=payload.timestamp,
                    PM1_0=payload.particulate_matter.PM1_0,
                    PM2_5=payload.particulate_matter.PM2_5,
                    PM10=payload.particulate_matter.PM10,
                )
                await self.forecast_plugin.async_ingest(forecast_reading)
            except Exception as e:
                logger.error(
                    "Forecast plugin ingest error for node %s: %s", node_id, e, exc_info=True
                )
                # Pipeline continues without forecast ingestion

        # Publish SSE event
        summary = {
            "reading_id": reading_id,
            "timestamp": payload_dict["timestamp"],
            "gas_class": inference_result.gas_class,
            "safety_status": inference_result.safety_status,
            "advisory_level": pipeline_results.advisory.level,
            "health_status": pipeline_results.health.status,
            "is_anomalous": pipeline_results.anomaly.is_anomalous,
        }

        # Include anomaly report summary in SSE if available
        if pipeline_results.anomaly_report is not None:
            ar = pipeline_results.anomaly_report
            summary["anomaly_report"] = {
                "detected": ar.anomaly.detected,
                "severity": ar.anomaly.severity.value if hasattr(ar.anomaly.severity, 'value') else ar.anomaly.severity,
                "confidence": ar.data_quality.confidence.value if hasattr(ar.data_quality.confidence, 'value') else ar.data_quality.confidence,
                "system_state": ar.system_state.value if hasattr(ar.system_state, 'value') else ar.system_state,
            }

        # Include source classification summary in SSE if available
        if pipeline_results.source_classification is not None:
            sc = pipeline_results.source_classification
            summary["source_classification"] = {
                "top_source": sc.top_source,
                "status": sc.status.value if hasattr(sc.status, 'value') else sc.status,
                "is_uncertain": sc.uncertainty.is_uncertain if sc.uncertainty else True,
            }

        await self.event_service.publish(node_id, "new_reading", summary)

        logger.info("Processed reading %s for node %s", reading_id, node_id)
        return ReadingAccepted(
            node_id=node_id,
            reading_id=reading_id,
            timestamp=timestamp,
            inference=inference_result,
            pipeline=pipeline_results,
        )

