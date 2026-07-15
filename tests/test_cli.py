import json
from pathlib import Path

from openpyxl import Workbook

from jewelry_on_hand.models import ReferenceRow, ScoredReference
from jewelry_on_hand.product_analysis import load_product_analysis
from jewelry_on_hand.reference_composition import build_candidate_snapshot
from jewelry_on_hand.review_package import write_review_package
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


def make_catalog(path, ref, *, snapshot_overrides=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "分类明细"
    ws.append(
        [
            "序号",
            "文件名",
            "相对路径",
            "绝对路径",
            "宽度",
            "高度",
            "大小MB",
            "用途分类",
            "手链手串适用性",
            "默认使用策略",
            "风格分类",
            "场景关键词",
            "饰品类型",
            "推荐使用方式",
            "备注",
            "判断置信度",
            "人物取景范围",
            "可见身体区域",
            "产品预计展示面积",
            "衣领类型",
            "衣物遮挡风险",
            "姿势关键词",
            "原有首饰类型",
            "裁切风险",
            "左右手",
            "手部朝向",
        ]
    )
    snapshot_fields = {
        "人物取景范围": "手部近景",
        "可见身体区域": "左手腕 / 前臂完整露出",
        "产品预计展示面积": "展示面积充足，大于 35%",
        "衣领类型": "无衣领",
        "衣物遮挡风险": "衣物无遮挡",
        "姿势关键词": "身体未入镜，前臂自然抬起",
        "原有首饰类型": "左手腕原有手链可完整识别并移除",
        "裁切风险": "裁切风险低",
        "左右手": "左手",
        "手部朝向": "手背朝向镜头",
    }
    snapshot_fields.update(snapshot_overrides or {})
    purposes = ["手部佩戴图"] * 3 + ["生活场景图"] * 3
    for i, purpose in enumerate(purposes, start=1):
        ws.append(
            [
                i,
                ref.name,
                ref.name,
                str(ref),
                100,
                200,
                0.1,
                purpose,
                "是：可用于手链/手串",
                "常规可优先使用",
                "暗调闪光",
                "车内 闪光",
                "手链/手串",
                "近景手腕",
                "正面视角，主体居中，无文字或 UI，手腕/前臂露出面积足",
                "高",
                *snapshot_fields.values(),
            ]
        )
    wb.save(path)


def make_analysis(path):
    data = {
        "product_type": "手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "深红主珠",
        "color_family": ["深红"],
        "style_mood": "暗调闪光",
        "composition": "手腕近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": ["保留主珠"],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def make_constraints(path, review_status="confirmed", must_keep=None):
    if must_keep is None:
        must_keep = [
            {
                "name": "白水晶随形",
                "source_text": "白水晶随形",
                "normalized_keyword": "随形",
                "location": "主珠右侧",
                "visual_shape": "透明不规则随形，非圆珠",
                "relationship": "位于两颗圆珠之间",
                "forbid": ["改成圆珠"],
                "qc_question": "白水晶随形是否仍是不规则透明异形珠",
            }
        ]
    data = {
        "schema_version": 1,
        "source": {
            "product_image": "input/product-on-hand.jpg",
            "product_analysis": "analysis/product_analysis.json",
        },
        "detected_keywords": ["随形"] if must_keep else [],
        "must_keep": must_keep,
        "must_not_change": ["珠子排列顺序"],
        "needs_user_review": bool(must_keep),
        "detail_crop_recommended": bool(must_keep),
        "review_status": review_status,
    }
    write_json(path, data)
    return data


def declare_scene_output_role(run_root, role="hand_worn"):
    write_json(
        Path(run_root) / "analysis" / "output_role.json",
        {"output_role": role},
    )


def test_prepare_review_cli_creates_review_html(tmp_path):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, ref)
    analysis = tmp_path / "analysis.json"
    make_analysis(analysis)

    assert (
        main(
            [
                "prepare-review",
                "--product-image",
                str(product),
                "--analysis-json",
                str(analysis),
                "--classification",
                str(catalog),
                "--output-root",
                str(tmp_path / "runs"),
                "--run-id",
                "demo",
                "--output-role",
                "hand_worn",
            ]
        )
        == 0
    )

    run_root = tmp_path / "runs" / "demo"
    assert (run_root / "review" / "review.html").is_file()
    assert (run_root / "analysis" / "product_analysis_prompt.txt").is_file()
    assert (run_root / "analysis" / "product_fidelity_constraints.json").is_file()
    fidelity = read_json(run_root / "analysis" / "product_fidelity_constraints.json")
    assert fidelity["schema_version"] == 1
    assert "must_keep" in fidelity
    assert fidelity["review_status"] in {"pending", "not_applicable"}
    assert read_json(run_root / "analysis" / "product_analysis.json")["product_type"] == "手链/手串"
    snapshots = read_json(
        run_root / "analysis" / "reference_composition_snapshots.json"
    )
    assert [item["rank"] for item in snapshots] == [1, 2, 3]
    assert "产品身份图" in (run_root / "review" / "review.html").read_text(
        encoding="utf-8"
    )
    assert not (run_root / "review" / "review_decision.json").exists()


def test_prepare_review_cli_rejects_existing_non_empty_run_without_overwrite(tmp_path):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    (run_root / "input").mkdir(parents=True)
    (run_root / "review").mkdir()
    old_product = run_root / "input" / "product-on-hand.jpg"
    old_product.write_bytes(b"old-product")
    write_json(run_root / "review" / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1]})

    product = tmp_path / "new-product.jpg"
    product.write_bytes(b"new-product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, ref)
    analysis = tmp_path / "analysis.json"
    make_analysis(analysis)

    assert (
        main(
            [
                "prepare-review",
                "--product-image",
                str(product),
                "--analysis-json",
                str(analysis),
                "--classification",
                str(catalog),
                "--output-root",
                str(tmp_path / "runs"),
                "--run-id",
                "demo",
                "--output-role",
                "hand_worn",
            ]
        )
        != 0
    )

    assert old_product.read_bytes() == b"old-product"
    assert (run_root / "review" / "review_decision.json").is_file()
    assert not (run_root / "review" / "review.html").exists()


def test_prepare_review_cli_writes_dimensions_json_and_includes_it_in_prompt(tmp_path):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, ref)
    analysis = tmp_path / "analysis.json"
    make_analysis(analysis)
    dimensions = tmp_path / "dimensions.json"
    dimensions.write_text(
        json.dumps(
            {"bead_diameter_mm": 12.5, "dimension_source": "用户提供尺寸"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "prepare-review",
                "--product-image",
                str(product),
                "--analysis-json",
                str(analysis),
                "--classification",
                str(catalog),
                "--output-root",
                str(tmp_path / "runs"),
                "--run-id",
                "demo",
                "--dimensions-json",
                str(dimensions),
                "--output-role",
                "hand_worn",
            ]
        )
        == 0
    )

    run_root = tmp_path / "runs" / "demo"
    assert read_json(run_root / "input" / "product_dimensions.json") == {
        "bead_diameter_mm": 12.5,
        "dimension_source": "用户提供尺寸",
    }
    prompt = (run_root / "analysis" / "product_analysis_prompt.txt").read_text(encoding="utf-8")
    assert "12.5" in prompt
    assert "用户提供尺寸" in prompt


def test_prepare_review_cli_without_analysis_json_writes_prompt_only(tmp_path):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, ref)

    assert (
        main(
            [
                "prepare-review",
                "--product-image",
                str(product),
                "--classification",
                str(catalog),
                "--output-root",
                str(tmp_path / "runs"),
                "--run-id",
                "demo",
                "--output-role",
                "hand_worn",
            ]
        )
        != 0
    )

    run_root = tmp_path / "runs" / "demo"
    assert (run_root / "analysis" / "product_analysis_prompt.txt").is_file()
    assert not (run_root / "analysis" / "product_analysis.json").exists()
    assert not (run_root / "review" / "review.html").exists()
    assert not (run_root / "review" / "review_decision.json").exists()


def test_record_decision_cli_writes_and_normalizes_generate_rank_1(tmp_path):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    declare_scene_output_role(run_root)

    assert (
        main(
            [
                "record-decision",
                "--run-root",
                str(run_root),
                "--action",
                "generate_rank_1",
                "--fidelity-confirmed",
                "--output-role",
                "hand_worn",
            ]
        )
        == 0
    )

    assert read_json(run_root / "review" / "review_decision.json") == {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
        "output_role": "hand_worn",
    }


def test_record_decision_cli_returns_nonzero_for_invalid_selected_rank(tmp_path):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    declare_scene_output_role(run_root)

    assert (
        main(
            [
                "record-decision",
                "--run-root",
                str(run_root),
                "--action",
                "generate_selected",
                "--selected-ranks",
                "abc",
                "--output-role",
                "hand_worn",
            ]
        )
        != 0
    )

    assert not (run_root / "review" / "review_decision.json").exists()


def test_record_decision_cli_rejects_generate_rank_1_with_rank_2(tmp_path):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    declare_scene_output_role(run_root)

    assert (
        main(
            [
                "record-decision",
                "--run-root",
                str(run_root),
                "--action",
                "generate_rank_1",
                "--selected-ranks",
                "2",
                "--fidelity-confirmed",
                "--output-role",
                "hand_worn",
            ]
        )
        != 0
    )

    assert not (run_root / "review" / "review_decision.json").exists()


def test_record_decision_cli_rejects_duplicate_selected_ranks(tmp_path):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    declare_scene_output_role(run_root)

    assert (
        main(
            [
                "record-decision",
                "--run-root",
                str(run_root),
                "--action",
                "generate_multiple",
                "--selected-ranks",
                "1",
                "--selected-ranks",
                "1",
                "--fidelity-confirmed",
                "--output-role",
                "hand_worn",
            ]
        )
        != 0
    )

    assert not (run_root / "review" / "review_decision.json").exists()


def test_qc_cli_writes_qc_json(tmp_path):
    from jewelry_on_hand.cli import main

    generation_dir = tmp_path / "runs" / "demo" / "generation" / "01"

    assert (
        main(
            [
                "qc",
                "--generation-dir",
                str(generation_dir),
                "--status",
                "rerun",
                "--passed",
                "无水印,构图正确",
                "--failed",
                "主珠被裁切",
                "--notes",
                "复跑",
            ]
        )
        == 0
    )

    assert read_json(generation_dir / "qc.json") == {
        "status": "rerun",
        "passed": ["无水印", "构图正确"],
        "failed": ["主珠被裁切"],
        "notes": "复跑",
        "fidelity_checks": [],
    }


def test_qc_cli_writes_fidelity_checks_from_json(tmp_path):
    from jewelry_on_hand.cli import main

    generation_dir = tmp_path / "runs" / "demo" / "generation" / "01"
    checks_json = tmp_path / "fidelity-checks.json"
    write_json(
        checks_json,
        [
            {
                "name": "白水晶随形",
                "question": "白水晶随形是否仍是不规则透明异形珠",
                "result": "fail",
                "notes": "变成圆珠",
            }
        ],
    )

    assert (
        main(
            [
                "qc",
                "--generation-dir",
                str(generation_dir),
                "--status",
                "rerun",
                "--failed",
                "关键识别点失败",
                "--fidelity-checks-json",
                str(checks_json),
            ]
        )
        == 0
    )

    assert read_json(generation_dir / "qc.json")["fidelity_checks"][0]["result"] == "fail"


def test_generate_cli_builds_prompts_after_review_gate(tmp_path, monkeypatch):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    product = input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    write_json(
        analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "wear_position": "手腕",
            "visible_appearance": "深红主珠",
            "color_family": ["深红"],
            "style_mood": "暗调闪光",
            "composition": "手腕近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": ["保留主珠"],
        },
    )
    write_json(
        analysis_dir / "selected_references.json",
        [
            {
                "selected_reference": str(ref),
                "score": 80,
                "rank": 1,
                "reason": ["匹配"],
                "risk": [],
                "ignored_reference_jewelry": [],
                "metadata": {
                    "序号": 1,
                    "文件名": "ref.jpg",
                    "用途分类": "上手姿势/手模构图参考",
                    "风格分类": "暗调闪光",
                    "场景关键词": "车内 闪光",
                    "饰品类型": "手链/手串",
                    "推荐使用方式": "近景手腕",
                    "备注": "手腕/前臂露出面积足",
                    "判断置信度": "高",
                },
            }
        ],
    )
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    declare_scene_output_role(run_root)
    write_json(review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True, "output_role": "hand_worn"})
    calls = []

    def fake_run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True):
        calls.append((paths, product_image, prompts_by_rank, helper_script, wait))
        return [paths.generation_dir / "01"]

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert (
        main(
            [
                "generate",
                "--run-root",
                str(run_root),
                "--helper-script",
                str(tmp_path / "helper.py"),
                "--no-wait",
            ]
        )
        == 0
    )

    assert len(calls) == 1
    assert calls[0][1] == product
    assert list(calls[0][2]) == [1]
    assert "内部图1" in calls[0][2][1]
    assert calls[0][4] is False


def test_generate_cli_accepts_selected_reference_without_metadata(tmp_path, monkeypatch):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    product = input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    write_json(
        analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "wear_position": "手腕",
            "visible_appearance": "深红主珠",
            "color_family": ["深红"],
            "style_mood": "暗调闪光",
            "composition": "手腕近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": ["保留主珠"],
        },
    )
    write_json(
        analysis_dir / "selected_references.json",
        [
            {
                "selected_reference": str(ref),
                "score": 80,
                "rank": 2,
                "reason": ["匹配"],
                "risk": [],
                "ignored_reference_jewelry": [],
            }
        ],
    )
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    declare_scene_output_role(run_root)
    write_json(review_dir / "review_decision.json", {"action": "generate_selected", "selected_ranks": [2], "fidelity_confirmed": True, "output_role": "hand_worn"})
    calls = []

    def fake_run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True):
        calls.append((paths, product_image, prompts_by_rank, helper_script, wait))
        return [paths.generation_dir / "02"]

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert (
        main(
            [
                "generate",
                "--run-root",
                str(run_root),
                "--helper-script",
                str(tmp_path / "helper.py"),
            ]
        )
        == 0
    )

    assert len(calls) == 1
    assert list(calls[0][2]) == [2]
    assert "ref.jpg" in calls[0][2][2]


def test_generate_cli_only_builds_prompts_for_approved_selected_ranks(tmp_path, monkeypatch):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    product = input_dir / "product-on-hand.jpg"
    product.write_bytes(b"product")
    references = []
    for rank in (1, 2, 3):
        ref = tmp_path / f"ref{rank}.jpg"
        ref.write_bytes(f"ref-{rank}".encode())
        references.append(
            {
                "selected_reference": str(ref),
                "score": 80 + rank,
                "rank": rank,
                "reason": [f"匹配 {rank}"],
                "risk": [],
                "ignored_reference_jewelry": [],
            }
        )
    write_json(
        analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "wear_position": "手腕",
            "visible_appearance": "深红主珠",
            "color_family": ["深红"],
            "style_mood": "暗调闪光",
            "composition": "手腕近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": ["保留主珠"],
        },
    )
    write_json(analysis_dir / "selected_references.json", references)
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    declare_scene_output_role(run_root)
    write_json(review_dir / "review_decision.json", {"action": "generate_selected", "selected_ranks": [2], "fidelity_confirmed": True, "output_role": "hand_worn"})
    built_ranks = []
    calls = []

    def fake_build_prompt(
        product_analysis,
        scored_reference,
        fidelity_constraints,
        *,
        output_role,
    ):
        assert fidelity_constraints.review_status == "confirmed"
        assert output_role.value == "hand_worn"
        built_ranks.append(scored_reference.rank)
        return f"prompt-rank-{scored_reference.rank}"

    def fake_run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True):
        calls.append((paths, product_image, prompts_by_rank, helper_script, wait))
        return [paths.generation_dir / "02"]

    monkeypatch.setattr("jewelry_on_hand.cli.build_prompt", fake_build_prompt)
    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert main(["generate", "--run-root", str(run_root), "--helper-script", str(tmp_path / "helper.py")]) == 0

    assert built_ranks == [2]
    assert len(calls) == 1
    assert list(calls[0][2]) == [2]
    assert calls[0][2] == {2: "prompt-rank-2"}


def test_generate_cli_returns_nonzero_when_decision_rank_is_missing(tmp_path, monkeypatch):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    (input_dir / "product-on-hand.jpg").write_bytes(b"product")
    references = []
    for rank in (1, 2):
        ref = tmp_path / f"ref{rank}.jpg"
        ref.write_bytes(f"ref-{rank}".encode())
        references.append(
            {
                "selected_reference": str(ref),
                "score": 80 + rank,
                "rank": rank,
                "reason": [f"匹配 {rank}"],
                "risk": [],
                "ignored_reference_jewelry": [],
            }
        )
    write_json(
        analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "wear_position": "手腕",
            "visible_appearance": "深红主珠",
            "color_family": ["深红"],
            "style_mood": "暗调闪光",
            "composition": "手腕近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": ["保留主珠"],
        },
    )
    write_json(analysis_dir / "selected_references.json", references)
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    declare_scene_output_role(run_root)
    write_json(review_dir / "review_decision.json", {"action": "generate_selected", "selected_ranks": [3], "fidelity_confirmed": True, "output_role": "hand_worn"})
    calls = []

    def fake_run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True):
        calls.append((paths, product_image, prompts_by_rank, helper_script, wait))
        return []

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert main(["generate", "--run-root", str(run_root), "--helper-script", str(tmp_path / "helper.py")]) != 0
    assert calls == []


def test_generate_cli_reruns_supported_product_gate_before_generation(tmp_path, monkeypatch):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "demo"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    (input_dir / "product-on-hand.jpg").write_bytes(b"product")
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(b"ref")
    analysis = make_analysis(analysis_dir / "product_analysis.json")
    analysis["product_type"] = "戒指"
    write_json(analysis_dir / "product_analysis.json", analysis)
    write_json(analysis_dir / "selected_references.json", [_selected_reference_payload(1, ref)])
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    declare_scene_output_role(run_root)
    write_json(review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True, "output_role": "hand_worn"})
    calls = []

    def fake_run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True):
        calls.append((paths, product_image, prompts_by_rank, helper_script, wait))
        return []

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert main(["generate", "--run-root", str(run_root), "--helper-script", str(tmp_path / "helper.py")]) != 0
    assert calls == []


def test_generate_cli_preserves_mirror_relative_path_from_review_package(tmp_path, monkeypatch):
    from jewelry_on_hand.cli import main

    paths_root = tmp_path / "runs"
    run_root = paths_root / "demo"
    product = run_root / "input" / "product-on-hand.jpg"
    product.parent.mkdir(parents=True)
    product.write_bytes(b"product")
    paths = RunPaths(root=run_root)
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    paths.review_dir.mkdir(parents=True, exist_ok=True)
    make_analysis(paths.analysis_dir / "product_analysis.json")

    original_ref = tmp_path / "plain.jpg"
    original_ref.write_bytes(b"ref")
    scored = ScoredReference(
        ReferenceRow(
            index=1,
            file_name="plain.jpg",
            relative_path="reference/对镜/plain.jpg",
            absolute_path=original_ref,
            width=100,
            height=200,
            size_mb=0.1,
            purpose_category="上手姿势/手模构图参考",
            bracelet_applicability="是",
            default_strategy="常规可优先使用",
            style_category="暗调闪光",
            scene_keywords="车内",
            jewelry_type="手链/手串",
            recommended_usage="近景",
            notes="手腕露出",
            confidence="高",
            file_exists=True,
        ),
        score=99,
        rank=1,
        reason=["匹配"],
        risk=[],
        ignored_reference_jewelry=[],
    )
    scored = ScoredReference(
        ReferenceRow(
            **{
                **scored.row.__dict__,
                "framing": "对镜近景",
                "visible_body_regions": "左手腕 / 前臂",
                "product_visibility": "展示面积充足",
                "collar_type": "无衣领",
                "clothing_occlusion_risk": "衣物无遮挡",
                "pose_keywords": "身体在镜中，前臂自然抬起",
                "existing_jewelry": "左手腕原有手链",
                "crop_risk": "裁切风险低",
                "hand_side": "左手",
                "hand_orientation": "手背朝向镜头",
                "notes": "正面视角，主体居中，无文字或 UI",
            }
        ),
        scored.score,
        scored.rank,
        scored.reason,
        scored.risk,
        scored.ignored_reference_jewelry,
    )
    write_review_package(
        paths,
        product,
        [scored],
        [scored],
        composition_snapshots=[
            build_candidate_snapshot(
                load_product_analysis(paths.analysis_dir / "product_analysis.json"),
                scored,
                "hand_worn",
            )
        ],
    )
    make_constraints(paths.analysis_dir / "product_fidelity_constraints.json")
    declare_scene_output_role(run_root)
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1], "fidelity_confirmed": True, "output_role": "hand_worn"})
    calls = []

    def fake_run_generation(paths, product_image, prompts_by_rank, helper_script, wait=True):
        calls.append((paths, product_image, prompts_by_rank, helper_script, wait))
        return [paths.generation_dir / "01"]

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fake_run_generation)

    assert main(["generate", "--run-root", str(run_root), "--helper-script", str(tmp_path / "helper.py")]) == 0

    assert len(calls) == 1
    assert "前景手部 + 镜中反射手部" in calls[0][2][1]


def _selected_reference_payload(rank, path):
    return {
        "selected_reference": str(path),
        "score": 80,
        "rank": rank,
        "reason": ["匹配"],
        "risk": [],
        "ignored_reference_jewelry": [],
        "metadata": {},
    }


def test_准备审核持久化场景输出角色(tmp_path):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, reference)
    analysis = tmp_path / "analysis.json"
    make_analysis(analysis)

    assert main(
        [
            "prepare-review",
            "--product-image",
            str(product),
            "--analysis-json",
            str(analysis),
            "--classification",
            str(catalog),
            "--output-root",
            str(tmp_path / "runs"),
            "--run-id",
            "scene",
            "--output-role",
            "lifestyle",
        ]
    ) == 0

    assert read_json(
        tmp_path / "runs" / "scene" / "analysis" / "output_role.json"
    ) == {"output_role": "lifestyle"}

    run_root = tmp_path / "runs" / "scene"
    assert main(
        [
            "record-decision",
            "--run-root",
            str(run_root),
            "--action",
            "generate_rank_1",
            "--fidelity-confirmed",
            "--output-role",
            "lifestyle",
        ]
    ) == 0
    assert read_json(run_root / "review" / "review_decision.json")[
        "output_role"
    ] == "lifestyle"


def test_准备审核在创建运行目录前拒绝主图角色(tmp_path):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    output_root = tmp_path / "runs"

    assert main(
        [
            "prepare-review",
            "--product-image",
            str(product),
            "--classification",
            str(tmp_path / "unused.xlsx"),
            "--output-root",
            str(output_root),
            "--run-id",
            "hero",
            "--output-role",
            "hero",
        ]
    ) != 0

    assert not (output_root / "hero").exists()


def test_记录决策持久化匹配的输出角色(tmp_path):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "scene"
    write_json(
        run_root / "analysis" / "output_role.json",
        {"output_role": "hand_worn"},
    )

    assert main(
        [
            "record-decision",
            "--run-root",
            str(run_root),
            "--action",
            "generate_rank_1",
            "--fidelity-confirmed",
            "--output-role",
            "hand_worn",
        ]
    ) == 0

    assert read_json(run_root / "review" / "review_decision.json")[
        "output_role"
    ] == "hand_worn"


def test_记录决策拒绝主图且不写决策(
    tmp_path,
    capsys,
):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "scene"
    write_json(
        run_root / "analysis" / "output_role.json",
        {"output_role": "hand_worn"},
    )

    assert main(
        [
            "record-decision",
            "--run-root",
            str(run_root),
            "--action",
            "rerank",
            "--output-role",
            "hero",
        ]
    ) != 0

    assert "主图 Skill" in capsys.readouterr().err
    assert not (run_root / "review" / "review_decision.json").exists()


def test_记录决策角色与运行角色不一致时不写决策(tmp_path, capsys):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "scene"
    write_json(
        run_root / "analysis" / "output_role.json",
        {"output_role": "hand_worn"},
    )

    assert main(
        [
            "record-decision",
            "--run-root",
            str(run_root),
            "--action",
            "rerank",
            "--output-role",
            "lifestyle",
        ]
    ) != 0

    assert "不一致" in capsys.readouterr().err
    assert not (run_root / "review" / "review_decision.json").exists()


def test_生成在调用助手前拒绝主图角色(
    tmp_path,
    monkeypatch,
    capsys,
):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "hero"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    (input_dir / "product-on-hand.jpg").write_bytes(b"product")
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    make_analysis(analysis_dir / "product_analysis.json")
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    write_json(
        analysis_dir / "selected_references.json",
        [_selected_reference_payload(1, reference)],
    )
    write_json(analysis_dir / "output_role.json", {"output_role": "hero"})
    write_json(
        review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "output_role": "hero",
        },
    )
    helper_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal helper_called
        helper_called = True
        raise AssertionError("生成 helper 不得被调用")

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fail_if_called)

    assert main(
        [
            "generate",
            "--run-root",
            str(run_root),
            "--helper-script",
            str(tmp_path / "helper.py"),
        ]
    ) != 0

    assert "主图 Skill" in capsys.readouterr().err
    assert helper_called is False


def test_生成时运行角色与决策角色不一致则不调用生成助手(
    tmp_path,
    monkeypatch,
    capsys,
):
    from jewelry_on_hand.cli import main

    run_root = tmp_path / "runs" / "mismatch"
    analysis_dir = run_root / "analysis"
    review_dir = run_root / "review"
    input_dir = run_root / "input"
    analysis_dir.mkdir(parents=True)
    review_dir.mkdir()
    input_dir.mkdir()
    (input_dir / "product-on-hand.jpg").write_bytes(b"product")
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    make_analysis(analysis_dir / "product_analysis.json")
    make_constraints(analysis_dir / "product_fidelity_constraints.json")
    write_json(
        analysis_dir / "selected_references.json",
        [_selected_reference_payload(1, reference)],
    )
    write_json(
        analysis_dir / "output_role.json",
        {"output_role": "hand_worn"},
    )
    write_json(
        review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "output_role": "lifestyle",
        },
    )
    helper_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal helper_called
        helper_called = True
        raise AssertionError("生成 helper 不得被调用")

    monkeypatch.setattr("jewelry_on_hand.cli.run_generation", fail_if_called)

    assert main(
        [
            "generate",
            "--run-root",
            str(run_root),
            "--helper-script",
            str(tmp_path / "helper.py"),
        ]
    ) != 0

    assert "不一致" in capsys.readouterr().err
    assert helper_called is False


def test_准备审核缺少输出角色时失败且不创建决策(tmp_path, capsys):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    output_root = tmp_path / "runs"

    assert main(
        [
            "prepare-review",
            "--product-image",
            str(product),
            "--classification",
            str(tmp_path / "unused.xlsx"),
            "--output-root",
            str(output_root),
            "--run-id",
            "missing-role",
        ]
    ) != 0

    assert "必须显式提供" in capsys.readouterr().err
    assert not (output_root / "missing-role" / "review" / "review_decision.json").exists()


def test_准备审核快照必填字段缺失时失败且不创建决策(tmp_path, capsys):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, reference, snapshot_overrides={"姿势关键词": ""})
    analysis = tmp_path / "analysis.json"
    make_analysis(analysis)
    output_root = tmp_path / "runs"

    assert main(
        [
            "prepare-review",
            "--product-image",
            str(product),
            "--analysis-json",
            str(analysis),
            "--classification",
            str(catalog),
            "--output-root",
            str(output_root),
            "--run-id",
            "missing-field",
            "--output-role",
            "hand_worn",
        ]
    ) != 0

    assert "pose_keywords" in capsys.readouterr().err
    assert not (
        output_root / "missing-field" / "review" / "review_decision.json"
    ).exists()


def test_批量重排加载各运行角色并清除旧快照后重建审核包(tmp_path):
    from jewelry_on_hand.cli import main

    product = tmp_path / "product.jpg"
    product.write_bytes(b"product")
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"reference")
    catalog = tmp_path / "catalog.xlsx"
    make_catalog(catalog, reference)
    analysis = tmp_path / "analysis.json"
    make_analysis(analysis)
    output_root = tmp_path / "runs"

    for run_id, output_role in (("hand", "hand_worn"), ("life", "lifestyle")):
        assert main(
            [
                "prepare-review",
                "--product-image",
                str(product),
                "--analysis-json",
                str(analysis),
                "--classification",
                str(catalog),
                "--output-root",
                str(output_root),
                "--run-id",
                run_id,
                "--output-role",
                output_role,
            ]
        ) == 0
        run_root = output_root / run_id
        write_json(
            run_root / "analysis" / "reference_composition_snapshots.json",
            [{"rank": 99, "stale": True}],
        )
        (run_root / "review" / "rank-99-stale.jpg").write_bytes(b"stale")

    assert main(
        [
            "rerank-batch",
            "--output-root",
            str(output_root),
            "--run-id",
            "hand",
            "--run-id",
            "life",
        ]
    ) == 0

    for run_id, expected_role in (("hand", "hand_worn"), ("life", "lifestyle")):
        run_root = output_root / run_id
        selected = read_json(run_root / "analysis" / "selected_references.json")
        snapshots = read_json(
            run_root / "analysis" / "reference_composition_snapshots.json"
        )
        assert len(selected) == len(snapshots) == 3
        assert {item["rank"] for item in snapshots} == {
            item["rank"] for item in selected
        }
        assert {item["output_role"] for item in snapshots} == {expected_role}
        assert not (run_root / "review" / "rank-99-stale.jpg").exists()
        assert "预计展示面积不足时不要选择" in (
            run_root / "review" / "review.html"
        ).read_text(encoding="utf-8")
        assert not (run_root / "review" / "review_decision.json").exists()
