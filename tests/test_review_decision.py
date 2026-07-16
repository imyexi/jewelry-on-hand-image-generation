from hashlib import sha256
from pathlib import Path

import pytest

import jewelry_on_hand.reference_composition as reference_composition
import jewelry_on_hand.review_decision as review_decision

from jewelry_on_hand.review_decision import (
    ReviewGateError,
    require_generation_decision,
    validate_confirmed_analysis,
    validate_decision_against_analysis,
    write_analysis_and_review_decision,
    write_review_decision,
)
from jewelry_on_hand.models import (
    ProductAnalysis,
    ReferenceRow,
    ReviewDecision,
    ScoredReference,
)
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    build_candidate_snapshot,
    reference_composition_sha256,
)
from jewelry_on_hand.product_fidelity import (
    build_product_fidelity_constraints,
    product_analysis_sha256,
)
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


VALID_REFERENCE_SNAPSHOT_SHA256 = "a" * 64


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


def _constraints_data(review_status="confirmed", must_keep=None, analysis_data=None):
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
    if analysis_data is not None:
        product = ProductAnalysis.from_dict(analysis_data)
        built = build_product_fidelity_constraints(product)
        data = built.to_dict()
        data["review_status"] = (
            review_status if built.must_keep else "not_applicable"
        )
    return data


def _write_confirmed_constraints(paths):
    analysis_path = paths.analysis_dir / "product_analysis.json"
    analysis_data = read_json(analysis_path) if analysis_path.is_file() else None
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        _constraints_data(analysis_data=analysis_data),
    )


def _bracelet_analysis_data():
    return {
        "product_type": "手链/手串",
        "wear_position": "手腕",
        "visible_appearance": "深红主珠手链",
        "color_family": ["深红"],
        "style_mood": "暗调闪光",
        "composition": "手腕近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
    }


def _write_reference_snapshot_artifacts(
    paths,
    source_dir,
    *,
    rank=1,
    output_role="hand_worn",
    analysis_data=None,
):
    (paths.input_dir / "product-on-hand.jpg").write_bytes(b"product-on-hand")
    source = source_dir / f"source-{rank}.jpg"
    source.write_bytes(f"reference-{rank}".encode())
    scored = ScoredReference(
        row=ReferenceRow(
            index=rank,
            file_name=source.name,
            relative_path=source.name,
            absolute_path=source,
            width=100,
            height=200,
            size_mb=0.1,
            purpose_category="手部佩戴图",
            bracelet_applicability="是",
            default_strategy="常规可优先使用",
            style_category="暗调闪光",
            scene_keywords="车内",
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
        ),
        score=99,
        rank=rank,
        reason=("匹配",),
        risk=(),
        ignored_reference_jewelry=("原有手链",),
    )
    if analysis_data is None:
        analysis_data = _bracelet_analysis_data()
    snapshot = build_candidate_snapshot(
        ProductAnalysis.from_dict(analysis_data),
        scored,
        output_role,
    )
    review_copy = paths.review_dir / f"rank-{rank}-{source.name}"
    review_copy.write_bytes(source.read_bytes())
    digest = sha256(source.read_bytes()).hexdigest()
    selected = scored.to_dict()
    selected["selected_reference"] = str(review_copy.resolve())
    selected["source_sha256"] = digest
    selected["review_sha256"] = digest
    selected["metadata"]["source_sha256"] = digest
    selected["metadata"]["review_sha256"] = digest
    write_json(paths.analysis_dir / "product_analysis.json", analysis_data)
    write_json(paths.analysis_dir / "output_role.json", {"output_role": output_role})
    write_json(paths.analysis_dir / "selected_references.json", [selected])
    write_json(
        paths.analysis_dir / "reference_composition_snapshots.json",
        [snapshot.to_dict()],
    )
    _write_confirmed_constraints(paths)
    return snapshot


def _write_完整现代审核_run(tmp_path, run_id="modern-snapshot"):
    paths = RunPaths.create(tmp_path, run_id)
    snapshot = _write_reference_snapshot_artifacts(paths, tmp_path)
    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "output_role": "hand_worn",
        },
    )
    return paths, snapshot


def _write_完整历史_run(tmp_path, run_id="legacy-read-only"):
    paths = RunPaths.create(tmp_path, run_id)
    product = paths.input_dir / "product-on-hand.jpg"
    product.write_bytes(b"legacy-product")
    source = tmp_path / f"{run_id}-source-1.jpg"
    source.write_bytes(b"legacy-reference-1")
    selected_items = []
    for rank in (1, 2, 3):
        ranked_source = source if rank == 1 else tmp_path / f"{run_id}-source-{rank}.jpg"
        if rank != 1:
            ranked_source.write_bytes(f"legacy-reference-{rank}".encode())
        selected = paths.review_dir / f"rank-{rank}-source.jpg"
        selected.write_bytes(ranked_source.read_bytes())
        digest = sha256(ranked_source.read_bytes()).hexdigest()
        selected_items.append(
            {
                "rank": rank,
                "score": 100 - rank,
                "selected_reference": str(selected.resolve()),
                "source_sha256": digest,
                "review_sha256": digest,
                "metadata": {
                    "source_reference": str(ranked_source.resolve()),
                    "source_sha256": digest,
                    "review_sha256": digest,
                },
            }
        )
    write_json(paths.analysis_dir / "product_analysis.json", _bracelet_analysis_data())
    write_json(
        paths.analysis_dir / "selected_references.json",
        selected_items,
    )
    _write_confirmed_constraints(paths)
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
    return paths


def _necklace_analysis_data(**overrides):
    data = {
        "product_type": "带链吊坠",
        "detected_product_type": "pendant_necklace",
        "confirmed_product_type": "pendant_necklace",
        "classification_confidence": "high",
        "classification_evidence": ["中央存在主吊坠"],
        "classification_source": "auto_confirmed",
        "display_mode": "worn",
        "source_image_type": "worn_source",
        "wear_position": "颈部和锁骨",
        "visible_appearance": "双层珠链，第二层中央有吊坠",
        "color_family": ["白色"],
        "style_mood": "精致",
        "composition": "胸前近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
        "layer_count": 2,
        "length_category": "collarbone",
        "chain_or_strand_type": "beaded",
        "has_pendant": True,
        "pendant_count": 1,
        "pendant_layer": 2,
        "pendant_position": "front_center",
        "pendant_orientation": "front_facing",
        "connection_structure": "metal_bail",
        "symmetry": "approximately_symmetric",
        "occluded_parts": ["后颈扣头"],
        "uncertain_details": ["扣头具体结构"],
        "is_independent_multi_item": False,
    }
    data.update(overrides)
    return data


def _confirmation_snapshot(**overrides):
    data = {
        "confirmed_product_type": "pendant_necklace",
        "source_image_type": "worn_source",
        "display_mode": "worn",
        "layer_count": 2,
        "length_category": "collarbone",
        "has_pendant": True,
        "pendant_count": 1,
        "pendant_layer": 2,
        "pendant_position": "front_center",
        "pendant_orientation": "front_facing",
        "connection_structure": "metal_bail",
        "is_independent_multi_item": False,
    }
    data.update(overrides)
    return data


def _ring_analysis_data(**overrides):
    data = _necklace_analysis_data(
        product_type="戒指",
        detected_product_type="ring",
        confirmed_product_type="ring",
        classification_evidence=["左手无名指根部可见单枚戒指"],
        wear_position="左手无名指根部",
        visible_appearance="单枚银色戒指",
        composition="手部近景",
        layer_count=1,
        length_category=None,
        chain_or_strand_type=None,
        has_pendant=False,
        pendant_count=0,
        pendant_layer=None,
        pendant_position=None,
        pendant_orientation=None,
        connection_structure=None,
        symmetry=None,
        occluded_parts=["戒圈背面"],
        uncertain_details=["戒圈背面结构"],
        ring_count=1,
        hand_side="left",
        finger_position="ring",
        ring_wear_style="finger_base",
    )
    data.update(overrides)
    return data


def _ring_confirmation_snapshot(**overrides):
    data = _confirmation_snapshot(
        confirmed_product_type="ring",
        layer_count=1,
        length_category=None,
        has_pendant=False,
        pendant_count=0,
        pendant_layer=None,
        pendant_position=None,
        pendant_orientation=None,
        connection_structure=None,
        ring_count=1,
        hand_side="left",
        finger_position="ring",
        ring_wear_style="finger_base",
    )
    data.update(overrides)
    return data


def _ring_fidelity_analysis_data(**overrides):
    data = _ring_analysis_data(
        visible_appearance=(
            "单枚银色开口戒，椭圆戒面中央有透明圆形主石，两个开口端点装饰对称"
        ),
        color_family=["银色", "透明"],
        special_requirements=["保持主石竖向朝向", "保留开口端点装饰排列"],
        occluded_parts=["指腹遮挡的左侧戒圈"],
        uncertain_details=["左侧镶嵌连接方式"],
    )
    data.update(overrides)
    return data


def _ring_fidelity_constraints_data(analysis_data, review_status="confirmed"):
    constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis_data)
    ).to_dict()
    constraints["review_status"] = review_status
    return constraints


def _invalidate_ring_constraints(payload, invalid_kind):
    if invalid_kind == "empty":
        payload["must_keep"] = []
    elif invalid_kind == "not_applicable":
        payload["must_keep"] = []
        payload["review_status"] = "not_applicable"
    elif invalid_kind == "bracelet_semantics":
        payload["must_not_change"].extend(["珠子排列顺序", "主珠和配件位置关系"])
    elif invalid_kind == "visible_appearance":
        payload["must_keep"] = [
            item
            for item in payload["must_keep"]
            if item["normalized_keyword"] != "戒指整体可见结构"
        ]
    elif invalid_kind == "color_family":
        color_item = next(
            item
            for item in payload["must_keep"]
            if item["normalized_keyword"] == "戒指可见颜色与材质表现"
        )
        color_item["source_text"] = "可见描述存在，但缺少分析中的颜色"
    elif invalid_kind == "special_requirements":
        payload["must_keep"] = [
            item
            for item in payload["must_keep"]
            if item["source_text"] != "保留开口端点装饰排列"
        ]
    elif invalid_kind == "special_visual_shape":
        item = next(
            item
            for item in payload["must_keep"]
            if item["source_text"] == "保持主石竖向朝向"
        )
        item["visual_shape"] = "按产品图肉眼可见事实核对"
    elif invalid_kind == "special_forbid":
        item = next(
            item
            for item in payload["must_keep"]
            if item["source_text"] == "保持主石竖向朝向"
        )
        item["forbid"] = ["不得改成通用款式"]
    elif invalid_kind == "special_qc_question":
        item = next(
            item
            for item in payload["must_keep"]
            if item["source_text"] == "保持主石竖向朝向"
        )
        item["qc_question"] = "该产品特定要求是否正确？"
    elif invalid_kind == "occluded_parts":
        payload["must_not_change"] = [
            item for item in payload["must_not_change"] if "指腹遮挡的左侧戒圈" not in item
        ]
    elif invalid_kind == "uncertain_details":
        payload["must_not_change"] = [
            item for item in payload["must_not_change"] if "左侧镶嵌连接方式" not in item
        ]
    else:
        raise AssertionError(f"未知测试类型：{invalid_kind}")
    return payload


def _ring_source_text_semantic_bypass(review_status="confirmed"):
    safe_analysis = _ring_fidelity_analysis_data(
        special_requirements=["保持主石竖向朝向"]
    )
    payload = _ring_fidelity_constraints_data(safe_analysis, review_status)
    analysis_data = dict(safe_analysis)
    analysis_data["special_requirements"] = ["主珠和配件位置关系"]
    payload["source"]["product_analysis_sha256"] = product_analysis_sha256(
        ProductAnalysis.from_dict(analysis_data)
    )
    item = next(
        item
        for item in payload["must_keep"]
        if item["normalized_keyword"] == "戒指产品特定要求"
    )
    item.update(
        {
            "source_text": "主珠和配件位置关系",
            "visual_shape": "按产品图肉眼可见事实核对该局部要求",
            "relationship": "保持该局部要求与戒指可见结构的原有关系",
            "forbid": ["不得改成通用戒指款式"],
            "qc_question": "该局部要求的可见事实是否保持一致？",
        }
    )
    return analysis_data, payload


def test_generation_requires_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    with pytest.raises(ReviewGateError, match="review_decision.json"):
        require_generation_decision(paths)


@pytest.mark.parametrize(
    ("action", "selected_ranks"),
    [
        ("generate_rank_1", [1]),
        ("generate_selected", [2]),
        ("generate_multiple", [1, 2]),
    ],
)
def test_generation_gate_requires_reference_snapshot_digest_for_every_generation_action(
    tmp_path,
    action,
    selected_ranks,
):
    paths = RunPaths.create(tmp_path, f"missing-digest-{action}")
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": action,
            "selected_ranks": selected_ranks,
            "fidelity_confirmed": True,
        },
    )

    with pytest.raises(
        ReviewGateError,
        match="reference_snapshot_sha256.*prepare-review|确认快照.*prepare-review",
    ):
        require_generation_decision(paths)


@pytest.mark.parametrize(
    "invalid_digest",
    [None, "", 123, "A" * 64, "g" * 64, "a" * 63, "a" * 65],
)
def test_generation_gate_rejects_every_invalid_reference_snapshot_digest(
    tmp_path,
    invalid_digest,
):
    paths = RunPaths.create(tmp_path, "invalid-digest")
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "reference_snapshot_sha256": invalid_digest,
        },
    )

    with pytest.raises(
        ReviewGateError,
        match="reference_snapshot_sha256.*prepare-review|确认快照.*prepare-review",
    ):
        require_generation_decision(paths)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"action": "rerank"}, "rerank"),
        (
            {"action": "manual_reference", "manual_reference": "manual.jpg"},
            "manual_reference",
        ),
    ],
)
def test_generation_gate_keeps_non_generation_action_error_without_digest(
    tmp_path,
    payload,
    message,
):
    paths = RunPaths.create(tmp_path, "non-generation")
    write_json(paths.review_dir / "review_decision.json", payload)

    with pytest.raises(ReviewGateError, match=message):
        require_generation_decision(paths)


def test_legacy_generation_decision_remains_available_for_read_only_audit():
    legacy = ReviewDecision.from_dict(
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
        }
    )

    assert legacy.reference_snapshot_sha256 is None


def test_writer_reuses_review_decision_model_serialization_boundary(
    tmp_path,
    monkeypatch,
):
    paths = RunPaths.create(tmp_path, "model-serialization")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    calls = []
    original_to_dict = ReviewDecision.to_dict

    def track_to_dict(decision):
        calls.append(decision)
        return original_to_dict(decision)

    monkeypatch.setattr(ReviewDecision, "to_dict", track_to_dict)

    write_review_decision(paths, {"action": "rerank"})

    assert len(calls) == 1
    assert not hasattr(review_decision, "_decision_to_dict")


@pytest.mark.parametrize(
    ("action", "ranks"),
    [
        ("generate_rank_1", [1]),
        ("generate_selected", [2]),
        ("generate_multiple", [1, 2]),
    ],
)
def test_旧公开写接口拒绝创建无确认参考快照的新生成决策(
    tmp_path,
    action,
    ranks,
):
    paths = RunPaths.create(tmp_path, f"run-old-writer-{action}")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    decision_data = {
        "action": action,
        "selected_ranks": ranks,
        "fidelity_confirmed": True,
    }

    with pytest.raises(ReviewGateError, match="旧写入接口.*write_review_bundle"):
        write_review_decision(paths, decision_data)
    with pytest.raises(ReviewGateError, match="旧写入接口.*write_review_bundle"):
        write_analysis_and_review_decision(
            paths,
            _bracelet_analysis_data(),
            decision_data,
        )

    assert not (paths.review_dir / "review_decision.json").exists()


def test_历史生成决策仍可读取(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_selected",
            "selected_ranks": [2],
            "fidelity_confirmed": True,
        },
    )
    legacy = ReviewDecision.from_dict(
        read_json(paths.review_dir / "review_decision.json")
    )
    assert legacy.selected_ranks == [2]
    with pytest.raises(ReviewGateError, match="prepare-review"):
        require_generation_decision(paths)


def test_generation_rejects_rerank_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    write_review_decision(paths, {"action": "rerank"})

    with pytest.raises(ReviewGateError, match="rerank"):
        require_generation_decision(paths)


def test_generation_rejects_manual_reference_decision(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    write_review_decision(paths, {"action": "manual_reference", "manual_reference": "manual.jpg"})

    with pytest.raises(ReviewGateError, match="manual_reference"):
        require_generation_decision(paths)


def test_read_decision_wraps_malformed_json(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    decision_path = paths.review_dir / "review_decision.json"
    decision_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ReviewGateError, match="review_decision.json") as exc_info:
        require_generation_decision(paths)

    assert str(decision_path) in str(exc_info.value)


def test_read_decision_wraps_persisted_invalid_action(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    decision_path = paths.review_dir / "review_decision.json"
    write_json(decision_path, {"action": "bad"})

    with pytest.raises(ReviewGateError, match="review_decision.json") as exc_info:
        require_generation_decision(paths)

    assert str(decision_path) in str(exc_info.value)


def test_read_decision_wraps_persisted_invalid_fields(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    decision_path = paths.review_dir / "review_decision.json"
    write_json(decision_path, {"action": "generate_selected"})

    with pytest.raises(ReviewGateError, match="review_decision.json") as exc_info:
        require_generation_decision(paths)

    assert str(decision_path) in str(exc_info.value)


def test_require_generation_decision_rejects_missing_fidelity_confirmation(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_confirmed_constraints(paths)
    write_json(paths.review_dir / "review_decision.json", {"action": "generate_rank_1", "selected_ranks": [1]})

    with pytest.raises(ReviewGateError, match="fidelity_confirmed"):
        require_generation_decision(paths)


def test_require_generation_decision_rejects_missing_constraints_file(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
        },
    )

    with pytest.raises(ReviewGateError, match="product_fidelity_constraints.json"):
        require_generation_decision(paths)


def test_require_generation_decision_rejects_pending_constraints(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", _constraints_data(review_status="pending"))
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
        },
    )

    with pytest.raises(ReviewGateError, match="pending"):
        require_generation_decision(paths)


def test_require_generation_decision_rejects_historical_noncanonical_path(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_confirmed_constraints(paths)
    imported_path = paths.review_dir / "historical-constraints.json"
    write_json(imported_path, _constraints_data(review_status="confirmed"))
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "review/historical-constraints.json",
            "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
        },
    )

    with pytest.raises(ReviewGateError, match="非标准.*重新.*record-decision"):
        require_generation_decision(paths)


def test_require_generation_decision_allows_not_applicable_constraints(tmp_path):
    paths, _snapshot = _write_完整现代审核_run(tmp_path, "run-1")
    analysis_data = _bracelet_analysis_data()
    analysis_data["visible_appearance"] = "普通同色圆珠手链"
    write_json(paths.analysis_dir / "product_analysis.json", analysis_data)
    constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis_data)
    ).to_dict()
    assert constraints["review_status"] == "not_applicable"
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", constraints)

    assert require_generation_decision(paths).selected_ranks == [1]


def test_necklace_generation_write_requires_confirmation_snapshot(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    analysis = ProductAnalysis.from_dict(_necklace_analysis_data())
    decision = ReviewDecision.from_dict(
        {"action": "generate_rank_1", "fidelity_confirmed": True}
    )

    with pytest.raises(ReviewGateError, match="确认快照"):
        validate_decision_against_analysis(decision, analysis)


def test_ring_generation_write_requires_confirmation_snapshot(tmp_path):
    analysis = ProductAnalysis.from_dict(_ring_analysis_data())
    decision = ReviewDecision.from_dict(
        {"action": "generate_rank_1", "fidelity_confirmed": True}
    )

    with pytest.raises(ReviewGateError, match="戒指.*确认快照"):
        validate_decision_against_analysis(decision, analysis)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    (
        ("ring_count", 2, "单枚戒指"),
        ("hand_side", "right", "hand_side.*不一致"),
        ("finger_position", "middle", "finger_position.*不一致"),
        ("ring_wear_style", "midi", "常规指根"),
    ),
)
def test_ring_generation_rejects_snapshot_ring_field_mismatch(
    tmp_path, field_name, value, message
):
    analysis = ProductAnalysis.from_dict(_ring_analysis_data())

    with pytest.raises((ReviewGateError, ValueError), match=message):
        decision = ReviewDecision.from_dict(
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "confirmation_snapshot": _ring_confirmation_snapshot(
                    **{field_name: value}
                ),
            }
        )
        validate_decision_against_analysis(decision, analysis)


@pytest.mark.parametrize(
    "missing_field",
    ("ring_count", "hand_side", "finger_position", "ring_wear_style"),
)
def test_ring_generation_rejects_incomplete_confirmation_snapshot(
    tmp_path, missing_field
):
    snapshot = _ring_confirmation_snapshot()
    del snapshot[missing_field]

    with pytest.raises(ValueError, match=missing_field):
        ReviewDecision.from_dict(
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "confirmation_snapshot": snapshot,
            },
        )


def test_ring_generation_accepts_matching_confirmation_snapshot(tmp_path):
    decision = ReviewDecision.from_dict(
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "confirmation_snapshot": _ring_confirmation_snapshot(),
        },
    )

    validate_decision_against_analysis(
        decision,
        ProductAnalysis.from_dict(_ring_analysis_data()),
    )


def test_necklace_snapshot_requires_final_analysis_on_write_and_read(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    payload = {
        "action": "generate_rank_1",
        "selected_ranks": [1],
        "fidelity_confirmed": True,
        "confirmation_snapshot": _confirmation_snapshot(),
        "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
    }

    _write_confirmed_constraints(paths)
    write_json(paths.review_dir / "review_decision.json", payload)
    with pytest.raises(ReviewGateError, match="缺少最终产品分析"):
        require_generation_decision(paths)


def test_necklace_decision_snapshot_roundtrip_and_strict_validation(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    analysis_data = _necklace_analysis_data()
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=analysis_data,
    )

    decision_path = review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "confirmation_snapshot": _confirmation_snapshot(),
            "output_role": "hand_worn",
        },
    )

    assert read_json(decision_path)["confirmation_snapshot"] == _confirmation_snapshot()
    decision = require_generation_decision(paths)
    validate_decision_against_analysis(decision, ProductAnalysis.from_dict(analysis_data))


def test_strict_validation_rejects_snapshot_that_differs_from_final_analysis(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_analysis.json", _necklace_analysis_data())
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
            "confirmation_snapshot": _confirmation_snapshot(layer_count=1, pendant_layer=1),
            "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
        },
    )

    with pytest.raises(ReviewGateError, match="layer_count.*不一致"):
        require_generation_decision(paths)


def test_read_rejects_incomplete_persisted_confirmation_snapshot(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(paths.analysis_dir / "product_analysis.json", _necklace_analysis_data())
    _write_confirmed_constraints(paths)
    snapshot = _confirmation_snapshot()
    del snapshot["pendant_orientation"]
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "confirmation_snapshot": snapshot,
        },
    )

    with pytest.raises(ReviewGateError, match="pendant_orientation"):
        require_generation_decision(paths)


def test_historical_bracelet_generation_without_snapshot_remains_compatible(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(
        paths.analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "wear_position": "手腕",
            "visible_appearance": "红色圆珠",
            "color_family": ["红色"],
            "style_mood": "简洁",
            "composition": "手腕近景",
            "product_dimensions": {},
        },
    )
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
        },
    )

    legacy = ReviewDecision.from_dict(
        read_json(paths.review_dir / "review_decision.json")
    )
    assert legacy.confirmation_snapshot is None
    with pytest.raises(ReviewGateError, match="prepare-review"):
        require_generation_decision(paths)


def test_historical_bracelet_without_snapshot_still_checks_mode_compatibility(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    write_json(
        paths.analysis_dir / "product_analysis.json",
        {
            "product_type": "手链/手串",
            "detected_product_type": "bracelet",
            "confirmed_product_type": "bracelet",
            "classification_confidence": "high",
            "classification_evidence": ["佩戴在手腕"],
            "classification_source": "auto_confirmed",
            "display_mode": "hand_held",
            "source_image_type": "worn_source",
            "wear_position": "手腕",
            "visible_appearance": "红色圆珠",
            "color_family": ["红色"],
            "style_mood": "简洁",
            "composition": "手腕近景",
            "product_dimensions": {},
        },
    )
    _write_confirmed_constraints(paths)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
        },
    )

    with pytest.raises(ReviewGateError, match="手串/手链与手持展示模式不兼容"):
        require_generation_decision(paths)


def test_confirmed_analysis_validation_does_not_depend_on_decision_action():
    analysis = ProductAnalysis.from_dict(
        _necklace_analysis_data(source_image_type="flat_lay_source")
    )

    with pytest.raises(ReviewGateError, match="第一阶段只接受真人佩戴原图"):
        validate_confirmed_analysis(analysis)


def test_pair_write_updates_analysis_and_decision_together(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    analysis_data = _necklace_analysis_data()
    decision_data = {
        "action": "rerank",
        "confirmation_snapshot": _confirmation_snapshot(),
    }

    decision_path = write_analysis_and_review_decision(
        paths,
        analysis_data,
        decision_data,
    )

    assert read_json(paths.analysis_dir / "product_analysis.json") == analysis_data
    assert decision_path == paths.review_dir / "review_decision.json"
    assert read_json(decision_path)["confirmation_snapshot"] == _confirmation_snapshot()


def test_pair_write_rolls_back_both_files_when_second_replace_fails(tmp_path, monkeypatch):
    import os

    paths = RunPaths.create(tmp_path, "run-1")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    write_review_decision(paths, {"action": "rerank"})
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    old_analysis = analysis_path.read_bytes()
    old_decision = decision_path.read_bytes()
    original_replace = os.replace
    replace_count = 0

    def fail_second_replace(source, target):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("模拟第二次替换失败")
        return original_replace(source, target)

    monkeypatch.setattr("jewelry_on_hand.review_decision.os.replace", fail_second_replace)

    with pytest.raises(ReviewGateError, match="2 文件提交失败.*模拟第二次替换失败"):
        write_analysis_and_review_decision(
            paths,
            _necklace_analysis_data(),
            {
                "action": "rerank",
                "confirmation_snapshot": _confirmation_snapshot(),
            },
        )

    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert not list(paths.analysis_dir.glob("*.tmp"))
    assert not list(paths.review_dir.glob("*.tmp"))


def test_review_bundle_imports_pending_constraints_to_canonical_and_confirms(tmp_path):
    paths = RunPaths.create(tmp_path, "run-1")
    imported_path = paths.review_dir / "imported-constraints.json"
    analysis_data = _necklace_analysis_data()
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=analysis_data,
    )
    write_json(
        imported_path,
        _constraints_data(review_status="pending", analysis_data=analysis_data),
    )

    decision_path = review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "review/imported-constraints.json",
            "confirmation_snapshot": _confirmation_snapshot(),
            "output_role": "hand_worn",
        },
    )

    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    assert read_json(canonical_path)["review_status"] == "confirmed"
    assert read_json(imported_path)["review_status"] == "pending"
    assert read_json(decision_path)["fidelity_constraints_path"] == (
        "analysis/product_fidelity_constraints.json"
    )


def test_necklace_review_bundle_rejects_v1_before_any_replace(
    tmp_path,
    monkeypatch,
) -> None:
    paths = RunPaths.create(tmp_path, "necklace-v1-rejected")
    analysis_data = _necklace_analysis_data()
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    write_json(analysis_path, analysis_data)
    decision_path.write_bytes(b'{"old_decision": true}\n')
    canonical_path.write_bytes(b'{"old_constraints": true}\n')
    old_analysis = analysis_path.read_bytes()
    old_decision = decision_path.read_bytes()
    old_constraints = canonical_path.read_bytes()
    imported_path = paths.review_dir / "legacy-v1-constraints.json"
    legacy = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis_data)
    ).to_dict()
    legacy["schema_version"] = 1
    legacy.pop("pendant_semantics")
    legacy["review_status"] = "pending"
    write_json(imported_path, legacy)
    decision_data = {
        "action": "generate_rank_1",
        "fidelity_confirmed": True,
        "fidelity_constraints_path": "review/legacy-v1-constraints.json",
        "confirmation_snapshot": _confirmation_snapshot(),
    }
    replaced: list[object] = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda *args: replaced.append(args),
    )

    with pytest.raises(ReviewGateError, match="历史 v1 只读.*prepare-review"):
        review_decision.write_review_bundle(paths, decision_data)

    assert replaced == []
    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints


def test_necklace_review_bundle_rejects_conflicting_v2_before_any_replace(
    tmp_path,
    monkeypatch,
) -> None:
    paths = RunPaths.create(tmp_path, "necklace-v2-conflict-rejected")
    analysis_data = _necklace_analysis_data()
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    write_json(analysis_path, analysis_data)
    decision_path.write_bytes(b'{"old_decision": true}\n')
    canonical_path.write_bytes(b'{"old_constraints": true}\n')
    old_analysis = analysis_path.read_bytes()
    old_decision = decision_path.read_bytes()
    old_constraints = canonical_path.read_bytes()
    imported_path = paths.review_dir / "conflicting-v2-constraints.json"
    conflicting = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(analysis_data)
    ).to_dict()
    conflicting["pendant_semantics"]["layer"] = 1
    conflicting["review_status"] = "pending"
    write_json(imported_path, conflicting)
    replace_calls: list[object] = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda *args: replace_calls.append(args),
    )

    with pytest.raises(ReviewGateError, match="吊坠结构冲突"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
            },
        )

    assert replace_calls == []
    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints


@pytest.mark.parametrize("review_status", ["confirmed", "corrected"])
def test_review_bundle_preserves_already_reviewed_constraint_status(
    tmp_path,
    review_status,
):
    paths = RunPaths.create(tmp_path, f"run-{review_status}")
    analysis_data = _necklace_analysis_data()
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=analysis_data,
    )
    imported_path = paths.review_dir / "imported-constraints.json"
    write_json(
        imported_path,
        _constraints_data(
            review_status=review_status,
            analysis_data=analysis_data,
        ),
    )

    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "fidelity_constraints_path": str(imported_path),
            "confirmation_snapshot": _confirmation_snapshot(),
            "output_role": "hand_worn",
        },
    )

    canonical = read_json(paths.analysis_dir / "product_fidelity_constraints.json")
    assert canonical["review_status"] == review_status


def test_review_bundle_rejects_non_ring_constraints_from_another_sku_before_replace(
    tmp_path,
    monkeypatch,
):
    paths = RunPaths.create(tmp_path, "cross-sku-necklace")
    final_analysis = _necklace_analysis_data(
        visible_appearance="本 SKU 双层白色珠链，第二层中央水滴吊坠"
    )
    other_analysis = _necklace_analysis_data(
        visible_appearance="另一 SKU 单层黑色金属链，中央圆牌吊坠"
    )
    imported = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(other_analysis)
    ).to_dict()
    imported_path = paths.review_dir / "other-sku-constraints.json"
    write_json(imported_path, imported)
    replace_calls = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda source, target: replace_calls.append((source, target)),
    )

    with pytest.raises(ReviewGateError, match="product_analysis_sha256.*不一致"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
            },
            analysis_data=final_analysis,
        )

    assert replace_calls == []


def test_review_bundle_rejects_bracelet_semantics_imported_into_necklace(
    tmp_path,
):
    paths = RunPaths.create(tmp_path, "cross-category-necklace")
    final_analysis = _necklace_analysis_data()
    bracelet_analysis = ProductAnalysis.from_dict(
        {
            "product_type": "手串",
            "wear_position": "手腕",
            "visible_appearance": "深红圆珠手串",
            "color_family": ["深红"],
            "style_mood": "自然",
            "composition": "手腕近景",
            "product_dimensions": {},
            "needs_full_front_display": True,
            "special_requirements": [],
        }
    )
    imported = build_product_fidelity_constraints(bracelet_analysis).to_dict()
    final_constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(final_analysis)
    )
    imported["schema_version"] = final_constraints.schema_version
    imported["pendant_semantics"] = final_constraints.pendant_semantics.to_dict()
    imported["must_keep"].extend(
        item.to_dict()
        for item in final_constraints.must_keep
        if item.normalized_keyword == "吊坠"
    )
    imported["review_status"] = "pending"
    imported["source"]["product_analysis_sha256"] = final_constraints.source[
        "product_analysis_sha256"
    ]
    imported_path = paths.review_dir / "bracelet-constraints.json"
    write_json(imported_path, imported)

    with pytest.raises(ReviewGateError, match="source.product_type|项链.*手串语义"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
            },
            analysis_data=final_analysis,
        )


def test_review_bundle_rejects_default_canonical_when_product_category_changes(
    tmp_path,
):
    paths = RunPaths.create(tmp_path, "bracelet-to-necklace-default")
    old_analysis = {
        "product_type": "手串",
        "wear_position": "手腕",
        "visible_appearance": "深红圆珠手串",
        "color_family": ["深红"],
        "style_mood": "自然",
        "composition": "手腕近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
    }
    write_json(paths.analysis_dir / "product_analysis.json", old_analysis)
    old_constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(old_analysis)
    ).to_dict()
    old_constraints["review_status"] = "corrected"
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        old_constraints,
    )
    final_analysis = _necklace_analysis_data()

    with pytest.raises(ReviewGateError, match="品类.*变化.*fidelity-constraints-path"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "confirmation_snapshot": _confirmation_snapshot(),
            },
            analysis_data=final_analysis,
        )

    assert read_json(paths.analysis_dir / "product_analysis.json") == old_analysis
    assert read_json(
        paths.analysis_dir / "product_fidelity_constraints.json"
    ) == old_constraints


def test_review_bundle_accepts_category_change_with_explicit_final_constraints(
    tmp_path,
):
    paths = RunPaths.create(tmp_path, "bracelet-to-necklace-explicit")
    old_analysis = {
        "product_type": "手串",
        "wear_position": "手腕",
        "visible_appearance": "深红圆珠手串",
        "color_family": ["深红"],
        "style_mood": "自然",
        "composition": "手腕近景",
        "product_dimensions": {},
        "needs_full_front_display": True,
        "special_requirements": [],
    }
    write_json(paths.analysis_dir / "product_analysis.json", old_analysis)
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        build_product_fidelity_constraints(
            ProductAnalysis.from_dict(old_analysis)
        ).to_dict(),
    )
    final_analysis = _necklace_analysis_data()
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=final_analysis,
    )
    write_json(paths.analysis_dir / "product_analysis.json", old_analysis)
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        build_product_fidelity_constraints(
            ProductAnalysis.from_dict(old_analysis)
        ).to_dict(),
    )
    imported = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(final_analysis)
    ).to_dict()
    imported_path = paths.review_dir / "final-necklace-constraints.json"
    write_json(imported_path, imported)

    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "fidelity_constraints_path": str(imported_path),
            "confirmation_snapshot": _confirmation_snapshot(),
            "output_role": "hand_worn",
        },
        analysis_data=final_analysis,
    )

    assert read_json(paths.analysis_dir / "product_analysis.json") == final_analysis
    canonical = read_json(
        paths.analysis_dir / "product_fidelity_constraints.json"
    )
    assert canonical["source"]["product_analysis_sha256"] == imported["source"][
        "product_analysis_sha256"
    ]
    assert canonical["must_keep"] == imported["must_keep"]


def test_review_bundle_same_category_correction_preserves_corrected_must_keep(
    tmp_path,
):
    paths = RunPaths.create(tmp_path, "necklace-same-category-correction")
    old_analysis = _necklace_analysis_data(display_mode="worn")
    write_json(paths.analysis_dir / "product_analysis.json", old_analysis)
    constraints = build_product_fidelity_constraints(
        ProductAnalysis.from_dict(old_analysis)
    ).to_dict()
    corrected_items = constraints["must_keep"]
    constraints["review_status"] = "corrected"
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        constraints,
    )
    final_analysis = _necklace_analysis_data(display_mode="hand_held")
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=final_analysis,
    )
    write_json(paths.analysis_dir / "product_analysis.json", old_analysis)
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        constraints,
    )

    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "confirmation_snapshot": _confirmation_snapshot(display_mode="hand_held"),
            "output_role": "hand_worn",
        },
        analysis_data=final_analysis,
    )

    canonical = read_json(
        paths.analysis_dir / "product_fidelity_constraints.json"
    )
    assert canonical["must_keep"] == corrected_items
    assert canonical["review_status"] == "corrected"
    assert canonical["source"]["product_analysis_sha256"] == product_analysis_sha256(
        ProductAnalysis.from_dict(final_analysis)
    )


@pytest.mark.parametrize(
    ("analysis_data", "foreign_text", "message"),
    [
        (_necklace_analysis_data(), "主珠和配珠保持手腕环绕", "canonical.must_keep"),
        (
            {
                "product_type": "手串",
                "wear_position": "手腕",
                "visible_appearance": "深红圆珠手串",
                "color_family": ["深红"],
                "style_mood": "自然",
                "composition": "手腕近景",
                "product_dimensions": {},
                "needs_full_front_display": True,
                "special_requirements": [],
            },
            "项链绕颈并落在锁骨",
            "canonical.must_keep",
        ),
    ],
)
def test_non_ring_constraints_reject_cross_category_semantics_in_must_keep(
    analysis_data,
    foreign_text,
    message,
):
    product = ProductAnalysis.from_dict(analysis_data)
    payload = build_product_fidelity_constraints(product).to_dict()
    payload["must_keep"].append(
        {
            "name": foreign_text,
            "source_text": foreign_text,
            "normalized_keyword": foreign_text,
            "location": foreign_text,
            "visual_shape": foreign_text,
            "relationship": foreign_text,
            "forbid": [foreign_text],
            "qc_question": f"{foreign_text}是否保持？",
        }
    )
    payload["review_status"] = "corrected"
    payload["needs_user_review"] = True
    payload["detail_crop_recommended"] = True

    with pytest.raises(ValueError, match=message):
        review_decision.validate_product_fidelity_constraints(
            product,
            review_decision.ProductFidelityConstraints.from_dict(payload),
        )


@pytest.mark.parametrize("source_kind", ["missing", "malformed"])
def test_review_bundle_validates_constraints_before_any_replace(
    tmp_path,
    monkeypatch,
    source_kind,
):
    paths = RunPaths.create(tmp_path, f"run-{source_kind}")
    analysis_data = _necklace_analysis_data()
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=analysis_data,
    )
    write_review_decision(paths, {"action": "rerank"})
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    old_analysis = analysis_path.read_bytes()
    old_decision = decision_path.read_bytes()
    old_constraints = canonical_path.read_bytes()
    imported_path = paths.review_dir / "imported-constraints.json"
    if source_kind == "malformed":
        write_json(imported_path, {"review_status": "pending"})
    replace_calls = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda source, target: replace_calls.append((source, target)),
    )

    with pytest.raises(ReviewGateError, match="产品保真约束"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
            },
            analysis_data=analysis_data,
        )

    assert replace_calls == []
    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "empty",
        "not_applicable",
        "bracelet_semantics",
        "visible_appearance",
        "color_family",
        "special_requirements",
        "special_visual_shape",
        "special_forbid",
        "special_qc_question",
        "occluded_parts",
        "uncertain_details",
    ],
)
def test_review_bundle_rejects_ring_constraints_not_traceable_to_final_analysis_before_replace(
    tmp_path,
    monkeypatch,
    invalid_kind,
):
    paths = RunPaths.create(tmp_path, f"ring-import-{invalid_kind}")
    analysis_data = _ring_fidelity_analysis_data()
    imported = _invalidate_ring_constraints(
        _ring_fidelity_constraints_data(analysis_data, review_status="pending"),
        invalid_kind,
    )
    imported_path = paths.review_dir / "imported-ring-constraints.json"
    write_json(imported_path, imported)

    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    old_analysis = b'{"old_analysis": true}\n'
    old_decision = b'{"old_decision": true}\n'
    old_constraints = b'{"old_constraints": true}\n'
    analysis_path.write_bytes(old_analysis)
    decision_path.write_bytes(old_decision)
    canonical_path.write_bytes(old_constraints)
    replace_calls = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda source, target: replace_calls.append((source, target)),
    )

    with pytest.raises(ReviewGateError, match="产品保真约束"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _ring_confirmation_snapshot(),
            },
            analysis_data=analysis_data,
        )

    assert replace_calls == []
    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints


def test_review_bundle_rejects_ring_bracelet_semantics_hidden_only_in_source_text_before_replace(
    tmp_path,
    monkeypatch,
):
    paths = RunPaths.create(tmp_path, "ring-import-source-text-semantics")
    analysis_data, imported = _ring_source_text_semantic_bypass(
        review_status="pending"
    )
    imported_path = paths.review_dir / "imported-ring-constraints.json"
    write_json(imported_path, imported)
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    old_analysis = b'{"old_analysis": true}\n'
    old_decision = b'{"old_decision": true}\n'
    old_constraints = b'{"old_constraints": true}\n'
    analysis_path.write_bytes(old_analysis)
    decision_path.write_bytes(old_decision)
    canonical_path.write_bytes(old_constraints)
    replace_calls = []
    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        lambda source, target: replace_calls.append((source, target)),
    )

    with pytest.raises(ReviewGateError, match="产品保真约束|手串语义.*主珠"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _ring_confirmation_snapshot(),
            },
            analysis_data=analysis_data,
        )

    assert replace_calls == []
    assert analysis_path.read_bytes() == old_analysis
    assert decision_path.read_bytes() == old_decision
    assert canonical_path.read_bytes() == old_constraints


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "empty",
        "not_applicable",
        "bracelet_semantics",
        "visible_appearance",
        "color_family",
        "special_requirements",
        "special_visual_shape",
        "special_forbid",
        "special_qc_question",
        "occluded_parts",
        "uncertain_details",
    ],
)
def test_generation_rejects_historical_ring_constraints_that_bypass_import_validation(
    tmp_path,
    invalid_kind,
):
    paths = RunPaths.create(tmp_path, f"ring-generate-{invalid_kind}")
    analysis_data = _ring_fidelity_analysis_data()
    write_json(paths.analysis_dir / "product_analysis.json", analysis_data)
    write_json(
        paths.review_dir / "review_decision.json",
        {
            "action": "generate_rank_1",
            "selected_ranks": [1],
            "fidelity_confirmed": True,
            "fidelity_constraints_path": "analysis/product_fidelity_constraints.json",
            "confirmation_snapshot": _ring_confirmation_snapshot(),
            "reference_snapshot_sha256": VALID_REFERENCE_SNAPSHOT_SHA256,
        },
    )
    invalid_constraints = _invalidate_ring_constraints(
        _ring_fidelity_constraints_data(analysis_data),
        invalid_kind,
    )
    write_json(
        paths.analysis_dir / "product_fidelity_constraints.json",
        invalid_constraints,
    )

    with pytest.raises(ReviewGateError, match="产品保真约束"):
        require_generation_decision(paths)


def test_四文件事务第三次替换失败时也回滚全部文件(
    tmp_path,
    monkeypatch,
):
    import os

    paths = RunPaths.create(tmp_path, "run-rollback-three")
    analysis_data = _necklace_analysis_data()
    _write_reference_snapshot_artifacts(
        paths,
        tmp_path,
        analysis_data=analysis_data,
    )
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    old_analysis = analysis_path.read_bytes()
    old_constraints = canonical_path.read_bytes()
    imported_path = paths.review_dir / "imported-constraints.json"
    write_json(
        imported_path,
        _constraints_data(review_status="pending", analysis_data=analysis_data),
    )
    original_replace = os.replace
    replace_count = 0

    def fail_third_replace(source, target):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 3:
            raise OSError("模拟第三次替换失败")
        return original_replace(source, target)

    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        fail_third_replace,
    )

    with pytest.raises(ReviewGateError, match="4 文件提交失败.*模拟第三次替换失败"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "confirmation_snapshot": _confirmation_snapshot(),
                "output_role": "hand_worn",
            },
            analysis_data=analysis_data,
        )

    assert analysis_path.read_bytes() == old_analysis
    assert canonical_path.read_bytes() == old_constraints
    assert not decision_path.exists()
    assert not snapshot_path.exists()
    assert not list(paths.analysis_dir.glob("*.tmp"))
    assert not list(paths.review_dir.glob("*.tmp"))


def test_审核事务原子绑定唯一人工确认参考构图快照(tmp_path):
    paths = RunPaths.create(tmp_path, "run-reference-snapshot")
    snapshot = _write_reference_snapshot_artifacts(paths, tmp_path, rank=2)
    analysis_data = _bracelet_analysis_data()

    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_selected",
            "selected_ranks": [2],
            "fidelity_confirmed": True,
            "output_role": "hand_worn",
        },
        analysis_data=analysis_data,
    )

    saved_snapshot = read_json(
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    )
    saved_decision = read_json(paths.review_dir / "review_decision.json")
    assert saved_snapshot == snapshot.to_dict()
    assert saved_snapshot["rank"] == 2
    assert saved_decision["reference_snapshot_sha256"] == (
        reference_composition_sha256(snapshot)
    )
    assert ReviewDecision.from_dict(
        saved_decision,
        require_reference_snapshot_sha256=True,
    ).to_dict() == saved_decision


def test_新快照事务未显式传入分析数据时仍提交四个目标(tmp_path, monkeypatch):
    import os

    paths = RunPaths.create(tmp_path, "run-four-targets")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    original_replace = os.replace
    replaced_targets = []

    def record_replace(source, target):
        replaced_targets.append(target)
        return original_replace(source, target)

    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        record_replace,
    )

    review_decision.write_review_bundle(
        paths,
        {
            "action": "generate_rank_1",
            "fidelity_confirmed": True,
            "output_role": "hand_worn",
        },
    )

    assert replaced_targets == [
        paths.analysis_dir / "product_analysis.json",
        paths.review_dir / "review_decision.json",
        paths.analysis_dir / "product_fidelity_constraints.json",
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    ]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("rank", 3),
        ("reference_file", "other-reference.jpg"),
        ("reference_sha256", "0" * 64),
        ("output_role", "lifestyle"),
    ],
)
def test_记录决策拒绝候选快照身份绑定篡改(
    tmp_path,
    field,
    invalid_value,
):
    paths = RunPaths.create(tmp_path, f"run-mutated-{field}")
    snapshot = _write_reference_snapshot_artifacts(paths, tmp_path, rank=2)
    snapshot_data = snapshot.to_dict()
    snapshot_data[field] = invalid_value
    write_json(
        paths.analysis_dir / "reference_composition_snapshots.json",
        [snapshot_data],
    )

    with pytest.raises(ReviewGateError, match=field.replace("_", ".*")):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_selected",
                "selected_ranks": [2],
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )

    assert not (paths.review_dir / "review_decision.json").exists()
    assert not (
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    ).exists()


@pytest.mark.parametrize("field", ["source_sha256", "review_sha256"])
def test_记录决策拒绝选中参考图双摘要篡改(tmp_path, field):
    paths = RunPaths.create(tmp_path, f"run-selected-{field}")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    selected_data = read_json(paths.analysis_dir / "selected_references.json")
    selected_data[0][field] = "0" * 64
    selected_data[0]["metadata"][field] = "0" * 64
    write_json(paths.analysis_dir / "selected_references.json", selected_data)

    with pytest.raises(ReviewGateError, match=field.replace("_", ".*")):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )

    assert not (paths.review_dir / "review_decision.json").exists()
    assert not (
        paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    ).exists()


def test_记录决策拒绝直接编辑候选构图描述并要求重新准备审核(tmp_path):
    paths = RunPaths.create(tmp_path, "run-mutated-description")
    snapshot = _write_reference_snapshot_artifacts(paths, tmp_path)
    snapshot_data = snapshot.to_dict()
    snapshot_data["framing"] = "被直接编辑的取景描述"
    write_json(
        paths.analysis_dir / "reference_composition_snapshots.json",
        [snapshot_data],
    )

    with pytest.raises(ReviewGateError, match="不可直接编辑.*重新.*prepare-review"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )


def test_记录决策拒绝两个选中序位和新的多图生成动作(tmp_path):
    paths = RunPaths.create(tmp_path, "run-multiple")
    _write_reference_snapshot_artifacts(paths, tmp_path)

    with pytest.raises(ReviewGateError, match="generate_selected.*一个"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_selected",
                "selected_ranks": [1, 2],
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )
    with pytest.raises(ReviewGateError, match="generate_multiple.*历史读取"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_multiple",
                "selected_ranks": [1, 2],
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )


def test_记录决策拒绝缺失候选序位和运行角色不一致(tmp_path):
    paths = RunPaths.create(tmp_path, "run-missing-rank")
    _write_reference_snapshot_artifacts(paths, tmp_path, rank=1)

    with pytest.raises(ReviewGateError, match="selected rank 2.*候选"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_selected",
                "selected_ranks": [2],
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )

    write_json(paths.analysis_dir / "output_role.json", {"output_role": "lifestyle"})
    with pytest.raises(ReviewGateError, match="output_role.*当前 run.*不一致"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )


def test_四文件事务第四次替换失败时逐字节回滚并清理临时文件(
    tmp_path,
    monkeypatch,
):
    import os

    paths = RunPaths.create(tmp_path, "run-four-file-rollback")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    analysis_path = paths.analysis_dir / "product_analysis.json"
    decision_path = paths.review_dir / "review_decision.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    old_files = {
        analysis_path: analysis_path.read_bytes(),
        canonical_path: canonical_path.read_bytes(),
    }
    imported_path = paths.review_dir / "imported-constraints.json"
    write_json(
        imported_path,
        _constraints_data(
            review_status="confirmed",
            analysis_data=_bracelet_analysis_data(),
        ),
    )
    original_replace = os.replace
    replace_count = 0

    def fail_fourth_replace(source, target):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 4:
            raise OSError("模拟第四次替换失败")
        return original_replace(source, target)

    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        fail_fourth_replace,
    )

    with pytest.raises(ReviewGateError, match="4 文件提交失败.*模拟第四次替换失败"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "fidelity_constraints_path": str(imported_path),
                "output_role": "hand_worn",
            },
            analysis_data=_bracelet_analysis_data(),
        )

    assert {path: path.read_bytes() for path in old_files} == old_files
    assert not decision_path.exists()
    assert not snapshot_path.exists()
    assert not list(paths.analysis_dir.glob("*.tmp"))
    assert not list(paths.review_dir.glob("*.tmp"))


def test_四文件事务失败时删除本次新建目标并恢复已有文件(
    tmp_path,
    monkeypatch,
):
    import os

    paths = RunPaths.create(tmp_path, "run-rollback-new-targets")
    _write_reference_snapshot_artifacts(paths, tmp_path)
    analysis_path = paths.analysis_dir / "product_analysis.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    decision_path = paths.review_dir / "review_decision.json"
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    old_analysis = analysis_path.read_bytes()
    old_canonical = canonical_path.read_bytes()
    original_replace = os.replace
    replace_count = 0

    def fail_fourth_replace(source, target):
        nonlocal replace_count
        replace_count += 1
        if replace_count == 4:
            raise OSError("模拟新目标第四次替换失败")
        return original_replace(source, target)

    monkeypatch.setattr(
        "jewelry_on_hand.review_decision.os.replace",
        fail_fourth_replace,
    )

    with pytest.raises(ReviewGateError, match="4 文件提交失败.*第四次替换失败"):
        review_decision.write_review_bundle(
            paths,
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        )

    assert analysis_path.read_bytes() == old_analysis
    assert canonical_path.read_bytes() == old_canonical
    assert not decision_path.exists()
    assert not snapshot_path.exists()
    assert not list(paths.analysis_dir.glob("*.tmp"))
    assert not list(paths.review_dir.glob("*.tmp"))


def test_migration_完整现代审核_run_分类并加载确认快照(tmp_path):
    paths, snapshot = _write_完整现代审核_run(tmp_path)

    assert reference_composition.classify_reference_run(paths) == "modern_snapshot"
    assert reference_composition.require_modern_reference_run(paths) == snapshot
    assert require_generation_decision(paths).selected_ranks == [1]


def test_legacy_read_only_完整历史_run_拒绝生成决策且只读(tmp_path):
    paths = _write_完整历史_run(tmp_path)
    before = _run_文件树快照(paths.root)

    assert reference_composition.classify_reference_run(paths) == "legacy_read_only"
    with pytest.raises(
        ReviewGateError,
        match="历史 run 只读.*重新执行 prepare-review",
    ):
        require_generation_decision(paths)

    assert _run_文件树快照(paths.root) == before


@pytest.mark.parametrize(
    ("写入入口", "decision_data"),
    (
        (
            "write_review_decision-rerank",
            {"action": "rerank"},
        ),
        (
            "write_review_decision-manual_reference",
            {"action": "manual_reference", "manual_reference": "manual.jpg"},
        ),
        (
            "write_analysis_and_review_decision-rerank",
            {"action": "rerank"},
        ),
        (
            "write_analysis_and_review_decision-manual_reference",
            {"action": "manual_reference", "manual_reference": "manual.jpg"},
        ),
        (
            "write_review_bundle-rerank",
            {"action": "rerank"},
        ),
        (
            "write_review_bundle-manual_reference",
            {"action": "manual_reference", "manual_reference": "manual.jpg"},
        ),
        (
            "write_review_bundle-generate_rank_1",
            {
                "action": "generate_rank_1",
                "fidelity_confirmed": True,
                "output_role": "hand_worn",
            },
        ),
    ),
)
def test_legacy_read_only_任何_review_写入入口均在写前拒绝且保持字节不变(
    tmp_path,
    写入入口,
    decision_data,
):
    paths = _write_完整历史_run(tmp_path, 写入入口)
    before = _run_文件树快照(paths.root)

    with pytest.raises(
        ReviewGateError,
        match="历史 run 只读.*重新执行 prepare-review",
    ):
        if 写入入口.startswith("write_analysis_and_review_decision"):
            write_analysis_and_review_decision(
                paths,
                _bracelet_analysis_data(),
                decision_data,
            )
        elif 写入入口.startswith("write_review_bundle"):
            review_decision.write_review_bundle(paths, decision_data)
        else:
            write_review_decision(paths, decision_data)

    assert _run_文件树快照(paths.root) == before


@pytest.mark.parametrize(
    "invalid_digest",
    [None, 1, "a" * 63, "a" * 65, "A" * 64, "g" * 64, "0" * 64],
)
def test_damaged_坏摘要均返回中文迁移错误且不修改_run(
    tmp_path,
    invalid_digest,
):
    paths, _snapshot = _write_完整现代审核_run(
        tmp_path,
        f"damaged-digest-{type(invalid_digest).__name__}-{len(str(invalid_digest))}",
    )
    decision_path = paths.review_dir / "review_decision.json"
    decision = read_json(decision_path)
    decision["reference_snapshot_sha256"] = invalid_digest
    write_json(decision_path, decision)
    before = _run_文件树快照(paths.root)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    with pytest.raises(
        ValueError,
        match="run 产物不完整/损坏.*重新执行 prepare-review",
    ):
        reference_composition.require_modern_reference_run(paths)

    assert _run_文件树快照(paths.root) == before


@pytest.mark.parametrize("decision_data", [[], "坏决策", None, True, 1])
def test_damaged_非对象决策返回中文迁移错误且不修改_run(
    tmp_path,
    decision_data,
):
    paths, _snapshot = _write_完整现代审核_run(
        tmp_path,
        f"damaged-decision-{type(decision_data).__name__}",
    )
    write_json(paths.review_dir / "review_decision.json", decision_data)
    before = _run_文件树快照(paths.root)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    with pytest.raises(
        ValueError,
        match="run 产物不完整/损坏.*重新执行 prepare-review",
    ):
        reference_composition.require_modern_reference_run(paths)

    assert _run_文件树快照(paths.root) == before


def test_damaged_确认快照与候选快照摘要链不一致(tmp_path):
    paths, _snapshot = _write_完整现代审核_run(tmp_path)
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    snapshot_data = read_json(snapshot_path)
    snapshot_data["background"] = "被单独篡改的背景"
    write_json(snapshot_path, snapshot_data)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    with pytest.raises(ValueError, match="run 产物不完整/损坏"):
        reference_composition.require_modern_reference_run(paths)


@pytest.mark.parametrize(
    "mutation",
    (
        "product",
        "analysis",
        "canonical",
        "selected",
        "review_copy",
        "source",
        "output_role",
        "fidelity_unconfirmed",
        "constraints_path",
    ),
)
def test_damaged_现代根产物与完整决策任一断链均拒绝(
    tmp_path,
    mutation,
):
    paths, _snapshot = _write_完整现代审核_run(tmp_path, mutation)
    selected_path = paths.analysis_dir / "selected_references.json"
    selected = read_json(selected_path)
    decision_path = paths.review_dir / "review_decision.json"
    decision = read_json(decision_path)
    target = {
        "product": paths.input_dir / "product-on-hand.jpg",
        "analysis": paths.analysis_dir / "product_analysis.json",
        "canonical": paths.analysis_dir / "product_fidelity_constraints.json",
        "selected": selected_path,
        "review_copy": Path(selected[0]["selected_reference"]),
        "source": Path(selected[0]["metadata"]["source_reference"]),
        "output_role": paths.analysis_dir / "output_role.json",
    }.get(mutation)
    if target is not None:
        target.unlink()
    elif mutation == "fidelity_unconfirmed":
        decision["fidelity_confirmed"] = False
        write_json(decision_path, decision)
    else:
        decision["fidelity_constraints_path"] = "review/other.json"
        write_json(decision_path, decision)

    assert reference_composition.classify_reference_run(paths) == "damaged"
    with pytest.raises(ValueError, match="run 产物不完整/损坏"):
        reference_composition.require_modern_reference_run(paths)
