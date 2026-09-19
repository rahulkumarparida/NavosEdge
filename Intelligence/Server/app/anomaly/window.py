"""
Rolling window manager for bounded-memory observation history.

Maintains a fixed-capacity deque of recent observations, evicting entries
older than the configured window.  Designed to be populated from JSONL
history on disk and then kept up-to-date as new readings arrive.
"""

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


class Observation:
    """A single validated observation with its timestamp and feature values."""

    __slots__ = ("timestamp", "features")

    def __init__(self, timestamp: datetime, features: Dict[str, Optional[float]]):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        self.timestamp = timestamp
        self.features = features  # feature_name -> value or None

    def __repr__(self) -> str:
        avail = sum(1 for v in self.features.values() if v is not None)
        return f"Observation(ts={self.timestamp.isoformat()}, features={avail}/{len(self.features)})"


class RollingWindow:
    """
    Bounded-memory rolling window of recent observations.

    Parameters
    ----------
    window_hours : int
        Maximum age of observations to keep (default 24).
    max_size : int
        Hard cap on the number of observations (protects against
        extremely high-frequency data).  Default 10 000.
    """

    def __init__(self, window_hours: int = 24, max_size: int = 10_000):
        self.window_hours = window_hours
        self.max_size = max_size
        self._data: deque[Observation] = deque(maxlen=max_size)

    # --- Mutation ---

    def add(self, obs: Observation) -> None:
        """Append a new observation and evict stale entries."""
        self._data.append(obs)
        self._evict()

    def load_bulk(self, observations: List[Observation]) -> None:
        """
        Replace window contents from a sorted list (oldest-first).
        Used when re-loading history from disk.
        """
        self._data.clear()
        for obs in observations:
            self._data.append(obs)
        self._evict()

    # --- Query ---

    def count(self) -> int:
        return len(self._data)

    def is_empty(self) -> bool:
        return len(self._data) == 0

    def newest(self) -> Optional[Observation]:
        return self._data[-1] if self._data else None

    def oldest(self) -> Optional[Observation]:
        return self._data[0] if self._data else None

    def time_span_seconds(self) -> float:
        """Total seconds between oldest and newest observation."""
        if len(self._data) < 2:
            return 0.0
        return (self._data[-1].timestamp - self._data[0].timestamp).total_seconds()

    def get_values(self, feature_name: str) -> List[float]:
        """
        Return non-None values for the named feature, in chronological order.
        """
        return [
            obs.features[feature_name]
            for obs in self._data
            if feature_name in obs.features and obs.features[feature_name] is not None
        ]

    def get_time_series(
        self, feature_name: str
    ) -> List[Tuple[datetime, float]]:
        """
        Return (timestamp, value) pairs for the named feature,
        excluding None values, in chronological order.
        """
        return [
            (obs.timestamp, obs.features[feature_name])
            for obs in self._data
            if feature_name in obs.features and obs.features[feature_name] is not None
        ]

    def get_recent(self, n: int) -> List[Observation]:
        """Return the most recent n observations."""
        if n >= len(self._data):
            return list(self._data)
        return list(self._data)[-n:]

    def all_observations(self) -> List[Observation]:
        return list(self._data)

    def available_features(self) -> set:
        """Return the set of feature names that have at least one non-None value."""
        features: set = set()
        for obs in self._data:
            for k, v in obs.features.items():
                if v is not None:
                    features.add(k)
        return features

    # --- Internal ---

    def _evict(self) -> None:
        """Remove observations older than the window."""
        if not self._data:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.window_hours)
        while self._data and self._data[0].timestamp < cutoff:
            self._data.popleft()
