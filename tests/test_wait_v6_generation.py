import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "wait_v6_generation.py"
)


def test_task_directories_returns_submitted_runs_without_results(tmp_path):
    spec = importlib.util.spec_from_file_location("wait_v6_generation", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    generation = tmp_path / "QY002-hero" / "generation" / "01"
    generation.mkdir(parents=True)
    (generation / "submit.json").write_text(
        json.dumps({"data": {"out_task_id": "task-1"}}), encoding="utf-8"
    )

    assert module.task_directories(tmp_path) == [generation]
