import json
from contextlib import contextmanager
from pathlib import Path

import pytest

import jewelry_on_hand.generation as generation
from jewelry_on_hand.generation import GenerationError, run_generation
from jewelry_on_hand.review_decision import ReviewGateError
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


HELPER = Path("skills/aireiter-image-generation/scripts/aireiter_image_helper.py")


class Completed:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


@contextmanager
def fake_image_response(content=b"png-bytes"):
    class Response:
        def read(self):
            return content

    yield Response()


def test_generation_uses_reference_then_product(tmp_path, monkeypatch):
    paths, product, ref = _ready_run(tmp_path)
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    command = calls[0]
    first = command.index("--image") + 1
    second = command.index("--image", first) + 1
    assert command[first] == str(ref)
    assert command[second] == str(product)
    assert command[command.index("--model") + 1] == "gpt_image_2"
    assert command[command.index("--aspect-ratio") + 1] == "3:4"
    assert command[command.index("--resolution") + 1] == "2K"
    assert (paths.generation_dir / "01" / "model.txt").read_text(encoding="utf-8") == "gpt_image_2"


def test_generation_keeps_image_2_after_one_failed_qc(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)
    _write_qc(paths.generation_dir / "01", "rerun")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-2"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generation_dirs = run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert generation_dirs == [paths.generation_dir / "02"]
    assert calls[0][calls[0].index("--model") + 1] == "gpt_image_2"
    assert (paths.generation_dir / "02" / "model.txt").read_text(encoding="utf-8") == "gpt_image_2"


def test_generation_falls_back_to_nanobanana_after_more_than_one_failed_qc(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)
    _write_qc(paths.generation_dir / "01", "rerun")
    _write_qc(paths.generation_dir / "02", "reject")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-3"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generation_dirs = run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert generation_dirs == [paths.generation_dir / "03"]
    assert calls[0][calls[0].index("--model") + 1] == "nano_banana_v2"
    assert (paths.generation_dir / "03" / "model.txt").read_text(encoding="utf-8") == "nano_banana_v2"


def test_generation_assigns_unique_task_id_for_each_rank(tmp_path, monkeypatch):
    paths, product, ref_1 = _ready_run(
        tmp_path,
        decision={"action": "generate_multiple", "selected_ranks": [1, 2]},
    )
    ref_2 = tmp_path / "ref-2.jpg"
    ref_2.write_bytes(b"ref 2")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref_1), _selected_reference(2, ref_2)],
    )
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    run_generation(
        paths,
        product,
        {1: "prompt 1", 2: "prompt 2"},
        HELPER,
        wait=False,
    )

    task_ids = [command[command.index("--task-id") + 1] for command in calls]
    assert len(task_ids) == 2
    assert len(set(task_ids)) == 2
    assert task_ids[0].startswith("run-1-rank-01-")
    assert task_ids[1].startswith("run-1-rank-02-")


def test_generation_requires_selected_references(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    _write_confirmed_constraints(paths)
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "fidelity_confirmed": True})

    with pytest.raises(FileNotFoundError, match="selected_references.json"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)


def test_generation_requires_prompt_for_rank(tmp_path):
    paths, product, _ref = _ready_run(tmp_path)

    with pytest.raises(KeyError, match="rank 1"):
        run_generation(paths, product, {}, HELPER, wait=False)


def test_generation_accepts_string_prompt_rank_keys(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)

    def fake_run(command, capture_output, text, check=False):
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    run_generation(paths, product, {"1": "prompt text"}, HELPER, wait=False)

    assert (paths.generation_dir / "01" / "prompt.txt").read_text(encoding="utf-8") == "prompt text"


def test_generation_waits_and_writes_result(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)
    calls = []
    responses = iter(
        [
            {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}},
            {
                "ok": True,
                "data": {
                    "status": "completed",
                    "out_task_id": "task-1",
                    "output": [{"url": "https://example.com/result.png"}],
                },
            },
        ]
    )

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(json.dumps(next(responses)))

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(
        generation.urllib.request,
        "urlopen",
        lambda request, timeout=120: fake_image_response(b"image-bytes"),
    )

    generation_dirs = run_generation(
        paths,
        product,
        {1: "prompt text"},
        HELPER,
        wait=True,
    )

    assert generation_dirs == [paths.generation_dir / "01"]
    assert read_json(paths.generation_dir / "01" / "result.json")["data"]["status"] == "completed"
    assert (paths.generation_dir / "01" / "result.png").read_bytes() == b"image-bytes"
    assert "wait" in calls[1]
    assert calls[1][calls[1].index("--task-id") + 1] == "task-1"


def test_generation_uses_selected_ranks_only(tmp_path, monkeypatch):
    paths, product, ref_1 = _ready_run(
        tmp_path,
        decision={"action": "generate_selected", "selected_ranks": [2]},
    )
    ref_2 = tmp_path / "ref-2.jpg"
    ref_2.write_bytes(b"ref 2")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref_1), _selected_reference(2, ref_2)],
    )
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-2"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generation_dirs = run_generation(
        paths,
        product,
        {1: "prompt 1", 2: "prompt 2"},
        HELPER,
        wait=False,
    )

    assert generation_dirs == [paths.generation_dir / "01"]
    assert (paths.generation_dir / "01" / "prompt.txt").read_text(encoding="utf-8") == "prompt 2"
    assert (paths.generation_dir / "01" / "hand-reference.jpg").read_bytes() == b"ref 2"
    assert not (paths.generation_dir / "02").exists()
    assert len(calls) == 1


def test_generation_uses_sequential_output_dirs_for_non_contiguous_ranks(
    tmp_path,
    monkeypatch,
):
    paths, product, ref_1 = _ready_run(
        tmp_path,
        decision={"action": "generate_multiple", "selected_ranks": [2, 3]},
    )
    ref_2 = tmp_path / "ref-2.jpg"
    ref_2.write_bytes(b"ref 2")
    ref_3 = tmp_path / "ref-3.jpg"
    ref_3.write_bytes(b"ref 3")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [
            _selected_reference(1, ref_1),
            _selected_reference(2, ref_2),
            _selected_reference(3, ref_3),
        ],
    )
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generation_dirs = run_generation(
        paths,
        product,
        {2: "prompt 2", 3: "prompt 3"},
        HELPER,
        wait=False,
    )

    assert generation_dirs == [
        paths.generation_dir / "01",
        paths.generation_dir / "02",
    ]
    assert (paths.generation_dir / "01" / "prompt.txt").read_text(encoding="utf-8") == "prompt 2"
    assert (paths.generation_dir / "01" / "hand-reference.jpg").read_bytes() == b"ref 2"
    assert (paths.generation_dir / "02" / "prompt.txt").read_text(encoding="utf-8") == "prompt 3"
    assert (paths.generation_dir / "02" / "hand-reference.jpg").read_bytes() == b"ref 3"
    assert not (paths.generation_dir / "03").exists()
    task_ids = [command[command.index("--task-id") + 1] for command in calls]
    assert task_ids[0].startswith("run-1-rank-02-")
    assert task_ids[1].startswith("run-1-rank-03-")


def test_generation_preflight_rejects_later_non_empty_dir_without_submit(
    tmp_path,
    monkeypatch,
):
    paths, product, ref_1 = _ready_run(
        tmp_path,
        decision={"action": "generate_multiple", "selected_ranks": [1, 2]},
    )
    ref_2 = tmp_path / "ref-2.jpg"
    ref_2.write_bytes(b"ref 2")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref_1), _selected_reference(2, ref_2)],
    )
    existing_dir = paths.generation_dir / "02"
    existing_dir.mkdir()
    (existing_dir / "existing.txt").write_text("old", encoding="utf-8")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(
            paths,
            product,
            {1: "prompt 1", 2: "prompt 2"},
            HELPER,
            wait=False,
        )

    assert "02" in str(exc_info.value)
    assert calls == []
    assert not (paths.generation_dir / "01" / "prompt.txt").exists()
    assert not (paths.generation_dir / "01" / "submit.json").exists()


def test_generation_preflight_rejects_duplicate_selected_ranks_without_submit(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(
        tmp_path,
        decision={"action": "generate_multiple", "selected_ranks": [1, 1]},
    )
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(ReviewGateError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert "review_decision.json" in str(exc_info.value)
    assert calls == []


def test_generation_preflight_rejects_later_unwritable_dir_without_submit(
    tmp_path,
    monkeypatch,
):
    paths, product, ref_1 = _ready_run(
        tmp_path,
        decision={"action": "generate_multiple", "selected_ranks": [1, 2]},
    )
    ref_2 = tmp_path / "ref-2.jpg"
    ref_2.write_bytes(b"ref 2")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref_1), _selected_reference(2, ref_2)],
    )
    unwritable_dir = paths.generation_dir / "02"
    unwritable_dir.mkdir()
    calls = []

    def fake_probe(path):
        if path == unwritable_dir:
            raise OSError("拒绝写入")

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr(generation, "_ensure_writable_probe", fake_probe, raising=False)
    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(
            paths,
            product,
            {1: "prompt 1", 2: "prompt 2"},
            HELPER,
            wait=False,
        )

    assert "02" in str(exc_info.value)
    assert calls == []
    rank_1_dir = paths.generation_dir / "01"
    assert not (rank_1_dir / "prompt.txt").exists()
    assert not (rank_1_dir / "submit.json").exists()
    assert not (rank_1_dir / "hand-reference.jpg").exists()
    assert not list(unwritable_dir.glob(".write-test-*.tmp"))


def test_generation_rejects_existing_non_empty_generation_dir(tmp_path):
    paths, product, _ref = _ready_run(tmp_path)
    generation_dir = paths.generation_dir / "01"
    generation_dir.mkdir()
    (generation_dir / "existing.txt").write_text("old", encoding="utf-8")

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert "qc.json" in str(exc_info.value)
    assert "01" in str(exc_info.value)


def test_generation_rejects_manual_reference(tmp_path):
    paths, product, ref = _ready_run(
        tmp_path,
        decision={"action": "manual_reference", "manual_reference": "manual.jpg"},
    )
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref)],
    )

    with pytest.raises(ReviewGateError, match="manual_reference"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)


def test_generation_rejects_duplicate_reference_rank(tmp_path):
    paths, product, ref = _ready_run(tmp_path)
    other_ref = tmp_path / "ref-other.jpg"
    other_ref.write_bytes(b"other")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref), _selected_reference(1, other_ref)],
    )

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert "重复" in str(exc_info.value)
    assert "rank 1" in str(exc_info.value)


def test_generation_copies_reference_with_source_extension(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)
    ref_png = tmp_path / "ref.png"
    ref_png.write_bytes(b"png")
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref_png)],
    )

    def fake_run(command, capture_output, text, check=False):
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert (paths.generation_dir / "01" / "hand-reference.png").is_file()
    assert not (paths.generation_dir / "01" / "hand-reference.jpg").exists()


def test_generation_uses_review_copy_when_original_reference_is_missing(tmp_path, monkeypatch):
    paths, product, original_ref = _ready_run(tmp_path)
    review_copy = paths.review_dir / "rank-1-ref.jpg"
    review_copy.write_bytes(b"review-copy")
    original_ref.unlink()
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, review_copy)],
    )
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    command = calls[0]
    reference_index = command.index("--image") + 1
    assert command[reference_index] == str(review_copy)
    assert (paths.generation_dir / "01" / "hand-reference.jpg").read_bytes() == b"review-copy"


def test_generation_rejects_missing_reference_file(tmp_path):
    paths, product, _ref = _ready_run(tmp_path)
    missing_ref = tmp_path / "missing.jpg"
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, missing_ref)],
    )

    with pytest.raises(FileNotFoundError, match="参考图不存在"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)


def test_generation_rejects_non_json_helper_stdout(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)

    def fake_run(command, capture_output, text, check=False):
        return Completed("not json")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    message = str(exc_info.value)
    assert "submit" in message
    assert "rank 1" in message
    assert "JSON" in message
    assert not (paths.generation_dir / "01" / "submit.json").exists()


def test_generation_rejects_non_object_helper_json(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)

    def fake_run(command, capture_output, text, check=False):
        return Completed(json.dumps(["bad"]))

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert "JSON 对象" in str(exc_info.value)
    assert read_json(paths.generation_dir / "01" / "submit.json") == ["bad"]


def test_generation_saves_non_object_submit_json_before_raising_on_failure(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)

    def fake_run(command, capture_output, text, check=False):
        return Completed(json.dumps(["bad"]), returncode=2, stderr="submit failed")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    message = str(exc_info.value)
    assert "JSON 对象" in message
    assert "returncode=2" in message
    assert read_json(paths.generation_dir / "01" / "submit.json") == ["bad"]


def test_generation_saves_submit_json_before_raising_on_submit_failure(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)

    def fake_run(command, capture_output, text, check=False):
        return Completed(
            json.dumps({"ok": False, "data": {"out_task_id": "task-1"}}),
            returncode=2,
            stderr="submit failed",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    message = str(exc_info.value)
    assert "submit" in message
    assert "rank 1" in message
    assert "returncode=2" in message
    assert "submit failed" in message
    assert read_json(paths.generation_dir / "01" / "submit.json")["ok"] is False


def test_generation_saves_result_json_before_raising_on_wait_failure(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)
    responses = iter(
        [
            Completed(
                json.dumps(
                    {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
                )
            ),
            Completed(
                json.dumps(
                    {"ok": False, "data": {"status": "failed", "out_task_id": "task-1"}}
                ),
                returncode=3,
                stderr="wait failed",
            ),
        ]
    )

    def fake_run(command, capture_output, text, check=False):
        return next(responses)

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=True)

    message = str(exc_info.value)
    assert "wait" in message
    assert "rank 1" in message
    assert "returncode=3" in message
    assert "wait failed" in message
    assert read_json(paths.generation_dir / "01" / "result.json")["data"]["status"] == "failed"


def test_generation_requires_result_output_url_before_success(tmp_path, monkeypatch):
    paths, product, _ref = _ready_run(tmp_path)
    responses = iter(
        [
            Completed(
                json.dumps(
                    {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
                )
            ),
            Completed(
                json.dumps(
                    {"ok": True, "data": {"status": "completed", "out_task_id": "task-1"}}
                )
            ),
        ]
    )

    def fake_run(command, capture_output, text, check=False):
        return next(responses)

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError, match="output"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=True)

    assert read_json(paths.generation_dir / "01" / "result.json")["data"]["status"] == "completed"
    assert not (paths.generation_dir / "01" / "result.png").exists()


def test_generation_saves_non_object_result_json_before_raising_on_wait_failure(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)
    responses = iter(
        [
            Completed(
                json.dumps(
                    {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
                )
            ),
            Completed(json.dumps(["bad"]), returncode=3, stderr="wait failed"),
        ]
    )

    def fake_run(command, capture_output, text, check=False):
        return next(responses)

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=True)

    message = str(exc_info.value)
    assert "wait" in message
    assert "JSON 对象" in message
    assert "returncode=3" in message
    assert read_json(paths.generation_dir / "01" / "result.json") == ["bad"]


def _ready_run(tmp_path, decision=None):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    write_json(
        paths.review_dir / "review_decision.json",
        {"action": "generate_rank_1", "fidelity_confirmed": True} if decision is None else _with_fidelity(decision),
    )
    _write_confirmed_constraints(paths)
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, ref)],
    )
    return paths, product, ref


def _with_fidelity(decision):
    if decision["action"] in {"generate_rank_1", "generate_selected", "generate_multiple"}:
        return {"fidelity_confirmed": True} | decision
    return decision


def _write_confirmed_constraints(paths):
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        {
            "schema_version": 1,
            "source": {
                "product_image": "input/product-on-hand.jpg",
                "product_analysis": "analysis/product_analysis.json",
            },
            "detected_keywords": [],
            "must_keep": [],
            "must_not_change": ["珠子排列顺序"],
            "needs_user_review": False,
            "detail_crop_recommended": False,
            "review_status": "not_applicable",
        },
    )


def _write_qc(generation_dir, status):
    generation_dir.mkdir(parents=True)
    write_json(
        generation_dir / "qc.json",
        {
            "status": status,
            "passed": [],
            "failed": ["product fidelity"],
            "notes": "",
            "fidelity_checks": [],
        },
    )


def _selected_reference(rank, path):
    return {
        "rank": rank,
        "selected_reference": str(path),
        "score": 100,
        "reason": [],
        "risk": [],
        "ignored_reference_jewelry": [],
        "metadata": {},
    }
