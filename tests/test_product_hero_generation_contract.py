import copy
import hashlib
import io
import json
import struct
import subprocess
import sys
from pathlib import Path
from urllib.request import Request

import pytest


SCRIPTS = (
    Path(__file__).parents[1]
    / "skills"
    / "jewelry-product-hero-workflow"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

from generation_contract import (  # noqa: E402
    CHECKLIST_CHECK_IDS,
    GenerationContractError,
    SUPPORTED_ASPECT_RATIOS,
    build_generation_contract,
    finalize_qc,
    freeze_fidelity_constraints,
    nearest_aspect_ratio,
    prepare_generation_attempt,
    read_image_size,
    record_generation_result,
    record_infrastructure_failure,
    validate_fidelity_constraints,
    validate_prompt_contract,
    validate_qc_record,
)
from product_hero_workflow import freeze_product_analysis, prepare_run  # noqa: E402
from reference_review import (  # noqa: E402
    ReferenceReviewError,
    collect_explicit_category_candidates,
    record_reference_decision,
    write_review_package,
)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_bytes(width=300, height=200):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(
        ">II", width, height
    ) + b"\x08\x02\x00\x00\x00" + b"payload"


def jpeg_bytes(width=300, height=200):
    return (
        b"\xff\xd8"
        + b"\xff\xe0\x00\x04JF"
        + b"\xff\xc0\x00\x11\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        + b"\xff\xd9"
    )


def webp_bytes(width=300, height=200):
    payload = b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (
        height - 1
    ).to_bytes(3, "little")
    return b"RIFF" + (len(payload) + 12).to_bytes(4, "little") + b"WEBPVP8X" + len(
        payload
    ).to_bytes(4, "little") + payload


def valid_analysis(product_id="PN-001", category="ring", component_counts=None):
    return {
        "schema_version": 1,
        "product_id": product_id,
        "category": category,
        "product_unit": "single",
        "physical_piece_count": 1,
        "silhouette": "圆形戒圈",
        "component_topology": ["主石", "戒托"],
        "component_counts": copy.deepcopy(component_counts or []),
        "colors": ["金色"],
        "materials": ["黄金"],
        "distinctive_features": ["圆形主石"],
        "uncertain_features": [],
        "evidence_by_view": ["front", "side"],
    }


def valid_constraints(product_id="PN-001", category="ring", component_counts=None):
    return {
        "schema_version": 1,
        "product_id": product_id,
        "category": category,
        "must_keep": [
            {
                "name": "圆形主石",
                "source_views": ["front", "detail_01"],
                "qc_question": "主石是否保持圆形？",
            }
        ],
        "must_not_change": ["戒托结构"],
        "uncertain_features": ["侧面刻字"],
        "component_counts": copy.deepcopy(component_counts or []),
    }


def user_selection(rank):
    return {
        "source": "user_message",
        "selected_rank": rank,
        "verbatim": f"选 {rank}",
    }


def assert_generation_error(call, *fragments):
    with pytest.raises(GenerationContractError) as caught:
        call()
    message = str(caught.value)
    assert any("\u4e00" <= char <= "\u9fff" for char in message)
    assert all(fragment in message for fragment in fragments)


def test_fidelity_constraints_validate_schema_copy_and_unique_names():
    data = valid_constraints()
    normalized = validate_fidelity_constraints(data, valid_analysis())
    assert normalized == data
    assert normalized is not data
    assert normalized["must_keep"] is not data["must_keep"]

    duplicate = valid_constraints()
    duplicate["must_keep"].append(copy.deepcopy(duplicate["must_keep"][0]))
    assert_generation_error(
        lambda: validate_fidelity_constraints(duplicate, valid_analysis()), "重复"
    )


def test_fidelity_constraints_must_mirror_product_component_counts():
    counts = [
        {
            "name": "圆珠",
            "physical_count": 13,
            "source_views": ["front", "side"],
        }
    ]
    analysis = valid_analysis("QY048", "beaded_bracelet", counts)
    constraints = valid_constraints("QY048", "beaded_bracelet", counts)

    assert validate_fidelity_constraints(constraints, analysis)["component_counts"] == counts

    constraints["component_counts"][0]["physical_count"] = 17
    assert_generation_error(
        lambda: validate_fidelity_constraints(constraints, analysis), "数量", "一致"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version=2),
        lambda data: data.update(product_id="PN-X"),
        lambda data: data.update(category="necklace"),
        lambda data: data.update(must_keep=[]),
        lambda data: data["must_keep"][0].update(source_views=[]),
        lambda data: data["must_keep"][0].update(qc_question=" "),
        lambda data: data.update(must_not_change="戒托"),
        lambda data: data.update(uncertain_features=[1]),
        lambda data: data.pop("component_counts"),
    ],
)
def test_fidelity_constraints_reject_invalid_contract(mutation):
    data = valid_constraints()
    mutation(data)
    assert_generation_error(lambda: validate_fidelity_constraints(data, valid_analysis()))


def test_freeze_constraints_writes_hash_without_advancing_state(tmp_path):
    run = tmp_path / "run"
    write_json(run / "state.json", {"schema_version": 1, "state": "ready_to_generate"})
    manifest_path = run / "input/input_manifest.json"
    write_json(
        manifest_path,
        {"schema_version": 1, "product_id": "PN-001", "images": []},
    )
    analysis_path = run / "analysis/product_analysis.json"
    write_json(analysis_path, valid_analysis())
    (run / "analysis/product_analysis.sha256").write_text(sha(analysis_path) + "\n")

    result = freeze_fidelity_constraints(run, valid_constraints())

    path = run / "analysis/fidelity_constraints.json"
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert result == valid_constraints()
    assert state["state"] == "ready_to_generate"
    assert state["input_manifest_sha256"] == sha(manifest_path)
    assert state["product_analysis_sha256"] == sha(analysis_path)
    assert state["fidelity_constraints_sha256"] == sha(path)
    assert (run / "analysis/fidelity_constraints.sha256").read_text().strip() == sha(path)
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    assert_generation_error(lambda: freeze_fidelity_constraints(run, valid_constraints()))
    assert before == {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("image.png", png_bytes(300, 200)),
        ("image.jpg", jpeg_bytes(300, 200)),
        ("image.webp", webp_bytes(300, 200)),
    ],
)
def test_standard_library_image_size_supports_png_jpeg_webp(tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    assert read_image_size(path) == (300, 200)


def test_image_size_rejects_corrupt_and_unsupported_with_chinese_error(tmp_path):
    corrupt = tmp_path / "bad.png"
    corrupt.write_bytes(b"not-an-image")
    unsupported = tmp_path / "image.gif"
    unsupported.write_bytes(b"GIF89a")
    assert_generation_error(lambda: read_image_size(corrupt))
    assert_generation_error(lambda: read_image_size(unsupported), "不支持")


def test_nearest_aspect_ratio_uses_log_error_and_stable_constant_order():
    assert SUPPORTED_ASPECT_RATIOS == (
        "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "21:9"
    )
    assert nearest_aspect_ratio(1500, 1000) == "3:2"
    assert nearest_aspect_ratio(1000, 1500) == "2:3"
    assert nearest_aspect_ratio(1, 1) == "1:1"
    assert_generation_error(lambda: nearest_aspect_ratio(0, 10))


def ready_generation_run(tmp_path, *, pair=False, component_counts=None):
    run = tmp_path / "run"
    product_id = "PN-EAR-001" if pair else "PN-001"
    category = "earrings" if pair else ("beaded_bracelet" if component_counts else "ring")
    analysis = valid_analysis(product_id, category, component_counts)
    if pair:
        analysis.update(product_unit="matched_earring_pair", physical_piece_count=2)
    constraints = valid_constraints(product_id, category, component_counts)
    image_specs = [
        ("front", "input/front.png", png_bytes(600, 600)),
        ("side", "input/side.jpg", jpeg_bytes(400, 600)),
        ("detail_01", "input/details/01.webp", webp_bytes(500, 400)),
        ("detail_02", "input/details/02.png", png_bytes(500, 400)),
    ]
    images = []
    for role, relative, content in image_specs:
        path = run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        images.append(
            {
                "role": role,
                "path": relative,
                "sha256": sha(path),
                "size_bytes": len(content),
            }
        )
    manifest_path = run / "input/input_manifest.json"
    write_json(
        manifest_path,
        {"schema_version": 1, "product_id": product_id, "images": images},
    )
    analysis_path = run / "analysis/product_analysis.json"
    write_json(analysis_path, analysis)
    (run / "analysis/product_analysis.sha256").write_text(sha(analysis_path) + "\n")
    constraints_path = run / "analysis/fidelity_constraints.json"
    write_json(constraints_path, constraints)
    (run / "analysis/fidelity_constraints.sha256").write_text(
        sha(constraints_path) + "\n"
    )
    reference_paths = {}
    for rank in (1, 2, 3):
        reference_path = run / f"review/candidates/rank-{rank}-RP00{rank}.webp"
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_bytes(webp_bytes(1600 + rank, 900))
        reference_paths[rank] = reference_path
    top3 = {
        "schema_version": 1,
        "product_id": product_id,
        "category": category,
        "product_unit": analysis["product_unit"],
        "items": [
            {
                "rank": rank,
                "record_id": f"rec-{rank}",
                "material_id": f"RP00{rank}",
                "selected_reference": f"review/candidates/rank-{rank}-RP00{rank}.webp",
                "image_sha256": sha(reference_paths[rank]),
                "score": 90 - rank,
                "reasons": ["构图匹配"],
                "risks": [],
            }
            for rank in (1, 2, 3)
        ],
    }
    top3_path = run / "review/top3.json"
    write_json(top3_path, top3)
    decision = {
        "schema_version": 1,
        "selected_rank": 1,
        "record_id": "rec-1",
        "material_id": "RP001",
        "selected_reference": "review/candidates/rank-1-RP001.webp",
        "image_sha256": sha(reference_paths[1]),
        "top3_sha256": sha(top3_path),
        "product_analysis_sha256": sha(analysis_path),
        "user_selection_evidence": user_selection(1),
    }
    decision_path = run / "review/decision.json"
    write_json(decision_path, decision)
    write_json(
        run / "state.json",
        {
            "schema_version": 1,
            "state": "ready_to_generate",
            "generation_attempts": 0,
            "non_pass_attempts": 0,
            "submission_attempts": 0,
            "input_manifest_sha256": sha(manifest_path),
            "product_analysis_sha256": sha(analysis_path),
            "fidelity_constraints_sha256": sha(constraints_path),
            "top3_sha256": sha(top3_path),
            "decision_sha256": sha(decision_path),
        },
    )
    return run


PROMPT_FRAGMENTS = (
    "【任务目标】",
    "【图片职责】",
    "【产品保真】",
    "【场景保持】",
    "【禁止项】",
    "图1仅负责场景",
    "图2正面图具有最高优先级",
    "图3只补充侧面厚度、弧度和连接关系",
    "只补充局部材质",
    "多视图冲突时立即停止",
    "不可见结构不得补造",
    "产品源图的白色或中性背景不得迁移",
    "移除参考图原商品、文字、水印和 logo",
    "构图、机位、道具、背景、光线和视觉高度保持一致",
    "只出现一个商品单元",
)


def test_build_generation_contract_binds_hashes_order_aspect_and_prompt(tmp_path):
    run = ready_generation_run(tmp_path)

    contract = build_generation_contract(run)

    assert set(contract) == {"prompt", "aspect_ratio", "model", "input_order"}
    assert contract["aspect_ratio"] == "16:9"
    assert contract["model"] == "gpt_image_2"
    assert [item["role"] for item in contract["input_order"]] == [
        "reference",
        "front",
        "side",
        "detail_01",
        "detail_02",
    ]
    assert all(not Path(item["path"]).is_absolute() for item in contract["input_order"])
    assert all(sha(run / item["path"]) == item["sha256"] for item in contract["input_order"])
    assert all(fragment in contract["prompt"] for fragment in PROMPT_FRAGMENTS)
    assert validate_prompt_contract(contract["prompt"], contract["input_order"]) == []


def test_pair_prompt_requires_exactly_two_earrings(tmp_path):
    contract = build_generation_contract(ready_generation_run(tmp_path, pair=True))
    assert "成对耳饰必须恰好两只" in contract["prompt"]
    assert validate_prompt_contract(contract["prompt"], contract["input_order"]) == []


def test_prompt_freezes_exact_component_count_and_isolates_reference_occlusion(tmp_path):
    counts = [
        {
            "name": "圆珠",
            "physical_count": 13,
            "source_views": ["front", "side"],
        }
    ]
    contract = build_generation_contract(
        ready_generation_run(tmp_path, component_counts=counts)
    )

    required = (
        "圆珠实体总数固定为且仅为13颗",
        "参考图原商品的数量、珠数、珠距、排列和被遮挡部分均不得作为目标商品结构依据",
        "遮挡只改变可见数量，不改变实体总数",
        "不得为了填满参考图圆环",
        "优先保持实体数量",
    )
    assert all(fragment in contract["prompt"] for fragment in required)
    assert validate_prompt_contract(contract["prompt"], contract["input_order"]) == []


@pytest.mark.parametrize("detail_count", [1, 2, 3, 4])
def test_prompt_uses_actual_last_input_number_for_detail_roles(tmp_path, detail_count):
    run = ready_generation_run(tmp_path)
    manifest_path = run / "input/input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    details = manifest["images"][2:]
    if detail_count < len(details):
        for item in details[detail_count:]:
            (run / item["path"]).unlink()
        manifest["images"] = manifest["images"][: 2 + detail_count]
    else:
        for index in range(len(details) + 1, detail_count + 1):
            relative = f"input/details/{index:02d}.png"
            path = run / relative
            path.write_bytes(png_bytes(500, 400))
            manifest["images"].append(
                {
                    "role": f"detail_{index:02d}",
                    "path": relative,
                    "sha256": sha(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    write_json(manifest_path, manifest)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["input_manifest_sha256"] = sha(manifest_path)
    write_json(state_path, state)

    contract = build_generation_contract(run)
    last_number = 3 + detail_count
    detail_label = "图4" if detail_count == 1 else f"图4–{last_number}"
    assert f"图2–{last_number}中的目标珠宝" in contract["prompt"]
    assert f"{detail_label}只补充局部材质" in contract["prompt"]
    assert f"图{last_number + 1}" not in contract["prompt"]
    assert validate_prompt_contract(contract["prompt"], contract["input_order"]) == []


@pytest.mark.parametrize("bad_fragment", [PROMPT_FRAGMENTS[0], PROMPT_FRAGMENTS[7]])
def test_prompt_validator_reports_missing_required_content_in_chinese(tmp_path, bad_fragment):
    contract = build_generation_contract(ready_generation_run(tmp_path))
    errors = validate_prompt_contract(
        contract["prompt"].replace(bad_fragment, ""), contract["input_order"]
    )
    assert errors and all(any("\u4e00" <= char <= "\u9fff" for char in item) for item in errors)


@pytest.mark.parametrize("garble", ["???", "锟", "�"])
def test_prompt_validator_rejects_utf8_garble(tmp_path, garble):
    contract = build_generation_contract(ready_generation_run(tmp_path))
    assert validate_prompt_contract(contract["prompt"] + garble, contract["input_order"])


def test_prompt_validator_rejects_non_contiguous_or_reordered_roles(tmp_path):
    contract = build_generation_contract(ready_generation_run(tmp_path))
    reordered = copy.deepcopy(contract["input_order"])
    reordered[1], reordered[2] = reordered[2], reordered[1]
    assert validate_prompt_contract(contract["prompt"], reordered)
    missing = [item for item in contract["input_order"] if item["role"] != "detail_01"]
    assert validate_prompt_contract(contract["prompt"], missing)


@pytest.mark.parametrize(
    ("target", "mutate"),
    [
        ("input/front.png", lambda path: path.write_bytes(png_bytes(601, 600))),
        ("analysis/product_analysis.json", lambda path: path.write_text("{}", encoding="utf-8")),
        ("analysis/fidelity_constraints.json", lambda path: path.write_text("{}", encoding="utf-8")),
        ("review/top3.json", lambda path: path.write_text("{}", encoding="utf-8")),
        ("review/decision.json", lambda path: path.write_text("{}", encoding="utf-8")),
        ("review/candidates/rank-1-RP001.webp", lambda path: path.write_bytes(webp_bytes(900, 1600))),
    ],
)
def test_build_generation_contract_rejects_any_tampered_binding(tmp_path, target, mutate):
    run = ready_generation_run(tmp_path)
    mutate(run / target)
    assert_generation_error(lambda: build_generation_contract(run), "哈希")


def snapshot_files(run):
    return {
        path.relative_to(run).as_posix(): path.read_bytes()
        for path in run.rglob("*")
        if path.is_file()
    }


def aireiter_receipts(run, task_id=None):
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    attempt_dir = run / state["current_attempt"]
    attempt = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
    input_order = json.loads(
        (attempt_dir / "input_order.json").read_text(encoding="utf-8")
    )
    task_id = task_id or f"hero-attempt-{attempt['attempt']}"
    output_url = f"https://example.invalid/{task_id}.png"
    submit = {
        "schema_version": 1,
        "provider": "aireiter",
        "endpoint": "https://aireiter.com/api/openapi/submit",
        "out_task_id": task_id,
        "request_contract": {
            "model": attempt["model"],
            "prompt_sha256": sha(attempt_dir / "prompt.txt"),
            "aspect_ratio": attempt["aspect_ratio"],
            "resolution": "2K",
            "input_sha256": [item["sha256"] for item in input_order],
        },
        "response": {
            "data": {"status": "pending", "out_task_id": task_id},
        },
    }
    result = {
        "schema_version": 1,
        "provider": "aireiter",
        "endpoint": "https://aireiter.com/api/openapi/query",
        "out_task_id": task_id,
        "selected_output_url": output_url,
        "response": {
            "data": {
                "status": "completed",
                "out_task_id": task_id,
                "output": [{"url": output_url}],
            }
        },
    }
    return submit, result


@pytest.fixture(autouse=True)
def fake_aireiter_download(monkeypatch):
    payloads = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.close()

        def getcode(self):
            return 200

    def fake_urlopen(request, timeout=60):
        url = request.full_url if isinstance(request, Request) else request
        payload = payloads.get(url, png_bytes(1200, 1200))
        if isinstance(payload, Exception):
            raise payload
        return Response(payload)

    monkeypatch.setitem(
        record_generation_result.__globals__, "urlopen", fake_urlopen
    )
    return payloads


def test_prepare_attempt_writes_frozen_contract_and_updates_submission_only(tmp_path):
    run = ready_generation_run(tmp_path)
    attempt = prepare_generation_attempt(run)

    attempt_dir = run / "generation/01"
    assert attempt["attempt"] == 1
    assert attempt["attempt_path"] == "generation/01"
    assert (attempt_dir / "prompt.txt").read_text(encoding="utf-8") == attempt["prompt"]
    assert (attempt_dir / "model.txt").read_text(encoding="utf-8").strip() == "gpt_image_2"
    assert (attempt_dir / "aspect_ratio.txt").read_text(encoding="utf-8").strip() == "16:9"
    assert json.loads((attempt_dir / "input_order.json").read_text(encoding="utf-8")) == attempt["input_order"]
    assert json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8")) == attempt
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "generating"
    assert state["submission_attempts"] == 1
    assert state["current_attempt"] == "generation/01"
    assert state["generation_attempts"] == 0


def test_infrastructure_failure_does_not_count_and_next_attempt_uses_new_directory(tmp_path):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    updated = record_infrastructure_failure(run, {"message": "服务超时", "code": "timeout"})

    assert updated["state"] == "ready_to_generate"
    assert updated["generation_attempts"] == 0
    assert updated["non_pass_attempts"] == 0
    assert json.loads((run / "generation/01/infrastructure_error.json").read_text(encoding="utf-8")) == {
        "message": "服务超时",
        "code": "timeout",
    }
    second = prepare_generation_attempt(run)
    assert second["attempt"] == 2
    assert second["attempt_path"] == "generation/02"
    assert (run / "generation/01/prompt.txt").is_file()


def test_record_result_rejects_png_without_bound_aireiter_receipts(tmp_path):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    before = snapshot_files(run)

    assert_generation_error(
        lambda: record_generation_result(run, {}, {}),
        "AIReiter",
    )
    assert snapshot_files(run) == before


def test_record_result_downloads_selected_aireiter_output_instead_of_local_path(
    tmp_path, fake_aireiter_download
):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    expected = png_bytes(777, 555)
    fake_aireiter_download[provider_result["selected_output_url"]] = expected

    updated = record_generation_result(run, submit, provider_result)

    assert (run / "generation/01/result.png").read_bytes() == expected
    assert updated["state"] == "awaiting_qc"


def test_record_result_downloads_aireiter_output_with_browser_user_agent(
    tmp_path, monkeypatch
):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.close()

        def getcode(self):
            return 200

    def fake_urlopen(request, timeout=60):
        captured["request"] = request
        return Response(png_bytes(777, 555))

    monkeypatch.setitem(
        record_generation_result.__globals__, "urlopen", fake_urlopen
    )

    record_generation_result(run, submit, provider_result)

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url == provider_result["selected_output_url"]
    assert request.get_header("User-agent").startswith("Mozilla/5.0")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda submit, result: submit["request_contract"].update(
            model="nano_banana_v2"
        ),
        lambda submit, result: submit.update(provider="other"),
        lambda submit, result: result.update(out_task_id="other-task"),
        lambda submit, result: result["response"]["data"].update(
            status="processing"
        ),
        lambda submit, result: result.update(
            selected_output_url="https://example.invalid/not-in-output.png"
        ),
    ],
)
def test_record_result_rejects_unbound_aireiter_receipt_fields(tmp_path, mutation):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    mutation(submit, provider_result)
    before = snapshot_files(run)

    assert_generation_error(
        lambda: record_generation_result(run, submit, provider_result),
        "AIReiter",
    )
    assert snapshot_files(run) == before


def test_record_result_rejects_attempt_and_receipt_tampered_together(tmp_path):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    attempt_path = run / "generation/01/attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["model"] = "nano_banana_v2"
    write_json(attempt_path, attempt)
    submit["request_contract"]["model"] = "nano_banana_v2"
    before = snapshot_files(run)

    assert_generation_error(
        lambda: record_generation_result(run, submit, provider_result),
        "尝试",
        "哈希",
    )
    assert snapshot_files(run) == before


def test_record_result_copies_rehashes_and_counts_visual_result(
    tmp_path, fake_aireiter_download
):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    expected = png_bytes(1024, 1024)
    fake_aireiter_download[provider_result["selected_output_url"]] = expected
    updated = record_generation_result(run, submit, provider_result)

    attempt_dir = run / "generation/01"
    assert (attempt_dir / "result.png").read_bytes() == expected
    assert json.loads((attempt_dir / "submit.json").read_text(encoding="utf-8")) == submit
    result = json.loads((attempt_dir / "result.json").read_text(encoding="utf-8"))
    assert result["provider"] == "aireiter"
    assert result["out_task_id"] == "hero-attempt-1"
    assert result["result_sha256"] == sha(attempt_dir / "result.png")
    assert updated["state"] == "awaiting_qc"
    assert updated["generation_attempts"] == 1
    assert updated["non_pass_attempts"] == 0
    assert updated["current_submit_sha256"] == sha(attempt_dir / "submit.json")
    assert updated["current_result_record_sha256"] == sha(
        attempt_dir / "result.json"
    )
    assert updated["current_result_sha256"] == sha(attempt_dir / "result.png")


@pytest.mark.parametrize("invalid", ["download_error", "empty", "corrupt", "wrong_state"])
def test_record_result_rejects_invalid_download_or_state_without_partial_outputs(
    tmp_path, invalid, fake_aireiter_download
):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    output_url = provider_result["selected_output_url"]
    if invalid == "download_error":
        fake_aireiter_download[output_url] = OSError("下载失败")
    elif invalid == "empty":
        fake_aireiter_download[output_url] = b""
    elif invalid == "corrupt":
        fake_aireiter_download[output_url] = b"not-png"
    elif invalid == "wrong_state":
        state = json.loads((run / "state.json").read_text(encoding="utf-8"))
        state["state"] = "ready_to_generate"
        write_json(run / "state.json", state)
    before = snapshot_files(run)

    assert_generation_error(
        lambda: record_generation_result(run, submit, provider_result)
    )
    assert snapshot_files(run) == before


def test_prepare_rejects_four_visual_results_and_never_overwrites_directory(tmp_path):
    run = ready_generation_run(tmp_path)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["generation_attempts"] = 4
    write_json(state_path, state)
    assert_generation_error(lambda: prepare_generation_attempt(run), "4")

    state["generation_attempts"] = 0
    write_json(state_path, state)
    occupied = run / "generation/01"
    occupied.mkdir(parents=True)
    (occupied / "keep.txt").write_text("keep", encoding="utf-8")
    attempt = prepare_generation_attempt(run)
    assert attempt["attempt"] == 2
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_prepare_state_write_failure_rolls_back_attempt_directory(tmp_path, monkeypatch):
    run = ready_generation_run(tmp_path)
    before = snapshot_files(run)
    real_write = prepare_generation_attempt.__globals__["_atomic_write_json"]

    def fail_state(path, data):
        if Path(path) == run / "state.json":
            (run / "state.json").write_bytes(b"partial")
            raise OSError("注入状态失败")
        return real_write(path, data)

    monkeypatch.setitem(prepare_generation_attempt.__globals__, "_atomic_write_json", fail_state)
    assert_generation_error(lambda: prepare_generation_attempt(run), "回滚")
    assert snapshot_files(run) == before


def test_result_state_write_failure_rolls_back_created_files(tmp_path, monkeypatch):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    before = snapshot_files(run)
    real_write = record_generation_result.__globals__["_atomic_write_json"]

    def fail_state(path, data):
        if Path(path) == run / "state.json":
            (run / "state.json").write_bytes(b"partial")
            raise OSError("注入状态失败")
        return real_write(path, data)

    monkeypatch.setitem(record_generation_result.__globals__, "_atomic_write_json", fail_state)
    assert_generation_error(
        lambda: record_generation_result(run, submit, provider_result),
        "回滚",
    )
    assert snapshot_files(run) == before


@pytest.mark.parametrize("binding", ["input", "reference"])
def test_build_contract_rejects_relative_path_escaping_run(tmp_path, binding):
    run = ready_generation_run(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(png_bytes())
    if binding == "input":
        manifest_path = run / "input/input_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["images"][0]["path"] = "../../outside.png"
        manifest["images"][0]["sha256"] = sha(outside)
        write_json(manifest_path, manifest)
        state_path = run / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["input_manifest_sha256"] = sha(manifest_path)
        write_json(state_path, state)
    else:
        decision_path = run / "review/decision.json"
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision["selected_reference"] = "../outside.png"
        decision["image_sha256"] = sha(outside)
        top3_path = run / "review/top3.json"
        top3 = json.loads(top3_path.read_text(encoding="utf-8"))
        top3["items"][0]["selected_reference"] = "../outside.png"
        top3["items"][0]["image_sha256"] = sha(outside)
        write_json(top3_path, top3)
        decision["top3_sha256"] = sha(top3_path)
        write_json(decision_path, decision)
        state_path = run / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["top3_sha256"] = sha(top3_path)
        state["decision_sha256"] = sha(decision_path)
        write_json(state_path, state)
    assert_generation_error(lambda: build_generation_contract(run), "run")


def test_prepare_counts_existing_visual_results_even_if_state_is_stale(tmp_path):
    run = ready_generation_run(tmp_path)
    for index in range(1, 5):
        path = run / f"generation/{index:02d}/result.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(png_bytes())
    assert_generation_error(lambda: prepare_generation_attempt(run), "4")


def test_infrastructure_state_failure_rolls_back_error_file(tmp_path, monkeypatch):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    before = snapshot_files(run)
    real_write = record_infrastructure_failure.__globals__["_atomic_write_json"]

    def fail_state(path, data):
        if Path(path) == run / "state.json":
            (run / "state.json").write_bytes(b"partial")
            raise OSError("注入状态失败")
        return real_write(path, data)

    monkeypatch.setitem(
        record_infrastructure_failure.__globals__, "_atomic_write_json", fail_state
    )
    assert_generation_error(
        lambda: record_infrastructure_failure(run, {"message": "timeout"}), "回滚"
    )
    assert snapshot_files(run) == before


@pytest.mark.parametrize("recorder", ["infrastructure", "result"])
@pytest.mark.parametrize("invalid_current", ["../outside/01", "generation/99"])
def test_recorders_reject_escaped_or_missing_current_attempt_before_writing(
    tmp_path, recorder, invalid_current
):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_attempt"] = invalid_current
    write_json(state_path, state)
    before_run = snapshot_files(run)
    outside = tmp_path / "outside"
    before_outside = snapshot_files(outside) if outside.exists() else {}

    if recorder == "infrastructure":
        call = lambda: record_infrastructure_failure(run, {"message": "timeout"})
    else:
        call = lambda: record_generation_result(run, {}, {})
    assert_generation_error(call)
    assert snapshot_files(run) == before_run
    assert (snapshot_files(outside) if outside.exists() else {}) == before_outside


def test_recorders_require_current_attempt_json_before_writing(tmp_path):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    (run / "generation/01/attempt.json").unlink()
    before = snapshot_files(run)
    assert_generation_error(
        lambda: record_infrastructure_failure(run, {"message": "timeout"}),
        "attempt.json",
    )
    assert snapshot_files(run) == before


@pytest.mark.parametrize("counter_source", ["state", "files"])
def test_record_result_rechecks_four_result_limit_before_any_write(tmp_path, counter_source):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if counter_source == "state":
        state["generation_attempts"] = 4
        write_json(state_path, state)
    else:
        for index in range(2, 6):
            path = run / f"generation/{index:02d}/result.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(png_bytes())
    before = snapshot_files(run)
    assert_generation_error(
        lambda: record_generation_result(run, {"request": 1}, {"result": 1}),
        "4",
    )
    assert snapshot_files(run) == before


def test_prepare_mkdtemp_failure_removes_generation_created_by_this_call(
    tmp_path, monkeypatch
):
    run = ready_generation_run(tmp_path)
    state_path = run / "state.json"
    original_state = state_path.read_bytes()
    assert not (run / "generation").exists()

    def fail_mkdtemp(*args, **kwargs):
        raise OSError("注入临时目录失败")

    monkeypatch.setattr(
        prepare_generation_attempt.__globals__["tempfile"], "mkdtemp", fail_mkdtemp
    )
    assert_generation_error(lambda: prepare_generation_attempt(run), "临时目录")
    assert not (run / "generation").exists()
    assert state_path.read_bytes() == original_state


@pytest.mark.parametrize(
    ("suffix", "content"),
    [(".jpg", jpeg_bytes()), (".webp", webp_bytes())],
)
def test_record_result_rejects_non_png_without_creating_fake_png(
    tmp_path, suffix, content, fake_aireiter_download
):
    run = ready_generation_run(tmp_path)
    prepare_generation_attempt(run)
    submit, provider_result = aireiter_receipts(run)
    fake_aireiter_download[provider_result["selected_output_url"]] = content
    before = snapshot_files(run)
    assert_generation_error(
        lambda: record_generation_result(run, submit, provider_result), "PNG"
    )
    assert snapshot_files(run) == before


@pytest.mark.parametrize("mutation", ["missing_state", "tampered_sidecar"])
def test_build_contract_requires_analysis_hash_in_state_and_matching_sidecar(
    tmp_path, mutation
):
    run = ready_generation_run(tmp_path)
    if mutation == "missing_state":
        state_path = run / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.pop("product_analysis_sha256")
        write_json(state_path, state)
    else:
        (run / "analysis/product_analysis.sha256").write_text("0" * 64 + "\n")
    assert_generation_error(lambda: build_generation_contract(run), "产品分析", "哈希")


@pytest.mark.parametrize("invalid_kind", ["duplicate_title", "reordered_titles"])
def test_prompt_validator_requires_titles_once_in_fixed_order(tmp_path, invalid_kind):
    contract = build_generation_contract(ready_generation_run(tmp_path))
    prompt = contract["prompt"]
    if invalid_kind == "duplicate_title":
        prompt += "\n【任务目标】"
    else:
        prompt = prompt.replace("【任务目标】", "__A__").replace("【图片职责】", "【任务目标】")
        prompt = prompt.replace("__A__", "【图片职责】")
    assert validate_prompt_contract(prompt, contract["input_order"])


def test_prompt_validator_requires_64_hexadecimal_sha256(tmp_path):
    contract = build_generation_contract(ready_generation_run(tmp_path))
    invalid_order = copy.deepcopy(contract["input_order"])
    invalid_order[0]["sha256"] = "z" * 64
    errors = validate_prompt_contract(contract["prompt"], invalid_order)
    assert errors
    assert any("sha256" in error for error in errors)


def test_contract_and_attempt_switch_to_nano_banana_after_two_non_pass(tmp_path):
    run = ready_generation_run(tmp_path)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["non_pass_attempts"] = 2
    write_json(state_path, state)

    assert build_generation_contract(run)["model"] == "nano_banana_v2"
    attempt = prepare_generation_attempt(run)
    assert attempt["model"] == "nano_banana_v2"
    assert (run / "generation/01/model.txt").read_text(encoding="utf-8").strip() == "nano_banana_v2"


def test_public_api_chain_from_prepare_run_to_finalize_pass_freezes_all_hashes(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    front = sources / "front.png"
    side = sources / "side.jpg"
    detail = sources / "detail.webp"
    front.write_bytes(png_bytes(600, 600))
    side.write_bytes(jpeg_bytes(400, 600))
    detail.write_bytes(webp_bytes(500, 400))
    run = tmp_path / "run"
    prepare_run(run, "PN-001", front, side, [detail])
    freeze_product_analysis(run, valid_analysis())

    records = []
    for index in range(1, 4):
        image = sources / f"reference-{index}.webp"
        image.write_bytes(webp_bytes(1600 + index, 900))
        records.append({
            "record_id": f"rec-{index}",
            "usable": True,
            "image_path": str(image),
            "source_fields": {
                "素材编号": f"RP{index:03d}",
                "图片类型": "主图",
                "适用品类": "戒指",
                "关键词": "亮色背景",
            },
        })
    input_manifest = json.loads(
        (run / "input/input_manifest.json").read_text(encoding="utf-8")
    )
    candidates = collect_explicit_category_candidates(
        records,
        "ring",
        excluded_sha256=[item["sha256"] for item in input_manifest["images"]],
        source_snapshot={
            "wiki_url": "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink",
            "base_name": "AI生图参考图素材库",
            "table_name": "素材收录池",
            "pagination_complete": True,
            "page_count": 1,
            "record_count": len(records),
        },
    )
    assessments = []
    for candidate in candidates:
        assessments.append(
            {
                "record_id": candidate["record_id"],
                "material_id": candidate["material_id"],
                "image_sha256": candidate["image_sha256"],
                "compatible": True,
                "single_product_unit": True,
                "requires_product_stretch": False,
                "requires_large_background_rebuild": False,
                "topology_layout": 25,
                "complete_replace_region": 15,
                "camera_orientation_scale": 12,
                "background_props": 12,
                "lighting_material": 8,
                "cleanup_cost": 8,
                "reasons": ["构图匹配"],
                "risks": [],
            }
        )
    write_review_package(run, candidates, assessments)
    record_reference_decision(run, 1, user_selection(1))

    state_before = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert "product_analysis_sha256" not in state_before
    freeze_fidelity_constraints(run, valid_constraints())
    state_after = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state_after["product_analysis_sha256"] == sha(
        run / "analysis/product_analysis.json"
    )
    assert state_after["fidelity_constraints_sha256"] == sha(
        run / "analysis/fidelity_constraints.json"
    )
    assert state_after["input_manifest_sha256"] == sha(
        run / "input/input_manifest.json"
    )
    assert build_generation_contract(run)["model"] == "gpt_image_2"

    prepare_generation_attempt(run)
    record_generation_result(run, *aireiter_receipts(run))
    manifest = finalize_qc(run, valid_qc("pass"))

    assert manifest["input_manifest_sha256"] == sha(
        run / "input/input_manifest.json"
    )
    assert (run / "final/result.png").is_file()


def test_prepare_failure_preserves_preexisting_empty_generation_directory(
    tmp_path, monkeypatch
):
    run = ready_generation_run(tmp_path)
    generation = run / "generation"
    generation.mkdir()
    original_state = (run / "state.json").read_bytes()
    real_write = prepare_generation_attempt.__globals__["_atomic_write_json"]

    def fail_state(path, data):
        if Path(path) == run / "state.json":
            (run / "state.json").write_bytes(b"partial")
            raise OSError("注入状态失败")
        return real_write(path, data)

    monkeypatch.setitem(prepare_generation_attempt.__globals__, "_atomic_write_json", fail_state)
    assert_generation_error(lambda: prepare_generation_attempt(run), "回滚")
    assert generation.is_dir()
    assert not any(generation.iterdir())
    assert (run / "state.json").read_bytes() == original_state


def valid_qc(status="pass", component_counts=None):
    checklist = [
        {"id": check_id, "result": "pass", "notes": "已核验"}
        for check_id in CHECKLIST_CHECK_IDS
    ]
    failure_codes = []
    if status == "rerun":
        checklist[5]["result"] = "fail"
        failure_codes = ["material_color_drift"]
    elif status == "reject":
        checklist[0]["result"] = "fail"
        failure_codes = ["product_category_mismatch"]
    return {
        "schema_version": 1,
        "status": status,
        "failure_codes": failure_codes,
        "checklist": checklist,
        "component_count_checks": [
            {
                "name": item["name"],
                "expected_physical_count": item["physical_count"],
                "visible_count": item["physical_count"],
                "occluded_count": 0,
                "occlusion_evidence": "无遮挡，全部部件均可见",
                "result": "pass",
                "notes": "逐项计数与冻结实体总数一致",
            }
            for item in (component_counts or [])
        ],
        "fidelity_checks": [
            {
                "name": "圆形主石",
                "question": "主石是否保持圆形？",
                "result": "pass",
                "notes": "形状一致",
            }
        ],
    }


def awaiting_qc_run(tmp_path, *, generation_attempts=1, component_counts=None):
    run = ready_generation_run(tmp_path, component_counts=component_counts)
    prepare_generation_attempt(run)
    record_generation_result(run, *aireiter_receipts(run))
    if generation_attempts != 1:
        state_path = run / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["generation_attempts"] = generation_attempts
        write_json(state_path, state)
    return run


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data["checklist"].pop(),
        lambda data: data["checklist"].append(copy.deepcopy(data["checklist"][0])),
        lambda data: data["checklist"].append(
            {"id": "extra", "result": "pass", "notes": "x"}
        ),
        lambda data: data["checklist"][0].update(result=True),
        lambda data: data["checklist"][0].update(notes=" "),
        lambda data: data.update(fidelity_checks=[]),
        lambda data: data["fidelity_checks"].append(
            copy.deepcopy(data["fidelity_checks"][0])
        ),
        lambda data: data["fidelity_checks"][0].update(question="错误问题"),
    ],
)
def test_validate_qc_rejects_checklist_and_fidelity_shape_errors(mutation):
    data = valid_qc()
    mutation(data)
    assert_generation_error(lambda: validate_qc_record(data, valid_constraints()))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(status="unknown"),
        lambda data: data.update(failure_codes=["unknown"]),
        lambda data: data.update(failure_codes=["material_color_drift"] * 2),
        lambda data: data["checklist"][0].update(result="fail"),
        lambda data: data.update(status="rerun", failure_codes=[]),
        lambda data: data.update(
            status="rerun", failure_codes=["product_category_mismatch"]
        ),
        lambda data: data.update(status="reject", failure_codes=[]),
    ],
)
def test_validate_qc_rejects_invalid_status_failure_combinations(mutation):
    data = valid_qc()
    mutation(data)
    assert_generation_error(lambda: validate_qc_record(data, valid_constraints()))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(status=[]),
        lambda data: data["checklist"][0].update(result={}),
        lambda data: data["fidelity_checks"][0].update(result=[]),
    ],
)
def test_validate_qc_rejects_unhashable_enum_values_with_chinese_contract_error(mutation):
    data = valid_qc()
    mutation(data)
    assert_generation_error(lambda: validate_qc_record(data, valid_constraints()))


@pytest.mark.parametrize("status", ["pass", "rerun", "reject"])
def test_validate_qc_accepts_three_legal_statuses_and_returns_copy(status):
    data = valid_qc(status)
    normalized = validate_qc_record(data, valid_constraints())
    assert normalized == data
    assert normalized is not data
    assert normalized["checklist"] is not data["checklist"]


def test_qc_requires_visible_plus_occluded_to_equal_frozen_physical_count():
    counts = [
        {
            "name": "圆珠",
            "physical_count": 13,
            "source_views": ["front", "side"],
        }
    ]
    constraints = valid_constraints("QY048", "beaded_bracelet", counts)
    valid = valid_qc(component_counts=counts)
    assert validate_qc_record(valid, constraints)["component_count_checks"][0][
        "visible_count"
    ] == 13

    too_many = copy.deepcopy(valid)
    too_many["component_count_checks"][0]["visible_count"] = 17
    assert_generation_error(lambda: validate_qc_record(too_many, constraints), "实体总数")


def test_qc_allows_scene_occlusion_only_with_evidence_and_preserved_total():
    counts = [
        {
            "name": "圆珠",
            "physical_count": 13,
            "source_views": ["front", "side"],
        }
    ]
    constraints = valid_constraints("QY048", "beaded_bracelet", counts)
    qc = valid_qc(component_counts=counts)
    qc["component_count_checks"][0].update(
        visible_count=11,
        occluded_count=2,
        occlusion_evidence="黑色前景道具遮挡左上方连续两颗",
    )

    assert validate_qc_record(qc, constraints)["component_count_checks"][0][
        "occluded_count"
    ] == 2

    qc["component_count_checks"][0]["occlusion_evidence"] = " "
    assert_generation_error(lambda: validate_qc_record(qc, constraints), "遮挡", "证据")


def test_component_count_failure_requires_rerun_code():
    counts = [
        {
            "name": "圆珠",
            "physical_count": 13,
            "source_views": ["front", "side"],
        }
    ]
    constraints = valid_constraints("QY048", "beaded_bracelet", counts)
    qc = valid_qc("rerun", component_counts=counts)
    qc["failure_codes"] = ["component_count_mismatch"]
    qc["component_count_checks"][0].update(
        visible_count=17,
        result="fail",
        notes="可见 17 颗，比冻结数量多 4 颗",
    )

    assert validate_qc_record(qc, constraints)["status"] == "rerun"

    qc["failure_codes"] = ["material_color_drift"]
    assert_generation_error(lambda: validate_qc_record(qc, constraints), "数量")


def test_finalize_pass_creates_bound_manifest_and_passed_state(tmp_path):
    run = awaiting_qc_run(tmp_path)
    result = finalize_qc(run, valid_qc("pass"))
    attempt = run / "generation/01"
    final = run / "final/result.png"
    manifest_path = run / "final/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    decision = json.loads((run / "review/decision.json").read_text(encoding="utf-8"))
    assert result == manifest
    assert (attempt / "qc.json").is_file()
    assert final.read_bytes() == (attempt / "result.png").read_bytes()
    assert manifest == {
        "schema_version": 1,
        "product_id": "PN-001",
        "result": "final/result.png",
        "result_sha256": sha(final),
        "attempt": 1,
        "attempt_sha256": state["current_attempt_sha256"],
        "model": "gpt_image_2",
        "aspect_ratio": "16:9",
        "provider": "aireiter",
        "out_task_id": "hero-attempt-1",
        "selected_output_url": "https://example.invalid/hero-attempt-1.png",
        "submit_receipt": "generation/01/submit.json",
        "submit_receipt_sha256": sha(attempt / "submit.json"),
        "result_receipt": "generation/01/result.json",
        "result_receipt_sha256": sha(attempt / "result.json"),
        "material_id": "RP001",
        "record_id": "rec-1",
        "user_selection_evidence": user_selection(1),
        "input_manifest_sha256": state["input_manifest_sha256"],
        "product_analysis_sha256": state["product_analysis_sha256"],
        "fidelity_constraints_sha256": state["fidelity_constraints_sha256"],
        "top3_sha256": state["top3_sha256"],
        "decision_sha256": state["decision_sha256"],
        "qc": "generation/01/qc.json",
        "qc_sha256": sha(attempt / "qc.json"),
    }
    assert state["state"] == "passed"


def test_finalize_revalidates_aireiter_receipts_before_pass(tmp_path):
    run = awaiting_qc_run(tmp_path)
    submit_path = run / "generation/01/submit.json"
    submit = json.loads(submit_path.read_text(encoding="utf-8"))
    submit["request_contract"]["model"] = "nano_banana_v2"
    write_json(submit_path, submit)
    before = snapshot_files(run)

    assert_generation_error(lambda: finalize_qc(run, valid_qc("pass")), "AIReiter")
    assert snapshot_files(run) == before


def test_finalize_rejects_structurally_valid_receipt_changed_after_recording(tmp_path):
    run = awaiting_qc_run(tmp_path)
    submit_path = run / "generation/01/submit.json"
    submit = json.loads(submit_path.read_text(encoding="utf-8"))
    submit["response"]["data"]["status"] = "processing"
    write_json(submit_path, submit)
    before = snapshot_files(run)

    assert_generation_error(lambda: finalize_qc(run, valid_qc("pass")), "提交回执", "哈希")
    assert snapshot_files(run) == before


def test_finalize_pass_rejects_existing_final_without_writes(tmp_path):
    run = awaiting_qc_run(tmp_path)
    (run / "final").mkdir()
    (run / "final/keep").write_bytes(b"keep")
    before = snapshot_files(run)
    assert_generation_error(lambda: finalize_qc(run, valid_qc("pass")), "final")
    assert snapshot_files(run) == before


def test_finalize_rejects_non_png_result_even_when_recorded_hash_matches(tmp_path):
    run = awaiting_qc_run(tmp_path)
    result_path = run / "generation/01/result.png"
    result_path.write_bytes(b"not-a-png")
    result_data_path = run / "generation/01/result.json"
    result_data = json.loads(result_data_path.read_text(encoding="utf-8"))
    result_data["result_sha256"] = sha(result_path)
    write_json(result_data_path, result_data)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_result_sha256"] = sha(result_path)
    state["current_result_record_sha256"] = sha(result_data_path)
    write_json(state_path, state)
    before = snapshot_files(run)
    assert_generation_error(lambda: finalize_qc(run, valid_qc("pass")), "PNG")
    assert snapshot_files(run) == before


@pytest.mark.parametrize(
    ("attempts", "expected_state"), [(1, "ready_to_generate"), (4, "failed")]
)
def test_finalize_rerun_updates_counts_without_final(tmp_path, attempts, expected_state):
    run = awaiting_qc_run(tmp_path, generation_attempts=attempts)
    finalize_qc(run, valid_qc("rerun"))
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == expected_state
    assert state["non_pass_attempts"] == 1
    assert (run / "generation/01/qc.json").is_file()
    assert not (run / "final").exists()


def test_rerun_prompt_includes_previous_qc_failure_codes_and_notes(tmp_path):
    run = awaiting_qc_run(tmp_path)
    qc = valid_qc("rerun")
    qc["checklist"][5]["notes"] = "金属颜色偏冷，需要恢复产品图暖金色"
    finalize_qc(run, qc)

    contract = build_generation_contract(run)

    assert "上轮 QC 纠偏" in contract["prompt"]
    assert "material_color_drift" in contract["prompt"]
    assert "金属颜色偏冷，需要恢复产品图暖金色" in contract["prompt"]


def test_rerun_prompt_includes_component_count_evidence(tmp_path):
    counts = [
        {
            "name": "圆珠",
            "physical_count": 13,
            "source_views": ["front", "side"],
        }
    ]
    run = awaiting_qc_run(tmp_path, component_counts=counts)
    qc = valid_qc("rerun", component_counts=counts)
    qc["failure_codes"] = ["component_count_mismatch"]
    qc["component_count_checks"][0].update(
        visible_count=16,
        result="fail",
        notes="画面可见16颗，必须减少到13颗",
    )
    finalize_qc(run, qc)

    contract = build_generation_contract(run)

    assert "component_count_mismatch" in contract["prompt"]
    assert "画面可见16颗，必须减少到13颗" in contract["prompt"]


def test_finalize_reject_archives_decision_and_allows_remaining_rank(tmp_path):
    run = awaiting_qc_run(tmp_path)
    finalize_qc(run, valid_qc("reject"))
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "awaiting_reference_decision"
    assert state["excluded_ranks"] == [1]
    assert (run / "review/decision-history/01.json").is_file()
    assert not (run / "review/decision.json").exists()
    with pytest.raises(ReferenceReviewError, match="排除"):
        record_reference_decision(run, 1, user_selection(1))
    record_reference_decision(run, 2, user_selection(2))
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "ready_to_generate"
    assert state["excluded_ranks"] == [1]
    assert state["decision_sha256"] == sha(run / "review/decision.json")


def test_two_rejects_then_remaining_rank_pass_preserves_history_and_hashes(tmp_path):
    run = awaiting_qc_run(tmp_path)

    finalize_qc(run, valid_qc("reject"))
    first_history = json.loads(
        (run / "review/decision-history/01.json").read_text(encoding="utf-8")
    )
    assert first_history["selected_rank"] == 1
    record_reference_decision(run, 2, user_selection(2))
    second_decision_sha = sha(run / "review/decision.json")

    prepare_generation_attempt(run)
    record_generation_result(run, *aireiter_receipts(run))
    finalize_qc(run, valid_qc("reject"))

    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    second_history_path = run / "review/decision-history/02.json"
    second_history = json.loads(second_history_path.read_text(encoding="utf-8"))
    assert second_history["selected_rank"] == 2
    assert sha(second_history_path) == second_decision_sha
    assert state["excluded_ranks"] == [1, 2]
    assert state["non_pass_attempts"] == 2

    record_reference_decision(run, 3, user_selection(3))
    third_decision_sha = sha(run / "review/decision.json")
    assert build_generation_contract(run)["model"] == "nano_banana_v2"
    prepare_generation_attempt(run)
    record_generation_result(run, *aireiter_receipts(run))
    manifest = finalize_qc(run, valid_qc("pass"))

    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "passed"
    assert state["generation_attempts"] == 3
    assert state["non_pass_attempts"] == 2
    assert state["excluded_ranks"] == [1, 2]
    assert state["decision_sha256"] == third_decision_sha
    assert manifest["attempt"] == 3
    assert manifest["material_id"] == "RP003"
    assert manifest["decision_sha256"] == third_decision_sha


@pytest.mark.parametrize("reason", ["all_ranks", "fourth_attempt"])
def test_finalize_reject_fails_when_no_more_reference_or_attempts(tmp_path, reason):
    run = awaiting_qc_run(tmp_path, generation_attempts=4 if reason == "fourth_attempt" else 1)
    if reason == "all_ranks":
        state_path = run / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["excluded_ranks"] = [2, 3]
        write_json(state_path, state)
    finalize_qc(run, valid_qc("reject"))
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "failed"


@pytest.mark.parametrize("status", ["pass", "reject"])
def test_finalize_state_failure_rolls_back_qc_final_history_and_state(
    tmp_path, monkeypatch, status
):
    run = awaiting_qc_run(tmp_path)
    before = snapshot_files(run)
    state_path = run / "state.json"
    real_write = finalize_qc.__globals__["_atomic_write_json"]

    def fail_state(path, data):
        if Path(path) == state_path:
            state_path.write_bytes(b"partial")
            raise OSError("注入 state 失败")
        return real_write(path, data)

    monkeypatch.setitem(finalize_qc.__globals__, "_atomic_write_json", fail_state)
    assert_generation_error(lambda: finalize_qc(run, valid_qc(status)), "回滚")
    assert snapshot_files(run) == before


@pytest.mark.parametrize("failure_point", ["qc", "final", "history"])
def test_finalize_injected_artifact_failure_leaves_run_unchanged(
    tmp_path, monkeypatch, failure_point
):
    run = awaiting_qc_run(tmp_path)
    before = snapshot_files(run)
    status = "reject" if failure_point == "history" else "pass"
    if failure_point == "qc":
        real_write = finalize_qc.__globals__["_atomic_write_json"]

        def fail_qc(path, data):
            if Path(path).name == "qc.json":
                raise OSError("注入 qc 失败")
            return real_write(path, data)

        monkeypatch.setitem(finalize_qc.__globals__, "_atomic_write_json", fail_qc)
    elif failure_point == "final":
        def fail_copy(source, destination):
            raise OSError("注入 final 复制失败")

        monkeypatch.setattr(finalize_qc.__globals__["shutil"], "copyfile", fail_copy)
    else:
        real_replace = Path.replace
        decision_path = run / "review/decision.json"

        def fail_history_move(path, target):
            if path == decision_path:
                raise OSError("注入 history 移动失败")
            return real_replace(path, target)

        monkeypatch.setattr(Path, "replace", fail_history_move)
    assert_generation_error(lambda: finalize_qc(run, valid_qc(status)))
    assert snapshot_files(run) == before


def test_finalize_reject_does_not_overwrite_history(tmp_path):
    run = awaiting_qc_run(tmp_path)
    history = run / "review/decision-history/01.json"
    history.parent.mkdir()
    history.write_bytes(b"old")
    before = snapshot_files(run)
    assert_generation_error(lambda: finalize_qc(run, valid_qc("reject")), "历史")
    assert snapshot_files(run) == before


@pytest.mark.parametrize(
    ("script", "success_args", "success_text"),
    [
        ("validate_prompt_contract.py", ("prompt.txt", "input_order.json"), "prompt contract OK"),
        ("validate_qc_record.py", ("qc.json", "constraints.json"), "qc record OK"),
    ],
)
def test_contract_cli_success_failure_and_usage(
    tmp_path, script, success_args, success_text
):
    run = ready_generation_run(tmp_path)
    contract = build_generation_contract(run)
    files = {
        "prompt.txt": contract["prompt"],
        "input_order.json": contract["input_order"],
        "qc.json": valid_qc(),
        "constraints.json": valid_constraints(),
    }
    for name, value in files.items():
        path = tmp_path / name
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            write_json(path, value)
    command = [sys.executable, str(SCRIPTS / script)]
    success = subprocess.run(
        command + [str(tmp_path / name) for name in success_args],
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    assert success.returncode == 0
    assert success.stdout.strip() == success_text
    before = {name: (tmp_path / name).read_bytes() for name in files}
    invalid = subprocess.run(
        command + [str(tmp_path / "missing"), str(tmp_path / success_args[1])],
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    assert invalid.returncode == 1
    assert any("\u4e00" <= char <= "\u9fff" for char in invalid.stderr)
    usage = subprocess.run(command, text=True, capture_output=True, encoding="utf-8")
    assert usage.returncode == 2
    assert before == {name: (tmp_path / name).read_bytes() for name in files}


def test_qc_cli_reports_unhashable_contract_value_without_traceback(tmp_path):
    qc = valid_qc()
    qc["checklist"][0]["result"] = {}
    qc_path = tmp_path / "qc.json"
    constraints_path = tmp_path / "constraints.json"
    write_json(qc_path, qc)
    write_json(constraints_path, valid_constraints())

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validate_qc_record.py"),
            str(qc_path),
            str(constraints_path),
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
    )

    assert result.returncode == 1
    assert any("\u4e00" <= char <= "\u9fff" for char in result.stderr)
    assert "Traceback" not in result.stderr
