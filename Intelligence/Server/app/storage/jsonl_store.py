import asyncio
import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class JsonlStorageService:
    def __init__(self, data_dir: Path, max_file_size_mb: float = 50.0, max_files_per_node: int = 30):
        self.data_dir = Path(data_dir)
        self.max_file_size_mb = max_file_size_mb
        self.max_files_per_node = max_files_per_node
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def _get_node_lock(self, node_id: str) -> threading.Lock:
        """Returns or creates a lock for the given node_id"""
        with self._locks_lock:
            if node_id not in self._locks:
                self._locks[node_id] = threading.Lock()
            return self._locks[node_id]

    def _get_current_file(self, node_id: str) -> Path:
        """Returns the path for today's JSONL file"""
        today_str = date.today().isoformat()
        return self.data_dir / "readings" / node_id / f"{today_str}.jsonl"

    def _rotate_if_needed(self, filepath: Path, node_id: str) -> None:
        """
        If file exceeds max_file_size_mb, rename it with a rotation suffix.
        Delete oldest files if count exceeds max_files_per_node.
        """
        if not filepath.exists():
            return
            
        size_mb = filepath.stat().st_size / (1024 * 1024)
        if size_mb > self.max_file_size_mb:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            rotated_path = filepath.with_name(f"{filepath.name}.{timestamp}")
            filepath.rename(rotated_path)
            logger.info(f"Rotated file {filepath} to {rotated_path}")

        # Enforce max files per node
        node_dir = self.data_dir / "readings" / node_id
        if node_dir.exists():
            all_files = [f for f in node_dir.iterdir() if f.is_file() and ".jsonl" in f.name]
            all_files.sort(key=lambda x: x.stat().st_mtime)
            
            while len(all_files) > self.max_files_per_node:
                oldest = all_files.pop(0)
                try:
                    oldest.unlink()
                    logger.info(f"Deleted old rotated file {oldest}")
                except OSError as e:
                    logger.error(f"Failed to delete old file {oldest}: {e}")

    def _sync_append_reading(self, node_id: str, record: dict) -> None:
        lock = self._get_node_lock(node_id)
        with lock:
            try:
                filepath = self._get_current_file(node_id)
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                json_line = json.dumps(record) + "\n"
                
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(json_line)
                    f.flush()
                
                self._rotate_if_needed(filepath, node_id)
            except Exception as e:
                logger.error(f"Error appending reading for node {node_id}: {e}", exc_info=True)

    async def append_reading(self, node_id: str, record: dict) -> None:
        """
        Serialize record to JSON, append a newline.
        Use asyncio run_in_executor to avoid blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_append_reading, node_id, record)

    def _read_last_line(self, filepath: Path) -> Optional[str]:
        """
        Efficiently read the last non-empty line from a file without loading the whole file.
        Seek from end, read backwards in chunks of 8192 bytes until a newline is found.
        """
        if not filepath.exists() or filepath.stat().st_size == 0:
            return None
            
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            chunk_size = min(8192, file_size)
            offset = file_size
            
            buffer = b""
            while offset > 0:
                read_size = min(chunk_size, offset)
                offset -= read_size
                f.seek(offset)
                chunk = f.read(read_size)
                buffer = chunk + buffer
                
                parts = buffer.split(b'\n')
                
                # If we have at least 2 parts, we've found at least one complete line
                # Note: parts[-1] might be empty if the file ends with \n
                if len(parts) > 1:
                    for part in reversed(parts):
                        if part.strip():
                            return part.decode('utf-8', errors='replace').strip()
                            
                # Otherwise, keep reading backwards
                buffer = parts[0]
                
            if buffer.strip():
                return buffer.decode('utf-8', errors='replace').strip()
                
        return None

    def _read_lines_from_end(self, filepath: Path):
        """Helper to yield lines from end for fallback parsing"""
        if not filepath.exists() or filepath.stat().st_size == 0:
            return
            
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            chunk_size = min(8192, file_size)
            offset = file_size
            
            buffer = b""
            while offset > 0:
                read_size = min(chunk_size, offset)
                offset -= read_size
                f.seek(offset)
                chunk = f.read(read_size)
                buffer = chunk + buffer
                
                parts = buffer.split(b'\n')
                buffer = parts[0]
                
                for part in reversed(parts[1:]):
                    if part.strip():
                        yield part.decode('utf-8', errors='replace').strip()
            
            if buffer.strip():
                yield buffer.decode('utf-8', errors='replace').strip()

    def _sync_get_latest_reading(self, node_id: str) -> Optional[dict]:
        lock = self._get_node_lock(node_id)
        with lock:
            node_dir = self.data_dir / "readings" / node_id
            if not node_dir.exists():
                return None
            
            all_files = [f for f in node_dir.iterdir() if f.is_file() and ".jsonl" in f.name]
            if not all_files:
                return None
                
            # Sort by modification time, newest first
            all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            for filepath in all_files:
                try:
                    for line in self._read_lines_from_end(filepath):
                        try:
                            return json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(f"Malformed JSON in line of {filepath}")
                            continue
                except Exception as e:
                    logger.error(f"Error reading latest from {filepath}: {e}", exc_info=True)
                    
            return None

    async def get_latest_reading(self, node_id: str) -> Optional[dict]:
        """
        Read the last valid line from the most recent JSONL file for this node.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_latest_reading, node_id)

    def _sync_get_readings_count(self, node_id: str) -> int:
        lock = self._get_node_lock(node_id)
        with lock:
            node_dir = self.data_dir / "readings" / node_id
            if not node_dir.exists():
                return 0
                
            all_files = [f for f in node_dir.iterdir() if f.is_file() and ".jsonl" in f.name]
            total_lines = 0
            
            for filepath in all_files:
                try:
                    with open(filepath, "rb") as f:
                        lines = sum(1 for _ in f)
                        total_lines += lines
                except Exception as e:
                    logger.error(f"Error counting lines in {filepath}: {e}", exc_info=True)
                    
            return total_lines

    async def get_readings_count(self, node_id: str) -> int:
        """
        Count total lines across all JSONL files for this node.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_readings_count, node_id)

    def check_storage_health(self) -> bool:
        """
        Verify that data_dir exists and is writable.
        """
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.data_dir / ".healthcheck"
            with open(test_file, "w") as f:
                f.write("ok")
            test_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Storage health check failed: {e}", exc_info=True)
            return False
