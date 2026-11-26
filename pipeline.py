"""End-to-end CERBERUS-X pipeline (independent of Streamlit, fully local).

extract -> sanitize -> claim extraction + entity resolution -> evidence graph
        -> deterministic analysis -> digital twin -> JSON on disk.

One bad file never stops the run. Nothing is sent to Ollama or any network
service; evidence is only read from and written to local disk.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Union

from pydantic import BaseModel, Field

from core.claim_extractor import extract_claims
from core.digital_twin import DigitalTwin
from core.entity_resolver import EntityResolver
from core.extractor import extract_file
from core.graph_engine import EvidenceGraph
from core.reasoner import ReasonerConfig, analyze, answer_question
from core.sanitizer import SanitizationResult, sanitize
from core.schemas import (Answer, AnalysisResult, Claim, FileType, SourceDocument,
                          SourceType, make_id)

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("data") / "analysis"


class SuspiciousItem(BaseModel):
    """A suspicious segment, kept for forensic review (never discarded)."""
    locator: str
    kind: str
    text: str
    reasons: list[str] = Field(default_factory=list)


class FileReport(BaseModel):
    """Per-file outcome shown to the user."""
    filename: str
    document_id: str
    status: str                              # "ok" | "failed" | "duplicate"
    error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    claim_count: int = 0
    suspicious: list[SuspiciousItem] = Field(default_factory=list)


@dataclass
class PipelineResult:
    analysis: AnalysisResult
    file_reports: list[FileReport]
    graph: EvidenceGraph
    saved_paths: dict[str, str] = field(default_factory=dict)
    config: ReasonerConfig = field(default_factory=ReasonerConfig)

    @property
    def documents(self) -> list[SourceDocument]:
        return self.analysis.documents

    @property
    def entities(self):
        return self.analysis.entities

    @property
    def claims(self) -> list[Claim]:
        return self.analysis.claims

    @property
    def conflicts(self):
        return self.analysis.conflicts

    @property
    def twin_states(self):
        return self.analysis.twin_states

    @property
    def warnings(self) -> list[str]:
        return self.analysis.warnings

    @property
    def created_at(self) -> datetime:
        return self.analysis.created_at

    def save_json(self, path: Union[str, Path]) -> None:
        self.analysis.save_json(Path(path))

    def twin(self) -> DigitalTwin:
        return DigitalTwin(self.graph)

    def ask(self, question: str) -> Answer:
        """Answer a question from the analysed evidence only (no LLM)."""
        a = self.analysis
        return answer_question(question, a.claims, a.conflicts, a.documents, a.entities,
                               self.config)

    def suspicious_claims(self) -> list[Claim]:
        return [c for c in self.analysis.claims if c.suspicious]


def _failed_document(path: Path, message: str) -> SourceDocument:
    return SourceDocument(id=make_id("doc", path.name, "error"), filename=path.name,
                          file_type=FileType.UNKNOWN, source_type=SourceType.UNKNOWN,
                          sha256="", stored_path=str(path), warnings=[message])


def _suspicious_items(sanitized: SanitizationResult) -> list[SuspiciousItem]:
    items = []
    for s in sanitized.suspicious_segments:
        reasons = [f.label for f in s.findings if f.category != "formatting"]
        items.append(SuspiciousItem(locator=s.segment.locator, kind=s.segment.kind.value,
                                    text=s.segment.text, reasons=reasons))
    return items


def _process_file(path: Path, enable_ocr: bool, resolver: EntityResolver,
                  seen: dict[str, SourceDocument]
                  ) -> tuple[SourceDocument, list[Claim], FileReport]:
    try:
        extraction = extract_file(path, enable_ocr=enable_ocr)
    except Exception as exc:  # extract_file should not raise; stay safe anyway
        logger.exception("Extraction crashed for %s", path)
        message = f"Unexpected extraction error: {exc}"
        doc = _failed_document(path, message)
        return doc, [], FileReport(filename=path.name, document_id=doc.id, status="failed",
                                   error=message, warnings=doc.warnings)
    doc = extraction.document
    if not extraction.ok:
        return doc, [], FileReport(filename=path.name, document_id=doc.id, status="failed",
                                   error=extraction.error, warnings=doc.warnings)

    original = seen.get(doc.sha256)
    if original is not None:
        note = f"Identical content to '{original.filename}'; not processed again."
        dup = doc.model_copy(update={"duplicate_of": original.id,
                                     "warnings": [*doc.warnings, note]})
        return dup, [], FileReport(filename=path.name, document_id=dup.id, status="duplicate",
                                   warnings=dup.warnings)
    seen[doc.sha256] = doc

    try:
        sanitized = sanitize(extraction)
        claims, notes = extract_claims(sanitized, resolver)
    except Exception as exc:
        logger.exception("Processing failed for %s", path)
        message = f"Processing failed: {exc}"
        failed = doc.model_copy(update={"warnings": [*doc.warnings, message]})
        return failed, [], FileReport(filename=path.name, document_id=doc.id, status="failed",
                                      error=message, warnings=failed.warnings)
    document = sanitized.document.model_copy(
        update={"warnings": [*sanitized.document.warnings, *notes]})
    report = FileReport(filename=path.name, document_id=document.id, status="ok",
                        warnings=document.warnings, claim_count=len(claims),
                        suspicious=_suspicious_items(sanitized))
    return document, claims, report


def run_pipeline(paths: Iterable[Union[str, Path]], *,
                 output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR, enable_ocr: bool = True,
                 config: Optional[ReasonerConfig] = None, save: bool = True) -> PipelineResult:
    """Process local evidence files and return the analysis.

    Saves ``analysis.json``, ``evidence_graph.json`` and ``file_reports.json`` in
    ``output_dir`` when ``save`` is true (write errors become warnings, not crashes).
    """
    cfg = config or ReasonerConfig()
    resolver = EntityResolver()
    seen: dict[str, SourceDocument] = {}
    documents: list[SourceDocument] = []
    raw_claims: list[Claim] = []
    reports: list[FileReport] = []
    warnings: list[str] = []

    path_list = [Path(p) for p in paths]
    if not path_list:
        warnings.append("No evidence files were supplied.")
    for path in path_list:
        document, claims, report = _process_file(path, enable_ocr, resolver, seen)
        documents.append(document)
        raw_claims.extend(claims)
        reports.append(report)
        if report.error:
            warnings.append(f"{path.name}: {report.error}")

    # Build the graph, then analyse the claims it holds.
    graph = EvidenceGraph()
    for entity in resolver.entities:
        graph.add_entity(entity)
    for document in documents:
        if document.sha256 and document.duplicate_of is None:
            graph.add_document(document)
    for claim in raw_claims:
        graph.add_claim(claim)

    outcome = analyze(graph.all_claims(), documents, cfg)
    for claim in outcome.claims:
        graph.add_claim(claim)
    for conflict in outcome.conflicts:
        graph.add_conflict(conflict)

    twin_states = DigitalTwin(graph).build_all()
    counts: dict[str, int] = {}
    for claim in outcome.claims:
        counts[claim.source_id] = counts.get(claim.source_id, 0) + 1
    for report in reports:
        report.claim_count = counts.get(report.document_id, report.claim_count)

    analysis = AnalysisResult(documents=documents, entities=resolver.entities,
                              claims=outcome.claims, conflicts=outcome.conflicts,
                              twin_states=twin_states, warnings=warnings)
    result = PipelineResult(analysis=analysis, file_reports=reports, graph=graph, config=cfg)

    if save:
        out = Path(output_dir)
        try:
            out.mkdir(parents=True, exist_ok=True)
            analysis.save_json(out / "analysis.json")
            graph.save_json(out / "evidence_graph.json")
            (out / "file_reports.json").write_text(
                json.dumps([r.model_dump(mode="json") for r in reports], indent=2),
                encoding="utf-8")
            result.saved_paths = {"analysis": str(out / "analysis.json"),
                                  "graph": str(out / "evidence_graph.json"),
                                  "file_reports": str(out / "file_reports.json")}
        except OSError as exc:
            analysis.warnings.append(f"Could not save results to {out}: {exc}")
    return result


def load_result(output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR,
                config: Optional[ReasonerConfig] = None) -> PipelineResult:
    """Reload a saved run (analysis, graph, file reports); raises ``ValueError`` if invalid."""
    out = Path(output_dir)
    analysis = AnalysisResult.load_json(out / "analysis.json")
    graph = EvidenceGraph.load_json(out / "evidence_graph.json")
    reports: list[FileReport] = []
    report_path = out / "file_reports.json"
    if report_path.exists():
        try:
            reports = [FileReport.model_validate(r)
                       for r in json.loads(report_path.read_text(encoding="utf-8"))]
        except Exception as exc:
            analysis.warnings.append(f"Could not read file_reports.json: {exc}")
    return PipelineResult(analysis=analysis, file_reports=reports, graph=graph,
                          saved_paths={"analysis": str(out / "analysis.json")},
                          config=config or ReasonerConfig())
