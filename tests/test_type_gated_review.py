import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "build_type_gated_review.py"
)


def test_type_gated_review_index_links_to_run_root():
    spec = importlib.util.spec_from_file_location("type_gated_review", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.review_relative_path("QY002-hero") == "QY002-hero/review/review.html"
