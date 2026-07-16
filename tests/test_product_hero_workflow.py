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
    / "product_hero_workflow.py"
)
workflow = runpy.run_path(str(MODULE_PATH))

CATEGORY_TO_FEISHU = workflow["CATEGORY_TO_FEISHU"]
MAX_GENERATION_ATTEMPTS = workflow["MAX_GENERATION_ATTEMPTS"]
WorkflowContractError = workflow["WorkflowContractError"]
freeze_product_analysis = workflow["freeze_product_analysis"]
model_for_non_pass_count = workflow["model_for_non_pass_count"]
prepare_run = workflow["prepare_run"]
sha256_file = workflow["sha256_file"]
validate_product_analysis = workflow["validate_product_analysis"]


EXPECTED_CATEGORIES = {
    "beaded_bracelet": "手串",
    "bracelet": "手链",
    "necklace": "项链",
    "long_necklace": "长链",
    "pendant": "吊坠",
    "cord_jewelry": "编绳",
    "ring": "戒指",
    "bangle": "手镯",
    "earrings": "耳饰",
}

LIST_FIELDS = (
    "component_topology",
    "component_counts",
    "colors",
    "materials",
    "distinctive_features",
    "uncertain_features",
    "evidence_by_view",
)


def write_image(path, content):
    path.write_bytes(content)
    return path


def valid_analysis(product_id="PN-001", **overrides):
    data = {
        "schema_version": 1,
        "product_id": product_id,
        "category": "ring",
        "product_unit": "single",
        "physical_piece_count": 1,
        "silhouette": "圆形戒圈",
        "component_topology": ["主石", "戒托"],
        "component_counts": [],
        "colors": ["金色"],
        "materials": ["黄金"],
        "distinctive_features": ["圆形主石"],
        "uncertain_features": [],
        "evidence_by_view": ["front", "side"],
    }
    data.update(overrides)
    return data


def assert_contract_error(call):
    with pytest.raises(WorkflowContractError) as caught:
        call()
    assert any("\u4e00" <= char <= "\u9fff" for char in str(caught.value))


def test_category_mapping_and_public_contract_are_exact():
    assert CATEGORY_TO_FEISHU == EXPECTED_CATEGORIES
    assert issubclass(WorkflowContractError, ValueError)
    assert MAX_GENERATION_ATTEMPTS == 4


def test_prepare_run_copies_inputs_and_writes_ordered_manifest_and_state(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    front = write_image(source / "front.jpg", b"front-image")
    side = write_image(source / "side.png", b"side-image")
    detail_1 = write_image(source / "detail-a.webp", b"detail-one")
    detail_2 = write_image(source / "detail-b.jpeg", b"detail-two")
    run_root = tmp_path / "run"

    result = prepare_run(
        run_root,
        "产品-001",
        front,
        side,
        [detail_1, detail_2],
    )

    assert isinstance(result, dict)
    manifest_path = run_root / "input" / "input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": 1,
        "product_id": "产品-001",
        "images": [
            {
                "role": "front",
                "path": "input/front.jpg",
                "sha256": hashlib.sha256(b"front-image").hexdigest(),
                "size_bytes": len(b"front-image"),
            },
            {
                "role": "side",
                "path": "input/side.png",
                "sha256": hashlib.sha256(b"side-image").hexdigest(),
                "size_bytes": len(b"side-image"),
            },
            {
                "role": "detail_01",
                "path": "input/details/01.webp",
                "sha256": hashlib.sha256(b"detail-one").hexdigest(),
                "size_bytes": len(b"detail-one"),
            },
            {
                "role": "detail_02",
                "path": "input/details/02.jpeg",
                "sha256": hashlib.sha256(b"detail-two").hexdigest(),
                "size_bytes": len(b"detail-two"),
            },
        ],
    }
    assert (run_root / "input" / "front.jpg").read_bytes() == b"front-image"
    assert (run_root / "input" / "side.png").read_bytes() == b"side-image"
    assert (run_root / "input" / "details" / "01.webp").read_bytes() == b"detail-one"
    assert (run_root / "input" / "details" / "02.jpeg").read_bytes() == b"detail-two"
    assert sha256_file(manifest_path) == hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    assert json.loads((run_root / "state.json").read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "state": "prepared",
        "generation_attempts": 0,
        "non_pass_attempts": 0,
    }
    assert "产品-001" in manifest_path.read_text(encoding="utf-8")
    assert "\\u4ea7" not in manifest_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("detail_count", [0, 5])
def test_prepare_run_rejects_detail_counts_outside_one_to_four(tmp_path, detail_count):
    front = write_image(tmp_path / "front.jpg", b"front")
    side = write_image(tmp_path / "side.jpg", b"side")
    details = [
        write_image(tmp_path / f"detail-{index}.jpg", f"detail-{index}".encode())
        for index in range(detail_count)
    ]

    assert_contract_error(
        lambda: prepare_run(tmp_path / "run", "PN-001", front, side, details)
    )


@pytest.mark.parametrize("invalid_kind", ["empty", "extension", "occupied_run"])
def test_prepare_run_rejects_invalid_files_and_nonempty_run_directory(
    tmp_path, invalid_kind
):
    front = write_image(tmp_path / "front.jpg", b"front")
    side = write_image(tmp_path / "side.jpg", b"side")
    detail = write_image(tmp_path / "detail.jpg", b"detail")
    run_root = tmp_path / "run"

    if invalid_kind == "empty":
        detail.write_bytes(b"")
    elif invalid_kind == "extension":
        detail = write_image(tmp_path / "detail.gif", b"detail")
    else:
        run_root.mkdir()
        (run_root / "existing.txt").write_text("keep", encoding="utf-8")

    assert_contract_error(
        lambda: prepare_run(run_root, "PN-001", front, side, [detail])
    )


@pytest.mark.parametrize(
    ("overrides", "is_valid"),
    [
        ({}, True),
        (
            {
                "category": "earrings",
                "product_unit": "matched_earring_pair",
                "physical_piece_count": 2,
            },
            True,
        ),
        (
            {
                "category": "ring",
                "product_unit": "matched_earring_pair",
                "physical_piece_count": 2,
            },
            False,
        ),
        (
            {
                "category": "earrings",
                "product_unit": "matched_earring_pair",
                "physical_piece_count": 1,
            },
            False,
        ),
        ({"category": "necklace", "physical_piece_count": 2}, False),
    ],
)
def test_validate_product_analysis_enforces_product_unit_rules(overrides, is_valid):
    data = valid_analysis(**overrides)

    if is_valid:
        normalized = validate_product_analysis(data)
        assert normalized == data
        assert normalized is not data
        assert normalized["component_topology"] is not data["component_topology"]
    else:
        assert_contract_error(lambda: validate_product_analysis(data))


def test_beaded_bracelet_requires_confirmed_component_count_from_target_views():
    valid = valid_analysis(
        category="beaded_bracelet",
        silhouette="单圈圆珠手串",
        component_topology=["单圈闭合圆珠"],
        component_counts=[
            {
                "name": "圆珠",
                "physical_count": 13,
                "source_views": ["front", "side"],
            }
        ],
    )

    normalized = validate_product_analysis(valid)

    assert normalized["component_counts"] == valid["component_counts"]
    assert normalized["component_counts"] is not valid["component_counts"]

    missing = copy.deepcopy(valid)
    missing["component_counts"] = []
    assert_contract_error(lambda: validate_product_analysis(missing))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: item.update(physical_count=0),
        lambda item: item.update(physical_count=True),
        lambda item: item.update(source_views=["reference"]),
        lambda item: item.update(source_views=[]),
        lambda item: item.update(name=" "),
    ],
)
def test_component_counts_reject_invalid_quantity_or_reference_evidence(mutation):
    data = valid_analysis(
        category="beaded_bracelet",
        component_counts=[
            {
                "name": "圆珠",
                "physical_count": 13,
                "source_views": ["front", "side"],
            }
        ],
    )
    mutation(data["component_counts"][0])

    assert_contract_error(lambda: validate_product_analysis(data))


def test_confirmed_bead_count_cannot_also_be_declared_uncertain():
    data = valid_analysis(
        category="beaded_bracelet",
        component_counts=[
            {
                "name": "圆珠",
                "physical_count": 13,
                "source_views": ["front", "side"],
            }
        ],
        uncertain_features=["受视角遮挡影响，准确珠数不作猜测"],
    )

    assert_contract_error(lambda: validate_product_analysis(data))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version=2),
        lambda data: data.update(product_id="   "),
        lambda data: data.update(category="brooch"),
        lambda data: data.update(category=[]),
        lambda data: data.update(product_unit="set"),
        lambda data: data.update(product_unit={}),
        lambda data: data.update(physical_piece_count=True),
        lambda data: data.pop("component_counts"),
        lambda data: data.update(silhouette=""),
        lambda data: data.update(materials="黄金"),
        lambda data: data.pop("evidence_by_view"),
    ],
)
def test_validate_product_analysis_rejects_invalid_required_fields(mutation):
    data = valid_analysis()
    mutation(data)
    assert_contract_error(lambda: validate_product_analysis(data))


def prepared_run(tmp_path, product_id="PN-001"):
    front = write_image(tmp_path / "front.jpg", b"front")
    side = write_image(tmp_path / "side.jpg", b"side")
    detail = write_image(tmp_path / "detail.jpg", b"detail")
    run_root = tmp_path / "run"
    prepare_run(run_root, product_id, front, side, [detail])
    return run_root


@pytest.mark.parametrize("invalid_kind", ["product_id", "state"])
def test_freeze_product_analysis_rejects_product_mismatch_and_wrong_state(
    tmp_path, invalid_kind
):
    run_root = prepared_run(tmp_path)
    data = valid_analysis()

    if invalid_kind == "product_id":
        data["product_id"] = "PN-OTHER"
    else:
        state_path = run_root / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["state"] = "awaiting_reference_review"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    assert_contract_error(lambda: freeze_product_analysis(run_root, data))


def test_freeze_product_analysis_writes_digest_and_advances_state(tmp_path):
    run_root = prepared_run(tmp_path)
    state_path = run_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["generation_attempts"] = 1
    state["non_pass_attempts"] = 1
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = freeze_product_analysis(run_root, valid_analysis())

    assert isinstance(result, dict)
    analysis_path = run_root / "analysis" / "product_analysis.json"
    digest_path = run_root / "analysis" / "product_analysis.sha256"
    assert json.loads(analysis_path.read_text(encoding="utf-8")) == valid_analysis()
    assert digest_path.read_text(encoding="utf-8").strip() == sha256_file(analysis_path)
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "state": "awaiting_reference_review",
        "generation_attempts": 1,
        "non_pass_attempts": 1,
    }


def test_model_switches_after_two_non_pass_results_and_rejects_out_of_range():
    assert [model_for_non_pass_count(count) for count in range(4)] == [
        "gpt_image_2",
        "gpt_image_2",
        "nano_banana_v2",
        "nano_banana_v2",
    ]
    assert_contract_error(lambda: model_for_non_pass_count(-1))
    assert_contract_error(lambda: model_for_non_pass_count(4))
