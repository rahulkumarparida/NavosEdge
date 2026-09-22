"""
Rolling 48-hour JSONL data store for the forecast plugin.

Design decisions:
- One JSONL file per node per calendar day: {node_id}/{YYYY-MM-DD}.jsonl
- Append-only writes with per-node threading locks.
- Reads stream line-by-line — never load entire history into RAM.
- Automatic cleanup of records older than the retention window.
- Completely independent of the main sensor JSONL store.
"""

import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ForecastStore:
    """File-based rolling time-series store for forecast plugin."""

    def __init__(
        self,
        storage_dir: Path,
        retention_hours: int = 48,
        max_file_size_mb: float = 10.0,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.retention_hours = retention_hours
        self.max_file_size_mb = max_file_size_mb
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _lock_for(self, node_id: str) -> threading.Lock:
        with self._locks_lock:
            if node_id not in self._locks:
                self._locks[node_id] = threading.Lock()
            return self._locks[node_id]

    def _node_dir(self, node_id: str) -> Path:
        return self.storage_dir / node_id

    def _file_for_date(self, node_id: str, d: date) -> Path:
        return self._node_dir(node_id) / f"{d.isoformat()}.jsonl"

    def _current_file(self, node_id: str) -> Path:
        return self._file_for_date(node_id, date.today())

    @staticmethod
    def _parse_ts(raw: str | None) -> Optional[datetime]:
        if raw is None:
            return None
        try:
            ts = datetime.fromisoformat(raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    def _candidate_files(self, node_id: str, hours: int) -> List[Path]:
        """Return JSONL files that *could* contain data within the window."""
        node_dir = self._node_dir(node_id)
        if not node_dir.exists():
            return []

        dates_needed: set[str] = set()
        for offset in range(hours // 24 + 2):
            d = (date.today() - timedelta(days=offset)).isoformat()
            dates_needed.add(d)

        files: list[Path] = []
        for f in node_dir.iterdir():
            if f.is_file() and f.suffix == ".jsonl":
                stem = f.stem  # YYYY-MM-DD
                if stem in dates_needed:
                    files.append(f)
        files.sort(key=lambda p: p.name)
        return files

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    def append(self, node_id: str, record: dict) -> None:
        """Append a single record (dict) as a JSON line."""
        lock = self._lock_for(node_id)
        with lock:
            fp = self._current_file(node_id)
            fp.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, default=str) + "\n"
            with open(fp, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    def _stream_records(
        self, node_id: str, hours: int, max_records: int = 50_000
    ) -> Iterator[dict]:
        """Yield records within the time window, oldest first."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        count = 0
        for fp in self._candidate_files(node_id, hours):
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = self._parse_ts(rec.get("timestamp"))
                        if ts is None or ts < cutoff:
                            continue
                        yield rec
                        count += 1
                        if count >= max_records:
                            return
            except OSError as exc:
                logger.warning("Error reading %s: %s", fp, exc)

    def get_history(
        self, node_id: str, hours: int | None = None, max_records: int = 50_000
    ) -> List[dict]:
        """Return records within the retention window."""
        lock = self._lock_for(node_id)
        with lock:
            h = hours if hours is not None else self.retention_hours
            return list(self._stream_records(node_id, h, max_records))

    def get_record_count(self, node_id: str) -> int:
        lock = self._lock_for(node_id)
        with lock:
            total = 0
            for fp in self._candidate_files(node_id, self.retention_hours):
                try:
                    with open(fp, "rb") as fh:
                        total += sum(1 for _ in fh)
                except OSError:
                    pass
            return total

    def get_time_range(
        self, node_id: str
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Return (oldest, newest) timestamps in the retention window."""
        lock = self._lock_for(node_id)
        with lock:
            oldest: Optional[datetime] = None
            newest: Optional[datetime] = None
            for fp in self._candidate_files(node_id, self.retention_hours):
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rec = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            ts = self._parse_ts(rec.get("timestamp"))
                            if ts is None:
                                continue
                            if oldest is None or ts < oldest:
                                oldest = ts
                            if newest is None or ts > newest:
                                newest = ts
                except OSError:
                    pass
            return oldest, newest

    # ------------------------------------------------------------------ #
    #  Cleanup                                                             #
    # ------------------------------------------------------------------ #

    def delete_expired(self, node_id: str | None = None) -> int:
        """
        Remove records older than the retention window.

        Strategy: delete entire files whose date is entirely outside the
        window. For files on the boundary, rewrite keeping only valid records.

        Returns the number of records deleted.
        """
        if node_id is not None:
            return self._delete_expired_for_node(node_id)

        total = 0
        if not self.storage_dir.exists():
            return 0
        for child in self.storage_dir.iterdir():
            if child.is_dir():
                total += self._delete_expired_for_node(child.name)
        return total

    def _delete_expired_for_node(self, node_id: str) -> int:
        lock = self._lock_for(node_id)
        with lock:
            node_dir = self._node_dir(node_id)
            if not node_dir.exists():
                return 0

            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
            cutoff_date = (date.today() - timedelta(days=self.retention_hours // 24 + 1))
            deleted = 0

            for fp in list(node_dir.iterdir()):
                if not fp.is_file() or fp.suffix != ".jsonl":
                    continue

                # If the file date is entirely before the cutoff, delete whole file
                try:
                    file_date = date.fromisoformat(fp.stem)
                except ValueError:
                    continue

                if file_date < cutoff_date:
                    try:
                        # Count lines before deleting
                        with open(fp, "rb") as fh:
                            deleted += sum(1 for _ in fh)
                        fp.unlink()
                        logger.info("Deleted expired forecast file %s", fp)
                    except OSError as exc:
                        logger.error("Failed to delete %s: %s", fp, exc)
                    continue

                # Boundary file — rewrite, keeping only valid records
                try:
                    kept: list[str] = []
                    removed = 0
                    with open(fp, "r", encoding="utf-8") as fh:
                        for line in fh:
                            stripped = line.strip()
                            if not stripped:
                                continue
                            try:
                                rec = json.loads(stripped)
                            except json.JSONDecodeError:
                                removed += 1
                                continue
                            ts = self._parse_ts(rec.get("timestamp"))
                            if ts is not None and ts >= cutoff:
                                kept.append(stripped + "\n")
                            else:
                                removed += 1

                    if removed > 0:
                        with open(fp, "w", encoding="utf-8") as fh:
                            fh.writelines(kept)
                        deleted += removed
                except OSError as exc:
                    logger.error("Error rewriting %s: %s", fp, exc)

            # Remove empty node directory
            try:
                if node_dir.exists() and not any(node_dir.iterdir()):
                    node_dir.rmdir()
            except OSError:
                pass

            return deleted

    # ------------------------------------------------------------------ #
    #  Health                                                              #
    # ------------------------------------------------------------------ #

    def check_health(self) -> bool:
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            probe = self.storage_dir / ".healthcheck"
            probe.write_text("ok")
            probe.unlink()
            return True
        except Exception:
            return False
