import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "write_v6_visual_qc.py"
)


def test_status_for_sku_marks_only_reviewed_mismatches_for_rerun():
    spec = importlib.util.spec_from_file_location("write_v6_visual_qc", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.status_for_sku("QY020") == "rerun"
    assert module.status_for_sku("QY002") == "pass"
