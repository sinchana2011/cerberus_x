from datetime import datetime, timezone

import pytest

from core.schemas import (
    AnalysisResult, Claim, ClaimStatus, SecurityFlag, SecurityFlagKind,
    Severity, SourceType, compute_reliability, make_id,
)


def _claim(**kw) -> Claim:
    base = dict(id="c1", source_id="s1", entity_name="X", predicate="p",
                value="1", raw_text="x is 1")
    base.update(kw)
    return Claim(**base)


def test_make_id_is_deterministic():
    assert make_id("clm", "a", 1) == make_id("clm", "a", 1)
    assert make_id("clm", "a", 1) != make_id("clm", "a", 2)
    assert make_id("clm", "a").startswith("clm_")


def test_hidden_text_lowers_reliability():
    clean = compute_reliability(SourceType.OFFICIAL_DOCUMENT, [])
    flag = SecurityFlag(kind=SecurityFlagKind.HIDDEN_TEXT, severity=Severity.HIGH,
                        description="white text")
    assert compute_reliability(SourceType.OFFICIAL_DOCUMENT, [flag]) < clean


def test_reliability_is_clamped():
    flags = [SecurityFlag(kind=k, severity=Severity.HIGH, description="x")
             for k in SecurityFlagKind]
    assert compute_reliability(SourceType.UNKNOWN, flags) == 0.0


def test_suspicious_claim_is_never_verified():
    c = _claim(suspicious=True, status=ClaimStatus.VERIFIED)
    assert c.status == ClaimStatus.SUSPICIOUS
    assert not c.is_verified and not c.is_usable


def test_event_time_is_normalised_to_naive_utc():
    aware = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)
    assert _claim(event_time=aware).event_time == datetime(2026, 3, 10, 14, 0)


def test_analysis_json_roundtrip(tmp_path):
    result = AnalysisResult(claims=[_claim()])
    path = tmp_path / "out" / "analysis.json"
    result.save_json(path)
    loaded = AnalysisResult.load_json(path)
    assert loaded.claims[0].id == "c1"


def test_load_json_reports_bad_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        AnalysisResult.load_json(bad)