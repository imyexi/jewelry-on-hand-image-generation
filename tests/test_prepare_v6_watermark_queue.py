import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "prepare_v6_watermark_queue.py"
)


def test_latest_passing_result_skips_newer_rerun(tmp_path):
    spec = importlib.util.spec_from_file_location("prepare_v6_watermark_queue", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for index, status in (("01", "pass"), ("02", "rerun")):
        directory = tmp_path / "generation" / index
        directory.mkdir(parents=True)
        (directory / "result.png").write_bytes(index.encode())
        (directory / "qc.json").write_text(json.dumps({"status": status}), encoding="utf-8")

    assert module.latest_passing_result(tmp_path).read_bytes() == b"01"
