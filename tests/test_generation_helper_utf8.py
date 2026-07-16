import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import jewelry_on_hand.generation as generation


def test_helper_commands_force_python_utf8_mode():
    helper_path = Path("helper.py")

    submit_command = generation._submit_command(
        helper_path,
        "prompt",
        Path("reference.jpg"),
        Path("product.jpg"),
        "task-1",
        "gpt_image_2",
    )
    wait_command = generation._wait_command(helper_path, "task-1")

    expected_prefix = [sys.executable, "-X", "utf8", str(helper_path)]
    assert submit_command[:4] == expected_prefix
    assert wait_command[:4] == expected_prefix


def test_run_helper_decodes_utf8_bytes_without_platform_default_encoding(
    tmp_path,
    monkeypatch,
):
    payload = {"ok": True, "data": {"message": "任务已完成"}}
    subprocess_kwargs = {}

    def fake_run(command, **kwargs):
        subprocess_kwargs.update(kwargs)
        return SimpleNamespace(
            stdout=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            stderr=b"",
            returncode=0,
        )

    monkeypatch.setattr(generation.subprocess, "run", fake_run)

    result = generation._run_helper(
        ["python", "helper.py", "wait"],
        stage="wait",
        rank=1,
        generation_dir=tmp_path,
        output_path=tmp_path / "result.json",
    )

    assert result == payload
    assert subprocess_kwargs == {
        "capture_output": True,
        "text": False,
        "check": False,
    }


def test_run_helper_safely_reports_invalid_utf8_in_diagnostics(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return SimpleNamespace(
            stdout=b"not-json-\xff",
            stderr="帮助程序错误".encode("utf-8") + b"\xfe",
            returncode=1,
        )

    monkeypatch.setattr(generation.subprocess, "run", fake_run)

    with pytest.raises(generation.GenerationError) as exc_info:
        generation._run_helper(
            ["python", "helper.py", "wait"],
            stage="wait",
            rank=1,
            generation_dir=tmp_path,
            output_path=tmp_path / "result.json",
        )

    message = str(exc_info.value)
    assert "AIReiter helper stdout 不是有效 UTF-8" in message
    assert "stdout=not-json-�" in message
    assert "stderr=帮助程序错误�" in message


def test_run_helper_rejects_invalid_utf8_inside_valid_json_without_writing_output(
    tmp_path,
    monkeypatch,
):
    output_path = tmp_path / "result.json"

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            stdout=b'{"ok":true,"data":{"out_task_id":"task-\xff"}}',
            stderr="帮助程序错误".encode("utf-8"),
            returncode=0,
        )

    monkeypatch.setattr(generation.subprocess, "run", fake_run)

    with pytest.raises(
        generation.GenerationError,
        match="AIReiter helper stdout 不是有效 UTF-8",
    ) as exc_info:
        generation._run_helper(
            ["python", "helper.py", "wait"],
            stage="wait",
            rank=1,
            generation_dir=tmp_path,
            output_path=output_path,
        )

    assert "stdout=" in str(exc_info.value)
    assert "task-�" in str(exc_info.value)
    assert not output_path.exists()
