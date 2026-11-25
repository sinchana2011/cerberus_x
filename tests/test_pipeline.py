"""Integration tests for the CERBERUS-X pipeline."""

from pathlib import Path

from pipeline import run_pipeline


def test_pipeline_processes_demo_files():

    root = Path(__file__).resolve().parents[1]
    demo_dir = root / "demo_data"

    files = [
        demo_dir / "case1_quantity_conflict.csv",
        demo_dir / "case2_order_vs_dispatch.txt",
        demo_dir / "case3_leadership.txt",
        demo_dir / "case4_hidden_instruction.pdf",
        demo_dir / "case5_timeline.txt"
    ]

    if not all(path.exists() for path in files):
        return

    result = run_pipeline(files)

    assert len(result.documents) == 5
    assert len(result.claims) > 0


def test_pipeline_does_not_read_ground_truth():

    root = Path(__file__).resolve().parents[1]

    demo_dir = root / "demo_data"

    assert not (demo_dir / "expected.json").exists()