"""Lightweight SQLite persistence layer for CERBERUS-X analyses."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, Union

from core.schemas import (
    AnalysisResult,
    Claim,
    Conflict,
    Entity,
    SecurityFlag,
    SourceDocument,
    TwinState,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    entity_count INTEGER NOT NULL,
    claim_count INTEGER NOT NULL,
    conflict_count INTEGER NOT NULL,
    twin_state_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    analysis_id TEXT NOT NULL,
    id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    stored_path TEXT,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    flags_json TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    duplicate_of TEXT,
    reliability REAL NOT NULL,
    is_suspicious INTEGER NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (analysis_id, id),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entities (
    analysis_id TEXT NOT NULL,
    id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, id),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS claims (
    analysis_id TEXT NOT NULL,
    id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_label TEXT,
    entity_name TEXT NOT NULL,
    entity_id TEXT,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    value_num REAL,
    unit TEXT,
    stage TEXT NOT NULL,
    event_time TEXT,
    location TEXT,
    raw_text TEXT NOT NULL,
    locator TEXT,
    suspicious INTEGER NOT NULL,
    status TEXT NOT NULL,
    reliability REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (analysis_id, id),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conflicts (
    analysis_id TEXT NOT NULL,
    id TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    claim_ids_json TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    predicate TEXT NOT NULL,
    explanation TEXT NOT NULL,
    severity TEXT NOT NULL,
    needs_review INTEGER NOT NULL,
    rule TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (analysis_id, id),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS twin_states (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    claim_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reliability REAL NOT NULL,
    source_filename TEXT,
    locator TEXT,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
"""


def _dt_to_iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _iso_to_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


class AnalysisRepository:
    """SQLite repository storing and reconstructing ``AnalysisResult`` runs."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._initialized = False

    def init_db(self) -> None:
        if self._initialized and self.db_path.exists():
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate_columns(conn)
        self._initialized = True

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection) -> None:
        migrations = (
            ("claims", "reliability", "REAL NOT NULL DEFAULT 0.0"),
            ("conflicts", "rule", "TEXT NOT NULL DEFAULT ''"),
            ("twin_states", "source_filename", "TEXT"),
            ("twin_states", "locator", "TEXT"),
        )
        for table, column, ddl in migrations:
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_analysis(self, analysis_id: str, result: Union[AnalysisResult, Any]) -> dict:
        """Persist an ``AnalysisResult`` (or ``PipelineResult``) and all child records atomically."""
        if hasattr(result, "analysis"):
            result = result.analysis
        self.init_db()
        with self._connect() as conn:
            conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
            conn.execute(
                """
                INSERT INTO analyses (
                    id, created_at, warnings_json,
                    document_count, entity_count, claim_count,
                    conflict_count, twin_state_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    result.created_at.isoformat(),
                    json.dumps(result.warnings),
                    len(result.documents),
                    len(result.entities),
                    len(result.claims),
                    len(result.conflicts),
                    len(result.twin_states),
                ),
            )

            conn.executemany(
                """
                INSERT INTO documents (
                    analysis_id, id, filename, file_type, source_type, sha256,
                    stored_path, text, metadata_json, flags_json, extraction_method,
                    warnings_json, duplicate_of, reliability, is_suspicious, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        doc.id,
                        doc.filename,
                        doc.file_type.value,
                        doc.source_type.value,
                        doc.sha256,
                        doc.stored_path,
                        doc.text,
                        json.dumps(doc.metadata),
                        json.dumps([f.model_dump(mode="json") for f in doc.flags]),
                        doc.extraction_method,
                        json.dumps(doc.warnings),
                        doc.duplicate_of,
                        doc.reliability,
                        int(doc.is_suspicious),
                        doc.ingested_at.isoformat(),
                    )
                    for doc in result.documents
                ],
            )

            conn.executemany(
                """
                INSERT INTO entities (analysis_id, id, canonical_name, entity_type, aliases_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        ent.id,
                        ent.canonical_name,
                        ent.entity_type,
                        json.dumps(ent.aliases),
                    )
                    for ent in result.entities
                ],
            )

            conn.executemany(
                """
                INSERT INTO claims (
                    analysis_id, id, source_id, source_label, entity_name, entity_id,
                    predicate, value, value_num, unit, stage, event_time, location,
                    raw_text, locator, suspicious, status, reliability
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        c.id,
                        c.source_id,
                        c.source_label,
                        c.entity_name,
                        c.entity_id,
                        c.predicate,
                        c.value,
                        c.value_num,
                        c.unit,
                        c.stage.value,
                        _dt_to_iso(c.event_time),
                        c.location,
                        c.raw_text,
                        c.locator,
                        int(c.suspicious),
                        c.status.value,
                        c.reliability,
                    )
                    for c in result.claims
                ],
            )

            conn.executemany(
                """
                INSERT INTO conflicts (
                    analysis_id, id, conflict_type, claim_ids_json,
                    entity_name, predicate, explanation, severity, needs_review, rule
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        conf.id,
                        conf.conflict_type.value,
                        json.dumps(conf.claim_ids),
                        conf.entity_name,
                        conf.predicate,
                        conf.explanation,
                        conf.severity.value,
                        int(conf.needs_review),
                        conf.rule,
                    )
                    for conf in result.conflicts
                ],
            )

            conn.executemany(
                """
                INSERT INTO twin_states (
                    analysis_id, entity_id, entity_name, attribute, value,
                    valid_from, valid_to, claim_id, source_id, status, reliability,
                    source_filename, locator
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        st.entity_id,
                        st.entity_name,
                        st.attribute,
                        st.value,
                        _dt_to_iso(st.valid_from),
                        _dt_to_iso(st.valid_to),
                        st.claim_id,
                        st.source_id,
                        st.status.value,
                        st.reliability,
                        st.source_filename,
                        st.locator,
                    )
                    for st in result.twin_states
                ],
            )

        return self.get_analysis_summary(analysis_id)  # type: ignore[return-value]

    def get_analysis_summary(self, analysis_id: str) -> Optional[dict]:
        self.init_db()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analyses WHERE id = ?",
                (analysis_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "analysis_id": row["id"],
                "created_at": row["created_at"],
                "warnings": json.loads(row["warnings_json"]),
                "counts": {
                    "documents": row["document_count"],
                    "entities": row["entity_count"],
                    "claims": row["claim_count"],
                    "conflicts": row["conflict_count"],
                    "twin_states": row["twin_state_count"],
                },
            }

    def list_analyses(self) -> list[dict]:
        self.init_db()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM analyses ORDER BY created_at DESC"
            ).fetchall()
            return [
                {
                    "analysis_id": r["id"],
                    "created_at": r["created_at"],
                    "counts": {
                        "documents": r["document_count"],
                        "entities": r["entity_count"],
                        "claims": r["claim_count"],
                        "conflicts": r["conflict_count"],
                        "twin_states": r["twin_state_count"],
                    },
                }
                for r in rows
            ]

    def get_analysis_result(self, analysis_id: str) -> Optional[AnalysisResult]:
        self.init_db()
        with self._connect() as conn:
            analysis_row = conn.execute(
                "SELECT * FROM analyses WHERE id = ?",
                (analysis_id,),
            ).fetchone()
            if analysis_row is None:
                return None

            doc_rows = conn.execute(
                "SELECT * FROM documents WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchall()
            documents = [
                SourceDocument(
                    id=r["id"],
                    filename=r["filename"],
                    file_type=r["file_type"],
                    source_type=r["source_type"],
                    sha256=r["sha256"],
                    stored_path=r["stored_path"],
                    text=r["text"],
                    metadata=json.loads(r["metadata_json"]),
                    flags=[SecurityFlag(**f) for f in json.loads(r["flags_json"])],
                    extraction_method=r["extraction_method"],
                    warnings=json.loads(r["warnings_json"]),
                    duplicate_of=r["duplicate_of"],
                    ingested_at=datetime.fromisoformat(r["ingested_at"]),
                )
                for r in doc_rows
            ]

            ent_rows = conn.execute(
                "SELECT * FROM entities WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchall()
            entities = [
                Entity(
                    id=r["id"],
                    canonical_name=r["canonical_name"],
                    entity_type=r["entity_type"],
                    aliases=json.loads(r["aliases_json"]),
                )
                for r in ent_rows
            ]

            claim_rows = conn.execute(
                "SELECT * FROM claims WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchall()
            claims = [
                Claim(
                    id=r["id"],
                    source_id=r["source_id"],
                    source_label=r["source_label"],
                    entity_name=r["entity_name"],
                    entity_id=r["entity_id"],
                    predicate=r["predicate"],
                    value=r["value"],
                    value_num=r["value_num"],
                    unit=r["unit"],
                    stage=r["stage"],
                    event_time=_iso_to_dt(r["event_time"]),
                    location=r["location"],
                    raw_text=r["raw_text"],
                    locator=r["locator"],
                    suspicious=bool(r["suspicious"]),
                    status=r["status"],
                    reliability=r["reliability"] if "reliability" in r.keys() else 0.0,
                )
                for r in claim_rows
            ]

            conf_rows = conn.execute(
                "SELECT * FROM conflicts WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchall()
            conflicts = [
                Conflict(
                    id=r["id"],
                    conflict_type=r["conflict_type"],
                    claim_ids=json.loads(r["claim_ids_json"]),
                    entity_name=r["entity_name"],
                    predicate=r["predicate"],
                    explanation=r["explanation"],
                    severity=r["severity"],
                    needs_review=bool(r["needs_review"]),
                    rule=r["rule"] if "rule" in r.keys() else "",
                )
                for r in conf_rows
            ]

            twin_rows = conn.execute(
                "SELECT * FROM twin_states WHERE analysis_id = ? ORDER BY row_id ASC",
                (analysis_id,),
            ).fetchall()
            twin_states = [
                TwinState(
                    entity_id=r["entity_id"],
                    entity_name=r["entity_name"],
                    attribute=r["attribute"],
                    value=r["value"],
                    valid_from=_iso_to_dt(r["valid_from"]),
                    valid_to=_iso_to_dt(r["valid_to"]),
                    claim_id=r["claim_id"],
                    source_id=r["source_id"],
                    status=r["status"],
                    reliability=r["reliability"],
                    source_filename=r["source_filename"] if "source_filename" in r.keys() else None,
                    locator=r["locator"] if "locator" in r.keys() else None,
                )
                for r in twin_rows
            ]

            return AnalysisResult(
                documents=documents,
                entities=entities,
                claims=claims,
                conflicts=conflicts,
                twin_states=twin_states,
                warnings=json.loads(analysis_row["warnings_json"]),
                created_at=datetime.fromisoformat(analysis_row["created_at"]),
            )

    def delete_analysis(self, analysis_id: str) -> bool:
        self.init_db()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
            return cur.rowcount > 0
