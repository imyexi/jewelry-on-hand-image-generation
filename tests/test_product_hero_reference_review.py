import copy
import hashlib
import json
import runpy
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "skills"
    / "jewelry-product-hero-workflow"
    / "scripts"
    / "reference_review.py"
)


if MODULE_PATH.is_file():
    review = runpy.run_path(str(MODULE_PATH))
else:
    class _MissingReferenceReviewError(ValueError):
        pass

    def _not_implemented(*args, **kwargs):
        raise _MissingReferenceReviewError("参考图评审功能尚未实现")

    review = {
        "ReferenceReviewError": _MissingReferenceReviewError,
        "collect_explicit_category_candidates": _not_implemented,
        "record_reference_decision": _not_implemented,
        "select_top3": _not_implemented,
        "validate_reference_assessments": _not_implemented,
        "write_review_package": _not_implemented,
    }

ReferenceReviewError = review["ReferenceReviewError"]
collect_explicit_category_candidates = review[
    "collect_explicit_category_candidates"
]
record_reference_decision = review["record_reference_decision"]
select_top3 = review["select_top3"]
validate_reference_assessments = review[
    "validate_reference_assessments"
]
write_review_package = review["write_review_package"]


SCORE_FIELDS = {
    "topology_layout": 30,
    "complete_replace_region": 20,
    "camera_orientation_scale": 15,
    "background_props": 15,
    "lighting_material": 10,
    "cleanup_cost": 10,
}

FEISHU_SOURCE = {
    "wiki_url": "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink",
    "base_name": "AI生图参考图素材库",
    "table_name": "素材收录池",
}


def source_snapshot(record_count):
    return {
        **FEISHU_SOURCE,
        "pagination_complete": True,
        "page_count": 1,
        "record_count": record_count,
    }


def write_image(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def candidate_record(
    tmp_path,
    material_id,
    *,
    record_id=None,
    category="戒指",
    image_type="主图",
    content=None,
    usable=True,
    keywords="亮色背景 简洁",
):
    record_id = record_id or f"rec-{material_id}"
    image_path = write_image(
        tmp_path / f"{record_id}.jpg",
        content if content is not None else material_id.encode("utf-8"),
    )
    return {
        "record_id": record_id,
        "usable": usable,
        "image_path": str(image_path),
        "source_fields": {
            "素材编号": material_id,
            "关键词": keywords,
            "图片类型": image_type,
            "适用品类": category,
        },
    }


def collect_records(records, category, excluded_sha256=None):
    excluded = excluded_sha256 or ["f" * 64]
    return collect_explicit_category_candidates(
        records,
        category,
        excluded_sha256=excluded,
        source_snapshot=source_snapshot(len(records)),
    )


def collect_three(tmp_path, category="ring", excluded_sha256=None):
    records = [
        candidate_record(tmp_path, f"RP{index:06d}")
        for index in range(1, 4)
    ]
    return collect_records(records, category, excluded_sha256)


def valid_assessment(candidate, *, score=60, **overrides):
    score_values = {
        "topology_layout": min(score, 30),
        "complete_replace_region": min(max(score - 30, 0), 20),
        "camera_orientation_scale": min(max(score - 50, 0), 15),
        "background_props": min(max(score - 65, 0), 15),
        "lighting_material": min(max(score - 80, 0), 10),
        "cleanup_cost": min(max(score - 90, 0), 10),
    }
    data = {
        "record_id": candidate["record_id"],
        "material_id": candidate["material_id"],
        "image_sha256": candidate["image_sha256"],
        "compatible": True,
        "single_product_unit": True,
        "requires_product_stretch": False,
        "requires_large_background_rebuild": False,
        **score_values,
        "reasons": ["构图适配"],
        "risks": [],
    }
    data.update(overrides)
    return data


def assert_review_error(call, *message_fragments):
    with pytest.raises(ReferenceReviewError) as caught:
        call()
    message = str(caught.value)
    assert any("\u4e00" <= char <= "\u9fff" for char in message)
    for fragment in message_fragments:
        assert fragment in message


def test_collect_requires_explicit_main_image_and_target_category(tmp_path):
    records = [
        candidate_record(tmp_path, "RP000001", category=["戒指", "通用"]),
        candidate_record(tmp_path, "RP000002", category=["戒指"]),
        candidate_record(tmp_path, "RP000003", category="戒指,手镯"),
        candidate_record(tmp_path, "RP000004", category=["通用"]),
        candidate_record(tmp_path, "RP000005", image_type=["生活场景图"]),
        candidate_record(tmp_path, "RP000006", image_type="非主图"),
    ]

    candidates = collect_records(records, "ring")

    assert [item["material_id"] for item in candidates] == [
        "RP000001",
        "RP000002",
        "RP000003",
    ]
    assert all(item["category"] == "ring" for item in candidates)
    assert candidates[0]["keywords"] == "亮色背景 简洁"


def test_collect_keeps_valid_light_background_candidates(tmp_path):
    records = [
        candidate_record(
            tmp_path,
            f"RP{index:06d}",
            keywords="纯白亮色背景 高调光",
        )
        for index in range(1, 4)
    ]

    candidates = collect_records(records, "ring")

    assert len(candidates) == 3
    assert all("亮色" in item["keywords"] for item in candidates)


def test_collect_excludes_product_hash_and_deduplicates_stably(tmp_path):
    product_bytes = b"product-input"
    duplicate_bytes = b"same-attachment"
    excluded = candidate_record(
        tmp_path,
        "RP000001",
        content=product_bytes,
    )
    duplicate_late = candidate_record(
        tmp_path,
        "RP000020",
        record_id="rec-z",
        content=duplicate_bytes,
    )
    duplicate_first = candidate_record(
        tmp_path,
        "RP000010",
        record_id="rec-a",
        content=duplicate_bytes,
    )
    records = [
        duplicate_late,
        candidate_record(tmp_path, "RP000030"),
        excluded,
        duplicate_first,
        candidate_record(tmp_path, "RP000040"),
    ]

    candidates = collect_explicit_category_candidates(
        records,
        "ring",
        excluded_sha256=[hashlib.sha256(product_bytes).hexdigest()],
        source_snapshot=source_snapshot(len(records)),
    )

    assert [item["material_id"] for item in candidates] == [
        "RP000010",
        "RP000030",
        "RP000040",
    ]
    assert candidates[0]["record_id"] == "rec-a"
    assert len({item["image_sha256"] for item in candidates}) == 3


@pytest.mark.parametrize(
    ("category", "chinese_category"),
    [("ring", "戒指"), ("bangle", "手镯")],
)
def test_collect_blocks_when_explicit_category_has_fewer_than_three(
    tmp_path, category, chinese_category
):
    records = [
        candidate_record(
            tmp_path,
            f"RP{index:06d}",
            category=chinese_category,
        )
        for index in range(1, 3)
    ]
    records.append(
        candidate_record(tmp_path, "RP000099", category="通用")
    )

    assert_review_error(
        lambda: collect_records(records, category),
        chinese_category,
        "2",
    )


def test_validate_assessments_returns_copy_and_computes_score(tmp_path):
    candidates = collect_three(tmp_path)
    assessments = [valid_assessment(item, score=55) for item in candidates]

    normalized = validate_reference_assessments(
        candidates, assessments, "single"
    )

    assert [item["score"] for item in normalized] == [55, 55, 55]
    assert normalized == [dict(item, score=55) for item in assessments]
    assert normalized is not assessments
    assert normalized[0] is not assessments[0]
    assert normalized[0]["reasons"] is not assessments[0]["reasons"]


@pytest.mark.parametrize("invalid_kind", ["missing", "duplicate", "extra"])
def test_validate_assessments_requires_exactly_one_per_candidate(
    tmp_path, invalid_kind
):
    candidates = collect_three(tmp_path)
    assessments = [valid_assessment(item) for item in candidates]
    if invalid_kind == "missing":
        assessments.pop()
    elif invalid_kind == "duplicate":
        assessments[-1] = copy.deepcopy(assessments[0])
    else:
        extra = copy.deepcopy(assessments[0])
        extra["record_id"] = "rec-extra"
        assessments.append(extra)

    assert_review_error(
        lambda: validate_reference_assessments(
            candidates, assessments, "single"
        )
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: item.update(material_id="RP-WRONG"),
        lambda item: item.update(image_sha256="0" * 64),
        lambda item: item.update(compatible=1),
        lambda item: item.update(single_product_unit="true"),
        lambda item: item.update(requires_product_stretch=0),
        lambda item: item.update(topology_layout=31),
        lambda item: item.update(cleanup_cost=-1),
        lambda item: item.update(background_props=True),
        lambda item: item.update(reasons=[]),
        lambda item: item.update(reasons=[" "]),
        lambda item: item.update(risks=[1]),
    ],
)
def test_validate_assessments_rejects_binding_types_ranges_and_empty_reasons(
    tmp_path, mutation
):
    candidates = collect_three(tmp_path)
    assessments = [valid_assessment(item) for item in candidates]
    mutation(assessments[0])

    assert_review_error(
        lambda: validate_reference_assessments(
            candidates, assessments, "single"
        )
    )


def test_validate_matched_pair_treats_one_pair_as_one_product_unit(tmp_path):
    records = [
        candidate_record(
            tmp_path,
            f"RP{index:06d}",
            category="耳饰",
        )
        for index in range(1, 4)
    ]
    candidates = collect_records(records, "earrings")
    assessments = [valid_assessment(item) for item in candidates]

    normalized = validate_reference_assessments(
        candidates, assessments, "matched_earring_pair"
    )

    assert all(item["single_product_unit"] is True for item in normalized)
    assert_review_error(
        lambda: validate_reference_assessments(candidates, assessments, "set")
    )


def test_select_top3_blocks_when_hard_gates_leave_fewer_than_three(tmp_path):
    candidates = collect_three(tmp_path)
    assessments = [valid_assessment(item) for item in candidates]
    assessments[0]["requires_product_stretch"] = True

    assert_review_error(
        lambda: select_top3(candidates, assessments, "single"),
        "3",
    )


def test_select_top3_sorts_by_score_then_stable_material_and_record_id(
    tmp_path,
):
    records = [
        candidate_record(tmp_path, "RP000020", record_id="rec-b"),
        candidate_record(
            tmp_path,
            "RP000010",
            record_id="rec-z",
            content=b"RP000010-rec-z",
        ),
        candidate_record(
            tmp_path,
            "RP000010",
            record_id="rec-a",
            content=b"RP000010-rec-a",
        ),
        candidate_record(tmp_path, "RP000030", record_id="rec-c"),
    ]
    candidates = collect_records(records, "ring")
    assessments = [
        valid_assessment(item, score=80 if item["material_id"] == "RP000030" else 70)
        for item in candidates
    ]

    top3 = select_top3(candidates, assessments, "single")

    assert [item["rank"] for item in top3] == [1, 2, 3]
    assert [
        (item["material_id"], item["record_id"], item["score"])
        for item in top3
    ] == [
        ("RP000030", "rec-c", 80),
        ("RP000010", "rec-a", 70),
        ("RP000010", "rec-z", 70),
    ]


def ready_review_run(tmp_path, product_unit="single"):
    run_root = tmp_path / "run"
    (run_root / "analysis").mkdir(parents=True)
    input_images = []
    for role, relative in (
        ("front", "input/front.jpg"),
        ("side", "input/side.jpg"),
        ("detail_01", "input/details/01.jpg"),
    ):
        path = write_image(run_root / relative, f"product-{role}".encode())
        input_images.append(
            {
                "role": role,
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
        )
    (run_root / "input" / "input_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product_id": "PN-测试-001",
                "images": input_images,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    state = {
        "schema_version": 1,
        "state": "awaiting_reference_review",
        "generation_attempts": 0,
        "non_pass_attempts": 0,
    }
    analysis = {
        "schema_version": 1,
        "product_id": "PN-测试-001",
        "category": "earrings" if product_unit == "matched_earring_pair" else "ring",
        "product_unit": product_unit,
    }
    (run_root / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_root / "analysis" / "product_analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_root


def run_input_hashes(run_root):
    manifest = json.loads(
        (run_root / "input" / "input_manifest.json").read_text(encoding="utf-8")
    )
    return [item["sha256"] for item in manifest["images"]]


def test_collect_requires_complete_fixed_feishu_snapshot_and_product_hashes(tmp_path):
    records = [
        candidate_record(tmp_path, f"RP{index:06d}") for index in range(1, 4)
    ]

    assert_review_error(
        lambda: collect_explicit_category_candidates(
            records,
            "ring",
            excluded_sha256=[],
            source_snapshot=source_snapshot(len(records)),
        ),
        "产品输入",
    )
    incomplete = source_snapshot(len(records))
    incomplete["pagination_complete"] = False
    assert_review_error(
        lambda: collect_explicit_category_candidates(
            records,
            "ring",
            excluded_sha256=["a" * 64],
            source_snapshot=incomplete,
        ),
        "分页",
    )


def test_write_review_package_rejects_raw_candidates_that_bypass_feishu_gate(tmp_path):
    run_root = ready_review_run(tmp_path)
    raw_candidates = []
    for index in range(1, 4):
        image = write_image(tmp_path / f"raw-{index}.jpg", f"raw-{index}".encode())
        raw_candidates.append(
            {
                "record_id": f"raw-{index}",
                "material_id": f"RP{index:06d}",
                "image_path": str(image),
                "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "category": "ring",
                "keywords": "",
            }
        )
    assessments = [valid_assessment(item) for item in raw_candidates]

    assert_review_error(
        lambda: write_review_package(run_root, raw_candidates, assessments),
        "飞书",
    )


def test_write_review_package_revalidates_frozen_feishu_fields(tmp_path):
    run_root = ready_review_run(tmp_path)
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    candidates[0]["source_fields"]["图片类型"] = "生活场景图"
    assessments = [valid_assessment(item) for item in candidates]

    assert_review_error(
        lambda: write_review_package(run_root, candidates, assessments),
        "候选集合",
        "快照",
    )


def test_write_review_package_rejects_candidate_appended_after_feishu_filter(tmp_path):
    run_root = ready_review_run(tmp_path)
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    forged_image = write_image(tmp_path / "forged.jpg", b"forged-reference")
    forged = {
        "record_id": "forged-record",
        "material_id": "RP999999",
        "image_path": str(forged_image),
        "image_sha256": hashlib.sha256(forged_image.read_bytes()).hexdigest(),
        "category": "ring",
        "keywords": "",
        "usable": True,
        "source_fields": {
            "素材编号": "RP999999",
            "图片类型": "主图",
            "适用品类": "戒指",
            "关键词": "",
        },
    }
    candidates.append(forged)
    assessments = [valid_assessment(item, score=100) for item in candidates]

    assert_review_error(
        lambda: write_review_package(run_root, candidates, assessments),
        "候选集合",
        "快照",
    )


def snapshot_run_files(run_root):
    return {
        path.relative_to(run_root).as_posix(): path.read_bytes()
        for path in run_root.rglob("*")
        if path.is_file()
    }


def test_write_review_package_copies_top3_writes_html_snapshot_and_state(
    tmp_path,
):
    run_root = ready_review_run(tmp_path)
    records = [
        candidate_record(
            tmp_path / "cache",
            f"RP{index:06d}",
            content=f"reference-{index}".encode(),
        )
        for index in range(1, 5)
    ]
    candidates = collect_records(records, "ring", run_input_hashes(run_root))
    assessments = [
        valid_assessment(item, score=50 + index)
        for index, item in enumerate(candidates)
    ]

    package = write_review_package(run_root, candidates, assessments)

    assessment_path = run_root / "analysis" / "reference_assessments.json"
    top3_path = run_root / "review" / "top3.json"
    html_path = run_root / "review" / "review.html"
    state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    top3_document = json.loads(top3_path.read_text(encoding="utf-8"))
    assert package == top3_document
    assert assessment_path.is_file()
    assert top3_document["schema_version"] == 1
    assert top3_document["product_id"] == "PN-测试-001"
    assert top3_document["category"] == "ring"
    assert top3_document["source"]["wiki_url"] == FEISHU_SOURCE["wiki_url"]
    assert top3_document["source"]["pagination_complete"] is True
    assert top3_document["source"]["record_count"] == len(records)
    assert top3_document["source"]["excluded_product_sha256"] == sorted(
        run_input_hashes(run_root)
    )
    assert len(top3_document["source"]["snapshot_sha256"]) == 64
    assert [item["rank"] for item in top3_document["items"]] == [1, 2, 3]
    for item in top3_document["items"]:
        copied = run_root / item["selected_reference"]
        assert copied.is_file()
        assert copied.name == f"rank-{item['rank']}-{item['material_id']}.jpg"
        assert item["image_sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()
        assert isinstance(item["score"], int)
        assert item["reasons"]
        assert isinstance(item["risks"], list)
        assert item["source_fields"]["图片类型"] == "主图"
        assert item["source_fields"]["适用品类"] == "戒指"
    html = html_path.read_text(encoding="utf-8")
    assert "PN-测试-001" in html
    assert "戒指" in html
    assert all(item["material_id"] in html for item in top3_document["items"])
    assert all(item["selected_reference"] in html for item in top3_document["items"])
    assert "auto" not in html.lower()
    assert state["state"] == "awaiting_reference_decision"
    assert state["top3_sha256"] == hashlib.sha256(top3_path.read_bytes()).hexdigest()
    assert not (run_root / "review" / "decision.json").exists()


def test_write_review_package_rejects_wrong_state(tmp_path):
    run_root = ready_review_run(tmp_path)
    state_path = run_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["state"] = "prepared"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )

    assert_review_error(
        lambda: write_review_package(
            run_root,
            candidates,
            [valid_assessment(item) for item in candidates],
        )
    )


@pytest.mark.parametrize("existing_artifact", ["assessment", "review", "decision"])
def test_write_review_package_rejects_existing_artifacts_without_changes(
    tmp_path, existing_artifact
):
    run_root = ready_review_run(tmp_path)
    if existing_artifact == "assessment":
        path = run_root / "analysis" / "reference_assessments.json"
        path.write_bytes(b"existing-assessment")
    elif existing_artifact == "review":
        path = run_root / "review" / "keep.bin"
        path.parent.mkdir()
        path.write_bytes(b"existing-review")
    else:
        path = run_root / "review" / "decision.json"
        path.parent.mkdir()
        path.write_bytes(b"existing-decision")
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    before = snapshot_run_files(run_root)

    assert_review_error(
        lambda: write_review_package(
            run_root,
            candidates,
            [valid_assessment(item) for item in candidates],
        ),
        "已存在",
    )

    assert snapshot_run_files(run_root) == before


def test_write_review_package_copy_failure_leaves_formal_run_unchanged(
    tmp_path, monkeypatch
):
    run_root = ready_review_run(tmp_path)
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    assessments = [valid_assessment(item) for item in candidates]
    before = snapshot_run_files(run_root)
    real_copyfile = write_review_package.__globals__["shutil"].copyfile
    copy_count = 0

    def fail_second_copy(source, destination):
        nonlocal copy_count
        copy_count += 1
        if copy_count == 2:
            raise OSError("注入复制失败")
        return real_copyfile(source, destination)

    monkeypatch.setattr(
        write_review_package.__globals__["shutil"],
        "copyfile",
        fail_second_copy,
    )

    assert_review_error(
        lambda: write_review_package(run_root, candidates, assessments),
        "复制",
    )

    assert snapshot_run_files(run_root) == before
    assert not list(run_root.glob(".reference-review-*"))


def test_write_review_package_rehashes_copied_candidate_before_commit(
    tmp_path, monkeypatch
):
    run_root = ready_review_run(tmp_path)
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    assessments = [valid_assessment(item) for item in candidates]
    before = snapshot_run_files(run_root)
    real_copyfile = write_review_package.__globals__["shutil"].copyfile
    copy_count = 0

    def mutate_first_copy(source, destination):
        nonlocal copy_count
        copy_count += 1
        result = real_copyfile(source, destination)
        if copy_count == 1:
            Path(destination).write_bytes(b"changed-during-copy")
        return result

    monkeypatch.setattr(
        write_review_package.__globals__["shutil"],
        "copyfile",
        mutate_first_copy,
    )

    assert_review_error(
        lambda: write_review_package(run_root, candidates, assessments),
        "哈希",
    )

    assert snapshot_run_files(run_root) == before
    assert not list(run_root.glob(".reference-review-*"))


def test_write_review_package_state_failure_rolls_back_created_outputs(
    tmp_path, monkeypatch
):
    run_root = ready_review_run(tmp_path)
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    assessments = [valid_assessment(item) for item in candidates]
    before = snapshot_run_files(run_root)
    real_write_json = write_review_package.__globals__["_write_json"]
    state_path = run_root / "state.json"

    def fail_state_write(path, data):
        if Path(path) == state_path:
            state_path.write_bytes(b"partially-written-state")
            raise ReferenceReviewError("注入状态写入失败")
        return real_write_json(path, data)

    monkeypatch.setitem(
        write_review_package.__globals__, "_write_json", fail_state_write
    )

    assert_review_error(
        lambda: write_review_package(run_root, candidates, assessments),
        "状态",
    )

    assert snapshot_run_files(run_root) == before
    assert not list(run_root.glob(".reference-review-*"))


def packaged_run(tmp_path):
    run_root = ready_review_run(tmp_path)
    candidates = collect_three(
        tmp_path / "cache", excluded_sha256=run_input_hashes(run_root)
    )
    assessments = [valid_assessment(item, score=50 + index) for index, item in enumerate(candidates)]
    write_review_package(run_root, candidates, assessments)
    return run_root


def selection_evidence(rank):
    return {
        "source": "user_message",
        "selected_rank": rank,
        "verbatim": f"选 {rank}",
    }


def test_record_reference_decision_rejects_missing_user_selection_evidence(tmp_path):
    run_root = packaged_run(tmp_path)

    assert_review_error(
        lambda: record_reference_decision(run_root, 1),
        "用户选择证据",
    )


@pytest.mark.parametrize(
    "evidence",
    [
        {"source": "agent", "selected_rank": 1, "verbatim": "选 1"},
        {"source": "user_message", "selected_rank": 2, "verbatim": "选 2"},
        {"source": "user_message", "selected_rank": 1, "verbatim": " "},
    ],
)
def test_record_reference_decision_rejects_invalid_user_selection_evidence(
    tmp_path, evidence
):
    run_root = packaged_run(tmp_path)

    assert_review_error(
        lambda: record_reference_decision(run_root, 1, evidence),
        "用户选择证据",
    )


def test_record_reference_decision_requires_explicit_rank_and_advances_state(
    tmp_path,
):
    run_root = packaged_run(tmp_path)
    top3 = json.loads(
        (run_root / "review" / "top3.json").read_text(encoding="utf-8")
    )

    decision = record_reference_decision(run_root, 2, selection_evidence(2))

    selected = top3["items"][1]
    decision_path = run_root / "review" / "decision.json"
    assert json.loads(decision_path.read_text(encoding="utf-8")) == decision
    assert decision == {
        "schema_version": 1,
        "selected_rank": 2,
        "record_id": selected["record_id"],
        "material_id": selected["material_id"],
        "selected_reference": selected["selected_reference"],
        "image_sha256": selected["image_sha256"],
        "top3_sha256": hashlib.sha256(
            (run_root / "review" / "top3.json").read_bytes()
        ).hexdigest(),
        "product_analysis_sha256": hashlib.sha256(
            (run_root / "analysis" / "product_analysis.json").read_bytes()
        ).hexdigest(),
        "user_selection_evidence": selection_evidence(2),
    }
    assert json.loads((run_root / "state.json").read_text(encoding="utf-8"))[
        "state"
    ] == "ready_to_generate"


@pytest.mark.parametrize("rank", [True, 0, 4, "1", None])
def test_record_reference_decision_rejects_illegal_rank(tmp_path, rank):
    run_root = packaged_run(tmp_path)

    assert_review_error(
        lambda: record_reference_decision(run_root, rank, selection_evidence(rank))
    )


def test_record_reference_decision_rejects_wrong_state(tmp_path):
    run_root = packaged_run(tmp_path)
    state_path = run_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["state"] = "awaiting_reference_review"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    assert_review_error(
        lambda: record_reference_decision(run_root, 1, selection_evidence(1))
    )


def test_record_reference_decision_rejects_tampered_top3(tmp_path):
    run_root = packaged_run(tmp_path)
    top3_path = run_root / "review" / "top3.json"
    top3 = json.loads(top3_path.read_text(encoding="utf-8"))
    top3["items"][0]["score"] = 0
    top3_path.write_text(
        json.dumps(top3, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    assert_review_error(
        lambda: record_reference_decision(run_root, 1, selection_evidence(1)),
        "篡改",
    )
    assert not (run_root / "review" / "decision.json").exists()


def test_record_reference_decision_rejects_existing_decision_without_changes(
    tmp_path,
):
    run_root = packaged_run(tmp_path)
    decision_path = run_root / "review" / "decision.json"
    decision_path.write_bytes(b"existing-decision")
    before = snapshot_run_files(run_root)

    assert_review_error(
        lambda: record_reference_decision(run_root, 1, selection_evidence(1)),
        "已存在",
    )

    assert snapshot_run_files(run_root) == before


def test_record_reference_decision_state_failure_removes_new_decision(
    tmp_path, monkeypatch
):
    run_root = packaged_run(tmp_path)
    before = snapshot_run_files(run_root)
    state_path = run_root / "state.json"
    real_write_json = record_reference_decision.__globals__["_write_json"]

    def fail_state_write(path, data):
        if Path(path) == state_path:
            state_path.write_bytes(b"partially-written-state")
            raise ReferenceReviewError("注入状态写入失败")
        return real_write_json(path, data)

    monkeypatch.setitem(
        record_reference_decision.__globals__, "_write_json", fail_state_write
    )

    assert_review_error(
        lambda: record_reference_decision(run_root, 2, selection_evidence(2)),
        "状态",
    )

    assert snapshot_run_files(run_root) == before
