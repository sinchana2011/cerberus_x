<<<<<<< HEAD
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
=======
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.extractor import extract_file
from core.sanitizer import sanitize
from core.entity_resolver import EntityResolver

from core.schemas import (
    AnalysisResult,
    Claim,
    ClaimStatus,
    WorkflowStage,
    make_id,
)

from core.graph_engine import (
    EvidenceGraph,
    detect_conflicts,
)

from core.digital_twin import build_twin_states


DATE_FORMATS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
]


def parse_date(text):

    for fmt in DATE_FORMATS:

        try:
            return datetime.strptime(text, fmt)

        except ValueError:
            continue

    return None


def _add_claim(
    claims,
    resolver,
    document,
    segment,
    entity_name,
    predicate,
    value,
    stage=WorkflowStage.UNKNOWN,
    event_time=None,
    location=None,
    unit=None,
    source_label=None,
):

    if not entity_name or not value:
        return

    entity_type = "unknown"

    if re.search(
        r"\b(shipment|truck|vehicle)\b",
        entity_name,
        re.I,
    ):
        entity_type = "shipment"

    elif re.search(
        r"\b(purchase order|po-)\b",
        entity_name,
        re.I,
    ):
        entity_type = "order"

    elif predicate == "role":
        entity_type = "organization"

    match = resolver.resolve(
        entity_name,
        entity_type,
    )

    claim = Claim(
        id=make_id(
            "clm",
            document.id,
            segment.locator,
            predicate,
            value,
        ),
        source_id=document.id,
        source_label=source_label,
        entity_name=entity_name,
        entity_id=match.entity_id,
        predicate=predicate,
        value=str(value),
        value_num=(
            float(value)
            if str(value).replace(".", "", 1).isdigit()
            else None
        ),
        unit=unit,
        stage=stage,
        event_time=event_time,
        location=location,
        raw_text=segment.text,
        locator=segment.locator,
        suspicious=False,
        status=ClaimStatus.UNVERIFIED,
    )

    claims.append(claim)


def extract_claims(
    document,
    sanitized,
    resolver,
):

    claims = []

    for item in sanitized.segments:

        segment = item.segment

        # Never extract factual claims from withheld evidence.
        if item.suspicious:
            continue

        text = segment.text.strip()

        if not text:
            continue

        # --------------------------------------------------
        # 1. Structured CSV records
        # --------------------------------------------------

        fields = segment.fields or {}

        if fields:

            entity = fields.get("entity", "")
            attribute = fields.get("attribute", "")
            value = fields.get("value", "")
            unit = fields.get("unit")
            timestamp = fields.get("timestamp")

            source_label = fields.get("source")

            stage = WorkflowStage.UNKNOWN

            if "dispatch" in attribute.lower():
                stage = WorkflowStage.DISPATCHED

            elif "order" in attribute.lower():
                stage = WorkflowStage.ORDERED

            elif "deliver" in attribute.lower():
                stage = WorkflowStage.DELIVERED

            event_time = (
                parse_date(timestamp)
                if timestamp
                else None
            )

            if entity and attribute and value:

                _add_claim(
                    claims,
                    resolver,
                    document,
                    segment,
                    entity,
                    "quantity",
                    value,
                    stage,
                    event_time,
                    unit=unit,
                    source_label=source_label,
                )

            continue

        # --------------------------------------------------
        # 2. Quantity claims
        # --------------------------------------------------

        quantity_pattern = re.compile(
            r"(?P<entity>"
            r"(?:Shipment|Purchase Order|PO)"
            r"[\s-]*[A-Z0-9-]+"
            r")",
            re.I,
        )

        quantity_match = quantity_pattern.search(text)

        quantity = re.search(
            r"\b(?P<verb>ordered|dispatched|delivered)"
            r"\s+(?P<number>\d+(?:\.\d+)?)"
            r"\s+(?P<unit>units?|items?|pieces?)\b",
            text,
            re.I,
        )

        if quantity_match and quantity:

            entity = quantity_match.group("entity")

            verb = quantity.group("verb").lower()

            stage = {
                "ordered": WorkflowStage.ORDERED,
                "dispatched": WorkflowStage.DISPATCHED,
                "delivered": WorkflowStage.DELIVERED,
            }[verb]

            _add_claim(
                claims,
                resolver,
                document,
                segment,
                entity,
                "quantity",
                quantity.group("number"),
                stage,
                unit=quantity.group("unit"),
            )

        # --------------------------------------------------
        # 3. CEO / role claims
        # --------------------------------------------------

        role_match = re.search(
            r"(?P<person>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
            r"\s+is\s+the\s+"
            r"(?P<role>CEO|CFO|CTO|manager)"
            r"\s+of\s+"
            r"(?P<org>[A-Z][A-Za-z0-9& ]+)",
            text,
            re.I,
        )

        if role_match:

            date_match = re.search(
                r"\b(\d{4}-\d{2}-\d{2})\b",
                text,
            )

            event_time = (
                parse_date(date_match.group(1))
                if date_match
                else None
            )

            person = role_match.group("person")
            role = role_match.group("role")
            org = role_match.group("org").strip().rstrip(".")

            _add_claim(
                claims,
                resolver,
                document,
                segment,
                org,
                "role:" + role.upper(),
                person,
                event_time=event_time,
            )

        # --------------------------------------------------
        # 4. Transport departure and arrival
        # --------------------------------------------------

        movement = re.search(
            r"(?P<entity>Truck\s+[A-Z0-9-]+)"
            r"\s+(?P<action>departed|arrived)"
            r"\s+(?P<place>[A-Za-z ]+?)"
            r"\s+on\s+"
            r"(?P<date>\d{4}-\d{2}-\d{2})"
            r"\s+at\s+"
            r"(?P<time>\d{2}:\d{2})",
            text,
            re.I,
        )

        if movement:

            entity = movement.group("entity")
            action = movement.group("action").lower()
            place = movement.group("place").strip()

            event_time = parse_date(
                movement.group("date")
                + " "
                + movement.group("time")
            )

            _add_claim(
                claims,
                resolver,
                document,
                segment,
                entity,
                action,
                place,
                event_time=event_time,
                location=place,
            )

        # --------------------------------------------------
        # 5. Person location claims
        # --------------------------------------------------

        person_location = re.search(
            r"(?P<person>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
            r"\s+(?:signed|attended|visited|was|is)"
            r".*?\bin\s+"
            r"(?P<place>Mumbai|Pune|Delhi|Bengaluru|Chennai)"
            r".*?"
            r"(?P<date>\d{4}-\d{2}-\d{2})"
            r"(?:\s+at\s+(?P<time>\d{2}:\d{2}))?",
            text,
            re.I,
        )

        if person_location:

            person = person_location.group("person")
            place = person_location.group("place")

            date_text = person_location.group("date")
            time_text = person_location.group("time") or "00:00"

            event_time = parse_date(
                date_text + " " + time_text
            )

            _add_claim(
                claims,
                resolver,
                document,
                segment,
                person,
                "location",
                place,
                event_time=event_time,
                location=place,
            )

    return claims


class CerberusPipeline:

    def __init__(self):

        self.resolver = EntityResolver()
        self.evidence_graph = EvidenceGraph()

    def process_files(
        self,
        paths,
        save_path=None,
    ):

        result = AnalysisResult()

        for path in paths:

            path = Path(path)

            extraction = extract_file(path)

            if not extraction.ok:

                result.warnings.append(
                    f"{path.name}: {extraction.error}"
                )

                continue

            sanitized = sanitize(extraction)

            document = sanitized.document

            result.documents.append(document)

            result.warnings.extend(
                sanitized.warnings
            )

            claims = extract_claims(
                document,
                sanitized,
                self.resolver,
            )

            result.claims.extend(claims)

        result.entities = self.resolver.entities

        # Identify conflicts and duplicates.
        result.conflicts = detect_conflicts(
            result.claims
        )

        # Construct digital twin states.
        result.twin_states = build_twin_states(
            result
        )

        # Construct evidence graph.
        self.evidence_graph.build(result)

        # Rebuild after conflict detection.
        self.evidence_graph.build(result)

        if save_path:

            result.save_json(
                Path(save_path)
            )

        return result


def run_pipeline(paths, save_path=None):

    pipeline = CerberusPipeline()

    return pipeline.process_files(
        paths,
        save_path=save_path,
    )


if __name__ == "__main__":

    demo_folder = Path("demo_data")

    files = [
        demo_folder / "case1_quantity_conflict.csv",
        demo_folder / "case2_order_vs_dispatch.txt",
        demo_folder / "case3_leadership.txt",
        demo_folder / "case4_hidden_instruction.pdf",
        demo_folder / "case5_timeline.txt",
    ]

    result = run_pipeline(
        files,
        save_path="data/analysis/analysis.json",
    )

    print("\nCERBERUS-X ANALYSIS COMPLETE")
    print("-" * 40)

    print("Documents:", len(result.documents))
    print("Entities:", len(result.entities))
    print("Claims:", len(result.claims))
    print("Conflicts:", len(result.conflicts))
    print("Digital Twin States:", len(result.twin_states))

    print("\nDetected Conflicts:")

    for conflict in result.conflicts:

        print(
            conflict.conflict_type.value,
            "->",
            conflict.explanation,
        )
>>>>>>> 4682e39edabba11574378524c8a1f84a103cb8cf
