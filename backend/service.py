"""Application service layer bridging core/pipeline with SQLite and FastAPI."""

from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from typing import Optional

from backend.config import BASE_DIR
from backend.database import AnalysisRepository
from backend.schemas import (
    AnalysisCounts,
    AnalysisDetailResponse,
    AnalysisListItem,
    AnalysisListResponse,
    AskResponse,
    BriefResponse,
    ConflictClaimDTO,
    ConflictDTO,
    ConflictsResponse,
    DeleteAnalysisResponse,
    DigitalTwinEntityView,
    DigitalTwinResponse,
    DocumentDTO,
    ForensicDocumentDTO,
    ForensicsResponse,
    GraphResponse,
    GraphStatistics,
    ReactFlowEdge,
    ReactFlowNode,
    ReactFlowPosition,
    UploadAnalysisResponse,
)
from core.digital_twin import DigitalTwin
from core.extractor import MAX_FILE_BYTES, save_upload
from core.graph_engine import EvidenceGraph, KIND_CLAIM, KIND_ENTITY, KIND_SOURCE, REL_CONTRADICTS
from core.llm import get_ollama_model, summarize_investigation, synthesize_answer
from core.reasoner import answer_question
from core.schemas import (
    AnalysisResult,
    ClaimStatus,
    Conflict,
    ConflictType,
    Severity,
    SourceDocument,
    TwinState,
)
from pipeline import run_pipeline


class AnalysisNotFoundError(KeyError):
    """Raised when an analysis_id does not exist in SQLite."""


class InvalidUploadError(ValueError):
    """Raised when an upload request contains no valid processable files."""


def _doc_dto(doc: SourceDocument) -> DocumentDTO:
    return DocumentDTO(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        source_type=doc.source_type,
        sha256=doc.sha256,
        extraction_method=doc.extraction_method,
        reliability=doc.reliability,
        is_suspicious=doc.is_suspicious,
        flags=doc.flags,
        warnings=doc.warnings,
        metadata=doc.metadata,
        duplicate_of=doc.duplicate_of,
        ingested_at=doc.ingested_at,
    )


def _conflict_dto(conflict: Conflict, result: AnalysisResult) -> ConflictDTO:
    claims_info: list[ConflictClaimDTO] = []
    for cid in conflict.claim_ids:
        claim = result.claim_by_id(cid)
        if claim is None:
            continue
        doc = result.doc_by_id(claim.source_id)
        claims_info.append(
            ConflictClaimDTO(
                id=claim.id,
                source_id=claim.source_id,
                source_filename=doc.filename if doc else None,
                source_label=claim.source_label,
                value=claim.value,
                unit=claim.unit,
                stage=claim.stage,
                event_time=claim.event_time,
                location=claim.location,
                locator=claim.locator,
                status=claim.status,
                reliability=claim.reliability if claim.reliability else (doc.reliability if doc else 0.0),
                raw_text=claim.raw_text,
            )
        )
    return ConflictDTO(
        id=conflict.id,
        conflict_type=conflict.conflict_type,
        claim_ids=conflict.claim_ids,
        entity_name=conflict.entity_name,
        predicate=conflict.predicate,
        explanation=conflict.explanation,
        severity=conflict.severity,
        needs_review=conflict.needs_review,
        is_real_problem=conflict.is_real_problem,
        rule=conflict.rule,
        claims=claims_info,
    )


def _counts(result: AnalysisResult) -> AnalysisCounts:
    return AnalysisCounts(
        documents=len(result.documents),
        entities=len(result.entities),
        claims=len(result.claims),
        conflicts=len(result.conflicts),
        twin_states=len(result.twin_states),
    )


class CerberusService:
    """Orchestrates evidence ingestion, persistence, and query projections."""

    def __init__(self, repo: AnalysisRepository, upload_dir: Path) -> None:
        self.repo = repo
        self.upload_dir = Path(upload_dir)

    def _require_result(self, analysis_id: str) -> AnalysisResult:
        result = self.repo.get_analysis_result(analysis_id)
        if result is None:
            raise AnalysisNotFoundError(f"Analysis '{analysis_id}' not found.")
        return result

    def ingest_uploads(self, files: list[tuple[str, bytes]]) -> UploadAnalysisResponse:
        if not files:
            raise InvalidUploadError("At least one file must be uploaded.")

        analysis_id = f"anl_{uuid.uuid4().hex[:12]}"
        run_upload_dir = self.upload_dir / analysis_id
        saved_paths: list[Path] = []

        for filename, data in files:
            if not filename or not filename.strip():
                raise InvalidUploadError("Uploaded file is missing a filename.")
            if not data:
                raise InvalidUploadError(f"Uploaded file '{filename}' is empty.")
            if len(data) > MAX_FILE_BYTES:
                raise InvalidUploadError(
                    f"Uploaded file '{filename}' exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit."
                )
            saved_paths.append(save_upload(filename, data, run_upload_dir))

        pipeline_result = run_pipeline(saved_paths, save=False)
        ok_reports = [
            r for r in pipeline_result.file_reports if r.status in ("ok", "duplicate")
        ]
        if not ok_reports:
            reasons = "; ".join(
                r.error or "; ".join(r.warnings)
                for r in pipeline_result.file_reports
                if r.error or r.warnings
            ) or "; ".join(pipeline_result.warnings) or "No readable documents could be extracted."
            raise InvalidUploadError(reasons)

        analysis = pipeline_result.analysis
        self.repo.save_analysis(analysis_id, analysis)
        return UploadAnalysisResponse(
            analysis_id=analysis_id,
            created_at=analysis.created_at,
            counts=_counts(analysis),
            warnings=analysis.warnings,
            documents=[_doc_dto(d) for d in analysis.documents],
        )

    def ingest_demo(self, include_bonus_image: bool = True) -> UploadAnalysisResponse:
        demo_dir = BASE_DIR / "demo_data"
        candidates = [
            demo_dir / "case1_quantity_conflict.csv",
            demo_dir / "case2_order_vs_dispatch.txt",
            demo_dir / "case3_leadership.txt",
            demo_dir / "case4_hidden_instruction.pdf",
            demo_dir / "case5_timeline.txt",
        ]
        if include_bonus_image and (demo_dir / "bonus_scanned_note.png").exists():
            candidates.append(demo_dir / "bonus_scanned_note.png")

        existing = [p for p in candidates if p.exists()]
        if not existing:
            raise InvalidUploadError(
                "Demo dataset files were not found in demo_data/. Run generate_demo_data.py first."
            )

        analysis_id = f"anl_demo_{uuid.uuid4().hex[:8]}"
        pipeline_result = run_pipeline(existing, save=False)
        analysis = pipeline_result.analysis
        self.repo.save_analysis(analysis_id, analysis)
        return UploadAnalysisResponse(
            analysis_id=analysis_id,
            created_at=analysis.created_at,
            counts=_counts(analysis),
            warnings=analysis.warnings,
            documents=[_doc_dto(d) for d in analysis.documents],
        )

    def list_analyses(self) -> AnalysisListResponse:
        rows = self.repo.list_analyses()
        items = [
            AnalysisListItem(
                analysis_id=row["analysis_id"],
                created_at=row["created_at"],
                counts=AnalysisCounts(**row["counts"]),
            )
            for row in rows
        ]
        aggregate = AnalysisCounts(
            documents=sum(item.counts.documents for item in items),
            entities=sum(item.counts.entities for item in items),
            claims=sum(item.counts.claims for item in items),
            conflicts=sum(item.counts.conflicts for item in items),
            twin_states=sum(item.counts.twin_states for item in items),
        )
        return AnalysisListResponse(
            total_investigations=len(items),
            aggregate_counts=aggregate,
            investigations=items,
        )

    def delete_analysis(self, analysis_id: str) -> DeleteAnalysisResponse:
        deleted = self.repo.delete_analysis(analysis_id)
        if not deleted:
            raise AnalysisNotFoundError(f"Analysis '{analysis_id}' not found.")
        return DeleteAnalysisResponse(analysis_id=analysis_id, deleted=True)

    def get_analysis(self, analysis_id: str) -> AnalysisDetailResponse:
        result = self._require_result(analysis_id)
        return AnalysisDetailResponse(
            analysis_id=analysis_id,
            created_at=result.created_at,
            counts=_counts(result),
            documents=[_doc_dto(d) for d in result.documents],
            entities=result.entities,
            claims=result.claims,
            conflicts=[_conflict_dto(c, result) for c in result.conflicts],
            twin_states=result.twin_states,
            warnings=result.warnings,
        )

    def get_graph(self, analysis_id: str) -> GraphResponse:
        result = self._require_result(analysis_id)
        engine = EvidenceGraph.from_analysis(result)
        nx_graph = engine.graph
        docs_by_id = {d.id: d for d in result.documents}

        column_x = {
            "document": 40.0,
            "claim": 420.0,
            "entity": 820.0,
        }
        row_spacing = {
            "document": 150.0,
            "claim": 135.0,
            "entity": 150.0,
        }
        row_counters: dict[str, int] = defaultdict(int)
        nodes: list[ReactFlowNode] = []

        for node_id, attrs in nx_graph.nodes(data=True):
            kind = attrs.get("kind", "unknown")
            ntype = "document" if kind == KIND_SOURCE else kind
            idx = row_counters[ntype]
            row_counters[ntype] += 1
            x = column_x.get(ntype, 0.0)
            y = 40.0 + idx * row_spacing.get(ntype, 130.0)

            payload = attrs.get("data", {}) if isinstance(attrs.get("data"), dict) else {}
            data: dict = {
                "label": attrs.get("label", str(node_id)),
                "nodeType": ntype,
            }
            if ntype == "document":
                doc = docs_by_id.get(str(node_id))
                data.update({
                    "filename": payload.get("filename", attrs.get("label", str(node_id))),
                    "file_type": payload.get("file_type", "unknown"),
                    "source_type": payload.get("source_type", "unknown"),
                    "extraction_method": payload.get("extraction_method", "none"),
                    "reliability": doc.reliability if doc else 0.4,
                    "is_suspicious": doc.is_suspicious if doc else False,
                    "flag_count": len(doc.flags) if doc else 0,
                })
            elif ntype == "claim":
                data.update({
                    "predicate": payload.get("predicate", ""),
                    "value": payload.get("value", ""),
                    "unit": payload.get("unit"),
                    "stage": payload.get("stage", "unknown"),
                    "status": attrs.get("status", payload.get("status", "unverified")),
                    "suspicious": bool(attrs.get("suspicious", payload.get("suspicious", False))),
                    "reliability": payload.get("reliability", 0.0),
                    "event_time": payload.get("event_time"),
                    "location": payload.get("location"),
                    "locator": payload.get("locator"),
                    "entity_name": payload.get("entity_name", ""),
                    "raw_text": payload.get("raw_text", ""),
                })
            elif ntype == "entity":
                data.update({
                    "entity_type": payload.get("entity_type", "unknown"),
                    "aliases": payload.get("aliases", []),
                })

            nodes.append(
                ReactFlowNode(
                    id=str(node_id),
                    type=ntype,
                    position=ReactFlowPosition(x=x, y=y),
                    data=data,
                )
            )

        edges: list[ReactFlowEdge] = []
        for idx, (src, dst, _key, attrs) in enumerate(nx_graph.edges(keys=True, data=True)):
            relation = attrs.get("relation", "RELATED_TO")
            edges.append(
                ReactFlowEdge(
                    id=f"edge_{idx}_{src}_{dst}",
                    source=str(src),
                    target=str(dst),
                    label=relation,
                    animated=(relation == REL_CONTRADICTS),
                    data={
                        "relation": relation,
                        "conflict_id": attrs.get("conflict_id"),
                        "conflict_type": attrs.get("conflict_type"),
                        "severity": attrs.get("severity"),
                        "explanation": attrs.get("explanation"),
                        "locator": attrs.get("locator"),
                        "filename": attrs.get("filename"),
                    },
                )
            )

        summary = engine.summary()
        return GraphResponse(
            analysis_id=analysis_id,
            nodes=nodes,
            edges=edges,
            statistics=GraphStatistics(
                nodes=summary["nodes"],
                edges=summary["edges"],
                documents=summary["sources"],
                entities=summary["entities"],
                claims=summary["claims"],
                conflicts=len(result.conflicts),
            ),
        )

    def get_conflicts(
        self,
        analysis_id: str,
        *,
        conflict_type: Optional[ConflictType] = None,
        severity: Optional[Severity] = None,
        only_real_problems: bool = False,
    ) -> ConflictsResponse:
        result = self._require_result(analysis_id)
        items = [_conflict_dto(c, result) for c in result.conflicts]
        if conflict_type is not None:
            items = [c for c in items if c.conflict_type == conflict_type]
        if severity is not None:
            items = [c for c in items if c.severity == severity]
        if only_real_problems:
            items = [c for c in items if c.is_real_problem]

        real_count = sum(1 for c in result.conflicts if c.is_real_problem)
        return ConflictsResponse(
            analysis_id=analysis_id,
            total=len(items),
            real_problem_count=real_count,
            conflicts=items,
        )

    def get_digital_twin(
        self,
        analysis_id: str,
        *,
        entity_id: Optional[str] = None,
    ) -> DigitalTwinResponse:
        result = self._require_result(analysis_id)
        graph = EvidenceGraph.from_analysis(result)
        twin = DigitalTwin(graph)

        entities_by_id = {e.id: e for e in result.entities}
        target_ids = [entity_id] if entity_id else twin.entity_ids()

        entity_views: list[DigitalTwinEntityView] = []
        filtered_states: list[TwinState] = []

        for eid in target_ids:
            states = twin.history(eid, include_suspicious=True)
            if not states:
                continue
            filtered_states.extend(states)
            ent = entities_by_id.get(eid)
            current_list = twin.current_states(eid)
            current_attributes: dict[str, TwinState] = {}
            for st in current_list:
                current_attributes.setdefault(st.attribute, st)
            entity_views.append(
                DigitalTwinEntityView(
                    entity_id=eid,
                    canonical_name=ent.canonical_name if ent else states[0].entity_name,
                    entity_type=ent.entity_type if ent else "unknown",
                    aliases=ent.aliases if ent else [],
                    states=states,
                    current_attributes=current_attributes,
                )
            )

        summary = {
            "total_entities": len(entity_views),
            "total_states": len(filtered_states),
            "verified_states": sum(1 for s in filtered_states if s.status == ClaimStatus.VERIFIED),
            "disputed_states": sum(1 for s in filtered_states if s.status == ClaimStatus.DISPUTED),
            "superseded_states": sum(1 for s in filtered_states if s.status == ClaimStatus.SUPERSEDED),
            "suspicious_states": sum(1 for s in filtered_states if s.status == ClaimStatus.SUSPICIOUS),
            "undated_states": sum(1 for s in filtered_states if s.valid_from is None),
        }

        return DigitalTwinResponse(
            analysis_id=analysis_id,
            summary=summary,
            entities=entity_views,
            states=filtered_states,
        )

    def ask(
        self,
        analysis_id: str,
        question: str,
        *,
        use_llm: bool = False,
    ) -> AskResponse:
        result = self._require_result(analysis_id)
        ans = answer_question(
            question,
            result.claims,
            result.conflicts,
            result.documents,
            result.entities,
        )

        answer_text = ans.answer_text
        used_llm = False
        model_name: Optional[str] = None
        notes = list(ans.notes)

        if use_llm:
            llm_text, llm_note = synthesize_answer(
                question,
                ans,
                result.claims,
                result.conflicts,
                result.documents,
            )
            if llm_text:
                answer_text = llm_text
                used_llm = True
                model_name = get_ollama_model()
                notes.insert(
                    0,
                    f"Synthesized locally with Ollama ({model_name}) from grounded evidence citations.",
                )
            elif llm_note:
                notes.append(llm_note)

        return AskResponse(
            analysis_id=analysis_id,
            question=ans.question,
            status=ans.status,
            answer_text=answer_text,
            confidence=ans.confidence,
            citations=ans.citations,
            conflict_ids=ans.conflict_ids,
            excluded_claim_ids=ans.excluded_claim_ids,
            used_llm=used_llm,
            model=model_name,
            notes=notes,
        )

    def generate_brief(self, analysis_id: str) -> BriefResponse:
        result = self._require_result(analysis_id)
        summary, highlights, used_llm, model_name, notes = summarize_investigation(result)
        return BriefResponse(
            analysis_id=analysis_id,
            summary=summary,
            highlights=highlights,
            used_llm=used_llm,
            model=model_name,
            notes=notes,
        )

    def get_forensics(self, analysis_id: str) -> ForensicsResponse:
        result = self._require_result(analysis_id)
        docs = [
            ForensicDocumentDTO(
                id=d.id,
                filename=d.filename,
                file_type=d.file_type,
                source_type=d.source_type,
                sha256=d.sha256,
                extraction_method=d.extraction_method,
                reliability=d.reliability,
                is_suspicious=d.is_suspicious,
                flags=d.flags,
                warnings=d.warnings,
                metadata=d.metadata,
                raw_text=d.text,
            )
            for d in result.documents
        ]
        return ForensicsResponse(
            analysis_id=analysis_id,
            total_documents=len(docs),
            suspicious_documents=sum(1 for d in docs if d.is_suspicious),
            total_flags=sum(len(d.flags) for d in docs),
            documents=docs,
        )
