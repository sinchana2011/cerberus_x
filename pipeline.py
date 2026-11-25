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