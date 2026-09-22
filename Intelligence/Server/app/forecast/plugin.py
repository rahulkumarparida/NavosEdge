"""
Forecast Plugin — unified interface for the forecast subsystem.

Provides:
    initialize(config)       — set up store and settings
    ingest(reading)          — add a PM reading to the rolling store
    forecast(node_id, ...)   — generate a forecast
    get_history(node_id)     — retrieve retained history / status
    delete_expired_data(...) — trigger cleanup
    shutdown()               — graceful teardown
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.forecast.config import ForecastSettings, get_forecast_settings
from app.forecast.model import generate_forecast
from app.forecast.store import ForecastStore
from app.schemas.forecast import (
    CleanupResponse,
    ForecastHistoryResponse,
    ForecastReadingAccepted,
    ForecastReadingInput,
    ForecastReliability,
    ForecastResponse,
    ForecastStatus,
)

logger = logging.getLogger(__name__)


class ForecastPlugin:
    """Stateful forecast plugin — one instance per server lifetime."""

    def __init__(self) -> None:
        self._store: Optional[ForecastStore] = None
        self._settings: Optional[ForecastSettings] = None
        self._initialized = False

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def initialize(self, settings: ForecastSettings | None = None) -> None:
        """Set up the plugin with the given (or default) settings."""
        self._settings = settings or get_forecast_settings()
        self._store = ForecastStore(
            storage_dir=self._settings.STORAGE_DIR,
            retention_hours=self._settings.RETENTION_HOURS,
            max_file_size_mb=self._settings.MAX_FILE_SIZE_MB,
        )
        self._settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info(
            "Forecast plugin initialized — storage=%s, retention=%dh",
            self._settings.STORAGE_DIR,
            self._settings.RETENTION_HOURS,
        )

    def shutdown(self) -> None:
        """Graceful shutdown — flush any pending state."""
        logger.info("Forecast plugin shutting down.")
        self._initialized = False
        self._store = None

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def _require_init(self) -> None:
        if not self._initialized or self._store is None:
            raise RuntimeError("Forecast plugin is not initialized.")

    # ------------------------------------------------------------------ #
    #  Ingest                                                              #
    # ------------------------------------------------------------------ #

    def ingest(self, reading: ForecastReadingInput) -> ForecastReadingAccepted:
        """Store a PM reading for future forecasting."""
        self._require_init()
        assert self._store is not None  # type guard

        record = {
            "timestamp": reading.timestamp.isoformat(),
            "node_id": reading.node_id,
            "is_synthetic": reading.is_synthetic,
        }
        for ch in self._settings.PM_CHANNELS:  # type: ignore[union-attr]
            val = getattr(reading, ch, None)
            if val is not None:
                record[ch] = val

        self._store.append(reading.node_id, record)

        return ForecastReadingAccepted(
            node_id=reading.node_id,
            timestamp=reading.timestamp,
            stored=True,
            message="Reading ingested for forecasting.",
        )

    async def async_ingest(
        self, reading: ForecastReadingInput
    ) -> ForecastReadingAccepted:
        """Async wrapper around ingest."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.ingest, reading)

    # ------------------------------------------------------------------ #
    #  Forecast                                                            #
    # ------------------------------------------------------------------ #

    def forecast(
        self,
        node_id: str,
        horizon_minutes: int | None = None,
        sampling_interval_minutes: int | None = None,
    ) -> ForecastResponse:
        """Generate a forecast for the given node."""
        self._require_init()
        assert self._store is not None and self._settings is not None

        h = horizon_minutes or self._settings.DEFAULT_HORIZON_MINUTES
        si = sampling_interval_minutes or self._settings.DEFAULT_SAMPLING_INTERVAL_MINUTES

        records = self._store.get_history(node_id)

        return generate_forecast(
            records=records,
            channels=self._settings.PM_CHANNELS,
            node_id=node_id,
            horizon_minutes=h,
            sampling_interval_minutes=si,
            min_history_points=self._settings.MIN_HISTORY_POINTS,
            max_ar_order=self._settings.MAX_AR_ORDER,
            trend_threshold=self._settings.TREND_THRESHOLD,
        )

    async def async_forecast(
        self,
        node_id: str,
        horizon_minutes: int | None = None,
        sampling_interval_minutes: int | None = None,
    ) -> ForecastResponse:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.forecast, node_id, horizon_minutes, sampling_interval_minutes
        )

    # ------------------------------------------------------------------ #
    #  History / status                                                    #
    # ------------------------------------------------------------------ #

    def get_history(self, node_id: str) -> ForecastHistoryResponse:
        """Return metadata about the stored history for a node."""
        self._require_init()
        assert self._store is not None and self._settings is not None

        count = self._store.get_record_count(node_id)
        oldest, newest = self._store.get_time_range(node_id)

        # Determine which channels have data
        channels: list[str] = []
        if count > 0:
            # Sample the first record to check available channels
            recs = self._store.get_history(node_id, max_records=1)
            if recs:
                for ch in self._settings.PM_CHANNELS:
                    if ch in recs[0] and recs[0][ch] is not None:
                        channels.append(ch)

        return ForecastHistoryResponse(
            node_id=node_id,
            total_records=count,
            oldest_timestamp=oldest,
            newest_timestamp=newest,
            retention_hours=self._settings.RETENTION_HOURS,
            storage_path=str(self._settings.STORAGE_DIR / node_id),
            channels_available=channels,
        )

    async def async_get_history(self, node_id: str) -> ForecastHistoryResponse:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_history, node_id)

    # ------------------------------------------------------------------ #
    #  Cleanup                                                             #
    # ------------------------------------------------------------------ #

    def delete_expired_data(
        self, node_id: str | None = None
    ) -> CleanupResponse:
        """Delete records older than the retention window."""
        self._require_init()
        assert self._store is not None

        deleted = self._store.delete_expired(node_id)
        return CleanupResponse(
            node_id=node_id,
            records_deleted=deleted,
            message=(
                f"Cleanup complete. {deleted} expired record(s) removed."
            ),
        )

    async def async_delete_expired(
        self, node_id: str | None = None
    ) -> CleanupResponse:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.delete_expired_data, node_id)
