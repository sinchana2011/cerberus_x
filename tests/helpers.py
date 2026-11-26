"""Small factories shared by Batch 3 tests."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from core.schemas import (Claim, Entity, FileType, SecurityFlag, SecurityFlagKind, Severity,
                          SourceDocument, SourceType, WorkflowStage)


def T(text: str) -> datetime:
    return datetime.fromisoformat(text)


def hidden_flags() -> list[SecurityFlag]:
    return [SecurityFlag(kind=SecurityFlagKind.HIDDEN_TEXT, severity=Severity.HIGH,
                         description="hidden")]


def make_doc(doc_id: str = "d1", filename: str = "file.txt",
             source_type: SourceType = SourceType.FREEFORM_NOTE,
             flags: Optional[list[SecurityFlag]] = None) -> SourceDocument:
    return SourceDocument(id=doc_id, filename=filename, file_type=FileType.TEXT,
                          source_type=source_type, sha256="0" * 64, flags=flags or [])


def make_entity(ent_id: str = "e1", name: str = "Shipment SH-1",
                etype: str = "shipment") -> Entity:
    return Entity(id=ent_id, canonical_name=name, entity_type=etype)


def make_claim(claim_id: str, *, source_id: str = "d1", entity_name: str = "Shipment SH-1",
               entity_id: str = "e1", predicate: str = "quantity", value: str = "85",
               value_num: Optional[float] = None, stage: WorkflowStage = WorkflowStage.UNKNOWN,
               event_time: Optional[datetime] = None, location: Optional[str] = None,
               source_label: Optional[str] = None, suspicious: bool = False,
               locator: str = "line 1", raw_text: Optional[str] = None) -> Claim:
    if value_num is None and predicate == "quantity":
        value_num = float(value)
    return Claim(id=claim_id, source_id=source_id, source_label=source_label,
                 entity_name=entity_name, entity_id=entity_id, predicate=predicate, value=value,
                 value_num=value_num, unit="units" if predicate == "quantity" else None,
                 stage=stage, event_time=event_time, location=location,
                 raw_text=raw_text or f"{entity_name} {predicate} {value}", locator=locator,
                 suspicious=suspicious)