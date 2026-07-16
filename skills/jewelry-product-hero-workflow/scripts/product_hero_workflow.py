from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


CATEGORY_TO_FEISHU = {
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

MAX_GENERATION_ATTEMPTS = 4
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ANALYSIS_LIST_FIELDS = (
    "component_topology",
    "component_counts",
    "colors",
    "materials",
    "distinctive_features",
    "uncertain_features",
    "evidence_by_view",
)
COUNT_SOURCE_PATTERN = re.compile(r"^(?:front|side|detail_[0-9]{2})$")
COUNT_UNCERTAINTY_PATTERN = re.compile(
    r"(?:准确珠数|总珠数|珠子总数|珠子数量|颗数).*(?:不作猜测|不确定|未知|无法确认|无法判断)"
)


class WorkflowContractError(ValueError):
    """珠宝主图工作流输入或状态不符合契约。"""


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise WorkflowContractError(f"文件不存在：{file_path}")

    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise WorkflowContractError(f"无法读取文件：{file_path}") from exc
    return digest.hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, content)


def _validate_product_id(product_id: Any) -> str:
    if not isinstance(product_id, str) or not product_id.strip():
        raise WorkflowContractError("产品 ID 不能为空")
    return product_id.strip()


def _validate_image_file(path: str | Path, role: str) -> Path:
    try:
        image_path = Path(path)
    except TypeError as exc:
        raise WorkflowContractError(f"{role}图片路径无效") from exc

    if not image_path.is_file():
        raise WorkflowContractError(f"{role}图片不存在：{image_path}")
    if image_path.stat().st_size == 0:
        raise WorkflowContractError(f"{role}图片不能为空文件：{image_path}")
    if image_path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise WorkflowContractError(f"{role}图片扩展名不受支持：{image_path.suffix}")
    return image_path


def _copy_manifest_image(
    source: Path,
    destination: Path,
    role: str,
    run_root: Path,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return {
        "role": role,
        "path": destination.relative_to(run_root).as_posix(),
        "sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
    }


def prepare_run(
    run_root: str | Path,
    product_id: str,
    front: str | Path,
    side: str | Path,
    details: Iterable[str | Path],
) -> dict[str, Any]:
    normalized_product_id = _validate_product_id(product_id)
    try:
        detail_paths = list(details)
    except TypeError as exc:
        raise WorkflowContractError("细节图片必须是包含 1 至 4 张图片的列表") from exc
    if not 1 <= len(detail_paths) <= 4:
        raise WorkflowContractError("细节图片数量必须为 1 至 4 张")

    validated_front = _validate_image_file(front, "正面")
    validated_side = _validate_image_file(side, "侧面")
    validated_details = [
        _validate_image_file(path, f"细节 {index:02d}")
        for index, path in enumerate(detail_paths, start=1)
    ]

    root = Path(run_root)
    if root.exists():
        if not root.is_dir():
            raise WorkflowContractError(f"运行目录不是文件夹：{root}")
        if any(root.iterdir()):
            raise WorkflowContractError(f"运行目录非空，禁止覆盖：{root}")

    root.mkdir(parents=True, exist_ok=True)
    images = [
        _copy_manifest_image(
            validated_front,
            root / "input" / f"front{validated_front.suffix.lower()}",
            "front",
            root,
        ),
        _copy_manifest_image(
            validated_side,
            root / "input" / f"side{validated_side.suffix.lower()}",
            "side",
            root,
        ),
    ]
    for index, detail_path in enumerate(validated_details, start=1):
        images.append(
            _copy_manifest_image(
                detail_path,
                root
                / "input"
                / "details"
                / f"{index:02d}{detail_path.suffix.lower()}",
                f"detail_{index:02d}",
                root,
            )
        )

    manifest = {
        "schema_version": 1,
        "product_id": normalized_product_id,
        "images": images,
    }
    state = {
        "schema_version": 1,
        "state": "prepared",
        "generation_attempts": 0,
        "non_pass_attempts": 0,
    }
    _atomic_write_json(root / "input" / "input_manifest.json", manifest)
    _atomic_write_json(root / "state.json", state)
    return manifest


def validate_component_counts(value: Any, category: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WorkflowContractError("component_counts 必须是列表")

    normalized = copy.deepcopy(value)
    names: set[str] = set()
    for index, item in enumerate(normalized, start=1):
        if not isinstance(item, dict):
            raise WorkflowContractError(f"component_counts 第 {index} 项必须是字典")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkflowContractError(f"component_counts 第 {index} 项 name 不能为空")
        name = name.strip()
        if name in names:
            raise WorkflowContractError(f"component_counts name 重复：{name}")
        names.add(name)

        physical_count = item.get("physical_count")
        if type(physical_count) is not int or physical_count <= 0:
            raise WorkflowContractError(
                f"component_counts {name} 的 physical_count 必须为正整数"
            )
        source_views = item.get("source_views")
        if not isinstance(source_views, list) or not source_views:
            raise WorkflowContractError(
                f"component_counts {name} 的 source_views 必须是非空列表"
            )
        if any(
            not isinstance(view, str) or COUNT_SOURCE_PATTERN.fullmatch(view) is None
            for view in source_views
        ):
            raise WorkflowContractError(
                f"component_counts {name} 的数量证据只能来自目标产品 front、side 或 detail_NN，禁止 reference"
            )
        if len(source_views) != len(set(source_views)):
            raise WorkflowContractError(
                f"component_counts {name} 的 source_views 不得重复"
            )
        item["name"] = name
        item["source_views"] = list(source_views)

    if category == "beaded_bracelet" and not normalized:
        raise WorkflowContractError("手串必须冻结可确认的精确珠数，无法确认时禁止生成")
    return normalized


def validate_product_analysis(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WorkflowContractError("产品分析必须是字典")

    normalized = copy.deepcopy(data)
    if type(normalized.get("schema_version")) is not int or normalized["schema_version"] != 1:
        raise WorkflowContractError("产品分析 schema_version 必须为 1")
    normalized["product_id"] = _validate_product_id(normalized.get("product_id"))

    category = normalized.get("category")
    if not isinstance(category, str) or category not in CATEGORY_TO_FEISHU:
        raise WorkflowContractError("产品品类必须属于固定九类之一")

    product_unit = normalized.get("product_unit")
    if not isinstance(product_unit, str) or product_unit not in {
        "single",
        "matched_earring_pair",
    }:
        raise WorkflowContractError("产品单位必须为单品或成对耳饰")

    piece_count = normalized.get("physical_piece_count")
    if type(piece_count) is not int or piece_count <= 0:
        raise WorkflowContractError("实物件数必须为正整数")

    silhouette = normalized.get("silhouette")
    if not isinstance(silhouette, str) or not silhouette.strip():
        raise WorkflowContractError("产品轮廓不能为空")
    normalized["silhouette"] = silhouette.strip()

    for field in ANALYSIS_LIST_FIELDS:
        if not isinstance(normalized.get(field), list):
            raise WorkflowContractError(f"产品分析字段 {field} 必须是列表")

    normalized["component_counts"] = validate_component_counts(
        normalized["component_counts"], category
    )
    if normalized["component_counts"] and any(
        COUNT_UNCERTAINTY_PATTERN.search(item)
        for item in normalized["uncertain_features"]
        if isinstance(item, str)
    ):
        raise WorkflowContractError("已冻结精确珠数时，不得同时把总珠数声明为未知")

    if category == "earrings":
        if product_unit == "matched_earring_pair" and piece_count != 2:
            raise WorkflowContractError("成对耳饰的实物件数必须为 2")
        if product_unit == "single" and piece_count != 1:
            raise WorkflowContractError("单只耳饰的实物件数必须为 1")
    elif product_unit != "single" or piece_count != 1:
        raise WorkflowContractError("非耳饰品类必须为一件单品")

    return normalized


def _read_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowContractError(f"无法读取{description}：{path}") from exc
    if not isinstance(data, dict):
        raise WorkflowContractError(f"{description}必须是 JSON 对象")
    return data


def freeze_product_analysis(
    run_root: str | Path, data: dict[str, Any]
) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json_object(state_path, "运行状态")
    if state.get("state") != "prepared":
        raise WorkflowContractError("仅 prepared 状态可以冻结产品分析")

    manifest = _read_json_object(
        root / "input" / "input_manifest.json", "输入清单"
    )
    normalized = validate_product_analysis(data)
    if normalized["product_id"] != manifest.get("product_id"):
        raise WorkflowContractError("产品分析中的产品 ID 与输入清单不一致")

    analysis_path = root / "analysis" / "product_analysis.json"
    _atomic_write_json(analysis_path, normalized)
    analysis_digest = sha256_file(analysis_path)
    _atomic_write_text(
        root / "analysis" / "product_analysis.sha256", analysis_digest + "\n"
    )

    next_state = dict(state)
    next_state["state"] = "awaiting_reference_review"
    _atomic_write_json(state_path, next_state)
    return normalized


def model_for_non_pass_count(non_pass_attempts: int) -> str:
    if type(non_pass_attempts) is not int or not 0 <= non_pass_attempts <= 3:
        raise WorkflowContractError("非 pass 次数必须是 0 至 3 的整数")
    if non_pass_attempts < 2:
        return "gpt_image_2"
    return "nano_banana_v2"
