"""
Processing pipeline — orchestrates validation, inference, storage and events.
"""

import logging
import uuid

from app.schemas.sensor import SensorPayload
from app.schemas.responses import ReadingAccepted
from app.services.events import EventService
from app.services.inference import InferenceAdapter
from app.services.node_registry import NodeRegistry
from app.storage.jsonl_store import JsonlStorageService
from app.services.pipeline import ModularPipeline

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(
        self,
        inference_adapter: InferenceAdapter,
        node_registry: NodeRegistry,
        storage: JsonlStorageService,
        event_service: EventService,
    ) -> None:
        self.inference_adapter = inference_adapter
        self.node_registry = node_registry
        self.storage = storage
        self.event_service = event_service
        self.pipeline = ModularPipeline()

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

        # Persist
        await self.storage.append_reading(node_id, record)

        # Publish SSE event
        summary = {
            "reading_id": reading_id,
            "timestamp": payload_dict["timestamp"],
            "gas_class": inference_result.gas_class,
            "safety_status": inference_result.safety_status,
            "advisory_level": pipeline_results.advisory.level,
            "health_status": pipeline_results.health.status,
            "is_anomalous": pipeline_results.anomaly.is_anomalous
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
