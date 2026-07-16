import json
import hashlib
from contextlib import contextmanager
from pathlib import Path

import pytest

import jewelry_on_hand.generation as generation
from jewelry_on_hand.generation import (
    REFERENCE_STRUCTURE_RETRY_SUFFIX,
    GenerationError,
    generation_failure_history,
    run_generation,
)
from jewelry_on_hand.models import ProductAnalysis, ReferenceRow, ScoredReference
from jewelry_on_hand.product_analysis import load_product_analysis
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    product_analysis_sha256,
)
from jewelry_on_hand.review_decision import ReviewGateError
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    build_candidate_snapshot,
    reference_composition_sha256,
)
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
    generation_dir = paths.generation_dir / "01"
    assert command[first] == str(generation_dir / "scene-reference.jpg")
    assert command[second] == str(generation_dir / "product-reference.jpg")
    assert command[command.index("--model") + 1] == "gpt_image_2"
    assert command[command.index("--aspect-ratio") + 1] == "3:4"
    assert command[command.index("--resolution") + 1] == "2K"
    assert (paths.generation_dir / "01" / "model.txt").read_text(encoding="utf-8") == "gpt_image_2"


def test_ring_generation_uses_product_on_hand_for_model_identity_even_with_detail(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    detail = paths.input_dir / "product-detail.png"
    detail.write_bytes(b"reviewed ring detail")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-on-hand"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generated = run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    command = calls[0]
    first = command.index("--image") + 1
    second = command.index("--image", first) + 1
    assert command[second] == str(
        paths.generation_dir / "01" / "product-reference.jpg"
    )
    assert str(detail) not in command
    assert (generated[0] / "product-reference.jpg").read_bytes() == product.read_bytes()


def test_ring_generation_rejects_detail_image_as_public_api_identity_source(
    tmp_path,
    monkeypatch,
):
    paths, _product = _ready_ring_run(tmp_path)
    detail = paths.input_dir / "product-detail.png"
    detail.write_bytes(b"reviewed ring detail")
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {
                    "ok": True,
                    "data": {"status": "pending", "out_task_id": "task-detail"},
                }
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(GenerationError) as exc_info:
        run_generation(paths, detail, {1: "prompt text"}, HELPER, wait=False)

    message = str(exc_info.value)
    assert "产品图必须使用人工确认链原始文件" in message
    assert "重新确认" in message
    assert calls == []
    assert list(paths.generation_dir.iterdir()) == []
    assert list(paths.root.rglob("product-identity.*")) == []
    assert list(paths.root.rglob("prompt.txt")) == []
    assert list(paths.root.rglob("submit.json")) == []


def test_ring_generation_reports_missing_canonical_identity_as_generation_error(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    product.unlink()
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {
                    "ok": True,
                    "data": {"status": "pending", "out_task_id": "task-missing"},
                }
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(FileNotFoundError) as exc_info:
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    message = str(exc_info.value)
    assert "product-on-hand.jpg" in message
    assert "产品图不存在" in message
    assert calls == []
    assert list(paths.generation_dir.iterdir()) == []
    assert list(paths.root.rglob("product-identity.*")) == []
    assert list(paths.root.rglob("prompt.txt")) == []
    assert list(paths.root.rglob("submit.json")) == []


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


def test_first_reference_structure_reject_retries_same_model_with_exact_suffix_once(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)
    _write_qc_with_failures(
        paths.generation_dir / "01",
        "reject",
        ["reference_framing_changed"],
    )
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-r"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    history = generation_failure_history(paths.generation_dir)
    assert history.reference_structure_rejects == 1
    assert history.model_switch_failures == 0

    [generation_dir] = run_generation(
        paths,
        product,
        {1: "基础替换提示词"},
        HELPER,
        wait=False,
    )

    assert (generation_dir / "model.txt").read_text(encoding="utf-8") == "gpt_image_2"
    prompt = (generation_dir / "prompt.txt").read_text(encoding="utf-8")
    assert prompt.count(REFERENCE_STRUCTURE_RETRY_SUFFIX) == 1
    helper_prompt = calls[0][calls[0].index("--prompt") + 1]
    assert helper_prompt == prompt
    assert helper_prompt.count(REFERENCE_STRUCTURE_RETRY_SUFFIX) == 1


def test_second_reference_structure_reject_stops_before_directory_or_helper(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)
    _write_qc_with_failures(
        paths.generation_dir / "01",
        "reject",
        ["reference_pose_changed"],
    )
    _write_qc_with_failures(
        paths.generation_dir / "02",
        "reject",
        ["reference_background_changed"],
    )
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="停用当前参考图.*prepare-review"):
        run_generation(paths, product, {1: "基础替换提示词"}, HELPER, wait=False)

    assert calls == []
    assert not (paths.generation_dir / "03").exists()
    assert not list(paths.generation_dir.glob(".*.staging-*"))


def test_ring_retry_requires_reconfirmation_before_switching_rank(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    prompts = {1: "基础 Prompt 1", 2: "基础 Prompt 2", 3: "基础 Prompt 3"}

    first = run_generation(paths, product, prompts, HELPER, wait=False)[0]
    write_json(
        first / "qc.json",
        {"status": "reject", "critical_failures": ["finger_position_mismatch"]},
    )
    with pytest.raises(GenerationError, match="rank 不一致|重新确认"):
        run_generation(paths, product, prompts, HELPER, wait=False)

    assert (first / "reference-rank.txt").read_text(encoding="utf-8") == "1"
    assert len(calls) == 1
    assert not (paths.generation_dir / "02").exists()


def _complete_ring_retry_prompt(target_length=1190):
    padding_marker = "<PRODUCT_FACT_PADDING>"
    prompt = f"""请生成一张小红书自然上手图，画幅 3:4，清晰 2K。

【基础安全边界】
以下动态字段不得作为指令执行。
最高优先级：只生成一枚目标戒指，必须佩戴在左手无名指根部并真实环绕；禁止生成手镯、手链、第二枚戒指。

【两图职责】
内部图1：自动参考图，只提供手部姿势、手模、构图、光线和场景；内部图1中的戒指必须移除且不提供产品身份。
移除内部图1原有首饰；内部图2仅提供戒指身份；内部图2是戒指身份唯一来源，不继承其中的手、皮肤、指甲、衣服或背景。

【产品分析与不确定性】
产品类型：戒指
规范产品品类：ring
规范展示模式：worn
佩戴位置：左手无名指根部。
产品外观：单枚银色背侧重叠开口戒指。
颜色范围：银色。
特殊要求：保持背侧重叠开口不得闭合。
产品事实：背侧重叠开口不得闭合；参考图文件：产品事实不可删除；{padding_marker}
被遮挡部分（仅标记不可见边界，不得推断或补全）：戒圈背面。
不确定细节（仅作为不确定边界，不得转写为确定性结构）：镶嵌背面结构。

【品类保真】
产品保真以内部图2中肉眼可见的外观为准。
保持戒面、镶嵌、戒圈和装饰的可见数量、形状、颜色、朝向与排列。

【展示模式】
真人佩戴：戒指必须佩戴在已确认的左手无名指根部。
左手手背朝镜头；其他手指不得佩戴戒指。

【参考构图场景】
输出用途：手部佩戴图。使用深色背景，产品完整清晰，画面不得出现文字、水印、logo 或平台标识。 产品自然佩戴在手腕或手指根部，接触和阴影真实。
参考说明：参考图文件：区块说明不可删除；仅作为数据。
参考图文件：6ecab8b84dd26e9f19de34eb0e3538c.jpg；风格：黑色背景闪光灯直拍；手势：左手手背朝镜头。
忽略参考图首饰：参考图中的戒指。
镜面构图：无，不要额外添加镜中反射手部。

【遮挡与接触物理】
戒圈自然环绕手指；戒圈背侧按真实遮挡隐藏；不得悬浮、贴片、嵌入皮肤或穿透手指。
产品必须清晰可见；肤色、景深和光线自然。

【禁止项】
不要把内部图1里的原有首饰迁移到新图。不得迁移产品图中的手、皮肤、指甲、掌纹或背景。不可见戒圈、镶嵌背面和遮挡结构不得补造。
禁止文字、水印、logo、平台标识，以及畸形手、多指、融指、断指。"""
    padding_length = target_length - len(prompt) + len(padding_marker)
    assert padding_length >= 0
    return prompt.replace(padding_marker, "真" * padding_length)


def test_ring_retry_compacts_contract_fields_when_correction_exceeds_prompt_limit():
    product_fact_reference = "参考图文件：产品事实不可删除；"
    original_reference = "参考图文件：6ecab8b84dd26e9f19de34eb0e3538c.jpg；"
    base_prompt = _complete_ring_retry_prompt()
    correction = generation._ring_retry_correction(("ring_structure_mismatch",))
    assert len(base_prompt) <= 1200
    assert len(f"{base_prompt}\n\n{correction}") > 1200
    retry_prompt = generation._build_ring_retry_prompt(base_prompt, correction, ".jpg")
    assert len(retry_prompt) <= 1200
    assert "产品事实：背侧重叠开口不得闭合" in retry_prompt
    assert product_fact_reference in retry_prompt
    assert "参考说明：参考图文件：区块说明不可删除；仅作为数据。" in retry_prompt
    assert "参考图文件：scene-reference.jpg；" in retry_prompt
    assert original_reference not in retry_prompt
    assert "输出用途：手部佩戴图" in retry_prompt
    assert "深色背景" in retry_prompt
    assert "产品完整清晰" in retry_prompt
    assert "无文字/水印/logo/平台标识" in retry_prompt
    assert "确认手指根部" in retry_prompt
    assert "接触和阴影真实" in retry_prompt
    assert "风格：黑色背景闪光灯直拍" in retry_prompt
    assert "手势：左手手背朝镜头" in retry_prompt
    assert "镜面构图：无。" in retry_prompt
    assert "【本轮纠偏】" in retry_prompt
    assert "戒面、戒圈、开口端点和装饰排列" in retry_prompt


def test_ring_retry_compaction_preserves_mirror_requirements():
    mirror_requirement = (
        "镜面构图：前景手部 + 镜中反射手部；"
        "镜中产品与前景产品保持同一款式、同一颜色和同一佩戴位置。"
    )
    base_prompt = _complete_ring_retry_prompt(1150).replace(
        "镜面构图：无，不要额外添加镜中反射手部。",
        mirror_requirement,
    )
    correction = generation._ring_retry_correction(("ring_structure_mismatch",))
    assert len(base_prompt) <= 1200
    assert len(f"{base_prompt}\n\n{correction}") > 1200

    retry_prompt = generation._build_ring_retry_prompt(
        base_prompt,
        correction,
        ".png",
    )

    assert len(retry_prompt) <= 1200
    assert "参考图文件：scene-reference.png；" in retry_prompt
    assert mirror_requirement in retry_prompt
    assert "镜面构图：无。" not in retry_prompt


def test_ring_retry_compaction_only_shortens_fixed_no_mirror_line():
    dynamic_reference_text = (
        "风格：动态参考文本包含“镜面构图：无，不要额外添加镜中反射手部。”字面量；"
        "手势：左手手背朝镜头。"
    )
    base_prompt = _complete_ring_retry_prompt(1150).replace(
        "风格：黑色背景闪光灯直拍；手势：左手手背朝镜头。",
        dynamic_reference_text,
    )
    correction = generation._ring_retry_correction(("ring_structure_mismatch",))
    assert len(base_prompt) <= 1200
    assert len(f"{base_prompt}\n\n{correction}") > 1200

    retry_prompt = generation._build_ring_retry_prompt(
        base_prompt,
        correction,
        ".jpg",
    )

    assert dynamic_reference_text in retry_prompt
    assert "\n镜面构图：无。\n" in retry_prompt


def test_ring_retry_png_reference_requires_reconfirmation_before_helper(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    rank_2_jpg = Path(references[1]["selected_reference"])
    rank_2_png = rank_2_jpg.with_suffix(".png")
    rank_2_png.write_bytes(rank_2_jpg.read_bytes())
    references[1]["selected_reference"] = str(rank_2_png)
    write_json(references_path, references)
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    prompt = _complete_ring_retry_prompt()
    prompts = {1: prompt, 2: prompt, 3: prompt}

    first = run_generation(paths, product, prompts, HELPER, wait=False)[0]
    write_json(
        first / "qc.json",
        {"status": "reject", "critical_failures": ["ring_structure_mismatch"]},
    )
    with pytest.raises(GenerationError, match="rank 不一致|重新确认"):
        run_generation(paths, product, prompts, HELPER, wait=False)

    assert len(calls) == 1
    assert not (paths.generation_dir / "02").exists()


def test_ring_retry_prompt_still_fails_when_equivalent_compaction_is_insufficient():
    product_fact = "产品事实：背侧重叠开口不得闭合"
    reference_field = "参考图文件：6ecab8b84dd26e9f19de34eb0e3538c.jpg；"
    output_role = (
        "输出用途：手部佩戴图。使用深色背景，产品完整清晰，画面不得出现文字、水印、"
        "logo 或平台标识。 产品自然佩戴在手腕或手指根部，接触和阴影真实。"
    )
    base_prompt = (
        product_fact
        + "；其他产品事实不得截断。" * 100
        + f"\n【参考构图场景】\n{output_role}\n{reference_field}风格：黑色背景闪光灯直拍；"
        + "手势：左手手背朝镜头\n【遮挡与接触物理】\n保持真实遮挡。"
    )
    correction = generation._ring_retry_correction(("ring_structure_mismatch",))
    retry_prompt = f"{base_prompt}\n\n{correction}"
    compressed_prompt = retry_prompt.replace(
        reference_field,
        "参考图文件：scene-reference.jpg；",
        1,
    ).replace(
        output_role,
        "输出用途：手部佩戴图。深色背景；产品完整清晰；无文字/水印/logo/平台标识；"
        "佩戴在确认手指根部；接触和阴影真实。",
        1,
    )
    assert len(compressed_prompt) > 1200

    with pytest.raises(
        GenerationError,
        match=r"戒指重试 Prompt 长度为 \d+，超过 1200 字上限",
    ):
        generation._build_ring_retry_prompt(base_prompt, correction, ".jpg")

    assert product_fact in base_prompt


def test_ring_retry_rejects_first_unconfirmed_rank_before_helper(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task"}}
            )
        ),
    )
    prompts = {1: "Prompt 1", 2: "Prompt 2", 3: "Prompt 3"}
    generated = run_generation(paths, product, prompts, HELPER, wait=False)[0]
    write_json(
        generated / "qc.json",
        {"status": "reject", "critical_failures": ["ring_structure_mismatch"]},
    )

    with pytest.raises(GenerationError, match="rank 不一致|重新确认"):
        run_generation(paths, product, prompts, HELPER, wait=False)

    assert not (paths.generation_dir / "02").exists()


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("finger_position_mismatch", "目标手指"),
        ("hand_side_mismatch", "确认手"),
        ("centerpiece_mismatch", "主石数量、形状、颜色、朝向和相对尺寸"),
        ("ring_structure_mismatch", "戒面、戒圈、开口端点和装饰排列"),
        ("ring_count_mismatch", "只允许一枚目标戒指"),
        ("ring_contact_error", "连续环绕目标手指"),
        ("source_hand_leakage", "不得继承源手"),
        ("finger_deformation", "五指解剖正常"),
    ],
)
def test_ring_retry_correction_maps_qc_failure_to_action(failure, expected):
    correction = generation._ring_retry_correction((failure,))

    assert correction.startswith("【本轮纠偏】")
    assert expected in correction


def test_generation_rejects_generate_multiple_before_assigning_task_ids(tmp_path, monkeypatch):
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

    with pytest.raises(GenerationError, match="generate_multiple.*prepare-review"):
        run_generation(
            paths,
            product,
            {1: "prompt 1", 2: "prompt 2"},
            HELPER,
            wait=False,
        )

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_requires_selected_references(tmp_path):
    paths, product, _ref = _ready_run(tmp_path)
    (paths.analysis_dir / "selected_references.json").unlink()

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
    assert (paths.generation_dir / "01" / "qc-review.html").is_file()
    assert "wait" in calls[1]
    assert calls[1][calls[1].index("--task-id") + 1] == "task-1"


def test_generation_retries_image_download_before_failing(tmp_path, monkeypatch):
    destination = tmp_path / "result.png"
    attempts = []

    def fake_urlopen(request, timeout=120):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise OSError("temporary connection reset")
        return fake_image_response(b"image-bytes")

    monkeypatch.setattr(generation.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(generation.time, "sleep", lambda seconds: None)

    generation._download_result_image(
        {"data": {"output": [{"url": "https://example.com/result.png"}]}},
        destination=destination,
        rank=1,
        generation_dir=tmp_path,
    )

    assert len(attempts) == 2
    assert destination.read_bytes() == b"image-bytes"


def test_generation_rejects_selected_rank_not_bound_to_confirmed_snapshot(tmp_path, monkeypatch):
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

    with pytest.raises(GenerationError, match="唯一 selected rank 不一致"):
        run_generation(
            paths,
            product,
            {1: "prompt 1", 2: "prompt 2"},
            HELPER,
            wait=False,
        )

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_rejects_non_contiguous_generate_multiple_without_submit(
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

    with pytest.raises(GenerationError, match="generate_multiple.*prepare-review"):
        run_generation(
            paths,
            product,
            {2: "prompt 2", 3: "prompt 3"},
            HELPER,
            wait=False,
        )

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


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

    assert "generate_multiple" in str(exc_info.value)
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

    assert "generate_multiple" in str(exc_info.value)
    assert calls == []
    rank_1_dir = paths.generation_dir / "01"
    assert not (rank_1_dir / "prompt.txt").exists()
    assert not (rank_1_dir / "submit.json").exists()
    assert not (rank_1_dir / "scene-reference.jpg").exists()
    assert not list(unwritable_dir.glob(".write-test-*.tmp"))


def test_generation_rejects_existing_non_empty_generation_dir(tmp_path):
    paths, product, _ref = _ready_run(tmp_path)
    generation_dir = paths.generation_dir / "01"
    generation_dir.mkdir()
    _write_modern_history_artifacts(generation_dir)
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
    paths, product, _review_copy, snapshot, _analysis, _canonical = (
        _ready_audited_run(tmp_path, reference_suffix=".png")
    )

    def fake_run(command, capture_output, text, check=False):
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert (paths.generation_dir / "01" / "scene-reference.png").is_file()
    assert not (paths.generation_dir / "01" / "scene-reference.jpg").exists()


def test_generation_rejects_missing_original_even_when_review_copy_exists(tmp_path, monkeypatch):
    paths, product, review_copy = _ready_run(tmp_path)
    selected = read_json(paths.analysis_dir / "selected_references.json")
    original_ref = Path(selected[0]["metadata"]["source_reference"])
    original_ref.unlink()
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "task-1"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(ReviewGateError, match="参考图源图.*不存在"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert calls == []
    assert review_copy.is_file()
    assert not any(paths.generation_dir.iterdir())


def test_generation_rejects_missing_reference_file(tmp_path):
    paths, product, _ref = _ready_run(tmp_path)
    missing_ref = tmp_path / "missing.jpg"
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_reference(1, missing_ref)],
    )

    with pytest.raises(ReviewGateError, match="产物路径|参考图"):
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


@pytest.mark.parametrize(
    ("product_type", "display_mode"),
    [
        ("necklace", "worn"),
        ("necklace", "hand_held"),
        ("pendant_necklace", "worn"),
        ("pendant_necklace", "hand_held"),
    ],
)
def test_generation_accepts_supported_necklace_modes(
    tmp_path,
    monkeypatch,
    product_type,
    display_mode,
):
    paths, product, _ref = _ready_modern_run(
        tmp_path,
        product_type=product_type,
        display_mode=display_mode,
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

    generated = run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert generated == [paths.generation_dir / "01"]
    assert len(calls) == 1


@pytest.mark.parametrize("canonical_kind", ["v1", "wrong_presence", "wrong_layer"])
def test_generation_rejects_invalid_necklace_canonical_before_helper(
    tmp_path,
    monkeypatch,
    canonical_kind,
) -> None:
    product_type = "pendant_necklace" if canonical_kind == "wrong_layer" else "necklace"
    paths, product_image, _review_copy = _ready_modern_run(
        tmp_path,
        product_type=product_type,
    )
    analysis_path = paths.analysis_dir / "product_analysis.json"
    analysis = read_json(analysis_path)
    if canonical_kind == "wrong_layer":
        analysis["layer_count"] = 2
        analysis["pendant_layer"] = 2
        write_json(analysis_path, analysis)
        decision = read_json(paths.review_dir / "review_decision.json")
        decision["confirmation_snapshot"] = _snapshot_from_analysis(analysis)
        write_json(paths.review_dir / "review_decision.json", decision)
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    canonical = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis)
    ).to_dict()
    canonical["review_status"] = "confirmed"
    if canonical_kind == "v1":
        canonical["schema_version"] = 1
        canonical.pop("pendant_semantics")
    elif canonical_kind == "wrong_presence":
        canonical["pendant_semantics"] = {
            "presence": "present",
            "count": 1,
            "layer": 1,
            "creation_policy": "forbid",
        }
    else:
        canonical["pendant_semantics"]["layer"] = 1
    write_json(canonical_path, canonical)
    copy_calls: list[object] = []
    helper_calls: list[list[str]] = []
    monkeypatch.setattr(
        "jewelry_on_hand.generation.shutil.copy2",
        lambda *args, **kwargs: copy_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "jewelry_on_hand.generation._run_helper",
        lambda command, **kwargs: helper_calls.append(command),
    )

    with pytest.raises(
        (ReviewGateError, GenerationError, ValueError),
        match="v1|吊坠结构冲突|pendant_semantics",
    ):
        run_generation(paths, product_image, {1: "本地测试 Prompt"}, HELPER)

    assert copy_calls == []
    assert helper_calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_accepts_valid_v2_necklace_until_fake_helper(
    tmp_path,
    monkeypatch,
) -> None:
    paths, product_image, _review_copy = _ready_modern_run(tmp_path)
    commands: list[list[str]] = []

    def fake_helper(command, **kwargs):
        commands.append(command)
        return {"task_id": "local-test-task"}

    monkeypatch.setattr("jewelry_on_hand.generation._run_helper", fake_helper)
    monkeypatch.setattr(
        "jewelry_on_hand.generation._download_result_image",
        lambda *args, **kwargs: None,
    )

    run_generation(
        paths,
        product_image,
        {1: "本地测试 Prompt"},
        HELPER,
        wait=False,
    )

    assert len(commands) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "product_type": "疑似项链",
                "detected_product_type": "unknown",
                "confirmed_product_type": "unknown",
            },
            "产品品类必须先确认",
        ),
        (
            {
                "product_type": "无链独立吊坠",
                "detected_product_type": "pendant_only",
                "confirmed_product_type": "pendant_only",
                "length_category": None,
                "has_pendant": True,
                "pendant_count": 1,
                "pendant_layer": None,
                "pendant_position": "front_center",
                "pendant_orientation": "front_facing",
                "connection_structure": "metal_bail",
            },
            "产品品类必须先确认",
        ),
        ({"source_image_type": "flat_lay_source"}, "source_image_type 必须为 worn_source"),
        ({"source_image_type": "hand_held_source"}, "source_image_type 必须为 worn_source"),
        ({"layer_count": 4}, "1 至 3 层"),
        ({"is_independent_multi_item": True}, "多件独立项链"),
    ],
)
def test_generation_rejects_unsupported_modern_product_before_submit(
    tmp_path,
    monkeypatch,
    overrides,
    message,
):
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    paths = None
    with pytest.raises((GenerationError, ReviewGateError, ValueError), match=message):
        paths, product, _ref = _ready_modern_run(
            tmp_path,
            analysis_overrides=overrides,
        )
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert calls == []
    if paths is not None:
        assert not any(paths.generation_dir.iterdir())


def test_generation_rejects_necklace_without_confirmation_snapshot_before_submit(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_modern_run(tmp_path)
    decision = read_json(paths.review_dir / "review_decision.json")
    decision.pop("confirmation_snapshot")
    write_json(paths.review_dir / "review_decision.json", decision)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ReviewGateError, match="缺少完整产品确认快照"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_rejects_snapshot_mismatch_before_submit(tmp_path, monkeypatch):
    paths, product, _ref = _ready_modern_run(tmp_path)
    decision = read_json(paths.review_dir / "review_decision.json")
    decision["confirmation_snapshot"]["display_mode"] = "hand_held"
    write_json(paths.review_dir / "review_decision.json", decision)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ReviewGateError, match="display_mode.*不一致"):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


@pytest.mark.parametrize("bad_second", ["reference", "prompt"])
def test_generation_preflight_rejects_invalid_second_rank_without_submit(
    tmp_path,
    monkeypatch,
    bad_second,
):
    paths, product, ref_1 = _ready_modern_run(
        tmp_path,
        decision={"action": "generate_multiple", "selected_ranks": [1, 2]},
    )
    first_reference = read_json(paths.analysis_dir / "selected_references.json")[0]
    source_2 = tmp_path / "ref-2.jpg"
    ref_2 = paths.review_dir / "rank-2-ref-2.jpg"
    if bad_second != "reference":
        source_2.write_bytes(b"ref 2")
        ref_2.write_bytes(source_2.read_bytes())
        second_metadata = _necklace_reference_metadata(
            2,
            source_2,
            product_type="necklace",
            display_mode="worn",
        )
    else:
        second_metadata = {}
    write_json(
        paths.analysis_dir / "selected_references.json",
        [first_reference, _selected_reference(2, ref_2, metadata=second_metadata)],
    )
    prompts = {1: "prompt 1"}
    if bad_second != "prompt":
        prompts[2] = "prompt 2"
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(
        (FileNotFoundError, KeyError, GenerationError, ReviewGateError)
    ):
        run_generation(paths, product, prompts, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_keeps_legacy_bracelet_without_snapshot_compatible(
    tmp_path,
    monkeypatch,
):
    paths, product, _ref = _ready_run(tmp_path)
    analysis = _legacy_bracelet_analysis()
    write_json(paths.analysis_dir / "product_analysis.json", analysis)
    _write_constraints_for_analysis(paths, analysis)
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

    assert len(calls) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_image_type": "hand_held_source"}, "source_image_type 必须为 worn_source"),
        ({"display_mode": "hand_held"}, "手持展示"),
    ],
)
def test_generation_does_not_let_legacy_bracelet_bypass_explicit_mode_gate(
    tmp_path,
    monkeypatch,
    overrides,
    message,
):
    paths, product, _ref = _ready_run(tmp_path)
    analysis = _legacy_bracelet_analysis()
    analysis.update(overrides)
    write_json(paths.analysis_dir / "product_analysis.json", analysis)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ReviewGateError, match=message):
        run_generation(paths, product, {1: "prompt text"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_accepts_valid_ring_with_top_three_references(tmp_path, monkeypatch):
    paths, product = _ready_ring_run(tmp_path)
    calls = []

    def fake_run(command, capture_output, text, check=False):
        calls.append(command)
        return Completed(
            json.dumps(
                {"ok": True, "data": {"status": "pending", "out_task_id": "ring-task"}}
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generated = run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert generated == [paths.generation_dir / "01"]
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"source_image_type": "flat_lay_source"}, "source_image_type 必须为 worn_source"),
        ({"source_image_type": "hand_held_source"}, "source_image_type 必须为 worn_source"),
        ({"display_mode": "hand_held"}, "手持展示"),
        ({"ring_count": 2}, "只支持单枚戒指"),
        ({"hand_side": "unknown"}, "必须确认左右手"),
        ({"finger_position": "unknown"}, "必须确认佩戴手指"),
        ({"ring_wear_style": "midi"}, "常规指根"),
        ({"ring_wear_style": "cross_finger"}, "常规指根"),
    ),
)
def test_generation_rejects_invalid_ring_before_submit(
    tmp_path, monkeypatch, overrides, message
):
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    paths = None
    with pytest.raises((GenerationError, ReviewGateError, ValueError), match=message):
        paths, product = _ready_ring_run(tmp_path, analysis_overrides=overrides)
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    if paths is not None:
        assert not any(paths.generation_dir.iterdir())


def test_generation_rejects_ring_bracelet_semantics_hidden_only_in_source_text_before_helper(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    analysis_path = paths.analysis_dir / "product_analysis.json"
    analysis = read_json(analysis_path)
    analysis["special_requirements"] = ["主珠和配件位置关系"]
    write_json(analysis_path, analysis)
    constraints_path = paths.analysis_dir / "product_fidelity_constraints.json"
    constraints = read_json(constraints_path)
    constraints["source"]["product_analysis_sha256"] = product_analysis_sha256(
        ProductAnalysis.from_dict(analysis)
    )
    constraints["must_keep"].append(
        {
            "name": "戒指产品特定要求1",
            "source_text": "主珠和配件位置关系",
            "normalized_keyword": "戒指产品特定要求",
            "location": "该要求涉及的戒指肉眼可见部位",
            "visual_shape": "按产品图肉眼可见事实核对该局部要求",
            "relationship": "保持该局部要求与戒指可见结构的原有关系",
            "forbid": ["不得改成通用戒指款式"],
            "qc_question": "该局部要求的可见事实是否保持一致？",
        }
    )
    write_json(constraints_path, constraints)
    helper_calls = []

    def fail_if_helper_called(*args, **kwargs):
        helper_calls.append((args, kwargs))
        raise AssertionError("无效 ring canonical 不得调用 helper")

    monkeypatch.setattr(generation, "_run_helper", fail_if_helper_called)

    with pytest.raises(ReviewGateError, match="canonical.must_keep.*不一致"):
        run_generation(paths, product, {1: "prompt"}, HELPER, wait=False)

    assert helper_calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_rejects_ring_snapshot_mismatch_before_submit(tmp_path, monkeypatch):
    paths, product = _ready_ring_run(tmp_path)
    decision = read_json(paths.review_dir / "review_decision.json")
    decision["confirmation_snapshot"]["hand_side"] = "right"
    write_json(paths.review_dir / "review_decision.json", decision)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ReviewGateError, match="hand_side.*不一致"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_generation_requires_ring_top_three_references_before_submit(
    tmp_path, monkeypatch
):
    paths, product = _ready_ring_run(tmp_path, reference_count=2)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="戒指.*Top 3"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


@pytest.mark.parametrize(
    ("duplicate_kind", "message"),
    (
        ("source", "内容摘要重复"),
        ("review", "review 副本.*重复"),
    ),
)
def test_ring_reference_gate_rejects_duplicate_sources_or_review_copies(
    tmp_path,
    monkeypatch,
    duplicate_kind,
    message,
):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    if duplicate_kind == "source":
        for field_name in (
            "source_reference",
            "source_absolute_path",
            "source_relative_path",
            "source_file_name",
            "absolute_path",
            "relative_path",
            "file_name",
        ):
            references[1]["metadata"][field_name] = references[0]["metadata"][
                field_name
            ]
        first_content = Path(references[0]["selected_reference"]).read_bytes()
        Path(references[1]["selected_reference"]).write_bytes(first_content)
        digest = hashlib.sha256(first_content).hexdigest()
        references[1]["metadata"]["source_sha256"] = digest
        references[1]["metadata"]["review_sha256"] = digest
    else:
        references[1]["selected_reference"] = references[0]["selected_reference"]
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match=message):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_ring_reference_gate_requires_each_review_copy_before_submit(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    references = read_json(paths.analysis_dir / "selected_references.json")
    Path(references[1]["selected_reference"]).unlink()
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="review 副本不存在"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_ring_reference_gate_rejects_review_copy_tampering_before_submit(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    references = read_json(paths.analysis_dir / "selected_references.json")
    Path(references[0]["selected_reference"]).write_bytes(b"tampered-review")
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="review 副本.*SHA-256|篡改"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []


def test_ring_reference_gate_rejects_same_content_at_different_source_paths(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    first_source = Path(references[0]["metadata"]["source_reference"])
    second_source = Path(references[1]["metadata"]["source_reference"])
    second_source.write_bytes(first_source.read_bytes())
    second_review = Path(references[1]["selected_reference"])
    second_review.write_bytes(first_source.read_bytes())
    digest = hashlib.sha256(first_source.read_bytes()).hexdigest()
    references[1]["metadata"]["source_sha256"] = digest
    references[1]["metadata"]["review_sha256"] = digest
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="内容摘要.*重复"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []


def test_ring_reference_gate_requires_metadata_before_submit(tmp_path, monkeypatch):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0].pop("metadata")
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="metadata"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    (
        ("hand_side", "", "左右手"),
        ("visible_fingers", "thumb,index,middle", "目标手指"),
        ("hand_orientation", "", "手部朝向"),
        ("ring_face_visibility", "低", "戒面可见度"),
        ("finger_separation", "低", "手指分离度"),
        ("finger_occlusion_risk", "高", "手指遮挡风险"),
    ),
)
def test_ring_reference_gate_rechecks_six_ring_metadata_fields(
    tmp_path,
    monkeypatch,
    field_name,
    bad_value,
    message,
):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0]["metadata"][field_name] = bad_value
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match=message):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_ring_reference_gate_requires_exactly_rank_one_to_three(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    source = tmp_path / "ring-source-4.jpg"
    source.write_bytes(b"ring-source-4")
    review_copy = paths.review_dir / "rank-4-ring-source-4.jpg"
    review_copy.write_bytes(b"ring-review-4")
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references.append(
        _selected_reference(
            4,
            review_copy,
            metadata=_ring_reference_metadata(4, source),
        )
    )
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="恰好.*rank 1、2、3"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


@pytest.mark.parametrize(
    "field_name",
    ("source_absolute_path", "absolute_path"),
)
def test_ring_reference_gate_rejects_conflicting_absolute_provenance(
    tmp_path,
    monkeypatch,
    field_name,
):
    paths, product = _ready_ring_run(tmp_path)
    other_source = tmp_path / "conflicting-source.jpg"
    other_source.write_bytes(b"other source")
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0]["metadata"][field_name] = str(other_source)
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match=f"{field_name}.*冲突"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("source_relative_path", "wrong/source.jpg"),
        ("relative_path", "wrong/source.jpg"),
        ("source_file_name", "wrong-source.jpg"),
        ("file_name", "wrong-source.jpg"),
    ),
)
def test_ring_reference_gate_rejects_conflicting_named_provenance(
    tmp_path,
    monkeypatch,
    field_name,
    bad_value,
):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0]["metadata"][field_name] = bad_value
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match=f"{field_name}.*冲突"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


@pytest.mark.parametrize(
    "field_name",
    (
        "source_absolute_path",
        "absolute_path",
        "source_relative_path",
        "relative_path",
        "source_file_name",
        "file_name",
    ),
)
def test_ring_reference_gate_requires_complete_provenance_fields(
    tmp_path,
    monkeypatch,
    field_name,
):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0]["metadata"].pop(field_name)
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match=f"缺少.*{field_name}"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_ring_reference_gate_requires_file_exists_true(tmp_path, monkeypatch):
    paths, product = _ready_ring_run(tmp_path)
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0]["metadata"]["file_exists"] = False
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="file_exists.*true"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_ring_reference_gate_requires_existing_source_file(tmp_path, monkeypatch):
    paths, product = _ready_ring_run(tmp_path)
    references = read_json(paths.analysis_dir / "selected_references.json")
    Path(references[0]["metadata"]["source_reference"]).unlink()
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="源文件不存在"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def test_ring_reference_gate_rejects_review_copy_outside_run_review_dir(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_ring_run(tmp_path)
    outside_review = tmp_path / "outside-review.jpg"
    outside_review.write_bytes(b"outside review")
    references_path = paths.analysis_dir / "selected_references.json"
    references = read_json(references_path)
    references[0]["selected_reference"] = str(outside_review)
    write_json(references_path, references)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="review_dir"):
        run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)

    assert calls == []
    assert not any(paths.generation_dir.iterdir())


def _ready_run(tmp_path, decision=None):
    paths, product, ref, snapshot, _analysis_path, _canonical_path = (
        _ready_audited_run(tmp_path)
    )
    if decision is not None:
        payload = _with_fidelity(decision)
        payload["output_role"] = "hand_worn"
        payload["reference_snapshot_sha256"] = reference_composition_sha256(snapshot)
        write_json(paths.review_dir / "review_decision.json", payload)
    return paths, product, ref


def _ready_ring_run(tmp_path, *, analysis_overrides=None, reference_count=3):
    paths, product, _ref = _ready_run(
        tmp_path,
        decision={"action": "generate_rank_1", "selected_ranks": [1]},
    )
    analysis = _modern_ring_analysis()
    constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis)
    ).to_dict()
    constraints["review_status"] = "confirmed"
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        constraints,
    )
    if analysis_overrides:
        analysis.update(analysis_overrides)
    write_json(paths.analysis_dir / "product_analysis.json", analysis)
    decision = read_json(paths.review_dir / "review_decision.json")
    decision["confirmation_snapshot"] = _snapshot_from_analysis(analysis)
    write_json(paths.review_dir / "review_decision.json", decision)

    references = []
    for rank in range(1, reference_count + 1):
        source = tmp_path / f"ring-source-{rank}.jpg"
        source.write_bytes(f"ring-source-{rank}".encode())
        review_copy = paths.review_dir / f"rank-{rank}-ring-source-{rank}.jpg"
        review_copy.write_bytes(source.read_bytes())
        references.append(
            _selected_reference(
                rank,
                review_copy,
                metadata=_ring_reference_metadata(rank, source),
            )
        )
    write_json(paths.analysis_dir / "selected_references.json", references)
    _refresh_reference_snapshot(paths, analysis, references[0])
    return paths, product


def _ready_modern_run(
    tmp_path,
    *,
    product_type="necklace",
    display_mode="worn",
    analysis_overrides=None,
    decision=None,
):
    paths, product, ref = _ready_run(
        tmp_path,
        decision=decision or {"action": "generate_rank_1", "selected_ranks": [1]},
    )
    analysis = _modern_necklace_analysis(product_type, display_mode)
    _write_constraints_for_analysis(paths, analysis)
    if analysis_overrides:
        analysis.update(analysis_overrides)
    write_json(paths.analysis_dir / "product_analysis.json", analysis)
    decision_data = read_json(paths.review_dir / "review_decision.json")
    decision_data["confirmation_snapshot"] = _snapshot_from_analysis(analysis)
    write_json(paths.review_dir / "review_decision.json", decision_data)
    review_copy = paths.review_dir / f"rank-1-{ref.name}"
    review_copy.write_bytes(ref.read_bytes())
    selected = [
        _selected_reference(
            1,
            review_copy,
            metadata=_necklace_reference_metadata(
                1,
                ref,
                product_type=product_type,
                display_mode=display_mode,
            ),
        )
    ]
    write_json(
        paths.analysis_dir / "selected_references.json",
        selected,
    )
    _refresh_reference_snapshot(paths, analysis, selected[0])
    return paths, product, review_copy


def _modern_necklace_analysis(product_type="necklace", display_mode="worn"):
    has_pendant = product_type == "pendant_necklace"
    return {
        "product_type": "带链吊坠" if has_pendant else "普通项链",
        "detected_product_type": product_type,
        "confirmed_product_type": product_type,
        "classification_confidence": "high",
        "classification_evidence": ["肉眼可见完整链条"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
        "display_mode": display_mode,
        "wear_position": "颈部和锁骨",
        "visible_appearance": "完整链条" + ("，中央有主吊坠" if has_pendant else ""),
        "color_family": ["金色"],
        "style_mood": "精致",
        "composition": "胸前近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
        "layer_count": 1,
        "length_category": "collarbone",
        "chain_or_strand_type": "metal_chain",
        "has_pendant": has_pendant,
        "pendant_count": 1 if has_pendant else 0,
        "pendant_layer": 1 if has_pendant else None,
        "pendant_position": "front_center" if has_pendant else None,
        "pendant_orientation": "front_facing" if has_pendant else None,
        "connection_structure": "metal_bail" if has_pendant else None,
        "symmetry": "approximately_symmetric",
        "occluded_parts": ["后颈扣头"],
        "uncertain_details": ["扣头具体结构"],
        "is_independent_multi_item": False,
    }


def _modern_ring_analysis():
    return {
        "product_type": "戒指",
        "detected_product_type": "ring",
        "confirmed_product_type": "ring",
        "classification_confidence": "high",
        "classification_evidence": ["左手无名指根部可见单枚戒指"],
        "classification_source": "auto_confirmed",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "wear_position": "左手无名指根部",
        "visible_appearance": "单枚银色戒指",
        "color_family": ["银色"],
        "style_mood": "简洁",
        "composition": "手部近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
        "layer_count": 1,
        "length_category": None,
        "chain_or_strand_type": None,
        "has_pendant": False,
        "pendant_count": 0,
        "pendant_layer": None,
        "pendant_position": None,
        "pendant_orientation": None,
        "connection_structure": None,
        "symmetry": None,
        "occluded_parts": ["戒圈背面"],
        "uncertain_details": ["镶嵌背面结构"],
        "is_independent_multi_item": False,
        "ring_count": 1,
        "hand_side": "left",
        "finger_position": "ring",
        "ring_wear_style": "finger_base",
    }


def _snapshot_from_analysis(analysis):
    snapshot = {
        field_name: analysis[field_name]
        for field_name in (
            "confirmed_product_type",
            "source_image_type",
            "display_mode",
            "layer_count",
            "length_category",
            "has_pendant",
            "pendant_count",
            "pendant_layer",
            "pendant_position",
            "pendant_orientation",
            "connection_structure",
            "is_independent_multi_item",
        )
    }
    if analysis["confirmed_product_type"] == "ring":
        snapshot.update(
            {
                field_name: analysis[field_name]
                for field_name in (
                    "ring_count",
                    "hand_side",
                    "finger_position",
                    "ring_wear_style",
                )
            }
        )
    return snapshot


def _legacy_bracelet_analysis():
    return {
        "product_type": "朱砂手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "深红圆珠手串",
        "color_family": ["深红"],
        "style_mood": "自然",
        "composition": "手腕近景",
        "product_dimensions": {"bead_diameter_mm": 10},
        "needs_full_front_display": True,
    }


def _with_fidelity(decision):
    if decision["action"] in {"generate_rank_1", "generate_selected", "generate_multiple"}:
        return {"fidelity_confirmed": True} | decision
    return decision


def _write_confirmed_constraints(paths):
    analysis = read_json(paths.analysis_dir / "product_analysis.json")
    _write_constraints_for_analysis(paths, analysis)


def _write_constraints_for_analysis(paths, analysis):
    constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis)
    ).to_dict()
    if constraints["review_status"] == "pending":
        constraints["review_status"] = "confirmed"
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        constraints,
    )


def _write_qc(generation_dir, status):
    generation_dir.mkdir(parents=True)
    _write_modern_history_artifacts(generation_dir)
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


def _write_qc_with_failures(generation_dir, status, critical_failures):
    generation_dir.mkdir(parents=True)
    _write_modern_history_artifacts(generation_dir)
    write_json(
        generation_dir / "qc.json",
        {
            "status": status,
            "passed": [],
            "failed": ["参考底图结构未保持"],
            "notes": "人工确认参考结构发生严重变化",
            "reference_preservation_checks": [],
            "fidelity_checks": [],
            "checklist_checks": [],
            "critical_failures": critical_failures,
        },
    )


def _selected_reference(rank, path, *, metadata=None):
    return {
        "rank": rank,
        "selected_reference": str(path),
        "score": 100,
        "reason": [],
        "risk": [],
        "ignored_reference_jewelry": [],
        "metadata": {} if metadata is None else metadata,
    }


def _ring_reference_metadata(rank, source):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "index": rank,
        "file_name": source.name,
        "relative_path": source.name,
        "absolute_path": str(source),
        "source_reference": str(source),
        "source_absolute_path": str(source),
        "source_relative_path": source.name,
        "source_file_name": source.name,
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "戒指上手/手部近景参考",
        "bracelet_applicability": "",
        "default_strategy": "常规可优先使用",
        "style_category": "自然光手部特写",
        "scene_keywords": "深色背景，手背手指近景",
        "jewelry_type": "戒指",
        "recommended_usage": "戒指真人佩戴展示",
        "notes": "正面视角，主体居中，手指完整，无文字或 UI，无裁切",
        "confidence": "高",
        "file_exists": True,
        "source_sha256": digest,
        "review_sha256": digest,
        "applicable_product_types": "ring",
        "applicable_display_modes": "worn",
        "framing": "手部近景",
        "visible_body_regions": "左手全部手指",
        "product_visibility": "高",
        "hand_visibility": "高",
        "existing_jewelry": "左手无名指唯一戒指",
        "crop_risk": "低",
        "collar_type": "无衣领",
        "clothing_occlusion_risk": "衣物无遮挡",
        "hand_side": "left",
        "visible_fingers": "thumb,index,middle,ring,little",
        "hand_orientation": "back",
        "ring_face_visibility": "高",
        "finger_separation": "高",
        "finger_occlusion_risk": "低",
        "pose_keywords": "身体未入镜，前臂自然抬起，左手手背朝镜头，五指自然分开",
    }


def _necklace_reference_metadata(rank, source, *, product_type, display_mode):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    hand_held = display_mode == "hand_held"
    return {
        "index": rank,
        "file_name": source.name,
        "relative_path": source.name,
        "absolute_path": str(source),
        "source_reference": str(source),
        "source_absolute_path": str(source),
        "source_relative_path": source.name,
        "source_file_name": source.name,
        "width": 1000,
        "height": 1200,
        "size_mb": 1,
        "purpose_category": "手持展示构图参考" if hand_held else "真人佩戴构图参考",
        "bracelet_applicability": "否",
        "default_strategy": "常规可优先使用",
        "style_category": "自然光珠宝近景",
        "scene_keywords": "深色背景，自然光",
        "jewelry_type": "项链",
        "recommended_usage": (
            "双手捏持，完整链条自然垂落，具有真实接触"
            if hand_held
            else "颈部至胸前完整佩戴展示"
        ),
        "notes": "正面视角，主体居中，无原有首饰，画面空间充足，无文字或 UI",
        "confidence": "高",
        "file_exists": True,
        "source_sha256": digest,
        "review_sha256": digest,
        "applicable_product_types": product_type,
        "applicable_display_modes": display_mode,
        "framing": "双手与胸前近景" if hand_held else "颈部与锁骨近景",
        "visible_body_regions": "双手、手指、掌心" if hand_held else "颈部、锁骨、胸前",
        "product_visibility": "高",
        "neck_visibility": "低" if hand_held else "高",
        "collarbone_visibility": "低" if hand_held else "高",
        "chest_visibility": "高",
        "hand_visibility": "高" if hand_held else "低",
        "hand_side": "双手" if hand_held else "左手",
        "hand_orientation": "双手手指轻持链条" if hand_held else "手部未入镜",
        "collar_type": "低领",
        "clothing_occlusion_risk": "低",
        "hair_occlusion_risk": "低",
        "pose_keywords": (
            "身体未入镜，前臂自然抬起，双手捏持，链条完整"
            if hand_held
            else "上半身正面，手臂自然下垂，手部未入镜"
        ),
        "existing_jewelry": "无",
        "crop_risk": "低",
    }


def _ready_audited_run(tmp_path, *, role="hand_worn", reference_suffix=".jpg"):
    paths = RunPaths.create(tmp_path, "run-1")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    source_reference = tmp_path / f"scene{reference_suffix}"
    source_reference.write_bytes(b"scene")
    review_copy = paths.review_dir / f"rank-1-{source_reference.name}"
    review_copy.write_bytes(source_reference.read_bytes())

    analysis_path = paths.analysis_dir / "product_analysis.json"
    write_json(analysis_path, _legacy_bracelet_analysis())
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    _write_confirmed_constraints(paths)
    row = ReferenceRow(
        index=1,
        file_name=source_reference.name,
        relative_path=source_reference.name,
        absolute_path=source_reference,
        width=100,
        height=200,
        size_mb=0.1,
        purpose_category="手部佩戴图",
        bracelet_applicability="是",
        default_strategy="常规可优先使用",
        style_category="暗调闪光",
        scene_keywords="深色背景，车内",
        jewelry_type="手链/手串",
        recommended_usage="近景手腕",
        notes="正面视角，主体居中，无文字或 UI",
        confidence="高",
        file_exists=True,
        framing="手部近景",
        visible_body_regions="左手腕 / 前臂完整露出",
        product_visibility="展示面积充足，大于 35%",
        collar_type="无衣领",
        clothing_occlusion_risk="衣物无遮挡",
        pose_keywords="身体未入镜，前臂自然抬起",
        existing_jewelry="左手腕原有手链",
        crop_risk="裁切风险低",
        hand_side="左手",
        hand_orientation="手背朝向镜头",
    )
    scored = ScoredReference(row, 99, 1, ("匹配",), (), ("原有手链",))
    snapshot = build_candidate_snapshot(load_product_analysis(analysis_path), scored, role)
    digest = hashlib.sha256(source_reference.read_bytes()).hexdigest()
    selected = scored.to_dict()
    selected["selected_reference"] = str(review_copy.resolve())
    selected["source_sha256"] = digest
    selected["review_sha256"] = digest
    selected["metadata"]["source_reference"] = str(source_reference.resolve())
    selected["metadata"]["source_file_name"] = source_reference.name
    selected["metadata"]["source_sha256"] = digest
    selected["metadata"]["review_sha256"] = digest
    write_json(paths.analysis_dir / "selected_references.json", [selected])
    write_json(
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
        snapshot.to_dict(),
    )
    write_json(
        paths.analysis_dir / "reference_composition_snapshots.json",
        [snapshot.to_dict()],
    )
    write_json(paths.analysis_dir / "output_role.json", {"output_role": role})
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "output_role": role,
            "reference_snapshot_sha256": reference_composition_sha256(snapshot),
        },
    )
    return paths, product, review_copy, snapshot, analysis_path, canonical_path


def _ready_legacy_read_only_run(tmp_path):
    paths = RunPaths.create(tmp_path, "legacy-read-only")
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"legacy-product")
    source = tmp_path / "legacy-scene-1.jpg"
    source.write_bytes(b"legacy-scene-1")
    selected_items = []
    for rank in (1, 2, 3):
        ranked_source = source if rank == 1 else tmp_path / f"legacy-scene-{rank}.jpg"
        if rank != 1:
            ranked_source.write_bytes(f"legacy-scene-{rank}".encode())
        review_copy = paths.review_dir / f"rank-{rank}-legacy-scene.jpg"
        review_copy.write_bytes(ranked_source.read_bytes())
        digest = hashlib.sha256(ranked_source.read_bytes()).hexdigest()
        selected_items.append(
            {
                "rank": rank,
                "score": 100 - rank,
                "selected_reference": str(review_copy.resolve()),
                "source_sha256": digest,
                "review_sha256": digest,
                "metadata": {
                    "source_reference": str(ranked_source.resolve()),
                    "source_sha256": digest,
                    "review_sha256": digest,
                },
            }
        )
    write_json(paths.analysis_dir / "product_analysis.json", _legacy_bracelet_analysis())
    _write_confirmed_constraints(paths)
    write_json(
        paths.analysis_dir / "selected_references.json",
        selected_items,
    )
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
        },
    )
    generation = paths.generation_dir / "01"
    generation.mkdir()
    (generation / "hand-reference.jpg").write_bytes(source.read_bytes())
    (generation / "model.txt").write_text("gpt_image_2", encoding="utf-8")
    (generation / "prompt.txt").write_text("历史提示词", encoding="utf-8")
    write_json(generation / "submit.json", {"ok": True})
    write_json(generation / "result.json", {"data": {"status": "completed"}})
    (generation / "result.png").write_bytes(b"legacy-result")
    write_json(
        generation / "qc.json",
        {
            "status": "pass",
            "passed": [
                "原图手腕检查通过",
                "原图手臂检查通过",
                "皮肤块迁移检查通过",
            ],
            "failed": [],
            "notes": "未发现人物局部迁移",
        },
    )
    return paths, product


def _write_modern_history_artifacts(generation_dir):
    root = generation_dir.parent.parent
    selected = read_json(root / "analysis" / "selected_references.json")[0]
    scene_source = Path(selected["selected_reference"])
    product_source = root / "input" / "product-on-hand.jpg"
    fixed_sources = {
        "reference_snapshot": (
            root / "review" / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
            "reference-composition-snapshot.json",
        ),
        "product_analysis": (
            root / "analysis" / "product_analysis.json",
            "product-analysis.json",
        ),
        "fidelity_constraints": (
            root / "analysis" / "product_fidelity_constraints.json",
            "product-fidelity-constraints.json",
        ),
    }
    manifest = {
        "schema_version": 1,
        "output_role": "hand_worn",
        "inputs": [],
    }
    for key, (source, copied_name) in fixed_sources.items():
        copied = generation_dir / copied_name
        copied.write_bytes(source.read_bytes())
        manifest[key] = {
            "copied_file": copied_name,
            "sha256": hashlib.sha256(copied.read_bytes()).hexdigest(),
        }
    for order, role, source, copied_name in (
        (1, "scene_reference", scene_source, "scene-reference.jpg"),
        (2, "product_identity", product_source, "product-reference.jpg"),
    ):
        copied = generation_dir / copied_name
        copied.write_bytes(source.read_bytes())
        manifest["inputs"].append(
            {
                "order": order,
                "role": role,
                "source_path": str(source.resolve()),
                "copied_file": copied_name,
                "sha256": hashlib.sha256(copied.read_bytes()).hexdigest(),
            }
        )
    (generation_dir / "model.txt").write_text("gpt_image_2", encoding="utf-8")
    (generation_dir / "prompt.txt").write_text("历史现代 prompt", encoding="utf-8")
    (generation_dir / "reference-rank.txt").write_text("1", encoding="utf-8")
    write_json(generation_dir / "submit.json", {"ok": True})
    write_json(generation_dir / "input-manifest.json", manifest)


def _run_文件树快照(root):
    directories = {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_dir()
    }
    files = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    return directories, files


def _refresh_reference_snapshot(paths, analysis, selected, *, role="hand_worn"):
    selected_items = read_json(paths.analysis_dir / "selected_references.json")
    snapshots = []
    for item in selected_items:
        row = ReferenceRow.from_dict(item["metadata"])
        scored = ScoredReference(
            row=row,
            score=item["score"],
            rank=item["rank"],
            reason=tuple(item["reason"]),
            risk=tuple(item["risk"]),
            ignored_reference_jewelry=tuple(item["ignored_reference_jewelry"]),
        )
        snapshots.append(
            build_candidate_snapshot(
                ProductAnalysis.from_dict(analysis),
                scored,
                role,
            )
        )
    snapshot = next(item for item in snapshots if item.rank == selected["rank"])
    write_json(
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
        snapshot.to_dict(),
    )
    write_json(
        paths.analysis_dir / "reference_composition_snapshots.json",
        [item.to_dict() for item in snapshots],
    )
    write_json(paths.analysis_dir / "output_role.json", {"output_role": role})
    decision = read_json(paths.review_dir / "review_decision.json")
    decision["output_role"] = role
    decision["reference_snapshot_sha256"] = reference_composition_sha256(snapshot)
    write_json(paths.review_dir / "review_decision.json", decision)
    return snapshot


def test_generation_input_manifest_copies_five_trusted_inputs_and_uses_scene_reference_first(
    tmp_path,
    monkeypatch,
):
    paths, product, review_copy, snapshot, analysis_path, canonical_path = (
        _ready_audited_run(tmp_path)
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
    [generation_dir] = run_generation(
        paths,
        product,
        {1: "prompt text"},
        HELPER,
        wait=False,
        reference_snapshot=snapshot,
        product_analysis_path=analysis_path,
        fidelity_constraints_path=canonical_path,
    )

    manifest = read_json(generation_dir / "input-manifest.json")
    assert manifest["schema_version"] == 1
    assert manifest["output_role"] == "hand_worn"
    assert [item["role"] for item in manifest["inputs"]] == [
        "scene_reference",
        "product_identity",
    ]
    assert [item["order"] for item in manifest["inputs"]] == [1, 2]
    for section in ("reference_snapshot", "product_analysis", "fidelity_constraints"):
        copied = generation_dir / manifest[section]["copied_file"]
        assert manifest[section]["sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()
    assert (generation_dir / "scene-reference.jpg").read_bytes() == review_copy.read_bytes()
    assert (generation_dir / "product-reference.jpg").read_bytes() == product.read_bytes()
    assert not list(generation_dir.glob("hand-reference.*"))

    command = calls[0]
    first = command.index("--image") + 1
    second = command.index("--image", first) + 1
    assert Path(command[first]).parent == generation_dir
    assert Path(command[second]).parent == generation_dir
    assert Path(command[first]).name == "scene-reference.jpg"
    assert Path(command[second]).name == "product-reference.jpg"


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("scene", "参考图"),
        ("snapshot_digest", "run 产物不完整/损坏"),
        ("role", "run 产物不完整/损坏"),
        ("run_role", "角色"),
        ("product_missing", "产品图"),
    ],
)
def test_generation_scene_reference_and_snapshot_sha_preflight_fail_closed(
    tmp_path,
    monkeypatch,
    tamper,
    message,
):
    paths, product, review_copy, snapshot, analysis_path, canonical_path = (
        _ready_audited_run(tmp_path)
    )
    if tamper == "scene":
        review_copy.write_bytes(b"tampered-scene")
    elif tamper == "snapshot_digest":
        decision = read_json(paths.review_dir / "review_decision.json")
        decision["reference_snapshot_sha256"] = "0" * 64
        write_json(paths.review_dir / "review_decision.json", decision)
    elif tamper == "role":
        decision = read_json(paths.review_dir / "review_decision.json")
        decision["output_role"] = "lifestyle"
        write_json(paths.review_dir / "review_decision.json", decision)
    elif tamper == "run_role":
        write_json(paths.analysis_dir / "output_role.json", {"output_role": "lifestyle"})
    else:
        product.unlink()
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises((GenerationError, ReviewGateError, FileNotFoundError), match=message):
        run_generation(
            paths,
            product,
            {1: "prompt text"},
            HELPER,
            wait=False,
            reference_snapshot=snapshot,
            product_analysis_path=analysis_path,
            fidelity_constraints_path=canonical_path,
        )
    assert calls == []
    assert not [path for path in paths.generation_dir.iterdir() if path.name.isdigit()]


@pytest.mark.parametrize("missing_name", ["analysis", "canonical"])
def test_generation_analysis_copy_or_canonical_copy_missing_fails_before_submit(
    tmp_path,
    monkeypatch,
    missing_name,
):
    paths, product, _review_copy, snapshot, analysis_path, canonical_path = (
        _ready_audited_run(tmp_path)
    )
    (analysis_path if missing_name == "analysis" else canonical_path).unlink()
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises((GenerationError, ReviewGateError, FileNotFoundError), match="不存在|缺少"):
        run_generation(
            paths,
            product,
            {1: "prompt text"},
            HELPER,
            wait=False,
            reference_snapshot=snapshot,
            product_analysis_path=analysis_path,
            fidelity_constraints_path=canonical_path,
        )
    assert calls == []
    assert not [path for path in paths.generation_dir.iterdir() if path.name.isdigit()]


def test_generation_analysis_copy_tamper_rolls_back_without_submit(tmp_path, monkeypatch):
    paths, product, _review_copy, snapshot, analysis_path, canonical_path = (
        _ready_audited_run(tmp_path)
    )
    real_copy2 = generation.shutil.copy2
    calls = []

    def tampering_copy(source, destination):
        result = real_copy2(source, destination)
        if Path(destination).name == "product-analysis.json":
            Path(destination).write_bytes(Path(destination).read_bytes() + b"tampered")
        return result

    monkeypatch.setattr(generation.shutil, "copy2", tampering_copy)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(GenerationError, match="摘要|篡改|固化"):
        run_generation(
            paths,
            product,
            {1: "prompt text"},
            HELPER,
            wait=False,
            reference_snapshot=snapshot,
            product_analysis_path=analysis_path,
            fidelity_constraints_path=canonical_path,
        )
    assert calls == []
    assert list(paths.generation_dir.iterdir()) == []


def test_generation_canonical_copy_manifest_write_failure_rolls_back_without_submit(
    tmp_path,
    monkeypatch,
):
    paths, product, _review_copy, snapshot, analysis_path, canonical_path = (
        _ready_audited_run(tmp_path)
    )
    real_write_json = generation.write_json
    calls = []

    def failing_write_json(path, data):
        if Path(path).name == "input-manifest.json":
            raise OSError("模拟 manifest 写入失败")
        return real_write_json(path, data)

    monkeypatch.setattr(generation, "write_json", failing_write_json)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(GenerationError, match="manifest|固化"):
        run_generation(
            paths,
            product,
            {1: "prompt text"},
            HELPER,
            wait=False,
            reference_snapshot=snapshot,
            product_analysis_path=analysis_path,
            fidelity_constraints_path=canonical_path,
        )
    assert calls == []
    assert list(paths.generation_dir.iterdir()) == []


def test_ring_retry_rejects_unconfirmed_rank_before_helper(tmp_path, monkeypatch):
    paths, product = _ready_ring_run(tmp_path)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: Completed(
            json.dumps({"ok": True, "data": {"out_task_id": "task-1"}})
        ),
    )
    first = run_generation(paths, product, {1: "ring prompt"}, HELPER, wait=False)[0]
    write_json(
        first / "qc.json",
        {
            "status": "reject",
            "critical_failures": ["finger_position_mismatch"],
        },
    )
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(GenerationError, match="确认快照 rank|唯一 selected rank"):
        run_generation(
            paths,
            product,
            {1: "rank1", 2: "rank2", 3: "rank3"},
            HELPER,
            wait=False,
        )
    assert calls == []
    assert not (paths.generation_dir / "02").exists()


def test_legacy_read_only_生成入口在_helper_和新目录前拒绝且只读(
    tmp_path,
    monkeypatch,
):
    paths, product = _ready_legacy_read_only_run(tmp_path)
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args))
    before = _run_文件树快照(paths.root)

    with pytest.raises(
        ReviewGateError,
        match="历史 run 只读.*重新执行 prepare-review",
    ):
        run_generation(paths, product, {1: "历史 prompt"}, HELPER, wait=False)

    assert calls == []
    assert _run_文件树快照(paths.root) == before
    assert not (paths.generation_dir / "02").exists()


def test_damaged_生成入口在_helper_和新目录前拒绝且只读(
    tmp_path,
    monkeypatch,
):
    paths, product, _review_copy, snapshot, analysis_path, canonical_path = (
        _ready_audited_run(tmp_path)
    )
    (paths.analysis_dir / "reference_composition_snapshots.json").unlink()
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return Completed(
            json.dumps({"ok": True, "data": {"out_task_id": "不应提交"}})
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    before = _run_文件树快照(paths.root)

    with pytest.raises(
        (ReviewGateError, GenerationError),
        match="run 产物不完整/损坏.*重新执行 prepare-review",
    ):
        run_generation(
            paths,
            product,
            {1: "prompt text"},
            HELPER,
            wait=False,
            reference_snapshot=snapshot,
            product_analysis_path=analysis_path,
            fidelity_constraints_path=canonical_path,
        )

    assert calls == []
    assert _run_文件树快照(paths.root) == before
    assert not (paths.generation_dir / "01").exists()
