"""
Persistent SQLite data layer for the NavosEdge Emergency Response &
Smart Actuator subsystem (Phase 1).

Uses Python's built-in `sqlite3` with WAL journal mode, strict foreign-key
enforcement, explicit transaction boundaries, versioned schema migrations,
and thread-safe access suitable for FastAPI.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.emergency.schemas import (
    ActuatorCommandLog,
    ActuatorCommandResponse,
    ActuatorConnectionStatus,
    ActuatorRegistration,
    ActuatorResponse,
    ActuatorState,
    CommandExecutionStatus,
    ConsentStatus,
    EmergencyContactCreate,
    EmergencyContactResponse,
    EmergencyContactUpdate,
    EmergencyEventCreate,
    EmergencyEventResponse,
    EmergencyEventStatus,
    EmergencySeverity,
    HumanAcknowledgementStatus,
    NodeOperationalStatus,
    NodeRegistration,
    NodeResponse,
    NotificationChannel,
    NotificationCreate,
    NotificationDeliveryStatus,
    NotificationResponse,
    ResidentCreate,
    ResidentResponse,
    ResidentUpdate,
    ensure_utc,
    utc_now,
)
from app.services.node_registry import NodeRegistry

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Typed Database Exceptions
# ---------------------------------------------------------------------------


class EmergencyDatabaseError(Exception):
    """Base exception for emergency database operations."""


class DuplicateRecordError(EmergencyDatabaseError):
    """Raised when attempting to insert a record with an existing primary key."""


class ForeignKeyViolationError(EmergencyDatabaseError):
    """Raised when a foreign key reference is invalid or deletion is restricted."""


class RecordNotFoundError(EmergencyDatabaseError):
    """Raised when an update targets a non-existent record."""


# ---------------------------------------------------------------------------
# Timestamp & Serialization Helpers
# ---------------------------------------------------------------------------


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    normalized = ensure_utc(dt)
    assert normalized is not None
    return normalized.isoformat()


def _iso_to_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Schema DDL (Migration v1)
# ---------------------------------------------------------------------------

MIGRATION_V1_DDL: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version     INTEGER PRIMARY KEY,
        description TEXT NOT NULL,
        applied_at  TEXT NOT NULL
    );
    """,
    # 1. registered_nodes
    """
    CREATE TABLE IF NOT EXISTS registered_nodes (
        node_id            TEXT PRIMARY KEY,
        node_name          TEXT NOT NULL,
        location           TEXT NOT NULL,
        operational_status TEXT NOT NULL DEFAULT 'ONLINE',
        resident_id        TEXT DEFAULT NULL,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL,
        FOREIGN KEY (resident_id) REFERENCES residents(resident_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # 2. residents
    """
    CREATE TABLE IF NOT EXISTS residents (
        resident_id        TEXT PRIMARY KEY,
        full_name          TEXT NOT NULL,
        age                INTEGER DEFAULT NULL CHECK (age IS NULL OR (age >= 0 AND age <= 130)),
        address_location   TEXT NOT NULL,
        associated_node_id TEXT DEFAULT NULL,
        safety_information TEXT DEFAULT NULL,
        consent_status     TEXT NOT NULL DEFAULT 'GRANTED',
        active_status      INTEGER NOT NULL DEFAULT 1 CHECK (active_status IN (0, 1)),
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL,
        FOREIGN KEY (associated_node_id) REFERENCES registered_nodes(node_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # 3. emergency_contacts
    """
    CREATE TABLE IF NOT EXISTS emergency_contacts (
        contact_id         TEXT PRIMARY KEY,
        resident_id        TEXT NOT NULL,
        full_name          TEXT NOT NULL,
        phone_number       TEXT NOT NULL,
        relationship       TEXT NOT NULL,
        priority           INTEGER NOT NULL DEFAULT 1 CHECK (priority >= 1 AND priority <= 100),
        preferred_channels TEXT NOT NULL,
        consent_status     TEXT NOT NULL DEFAULT 'GRANTED',
        active_status      INTEGER NOT NULL DEFAULT 1 CHECK (active_status IN (0, 1)),
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL,
        FOREIGN KEY (resident_id) REFERENCES residents(resident_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # 4. actuators
    """
    CREATE TABLE IF NOT EXISTS actuators (
        actuator_id        TEXT PRIMARY KEY,
        associated_node_id TEXT NOT NULL,
        actuator_type      TEXT NOT NULL,
        device_name        TEXT NOT NULL,
        ip_address         TEXT DEFAULT NULL,
        connection_status  TEXT NOT NULL DEFAULT 'OFFLINE',
        current_state      TEXT NOT NULL DEFAULT 'OFF',
        last_heartbeat     TEXT DEFAULT NULL,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL,
        FOREIGN KEY (associated_node_id) REFERENCES registered_nodes(node_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # 5. emergency_events
    """
    CREATE TABLE IF NOT EXISTS emergency_events (
        event_id           TEXT PRIMARY KEY,
        associated_node_id TEXT NOT NULL,
        resident_id        TEXT DEFAULT NULL,
        event_type         TEXT NOT NULL,
        severity           TEXT NOT NULL,
        event_status       TEXT NOT NULL DEFAULT 'DETECTED',
        detected_at        TEXT NOT NULL,
        acknowledged_at    TEXT DEFAULT NULL,
        resolved_at        TEXT DEFAULT NULL,
        event_metadata     TEXT NOT NULL DEFAULT '{}',
        escalation_level   INTEGER NOT NULL DEFAULT 1 CHECK (escalation_level >= 0),
        FOREIGN KEY (associated_node_id) REFERENCES registered_nodes(node_id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (resident_id) REFERENCES residents(resident_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # 6. emergency_notifications
    """
    CREATE TABLE IF NOT EXISTS emergency_notifications (
        notification_id        TEXT PRIMARY KEY,
        event_id               TEXT NOT NULL,
        contact_id             TEXT NOT NULL,
        notification_channel   TEXT NOT NULL,
        provider               TEXT NOT NULL,
        delivery_status        TEXT NOT NULL DEFAULT 'QUEUED',
        acknowledgement_status TEXT NOT NULL DEFAULT 'PENDING',
        provider_reference_id  TEXT DEFAULT NULL,
        sent_at                TEXT DEFAULT NULL,
        delivered_at           TEXT DEFAULT NULL,
        acknowledged_at        TEXT DEFAULT NULL,
        failure_reason         TEXT DEFAULT NULL,
        created_at             TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES emergency_events(event_id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (contact_id) REFERENCES emergency_contacts(contact_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # 7. actuator_command_logs
    """
    CREATE TABLE IF NOT EXISTS actuator_command_logs (
        command_id       TEXT PRIMARY KEY,
        actuator_id      TEXT NOT NULL,
        event_id         TEXT DEFAULT NULL,
        command          TEXT NOT NULL,
        requested_at     TEXT NOT NULL,
        acknowledged_at  TEXT DEFAULT NULL,
        execution_status TEXT NOT NULL DEFAULT 'PENDING',
        error_details    TEXT DEFAULT NULL,
        FOREIGN KEY (actuator_id) REFERENCES actuators(actuator_id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (event_id) REFERENCES emergency_events(event_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    );
    """,
    # Indexes for node_id, resident_id, event_status, contact priority, and timestamps
    "CREATE INDEX IF NOT EXISTS idx_residents_node_id ON residents(associated_node_id);",
    "CREATE INDEX IF NOT EXISTS idx_residents_created_at ON residents(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_contacts_resident_priority ON emergency_contacts(resident_id, priority ASC, created_at ASC);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_resident_id ON registered_nodes(resident_id);",
    "CREATE INDEX IF NOT EXISTS idx_actuators_node_id ON actuators(associated_node_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_node_id ON emergency_events(associated_node_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_resident_id ON emergency_events(resident_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_status ON emergency_events(event_status);",
    "CREATE INDEX IF NOT EXISTS idx_events_detected_at ON emergency_events(detected_at);",
    "CREATE INDEX IF NOT EXISTS idx_notifications_event_id ON emergency_notifications(event_id);",
    "CREATE INDEX IF NOT EXISTS idx_notifications_contact_id ON emergency_notifications(contact_id);",
    "CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON emergency_notifications(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_command_logs_actuator_id ON actuator_command_logs(actuator_id);",
    "CREATE INDEX IF NOT EXISTS idx_command_logs_event_id ON actuator_command_logs(event_id);",
    "CREATE INDEX IF NOT EXISTS idx_command_logs_requested_at ON actuator_command_logs(requested_at);",
]


class EmergencyDatabase:
    """
    Thread-safe SQLite repository for NavosEdge emergency and actuator records.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized and self._conn is not None

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # Explicit transaction management via BEGIN / COMMIT / ROLLBACK
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Thread-safe explicit transaction context manager.
        Executes `BEGIN IMMEDIATE`, commits on success, and rolls back on any error.
        Translates sqlite3.IntegrityError into typed domain exceptions.
        """
        with self._lock:
            conn = self._get_conn()
            in_outer_tx = conn.in_transaction
            if not in_outer_tx:
                conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
                if not in_outer_tx:
                    conn.execute("COMMIT;")
            except sqlite3.IntegrityError as exc:
                if not in_outer_tx and conn.in_transaction:
                    conn.execute("ROLLBACK;")
                msg = str(exc)
                if "FOREIGN KEY constraint failed" in msg:
                    raise ForeignKeyViolationError(
                        f"Foreign key constraint failed: {msg}"
                    ) from exc
                if "UNIQUE constraint failed" in msg or "PRIMARY KEY" in msg:
                    raise DuplicateRecordError(
                        f"Duplicate record identifier: {msg}"
                    ) from exc
                raise EmergencyDatabaseError(f"Database integrity error: {msg}") from exc
            except Exception:
                if not in_outer_tx and conn.in_transaction:
                    conn.execute("ROLLBACK;")
                raise

    def _apply_migration_v2(self, tx: sqlite3.Connection) -> None:
        """
        Migration v2 (Phase 2): Add structured hazard/policy columns to
        `emergency_events` idempotently while preserving Phase 1 data.
        """
        existing_cols = {
            r["name"]
            for r in tx.execute("PRAGMA table_info(emergency_events);").fetchall()
        }
        v2_columns = [
            ("decision_reason", "TEXT DEFAULT NULL"),
            ("supporting_measurements", "TEXT NOT NULL DEFAULT '{}'"),
            ("model_uncertainty", "REAL DEFAULT NULL"),
            ("recommended_actions", "TEXT NOT NULL DEFAULT '[]'"),
            ("decision_timestamp", "TEXT DEFAULT NULL"),
            ("human_intervention_required", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in v2_columns:
            if col_name not in existing_cols:
                tx.execute(
                    f"ALTER TABLE emergency_events ADD COLUMN {col_name} {col_def};"
                )

    def initialize(self) -> None:
        """
        Initialize the SQLite database, enable WAL and foreign keys, and apply
        versioned migrations idempotently.
        """
        with self._lock:
            conn = self._get_conn()
            with self.transaction() as tx:
                for statement in MIGRATION_V1_DDL:
                    tx.execute(statement)

                row_v1 = tx.execute(
                    "SELECT version FROM schema_migrations WHERE version = 1;"
                ).fetchone()
                if row_v1 is None:
                    tx.execute(
                        """
                        INSERT INTO schema_migrations (version, description, applied_at)
                        VALUES (?, ?, ?);
                        """,
                        (
                            1,
                            "Phase 1 foundational emergency and actuator schema",
                            _dt_to_iso(utc_now()),
                        ),
                    )

                self._apply_migration_v2(tx)
                row_v2 = tx.execute(
                    "SELECT version FROM schema_migrations WHERE version = 2;"
                ).fetchone()
                if row_v2 is None:
                    tx.execute(
                        """
                        INSERT INTO schema_migrations (version, description, applied_at)
                        VALUES (?, ?, ?);
                        """,
                        (
                            2,
                            "Phase 2 structured hazard evaluation and response policy columns",
                            _dt_to_iso(utc_now()),
                        ),
                    )
            # Re-assert foreign keys outside transaction
            conn.execute("PRAGMA foreign_keys = ON;")
            self._initialized = True
            logger.info("EmergencyDatabase initialized at %s", self.db_path)

    def close(self) -> None:
        """Cleanly close the SQLite database connection."""
        with self._lock:
            if self._conn is not None:
                try:
                    if self._conn.in_transaction:
                        self._conn.execute("ROLLBACK;")
                    self._conn.close()
                except Exception as exc:
                    logger.warning("Error closing EmergencyDatabase: %s", exc)
                finally:
                    self._conn = None
                    self._initialized = False

    def backup_to(self, dest_path: Path | str) -> Path:
        """
        Create a consistent online SQLite backup (safe while WAL mode is active).
        """
        target = Path(dest_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            src_conn = self._get_conn()
            dst_conn = sqlite3.connect(str(target))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        return target

    def get_schema_version(self) -> int:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT MAX(version) AS max_ver FROM schema_migrations;"
            ).fetchone()
            return int(row["max_ver"]) if row and row["max_ver"] is not None else 0

    def list_tables(self) -> List[str]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            ).fetchall()
            return [r["name"] for r in rows]

    def get_pragmas(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            return {"foreign_keys": int(fk), "journal_mode": str(jm).lower()}

    # ------------------------------------------------------------------
    # 1. Residents CRUD
    # ------------------------------------------------------------------

    def _row_to_resident(
        self, row: sqlite3.Row, include_safety_info: bool = False
    ) -> ResidentResponse:
        safety_raw = row["safety_information"]
        has_safety = bool(safety_raw and str(safety_raw).strip())
        return ResidentResponse(
            resident_id=row["resident_id"],
            full_name=row["full_name"],
            age=row["age"],
            address_location=row["address_location"],
            associated_node_id=row["associated_node_id"],
            has_safety_information=has_safety,
            safety_information=safety_raw if include_safety_info else None,
            consent_status=ConsentStatus(row["consent_status"]),
            active_status=bool(row["active_status"]),
            created_at=_iso_to_dt(row["created_at"]),  # type: ignore[arg-type]
            updated_at=_iso_to_dt(row["updated_at"]),  # type: ignore[arg-type]
        )

    def create_resident(
        self, payload: ResidentCreate, include_safety_info: bool = False
    ) -> ResidentResponse:
        now_iso = _dt_to_iso(utc_now())
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO residents (
                    resident_id, full_name, age, address_location,
                    associated_node_id, safety_information, consent_status,
                    active_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.resident_id,
                    payload.full_name,
                    payload.age,
                    payload.address_location,
                    payload.associated_node_id,
                    payload.safety_information,
                    payload.consent_status.value,
                    1 if payload.active_status else 0,
                    now_iso,
                    now_iso,
                ),
            )
            if payload.associated_node_id is not None:
                conn.execute(
                    """
                    UPDATE registered_nodes
                    SET resident_id = ?, updated_at = ?
                    WHERE node_id = ?;
                    """,
                    (payload.resident_id, now_iso, payload.associated_node_id),
                )
            row = conn.execute(
                "SELECT * FROM residents WHERE resident_id = ?;",
                (payload.resident_id,),
            ).fetchone()
            return self._row_to_resident(row, include_safety_info=include_safety_info)

    def get_resident(
        self, resident_id: str, include_safety_info: bool = False
    ) -> Optional[ResidentResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM residents WHERE resident_id = ?;", (resident_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_resident(row, include_safety_info=include_safety_info)

    def list_residents(
        self, active_only: bool = False, include_safety_info: bool = False
    ) -> List[ResidentResponse]:
        with self._lock:
            conn = self._get_conn()
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM residents WHERE active_status = 1 ORDER BY created_at ASC, resident_id ASC;"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM residents ORDER BY created_at ASC, resident_id ASC;"
                ).fetchall()
            return [
                self._row_to_resident(r, include_safety_info=include_safety_info)
                for r in rows
            ]

    def update_resident(
        self,
        resident_id: str,
        payload: ResidentUpdate,
        include_safety_info: bool = False,
    ) -> ResidentResponse:
        now_iso = _dt_to_iso(utc_now())
        updates = payload.model_dump(exclude_unset=True)
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM residents WHERE resident_id = ?;", (resident_id,)
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(f"Resident '{resident_id}' not found")

            fields: List[str] = []
            values: List[Any] = []
            for col in (
                "full_name",
                "age",
                "address_location",
                "associated_node_id",
                "safety_information",
            ):
                if col in updates:
                    fields.append(f"{col} = ?")
                    values.append(updates[col])

            if "consent_status" in updates and updates["consent_status"] is not None:
                fields.append("consent_status = ?")
                values.append(updates["consent_status"].value)

            if "active_status" in updates and updates["active_status"] is not None:
                fields.append("active_status = ?")
                values.append(1 if updates["active_status"] else 0)

            fields.append("updated_at = ?")
            values.append(now_iso)
            values.append(resident_id)

            conn.execute(
                f"UPDATE residents SET {', '.join(fields)} WHERE resident_id = ?;",
                tuple(values),
            )

            if "associated_node_id" in updates:
                old_node_id = existing["associated_node_id"]
                new_node_id = updates["associated_node_id"]
                if old_node_id and old_node_id != new_node_id:
                    conn.execute(
                        "UPDATE registered_nodes SET resident_id = NULL, updated_at = ? WHERE node_id = ? AND resident_id = ?;",
                        (now_iso, old_node_id, resident_id),
                    )
                if new_node_id:
                    conn.execute(
                        "UPDATE registered_nodes SET resident_id = ?, updated_at = ? WHERE node_id = ?;",
                        (resident_id, now_iso, new_node_id),
                    )

            row = conn.execute(
                "SELECT * FROM residents WHERE resident_id = ?;", (resident_id,)
            ).fetchone()
            return self._row_to_resident(row, include_safety_info=include_safety_info)

    def deactivate_resident(self, resident_id: str) -> ResidentResponse:
        """
        Soft-deactivate a resident without deleting any historical emergency events
        or notifications.
        """
        return self.update_resident(
            resident_id, ResidentUpdate(active_status=False)
        )

    # ------------------------------------------------------------------
    # 2. Emergency Contacts CRUD
    # ------------------------------------------------------------------

    def _row_to_contact(self, row: sqlite3.Row) -> EmergencyContactResponse:
        channels_raw = json.loads(row["preferred_channels"])
        return EmergencyContactResponse(
            contact_id=row["contact_id"],
            resident_id=row["resident_id"],
            full_name=row["full_name"],
            phone_number=row["phone_number"],
            relationship=row["relationship"],
            priority=int(row["priority"]),
            preferred_channels=[NotificationChannel(ch) for ch in channels_raw],
            consent_status=ConsentStatus(row["consent_status"]),
            active_status=bool(row["active_status"]),
            created_at=_iso_to_dt(row["created_at"]),  # type: ignore[arg-type]
            updated_at=_iso_to_dt(row["updated_at"]),  # type: ignore[arg-type]
        )

    def create_contact(
        self, payload: EmergencyContactCreate
    ) -> EmergencyContactResponse:
        now_iso = _dt_to_iso(utc_now())
        channels_json = json.dumps([ch.value for ch in payload.preferred_channels])
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO emergency_contacts (
                    contact_id, resident_id, full_name, phone_number,
                    relationship, priority, preferred_channels,
                    consent_status, active_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.contact_id,
                    payload.resident_id,
                    payload.full_name,
                    payload.phone_number,
                    payload.relationship,
                    payload.priority,
                    channels_json,
                    payload.consent_status.value,
                    1 if payload.active_status else 0,
                    now_iso,
                    now_iso,
                ),
            )
            row = conn.execute(
                "SELECT * FROM emergency_contacts WHERE contact_id = ?;",
                (payload.contact_id,),
            ).fetchone()
            return self._row_to_contact(row)

    def get_contact(self, contact_id: str) -> Optional[EmergencyContactResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM emergency_contacts WHERE contact_id = ?;",
                (contact_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_contact(row)

    def list_contacts_for_resident(
        self, resident_id: str, active_only: bool = True
    ) -> List[EmergencyContactResponse]:
        """
        Return contacts for a resident ordered deterministically by:
        priority ASC, created_at ASC, contact_id ASC.
        """
        with self._lock:
            conn = self._get_conn()
            if active_only:
                rows = conn.execute(
                    """
                    SELECT * FROM emergency_contacts
                    WHERE resident_id = ? AND active_status = 1
                    ORDER BY priority ASC, created_at ASC, contact_id ASC;
                    """,
                    (resident_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM emergency_contacts
                    WHERE resident_id = ?
                    ORDER BY priority ASC, created_at ASC, contact_id ASC;
                    """,
                    (resident_id,),
                ).fetchall()
            return [self._row_to_contact(r) for r in rows]

    def update_contact(
        self, contact_id: str, payload: EmergencyContactUpdate
    ) -> EmergencyContactResponse:
        now_iso = _dt_to_iso(utc_now())
        updates = payload.model_dump(exclude_unset=True)
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM emergency_contacts WHERE contact_id = ?;",
                (contact_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(f"EmergencyContact '{contact_id}' not found")

            fields: List[str] = []
            values: List[Any] = []
            for col in ("full_name", "phone_number", "relationship", "priority"):
                if col in updates and updates[col] is not None:
                    fields.append(f"{col} = ?")
                    values.append(updates[col])

            if "preferred_channels" in updates and updates["preferred_channels"] is not None:
                fields.append("preferred_channels = ?")
                values.append(
                    json.dumps([ch.value for ch in updates["preferred_channels"]])
                )

            if "consent_status" in updates and updates["consent_status"] is not None:
                fields.append("consent_status = ?")
                values.append(updates["consent_status"].value)

            if "active_status" in updates and updates["active_status"] is not None:
                fields.append("active_status = ?")
                values.append(1 if updates["active_status"] else 0)

            fields.append("updated_at = ?")
            values.append(now_iso)
            values.append(contact_id)

            conn.execute(
                f"UPDATE emergency_contacts SET {', '.join(fields)} WHERE contact_id = ?;",
                tuple(values),
            )
            row = conn.execute(
                "SELECT * FROM emergency_contacts WHERE contact_id = ?;",
                (contact_id,),
            ).fetchone()
            return self._row_to_contact(row)

    def deactivate_contact(self, contact_id: str) -> EmergencyContactResponse:
        """
        Soft-deactivate an emergency contact while preserving all notification history.
        """
        return self.update_contact(
            contact_id, EmergencyContactUpdate(active_status=False)
        )

    # ------------------------------------------------------------------
    # 3. Registered Nodes CRUD & NodeRegistry Adapter
    # ------------------------------------------------------------------

    def _row_to_node(
        self,
        row: sqlite3.Row,
        node_registry: Optional[NodeRegistry] = None,
    ) -> NodeResponse:
        runtime_status: Optional[str] = None
        last_seen: Optional[datetime] = None
        total_readings: Optional[int] = None
        if node_registry is not None:
            live_info = node_registry.get_node(row["node_id"])
            if live_info is not None:
                runtime_status = live_info.status
                last_seen = ensure_utc(live_info.last_seen)
                total_readings = live_info.total_readings

        return NodeResponse(
            node_id=row["node_id"],
            node_name=row["node_name"],
            location=row["location"],
            operational_status=NodeOperationalStatus(row["operational_status"]),
            resident_id=row["resident_id"],
            created_at=_iso_to_dt(row["created_at"]),  # type: ignore[arg-type]
            updated_at=_iso_to_dt(row["updated_at"]),  # type: ignore[arg-type]
            runtime_status=runtime_status,
            last_seen=last_seen,
            total_readings=total_readings,
        )

    def register_node(
        self,
        payload: NodeRegistration,
        node_registry: Optional[NodeRegistry] = None,
    ) -> NodeResponse:
        now_iso = _dt_to_iso(utc_now())
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO registered_nodes (
                    node_id, node_name, location, operational_status,
                    resident_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.node_id,
                    payload.node_name,
                    payload.location,
                    payload.operational_status.value,
                    payload.resident_id,
                    now_iso,
                    now_iso,
                ),
            )
            if payload.resident_id is not None:
                conn.execute(
                    """
                    UPDATE residents
                    SET associated_node_id = ?, updated_at = ?
                    WHERE resident_id = ?;
                    """,
                    (payload.node_id, now_iso, payload.resident_id),
                )
            row = conn.execute(
                "SELECT * FROM registered_nodes WHERE node_id = ?;",
                (payload.node_id,),
            ).fetchone()
            return self._row_to_node(row, node_registry=node_registry)

    def associate_node_with_resident(
        self,
        node_id: str,
        resident_id: Optional[str],
        node_registry: Optional[NodeRegistry] = None,
    ) -> NodeResponse:
        """
        Atomically associate (or disassociate if resident_id is None) a registered node
        and a resident in both `registered_nodes` and `residents`.
        """
        now_iso = _dt_to_iso(utc_now())
        with self.transaction() as conn:
            node_row = conn.execute(
                "SELECT * FROM registered_nodes WHERE node_id = ?;", (node_id,)
            ).fetchone()
            if node_row is None:
                raise RecordNotFoundError(f"Node '{node_id}' not found")

            old_resident_id = node_row["resident_id"]
            if old_resident_id and old_resident_id != resident_id:
                conn.execute(
                    "UPDATE residents SET associated_node_id = NULL, updated_at = ? WHERE resident_id = ? AND associated_node_id = ?;",
                    (now_iso, old_resident_id, node_id),
                )

            conn.execute(
                "UPDATE registered_nodes SET resident_id = ?, updated_at = ? WHERE node_id = ?;",
                (resident_id, now_iso, node_id),
            )

            if resident_id is not None:
                res_row = conn.execute(
                    "SELECT resident_id FROM residents WHERE resident_id = ?;",
                    (resident_id,),
                ).fetchone()
                if res_row is None:
                    raise ForeignKeyViolationError(
                        f"Resident '{resident_id}' does not exist"
                    )
                conn.execute(
                    "UPDATE residents SET associated_node_id = ?, updated_at = ? WHERE resident_id = ?;",
                    (node_id, now_iso, resident_id),
                )

            updated = conn.execute(
                "SELECT * FROM registered_nodes WHERE node_id = ?;", (node_id,)
            ).fetchone()
            return self._row_to_node(updated, node_registry=node_registry)

    def get_node(
        self,
        node_id: str,
        node_registry: Optional[NodeRegistry] = None,
    ) -> Optional[NodeResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM registered_nodes WHERE node_id = ?;", (node_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_node(row, node_registry=node_registry)

    def list_nodes(
        self, node_registry: Optional[NodeRegistry] = None
    ) -> List[NodeResponse]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM registered_nodes ORDER BY created_at ASC, node_id ASC;"
            ).fetchall()
            return [self._row_to_node(r, node_registry=node_registry) for r in rows]

    # ------------------------------------------------------------------
    # 4. Actuators CRUD
    # ------------------------------------------------------------------

    def _row_to_actuator(self, row: sqlite3.Row) -> ActuatorResponse:
        return ActuatorResponse(
            actuator_id=row["actuator_id"],
            associated_node_id=row["associated_node_id"],
            actuator_type=row["actuator_type"],
            device_name=row["device_name"],
            ip_address=row["ip_address"],
            connection_status=ActuatorConnectionStatus(row["connection_status"]),
            current_state=ActuatorState(row["current_state"]),
            last_heartbeat=_iso_to_dt(row["last_heartbeat"]),
            created_at=_iso_to_dt(row["created_at"]),  # type: ignore[arg-type]
            updated_at=_iso_to_dt(row["updated_at"]),  # type: ignore[arg-type]
        )

    def register_actuator(self, payload: ActuatorRegistration) -> ActuatorResponse:
        now_iso = _dt_to_iso(utc_now())
        hb_iso = _dt_to_iso(payload.last_heartbeat)
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO actuators (
                    actuator_id, associated_node_id, actuator_type,
                    device_name, ip_address, connection_status,
                    current_state, last_heartbeat, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.actuator_id,
                    payload.associated_node_id,
                    payload.actuator_type,
                    payload.device_name,
                    payload.ip_address,
                    payload.connection_status.value,
                    payload.current_state.value,
                    hb_iso,
                    now_iso,
                    now_iso,
                ),
            )
            row = conn.execute(
                "SELECT * FROM actuators WHERE actuator_id = ?;",
                (payload.actuator_id,),
            ).fetchone()
            return self._row_to_actuator(row)

    def get_actuator(self, actuator_id: str) -> Optional[ActuatorResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM actuators WHERE actuator_id = ?;",
                (actuator_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_actuator(row)

    def list_actuators_for_node(self, node_id: str) -> List[ActuatorResponse]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM actuators WHERE associated_node_id = ? ORDER BY created_at ASC, actuator_id ASC;",
                (node_id,),
            ).fetchall()
            return [self._row_to_actuator(r) for r in rows]

    def update_actuator_heartbeat(
        self,
        actuator_id: str,
        current_state: ActuatorState,
        connection_status: ActuatorConnectionStatus = ActuatorConnectionStatus.ONLINE,
        ip_address: Optional[str] = None,
        heartbeat_at: Optional[datetime] = None,
    ) -> ActuatorResponse:
        now_dt = ensure_utc(heartbeat_at) or utc_now()
        now_iso = _dt_to_iso(now_dt)
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM actuators WHERE actuator_id = ?;",
                (actuator_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(f"Actuator '{actuator_id}' not found")

            effective_ip = ip_address if ip_address is not None else existing["ip_address"]
            conn.execute(
                """
                UPDATE actuators
                SET current_state = ?, connection_status = ?, ip_address = ?,
                    last_heartbeat = ?, updated_at = ?
                WHERE actuator_id = ?;
                """,
                (
                    current_state.value,
                    connection_status.value,
                    effective_ip,
                    now_iso,
                    now_iso,
                    actuator_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM actuators WHERE actuator_id = ?;",
                (actuator_id,),
            ).fetchone()
            return self._row_to_actuator(row)

    # ------------------------------------------------------------------
    # 5. Emergency Events CRUD
    # ------------------------------------------------------------------

    def _row_to_event(self, row: sqlite3.Row) -> EmergencyEventResponse:
        row_keys = set(row.keys())
        meta_raw = row["event_metadata"]
        metadata = json.loads(meta_raw) if meta_raw else {}

        supp_raw = (
            row["supporting_measurements"]
            if "supporting_measurements" in row_keys and row["supporting_measurements"]
            else None
        )
        supporting_measurements = (
            json.loads(supp_raw)
            if supp_raw
            else metadata.get("supporting_measurements", {})
        )

        rec_raw = (
            row["recommended_actions"]
            if "recommended_actions" in row_keys and row["recommended_actions"]
            else None
        )
        recommended_actions = (
            json.loads(rec_raw)
            if rec_raw
            else metadata.get("recommended_actions", [])
        )

        decision_reason = (
            row["decision_reason"]
            if "decision_reason" in row_keys and row["decision_reason"] is not None
            else metadata.get("decision_reason")
        )
        model_uncertainty = (
            float(row["model_uncertainty"])
            if "model_uncertainty" in row_keys and row["model_uncertainty"] is not None
            else metadata.get("model_uncertainty")
        )
        decision_ts_raw = (
            row["decision_timestamp"]
            if "decision_timestamp" in row_keys and row["decision_timestamp"]
            else metadata.get("decision_timestamp")
        )
        human_int = (
            bool(row["human_intervention_required"])
            if "human_intervention_required" in row_keys
            and row["human_intervention_required"] is not None
            else bool(metadata.get("human_intervention_required", False))
        )

        return EmergencyEventResponse(
            event_id=row["event_id"],
            associated_node_id=row["associated_node_id"],
            resident_id=row["resident_id"],
            event_type=row["event_type"],
            severity=EmergencySeverity(row["severity"]),
            event_status=EmergencyEventStatus(row["event_status"]),
            detected_at=_iso_to_dt(row["detected_at"]),  # type: ignore[arg-type]
            acknowledged_at=_iso_to_dt(row["acknowledged_at"]),
            resolved_at=_iso_to_dt(row["resolved_at"]),
            event_metadata=metadata,
            escalation_level=int(row["escalation_level"]),
            decision_reason=decision_reason,
            supporting_measurements=supporting_measurements,
            model_uncertainty=model_uncertainty,
            recommended_actions=recommended_actions,
            decision_timestamp=_iso_to_dt(decision_ts_raw),
            human_intervention_required=human_int,
        )

    def create_emergency_event(
        self, payload: EmergencyEventCreate
    ) -> EmergencyEventResponse:
        meta_json = json.dumps(payload.event_metadata or {})
        supp_json = json.dumps(payload.supporting_measurements or {})
        rec_json = json.dumps(payload.recommended_actions or [])
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO emergency_events (
                    event_id, associated_node_id, resident_id, event_type,
                    severity, event_status, detected_at, acknowledged_at,
                    resolved_at, event_metadata, escalation_level,
                    decision_reason, supporting_measurements, model_uncertainty,
                    recommended_actions, decision_timestamp, human_intervention_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.event_id,
                    payload.associated_node_id,
                    payload.resident_id,
                    payload.event_type,
                    payload.severity.value,
                    payload.event_status.value,
                    _dt_to_iso(payload.detected_at),
                    _dt_to_iso(payload.acknowledged_at),
                    _dt_to_iso(payload.resolved_at),
                    meta_json,
                    payload.escalation_level,
                    payload.decision_reason,
                    supp_json,
                    payload.model_uncertainty,
                    rec_json,
                    _dt_to_iso(payload.decision_timestamp or payload.detected_at),
                    1 if payload.human_intervention_required else 0,
                ),
            )
            row = conn.execute(
                "SELECT * FROM emergency_events WHERE event_id = ?;",
                (payload.event_id,),
            ).fetchone()
            return self._row_to_event(row)

    def get_emergency_event(
        self, event_id: str
    ) -> Optional[EmergencyEventResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM emergency_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_event(row)

    def list_emergency_events(
        self,
        node_id: Optional[str] = None,
        resident_id: Optional[str] = None,
        event_status: Optional[EmergencyEventStatus] = None,
    ) -> List[EmergencyEventResponse]:
        with self._lock:
            conn = self._get_conn()
            clauses: List[str] = []
            params: List[Any] = []
            if node_id is not None:
                clauses.append("associated_node_id = ?")
                params.append(node_id)
            if resident_id is not None:
                clauses.append("resident_id = ?")
                params.append(resident_id)
            if event_status is not None:
                clauses.append("event_status = ?")
                params.append(event_status.value)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                f"SELECT * FROM emergency_events {where_sql} ORDER BY detected_at DESC, event_id ASC;",
                tuple(params),
            ).fetchall()
            return [self._row_to_event(r) for r in rows]

    def update_emergency_event_status(
        self,
        event_id: str,
        event_status: EmergencyEventStatus,
        escalation_level: Optional[int] = None,
        acknowledged_at: Optional[datetime] = None,
        resolved_at: Optional[datetime] = None,
    ) -> EmergencyEventResponse:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM emergency_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(f"EmergencyEvent '{event_id}' not found")

            ack_iso = (
                _dt_to_iso(acknowledged_at)
                if acknowledged_at is not None
                else existing["acknowledged_at"]
            )
            res_iso = (
                _dt_to_iso(resolved_at)
                if resolved_at is not None
                else existing["resolved_at"]
            )
            esc_lvl = (
                escalation_level
                if escalation_level is not None
                else existing["escalation_level"]
            )
            conn.execute(
                """
                UPDATE emergency_events
                SET event_status = ?, escalation_level = ?,
                    acknowledged_at = ?, resolved_at = ?
                WHERE event_id = ?;
                """,
                (event_status.value, esc_lvl, ack_iso, res_iso, event_id),
            )
            row = conn.execute(
                "SELECT * FROM emergency_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            return self._row_to_event(row)

    def get_active_emergency_event_for_node(
        self, node_id: str
    ) -> Optional[EmergencyEventResponse]:
        """
        Return the most recent unresolved/uncancelled emergency event for a node,
        supporting deduplicated event continuation, escalation, and recovery.
        """
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT * FROM emergency_events
                WHERE associated_node_id = ?
                  AND event_status NOT IN ('RESOLVED', 'CANCELLED')
                ORDER BY detected_at DESC, event_id ASC
                LIMIT 1;
                """,
                (node_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_event(row)

    def update_emergency_event_lifecycle(
        self,
        event_id: str,
        *,
        event_type: Optional[str] = None,
        severity: Optional[EmergencySeverity] = None,
        event_status: Optional[EmergencyEventStatus] = None,
        escalation_level: Optional[int] = None,
        decision_reason: Optional[str] = None,
        supporting_measurements: Optional[Dict[str, Any]] = None,
        model_uncertainty: Optional[float] = None,
        recommended_actions: Optional[List[str]] = None,
        decision_timestamp: Optional[datetime] = None,
        human_intervention_required: Optional[bool] = None,
        event_metadata: Optional[Dict[str, Any]] = None,
        acknowledged_at: Optional[datetime] = None,
        resolved_at: Optional[datetime] = None,
    ) -> EmergencyEventResponse:
        """
        Update an active emergency event in-place during continuation,
        escalation, severity reduction, recovery, or resolution.
        """
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM emergency_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(f"EmergencyEvent '{event_id}' not found")

            eff_type = event_type if event_type is not None else existing["event_type"]
            eff_sev = (
                severity.value if severity is not None else existing["severity"]
            )
            eff_status = (
                event_status.value
                if event_status is not None
                else existing["event_status"]
            )
            eff_esc = (
                escalation_level
                if escalation_level is not None
                else existing["escalation_level"]
            )
            eff_reason = (
                decision_reason
                if decision_reason is not None
                else existing["decision_reason"]
            )
            eff_supp = (
                json.dumps(supporting_measurements)
                if supporting_measurements is not None
                else existing["supporting_measurements"]
            )
            eff_unc = (
                model_uncertainty
                if model_uncertainty is not None
                else existing["model_uncertainty"]
            )
            eff_actions = (
                json.dumps(recommended_actions)
                if recommended_actions is not None
                else existing["recommended_actions"]
            )
            eff_dec_ts = (
                _dt_to_iso(decision_timestamp)
                if decision_timestamp is not None
                else existing["decision_timestamp"]
            )
            eff_human = (
                (1 if human_intervention_required else 0)
                if human_intervention_required is not None
                else existing["human_intervention_required"]
            )
            eff_meta = (
                json.dumps(event_metadata)
                if event_metadata is not None
                else existing["event_metadata"]
            )
            eff_ack = (
                _dt_to_iso(acknowledged_at)
                if acknowledged_at is not None
                else existing["acknowledged_at"]
            )
            eff_res = (
                _dt_to_iso(resolved_at)
                if resolved_at is not None
                else existing["resolved_at"]
            )

            conn.execute(
                """
                UPDATE emergency_events
                SET event_type = ?, severity = ?, event_status = ?,
                    escalation_level = ?, decision_reason = ?,
                    supporting_measurements = ?, model_uncertainty = ?,
                    recommended_actions = ?, decision_timestamp = ?,
                    human_intervention_required = ?, event_metadata = ?,
                    acknowledged_at = ?, resolved_at = ?
                WHERE event_id = ?;
                """,
                (
                    eff_type,
                    eff_sev,
                    eff_status,
                    eff_esc,
                    eff_reason,
                    eff_supp,
                    eff_unc,
                    eff_actions,
                    eff_dec_ts,
                    eff_human,
                    eff_meta,
                    eff_ack,
                    eff_res,
                    event_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM emergency_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            return self._row_to_event(row)

    # ------------------------------------------------------------------
    # 6. Emergency Notifications CRUD
    # ------------------------------------------------------------------

    def _row_to_notification(self, row: sqlite3.Row) -> NotificationResponse:
        return NotificationResponse(
            notification_id=row["notification_id"],
            event_id=row["event_id"],
            contact_id=row["contact_id"],
            notification_channel=NotificationChannel(row["notification_channel"]),
            provider=row["provider"],
            delivery_status=NotificationDeliveryStatus(row["delivery_status"]),
            acknowledgement_status=HumanAcknowledgementStatus(
                row["acknowledgement_status"]
            ),
            provider_reference_id=row["provider_reference_id"],
            sent_at=_iso_to_dt(row["sent_at"]),
            delivered_at=_iso_to_dt(row["delivered_at"]),
            acknowledged_at=_iso_to_dt(row["acknowledged_at"]),
            failure_reason=row["failure_reason"],
            created_at=_iso_to_dt(row["created_at"]),  # type: ignore[arg-type]
        )

    def create_notification(
        self, payload: NotificationCreate
    ) -> NotificationResponse:
        now_iso = _dt_to_iso(utc_now())
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO emergency_notifications (
                    notification_id, event_id, contact_id,
                    notification_channel, provider, delivery_status,
                    acknowledgement_status, provider_reference_id,
                    sent_at, delivered_at, acknowledged_at,
                    failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.notification_id,
                    payload.event_id,
                    payload.contact_id,
                    payload.notification_channel.value,
                    payload.provider,
                    payload.delivery_status.value,
                    payload.acknowledgement_status.value,
                    payload.provider_reference_id,
                    _dt_to_iso(payload.sent_at),
                    _dt_to_iso(payload.delivered_at),
                    _dt_to_iso(payload.acknowledged_at),
                    payload.failure_reason,
                    now_iso,
                ),
            )
            row = conn.execute(
                "SELECT * FROM emergency_notifications WHERE notification_id = ?;",
                (payload.notification_id,),
            ).fetchone()
            return self._row_to_notification(row)

    def get_notification(
        self, notification_id: str
    ) -> Optional[NotificationResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM emergency_notifications WHERE notification_id = ?;",
                (notification_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_notification(row)

    def list_notifications_for_event(
        self, event_id: str
    ) -> List[NotificationResponse]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT * FROM emergency_notifications
                WHERE event_id = ?
                ORDER BY created_at ASC, notification_id ASC;
                """,
                (event_id,),
            ).fetchall()
            return [self._row_to_notification(r) for r in rows]

    def get_notification_by_provider_ref(
        self, provider_reference_id: str
    ) -> Optional[NotificationResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT * FROM emergency_notifications
                WHERE provider_reference_id = ?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (provider_reference_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_notification(row)

    def get_latest_pending_notification_for_phone(
        self, phone_number: str
    ) -> Optional[NotificationResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT n.* FROM emergency_notifications n
                JOIN emergency_contacts c ON c.contact_id = n.contact_id
                WHERE c.phone_number = ?
                  AND n.acknowledgement_status = 'PENDING'
                ORDER BY CASE WHEN n.notification_channel = 'SMS' THEN 0 ELSE 1 END ASC,
                         n.created_at DESC
                LIMIT 1;
                """,
                (phone_number,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_notification(row)

    def list_unresolved_emergency_events(self) -> List[EmergencyEventResponse]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT * FROM emergency_events
                WHERE event_status NOT IN ('RESOLVED', 'CANCELLED')
                ORDER BY detected_at ASC, event_id ASC;
                """
            ).fetchall()
            return [self._row_to_event(r) for r in rows]

    def update_notification_delivery(
        self,
        notification_id: str,
        delivery_status: NotificationDeliveryStatus,
        provider_reference_id: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        delivered_at: Optional[datetime] = None,
        failure_reason: Optional[str] = None,
    ) -> NotificationResponse:
        """
        Update provider delivery status without altering human acknowledgement state.
        """
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM emergency_notifications WHERE notification_id = ?;",
                (notification_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(
                    f"Notification '{notification_id}' not found"
                )

            ref_id = (
                provider_reference_id
                if provider_reference_id is not None
                else existing["provider_reference_id"]
            )
            sent_iso = (
                _dt_to_iso(sent_at)
                if sent_at is not None
                else existing["sent_at"]
            )
            deliv_iso = (
                _dt_to_iso(delivered_at)
                if delivered_at is not None
                else existing["delivered_at"]
            )
            fail_msg = (
                failure_reason
                if failure_reason is not None
                else existing["failure_reason"]
            )

            conn.execute(
                """
                UPDATE emergency_notifications
                SET delivery_status = ?, provider_reference_id = ?,
                    sent_at = ?, delivered_at = ?, failure_reason = ?
                WHERE notification_id = ?;
                """,
                (
                    delivery_status.value,
                    ref_id,
                    sent_iso,
                    deliv_iso,
                    fail_msg,
                    notification_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM emergency_notifications WHERE notification_id = ?;",
                (notification_id,),
            ).fetchone()
            return self._row_to_notification(row)

    def acknowledge_notification_by_human(
        self,
        notification_id: str,
        acknowledgement_status: HumanAcknowledgementStatus = HumanAcknowledgementStatus.ACKNOWLEDGED,
        acknowledged_at: Optional[datetime] = None,
    ) -> NotificationResponse:
        """
        Record explicit human acknowledgement separately from carrier delivery status.
        """
        ack_dt = ensure_utc(acknowledged_at) or utc_now()
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM emergency_notifications WHERE notification_id = ?;",
                (notification_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(
                    f"Notification '{notification_id}' not found"
                )
            conn.execute(
                """
                UPDATE emergency_notifications
                SET acknowledgement_status = ?, acknowledged_at = ?
                WHERE notification_id = ?;
                """,
                (acknowledgement_status.value, _dt_to_iso(ack_dt), notification_id),
            )
            row = conn.execute(
                "SELECT * FROM emergency_notifications WHERE notification_id = ?;",
                (notification_id,),
            ).fetchone()
            return self._row_to_notification(row)

    # ------------------------------------------------------------------
    # 7. Actuator Command Logs CRUD
    # ------------------------------------------------------------------

    def _row_to_command_log(self, row: sqlite3.Row) -> ActuatorCommandResponse:
        return ActuatorCommandResponse(
            command_id=row["command_id"],
            actuator_id=row["actuator_id"],
            event_id=row["event_id"],
            command=row["command"],
            requested_at=_iso_to_dt(row["requested_at"]),  # type: ignore[arg-type]
            acknowledged_at=_iso_to_dt(row["acknowledged_at"]),
            execution_status=CommandExecutionStatus(row["execution_status"]),
            error_details=row["error_details"],
        )

    def create_actuator_command_log(
        self, payload: ActuatorCommandLog
    ) -> ActuatorCommandResponse:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO actuator_command_logs (
                    command_id, actuator_id, event_id, command,
                    requested_at, acknowledged_at, execution_status, error_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.command_id,
                    payload.actuator_id,
                    payload.event_id,
                    payload.command,
                    _dt_to_iso(payload.requested_at),
                    _dt_to_iso(payload.acknowledged_at),
                    payload.execution_status.value,
                    payload.error_details,
                ),
            )
            row = conn.execute(
                "SELECT * FROM actuator_command_logs WHERE command_id = ?;",
                (payload.command_id,),
            ).fetchone()
            return self._row_to_command_log(row)

    def get_actuator_command_log(
        self, command_id: str
    ) -> Optional[ActuatorCommandResponse]:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM actuator_command_logs WHERE command_id = ?;",
                (command_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_command_log(row)

    def list_command_logs_for_actuator(
        self, actuator_id: str
    ) -> List[ActuatorCommandResponse]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT * FROM actuator_command_logs
                WHERE actuator_id = ?
                ORDER BY requested_at DESC, command_id ASC;
                """,
                (actuator_id,),
            ).fetchall()
            return [self._row_to_command_log(r) for r in rows]

    def update_actuator_command_status(
        self,
        command_id: str,
        execution_status: CommandExecutionStatus,
        acknowledged_at: Optional[datetime] = None,
        error_details: Optional[str] = None,
    ) -> ActuatorCommandResponse:
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM actuator_command_logs WHERE command_id = ?;",
                (command_id,),
            ).fetchone()
            if existing is None:
                raise RecordNotFoundError(
                    f"ActuatorCommandLog '{command_id}' not found"
                )
            ack_iso = (
                _dt_to_iso(acknowledged_at)
                if acknowledged_at is not None
                else existing["acknowledged_at"]
            )
            err_msg = (
                error_details
                if error_details is not None
                else existing["error_details"]
            )
            conn.execute(
                """
                UPDATE actuator_command_logs
                SET execution_status = ?, acknowledged_at = ?, error_details = ?
                WHERE command_id = ?;
                """,
                (execution_status.value, ack_iso, err_msg, command_id),
            )
            row = conn.execute(
                "SELECT * FROM actuator_command_logs WHERE command_id = ?;",
                (command_id,),
            ).fetchone()
            return self._row_to_command_log(row)

