from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from product_hero_workflow import (  # noqa: E402
    WorkflowContractError,
    model_for_non_pass_count,
    sha256_file,
    validate_component_counts,
)


SUPPORTED_ASPECT_RATIOS = (
    "1:1",
    "3:2",
    "2:3",
    "4:3",
    "3:4",
    "5:4",
    "4:5",
    "16:9",
    "9:16",
    "21:9",
)

REJECT_CODES = (
    "product_category_mismatch",
    "product_unit_mismatch",
    "product_structure_mismatch",
    "component_relationship_mismatch",
    "distinctive_feature_missing",
    "source_view_conflict",
)
RERUN_CODES = (
    "material_color_drift",
    "component_count_mismatch",
    "product_crop",
    "reference_product_residue",
    "scene_layout_drift",
    "prop_or_background_drift",
    "text_watermark_logo",
    "contact_shadow_error",
    "source_background_leakage",
    "generation_artifact",
)

RERUN_PROMPT_GUIDANCE = {
    "material_color_drift": "严格保持目标产品的材质、颜色、透明度、纹理和反光，不得偏色或改材质",
    "component_count_mismatch": "严格遵守已冻结的部件实体总数，遮挡只改变可见数量，不得新增、复制、删除、拆分或合并部件",
    "product_crop": "目标商品必须完整入镜，不得裁切主体或关键结构",
    "reference_product_residue": "彻底移除图1中的原商品，不得残留、叠加或融合参考商品",
    "scene_layout_drift": "严格保持图1的构图、机位、视觉高度和主体位置关系",
    "prop_or_background_drift": "严格保持图1的道具、背景和空间关系，不得替换或新增场景元素",
    "text_watermark_logo": "画面不得出现文字、水印、logo 或平台标识",
    "contact_shadow_error": "保持商品与承托面或道具的真实接触，阴影、反射和遮挡必须符合光线与空间关系",
    "source_background_leakage": "不得迁移产品源图的白色、中性背景、边缘或抠图痕迹",
    "generation_artifact": "清除多余重影、粘连、破碎边缘和不符合现实的生成痕迹，保持商品结构完整",
}
CHECKLIST_CHECK_IDS = (
    "product_category",
    "product_unit",
    "component_topology",
    "component_counts",
    "component_relationships",
    "distinctive_features",
    "material_color_texture",
    "complete_uncropped",
    "reference_product_removed",
    "scene_layout",
    "background_props",
    "lighting",
    "contact_shadow_reflection",
    "source_background_leakage",
    "text_watermark_logo",
    "generation_artifacts",
)
AIREITER_SUBMIT_ENDPOINT = "https://aireiter.com/api/openapi/submit"
AIREITER_QUERY_ENDPOINT = "https://aireiter.com/api/openapi/query"


class GenerationContractError(WorkflowContractError):
    """生成、QC 或交付数据不符合珠宝主图工作流契约。"""


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GenerationContractError(f"无法读取{description}：{path}") from exc
    if not isinstance(data, dict):
        raise GenerationContractError(f"{description}必须是 JSON 对象")
    return data


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
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
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, data: Any) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _string_list(value: Any, description: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = "非空字符串列表" if nonempty else "字符串列表"
        raise GenerationContractError(f"{description}必须是{suffix}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise GenerationContractError(f"{description}必须是字符串列表且项目不能为空")
    return [item.strip() for item in value]


def validate_fidelity_constraints(
    data: dict[str, Any], product_analysis: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise GenerationContractError("产品保真约束必须是字典")
    if not isinstance(product_analysis, dict):
        raise GenerationContractError("产品分析必须是字典")
    normalized = copy.deepcopy(data)
    if type(normalized.get("schema_version")) is not int or normalized["schema_version"] != 1:
        raise GenerationContractError("产品保真约束 schema_version 必须为 1")
    for field, label in (("product_id", "产品 ID"), ("category", "产品品类")):
        value = normalized.get(field)
        if not isinstance(value, str) or not value.strip():
            raise GenerationContractError(f"{label}不能为空")
        value = value.strip()
        if value != product_analysis.get(field):
            raise GenerationContractError(f"产品保真约束中的{label}与产品分析不一致")
        normalized[field] = value

    must_keep = normalized.get("must_keep")
    if not isinstance(must_keep, list) or not must_keep:
        raise GenerationContractError("must_keep 必须是非空列表")
    names: set[str] = set()
    for index, item in enumerate(must_keep, start=1):
        if not isinstance(item, dict):
            raise GenerationContractError(f"must_keep 第 {index} 项必须是字典")
        name = item.get("name")
        question = item.get("qc_question")
        if not isinstance(name, str) or not name.strip():
            raise GenerationContractError(f"must_keep 第 {index} 项 name 不能为空")
        name = name.strip()
        if name in names:
            raise GenerationContractError(f"must_keep name 重复：{name}")
        names.add(name)
        if not isinstance(question, str) or not question.strip():
            raise GenerationContractError(f"must_keep 第 {index} 项 qc_question 不能为空")
        item["name"] = name
        item["source_views"] = _string_list(
            item.get("source_views"), f"must_keep {name} 的 source_views", nonempty=True
        )
        item["qc_question"] = question.strip()
    normalized["must_not_change"] = _string_list(
        normalized.get("must_not_change"), "must_not_change"
    )
    normalized["uncertain_features"] = _string_list(
        normalized.get("uncertain_features"), "uncertain_features"
    )
    try:
        normalized_counts = validate_component_counts(
            normalized.get("component_counts"), normalized["category"]
        )
        analysis_counts = validate_component_counts(
            product_analysis.get("component_counts"), product_analysis.get("category")
        )
    except WorkflowContractError as exc:
        raise GenerationContractError(str(exc)) from exc
    if normalized_counts != analysis_counts:
        raise GenerationContractError("产品保真约束的组件数量必须与产品分析完全一致")
    normalized["component_counts"] = normalized_counts
    return normalized


def freeze_fidelity_constraints(run_root: str | Path, data: dict[str, Any]) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json(state_path, "运行状态")
    if state.get("state") != "ready_to_generate":
        raise GenerationContractError("仅 ready_to_generate 状态可以冻结产品保真约束")
    target = root / "analysis" / "fidelity_constraints.json"
    digest_path = root / "analysis" / "fidelity_constraints.sha256"
    if target.exists() or digest_path.exists():
        raise GenerationContractError("产品保真约束已存在，禁止覆盖")
    analysis_path = root / "analysis" / "product_analysis.json"
    analysis = _read_json(analysis_path, "产品分析")
    manifest_path = root / "input" / "input_manifest.json"
    _read_json(manifest_path, "输入清单")
    try:
        manifest_digest = sha256_file(manifest_path)
        analysis_sidecar_digest = (
            root / "analysis" / "product_analysis.sha256"
        ).read_text(encoding="utf-8").strip()
        analysis_digest = sha256_file(analysis_path)
    except (OSError, UnicodeError, WorkflowContractError) as exc:
        raise GenerationContractError("无法校验产品分析哈希") from exc
    if analysis_sidecar_digest != analysis_digest:
        raise GenerationContractError("产品分析哈希 sidecar 与实际文件不一致")
    normalized = validate_fidelity_constraints(data, analysis)
    original_state = state_path.read_bytes()
    created: list[Path] = []
    try:
        _atomic_write_json(target, normalized)
        created.append(target)
        digest = sha256_file(target)
        _atomic_write_text(digest_path, digest + "\n")
        created.append(digest_path)
        next_state = dict(state)
        next_state["input_manifest_sha256"] = manifest_digest
        next_state["product_analysis_sha256"] = analysis_digest
        next_state["fidelity_constraints_sha256"] = digest
        _atomic_write_json(state_path, next_state)
    except Exception as exc:
        for path in reversed(created):
            if path.exists():
                path.unlink()
        state_path.write_bytes(original_state)
        if isinstance(exc, GenerationContractError):
            raise
        raise GenerationContractError("冻结产品保真约束失败，已回滚") from exc
    return normalized


def _jpeg_size(data: bytes) -> tuple[int, int]:
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                break
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    raise GenerationContractError("JPEG 图片损坏，无法读取宽高")


def _webp_size(data: bytes) -> tuple[int, int]:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and len(data) >= 30:
        start = data.find(b"\x9d\x01\x2a", 20)
        if start >= 0 and start + 7 <= len(data):
            width, height = struct.unpack_from("<HH", data, start + 3)
            return width & 0x3FFF, height & 0x3FFF
    raise GenerationContractError("WebP 图片损坏，无法读取宽高")


def read_image_size(path: str | Path) -> tuple[int, int]:
    image_path = Path(path)
    suffix = image_path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise GenerationContractError(f"图片格式不支持：{suffix or '无扩展名'}")
    try:
        data = image_path.read_bytes()
    except OSError as exc:
        raise GenerationContractError(f"无法读取图片：{image_path}") from exc
    if suffix == ".png":
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise GenerationContractError("PNG 图片损坏，无法读取宽高")
        width, height = struct.unpack_from(">II", data, 16)
    elif suffix in {".jpg", ".jpeg"}:
        if not data.startswith(b"\xff\xd8"):
            raise GenerationContractError("JPEG 图片损坏，无法读取宽高")
        width, height = _jpeg_size(data)
    else:
        if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            raise GenerationContractError("WebP 图片损坏，无法读取宽高")
        width, height = _webp_size(data)
    if width <= 0 or height <= 0:
        raise GenerationContractError("图片宽高必须为正整数")
    return width, height


def nearest_aspect_ratio(width: int, height: int) -> str:
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise GenerationContractError("图片宽高必须为正整数")
    actual = width / height
    return min(
        SUPPORTED_ASPECT_RATIOS,
        key=lambda item: abs(math.log(actual / (int(item.split(":")[0]) / int(item.split(":")[1])))),
    )


PROMPT_REQUIRED_FRAGMENTS = (
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
    "参考图原商品的数量、珠数、珠距、排列和被遮挡部分均不得作为目标商品结构依据",
    "遮挡只改变可见数量，不改变实体总数",
    "不得为了填满参考图圆环",
    "优先保持实体数量",
)
PROMPT_TITLES = (
    "【任务目标】",
    "【图片职责】",
    "【产品保真】",
    "【场景保持】",
    "【禁止项】",
)


def _verify_digest(path: Path, expected: Any, description: str) -> str:
    if not isinstance(expected, str) or not expected:
        raise GenerationContractError(f"{description}缺少已冻结哈希")
    try:
        actual = sha256_file(path)
    except WorkflowContractError as exc:
        raise GenerationContractError(f"无法校验{description}哈希") from exc
    if actual != expected:
        raise GenerationContractError(f"{description}哈希不一致，可能已被篡改")
    return actual


def _frozen_digest(state: dict[str, Any], path: Path, key: str, description: str) -> str:
    expected = state.get(key)
    if expected is None:
        digest_path = path.with_suffix(".sha256")
        try:
            expected = digest_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise GenerationContractError(f"{description}缺少已冻结哈希") from exc
    return _verify_digest(path, expected, description)


def _required_state_and_sidecar_digest(
    state: dict[str, Any], path: Path, key: str, description: str
) -> str:
    expected = state.get(key)
    if not isinstance(expected, str) or not expected:
        raise GenerationContractError(f"运行状态缺少{description}哈希：{key}")
    actual = _verify_digest(path, expected, description)
    sidecar = path.with_suffix(".sha256")
    try:
        sidecar_digest = sidecar.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise GenerationContractError(f"无法读取{description}哈希 sidecar") from exc
    if sidecar_digest != expected:
        raise GenerationContractError(f"{description}哈希 sidecar 与运行状态不一致")
    return actual


def _run_path(root: Path, relative: Any, description: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise GenerationContractError(f"{description}必须是 run 内相对路径")
    try:
        resolved_root = root.resolve()
        resolved = (root / relative).resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise GenerationContractError(f"{description}必须位于 run 内，禁止路径越界") from exc
    return resolved


def _current_attempt_dir(root: Path, state: dict[str, Any]) -> Path:
    current = state.get("current_attempt")
    if not isinstance(current, str) or re.fullmatch(r"generation/[0-9]{2,}", current) is None:
        raise GenerationContractError(
            "current_attempt 必须严格匹配 run 内 generation/NN 路径"
        )
    attempt_dir = _run_path(root, current, "current_attempt")
    attempt_json = attempt_dir / "attempt.json"
    if not attempt_dir.is_dir() or not attempt_json.is_file():
        raise GenerationContractError(
            "current_attempt 必须指向已存在且包含 attempt.json 的生成尝试目录"
        )
    attempt = _read_json(attempt_json, "生成尝试记录")
    if attempt.get("attempt_path") != current or attempt.get("attempt") != int(attempt_dir.name):
        raise GenerationContractError("current_attempt 与 attempt.json 绑定不一致")
    return attempt_dir


def _recorded_visual_results(root: Path) -> int:
    generation_root = root / "generation"
    if not generation_root.is_dir():
        return 0
    return sum(
        1
        for path in generation_root.iterdir()
        if path.is_dir() and path.name.isdigit() and (path / "result.png").is_file()
    )


def _build_prompt(
    analysis: dict[str, Any],
    constraints: dict[str, Any],
    input_order: list[dict[str, Any]],
    retry_guidance: str = "",
) -> str:
    must_keep = "；".join(item["name"] for item in constraints["must_keep"])
    must_not_change = "；".join(constraints["must_not_change"]) or "无额外项目"
    uncertain = "；".join(constraints["uncertain_features"]) or "无"
    component_counts = constraints["component_counts"]
    if component_counts:
        count_facts = "；".join(
            f"{item['name']}实体总数固定为且仅为{item['physical_count']}颗"
            for item in component_counts
        )
    else:
        count_facts = "没有已冻结的重复部件精确数量，实体结构仍只以目标产品图为准"
    unit_rule = (
        "只出现一个商品单元；成对耳饰必须恰好两只，且两只属于同一商品单元。"
        if analysis.get("product_unit") == "matched_earring_pair"
        else "只出现一个商品单元。"
    )
    last_number = len(input_order)
    if not 4 <= last_number <= 7:
        raise GenerationContractError("生成输入总数必须为 4 至 7 张")
    detail_label = "图4" if last_number == 4 else f"图4–{last_number}"
    retry_line = f"【强化要求】{retry_guidance}。" if retry_guidance else ""
    return (
        "【任务目标】\n"
        f"以图1的场景为唯一场景模板，将图2–{last_number}中的目标珠宝准确置入，生成真实商品主图。\n"
        "【图片职责】\n"
        "图1仅负责场景，不提供目标商品结构；图2正面图具有最高优先级；"
        f"图3只补充侧面厚度、弧度和连接关系；{detail_label}只补充局部材质。\n"
        "【产品保真】\n"
        f"必须保持：{must_keep}。不得改变：{must_not_change}。不确定特征：{uncertain}。"
        f"数量与遮挡：{count_facts}。"
        "参考图原商品的数量、珠数、珠距、排列和被遮挡部分均不得作为目标商品结构依据。"
        "允许参考场景中的前景道具自然遮挡目标商品的部分部件；遮挡只改变可见数量，不改变实体总数。"
        "不得为了填满参考图圆环、匹配参考商品尺寸或补足遮挡弧段而新增、复制、拆分、合并或删除部件。"
        "场景构图与数量冲突时优先保持实体数量，允许调整目标商品的整体尺寸、位置和旋转。"
        f"{retry_line}"
        "多视图冲突时立即停止，不可见结构不得补造。\n"
        "【场景保持】\n"
        "构图、机位、道具、背景、光线和视觉高度保持一致；"
        "产品源图的白色或中性背景不得迁移。\n"
        "【禁止项】\n"
        "移除参考图原商品、文字、水印和 logo；禁止残留源背景；"
        f"{unit_rule}"
    )


def _previous_rerun_guidance(root: Path) -> str:
    generation_root = root / "generation"
    if not generation_root.is_dir():
        return ""
    attempts = sorted(
        (
            path
            for path in generation_root.iterdir()
            if path.is_dir() and path.name.isdigit() and (path / "qc.json").is_file()
        ),
        key=lambda path: int(path.name),
        reverse=True,
    )
    if not attempts:
        return ""
    qc = _read_json(attempts[0] / "qc.json", "上一轮 QC")
    if qc.get("status") != "rerun":
        return ""
    failure_codes = qc.get("failure_codes")
    if not isinstance(failure_codes, list) or not failure_codes:
        raise GenerationContractError("上一轮 rerun QC 缺少 failure_codes")
    guidance: list[str] = []
    for code in failure_codes:
        instruction = RERUN_PROMPT_GUIDANCE.get(code)
        if instruction is None:
            raise GenerationContractError(f"上一轮 rerun QC 无可用纠偏指令：{code}")
        if instruction not in guidance:
            guidance.append(instruction)
    return "；".join(guidance)


def _validated_user_selection_evidence(
    decision: dict[str, Any], selected_rank: Any
) -> dict[str, Any]:
    evidence = decision.get("user_selection_evidence")
    if not isinstance(evidence, dict):
        raise GenerationContractError("人工决策缺少用户选择证据")
    if evidence.get("source") not in {"user_message", "user_interface"}:
        raise GenerationContractError("人工决策用户选择证据 source 无效")
    if evidence.get("selected_rank") != selected_rank:
        raise GenerationContractError("人工决策用户选择证据 rank 不一致")
    if not isinstance(evidence.get("verbatim"), str) or not evidence["verbatim"].strip():
        raise GenerationContractError("人工决策用户选择证据 verbatim 不能为空")
    return copy.deepcopy(evidence)


def build_generation_contract(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root)
    state = _read_json(root / "state.json", "运行状态")
    if state.get("state") != "ready_to_generate":
        raise GenerationContractError("仅 ready_to_generate 状态可以构建生成契约")

    manifest_path = root / "input" / "input_manifest.json"
    analysis_path = root / "analysis" / "product_analysis.json"
    constraints_path = root / "analysis" / "fidelity_constraints.json"
    top3_path = root / "review" / "top3.json"
    decision_path = root / "review" / "decision.json"
    if "input_manifest_sha256" in state:
        _verify_digest(
            manifest_path, state["input_manifest_sha256"], "输入清单"
        )
    analysis_digest = _required_state_and_sidecar_digest(
        state, analysis_path, "product_analysis_sha256", "产品分析"
    )
    constraints_digest = _frozen_digest(
        state, constraints_path, "fidelity_constraints_sha256", "产品保真约束"
    )
    top3_digest = _verify_digest(top3_path, state.get("top3_sha256"), "Top 3 快照")
    if "decision_sha256" in state:
        _verify_digest(decision_path, state["decision_sha256"], "人工决策")

    manifest = _read_json(manifest_path, "输入清单")
    analysis = _read_json(analysis_path, "产品分析")
    constraints = _read_json(constraints_path, "产品保真约束")
    top3 = _read_json(top3_path, "Top 3 快照")
    decision = _read_json(decision_path, "人工决策")
    validate_fidelity_constraints(constraints, analysis)
    if decision.get("product_analysis_sha256") != analysis_digest:
        raise GenerationContractError("人工决策绑定的产品分析哈希不一致")
    if decision.get("top3_sha256") != top3_digest:
        raise GenerationContractError("人工决策绑定的 Top 3 哈希不一致")
    if constraints_digest != state.get("fidelity_constraints_sha256"):
        raise GenerationContractError("产品保真约束哈希不一致")

    items = top3.get("items")
    selected_rank = decision.get("selected_rank")
    if not isinstance(items, list):
        raise GenerationContractError("Top 3 快照 items 必须是列表")
    selected = next(
        (item for item in items if isinstance(item, dict) and item.get("rank") == selected_rank),
        None,
    )
    if selected is None:
        raise GenerationContractError("人工决策 rank 未绑定到 Top 3")
    _validated_user_selection_evidence(decision, selected_rank)
    for field in ("record_id", "material_id", "selected_reference", "image_sha256"):
        if decision.get(field) != selected.get(field):
            raise GenerationContractError(f"人工决策字段 {field} 与 Top 3 绑定不一致")
    reference_relative = decision["selected_reference"]
    reference_path = _run_path(root, reference_relative, "选中参考副本路径")
    _verify_digest(reference_path, decision.get("image_sha256"), "选中参考副本")

    images = manifest.get("images")
    if not isinstance(images, list):
        raise GenerationContractError("输入清单 images 必须是列表")
    expected_roles = ["front", "side"] + [
        f"detail_{index:02d}" for index in range(1, max(len(images) - 1, 1))
    ]
    actual_roles = [item.get("role") if isinstance(item, dict) else None for item in images]
    if actual_roles != expected_roles:
        raise GenerationContractError("输入清单角色必须按 front、side、连续 detail 顺序排列")
    input_order = [
        {
            "role": "reference",
            "path": Path(reference_relative).as_posix(),
            "sha256": decision["image_sha256"],
        }
    ]
    for item in images:
        relative = item.get("path")
        image_path = _run_path(root, relative, "输入图片路径")
        _verify_digest(image_path, item.get("sha256"), f"输入图片 {item.get('role')}")
        input_order.append(
            {"role": item["role"], "path": Path(relative).as_posix(), "sha256": item["sha256"]}
        )
    prompt = _build_prompt(
        analysis,
        constraints,
        input_order,
        retry_guidance=_previous_rerun_guidance(root),
    )
    errors = validate_prompt_contract(prompt, input_order)
    if errors:
        raise GenerationContractError("Prompt 契约无效：" + "；".join(errors))
    width, height = read_image_size(reference_path)
    return {
        "prompt": prompt,
        "aspect_ratio": nearest_aspect_ratio(width, height),
        "model": model_for_non_pass_count(state.get("non_pass_attempts", 0)),
        "input_order": input_order,
    }


def validate_prompt_contract(prompt: str, input_order: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(prompt, str):
        return ["Prompt 必须是字符串"]
    for fragment in PROMPT_REQUIRED_FRAGMENTS:
        if fragment not in prompt:
            errors.append(f"Prompt 缺少固定内容：{fragment}")
    if isinstance(input_order, list) and 4 <= len(input_order) <= 7:
        last_number = len(input_order)
        detail_label = "图4" if last_number == 4 else f"图4–{last_number}"
        for fragment in (
            f"图2–{last_number}中的目标珠宝",
            f"{detail_label}只补充局部材质",
        ):
            if fragment not in prompt:
                errors.append(f"Prompt 图片编号与输入数量不一致：缺少 {fragment}")
    title_positions: list[int] = []
    for title in PROMPT_TITLES:
        count = prompt.count(title)
        if count != 1:
            errors.append(f"Prompt 标题必须恰好出现一次：{title}，实际 {count} 次")
        title_positions.append(prompt.find(title))
    if all(position >= 0 for position in title_positions) and title_positions != sorted(title_positions):
        errors.append("Prompt 五个固定标题顺序错误")
    for marker in ("???", "锟", "�"):
        if marker in prompt:
            errors.append(f"Prompt 含 UTF-8 乱码片段：{marker}")
    if not isinstance(input_order, list):
        errors.append("输入顺序必须是列表")
        return errors
    roles = [item.get("role") if isinstance(item, dict) else None for item in input_order]
    expected = ["reference", "front", "side"] + [
        f"detail_{index:02d}" for index in range(1, max(len(roles) - 2, 1))
    ]
    if roles != expected:
        errors.append("图片角色必须按 reference、front、side、连续 detail 顺序排列")
    for index, item in enumerate(input_order, start=1):
        if not isinstance(item, dict):
            errors.append(f"第 {index} 个输入必须是字典")
            continue
        if not isinstance(item.get("path"), str) or not item["path"]:
            errors.append(f"第 {index} 个输入缺少相对路径")
        elif Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
            errors.append(f"第 {index} 个输入路径必须是 run 内相对路径且不得越界")
        digest = item.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            errors.append(f"第 {index} 个输入缺少 64 位十六进制 sha256")
    return errors


def prepare_generation_attempt(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json(state_path, "运行状态")
    if state.get("state") != "ready_to_generate":
        raise GenerationContractError("仅 ready_to_generate 状态可以提交生成尝试")
    visual_count = state.get("generation_attempts", 0)
    if type(visual_count) is not int or visual_count < 0:
        raise GenerationContractError("视觉结果次数必须是非负整数")
    generation_root = root / "generation"
    recorded_results = _recorded_visual_results(root)
    if max(visual_count, recorded_results) >= 4:
        raise GenerationContractError("视觉结果已达到 4 次上限，禁止继续生成")
    if not (root / "analysis" / "fidelity_constraints.json").is_file():
        raise GenerationContractError("提交生成前必须冻结产品保真约束")

    contract = build_generation_contract(root)
    existing_numbers = [
        int(path.name)
        for path in generation_root.iterdir()
        if path.is_dir() and path.name.isdigit()
    ] if generation_root.is_dir() else []
    attempt_number = max(existing_numbers, default=0) + 1
    attempt_relative = (Path("generation") / f"{attempt_number:02d}").as_posix()
    attempt_dir = root / attempt_relative
    if attempt_dir.exists():
        raise GenerationContractError(f"生成尝试目录已存在，禁止覆盖：{attempt_relative}")
    attempt = {
        "schema_version": 1,
        "attempt": attempt_number,
        "attempt_path": attempt_relative,
        **contract,
    }

    generation_created = not generation_root.exists()
    try:
        original_state = state_path.read_bytes()
        generation_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".attempt-", dir=generation_root))
    except OSError as exc:
        if generation_created and generation_root.is_dir():
            try:
                if not any(generation_root.iterdir()):
                    generation_root.rmdir()
            except OSError:
                pass
        raise GenerationContractError("无法创建生成尝试临时目录") from exc
    committed = False
    try:
        _atomic_write_text(temporary / "prompt.txt", contract["prompt"])
        _atomic_write_text(temporary / "model.txt", contract["model"] + "\n")
        _atomic_write_text(temporary / "aspect_ratio.txt", contract["aspect_ratio"] + "\n")
        _atomic_write_json(temporary / "input_order.json", contract["input_order"])
        _atomic_write_json(temporary / "attempt.json", attempt)
        attempt_digest = sha256_file(temporary / "attempt.json")
        temporary.replace(attempt_dir)
        committed = True
        next_state = dict(state)
        next_state["state"] = "generating"
        next_state["submission_attempts"] = state.get("submission_attempts", 0) + 1
        next_state["current_attempt"] = attempt_relative
        next_state["current_attempt_sha256"] = attempt_digest
        _atomic_write_json(state_path, next_state)
    except Exception as exc:
        try:
            if committed and attempt_dir.exists():
                shutil.rmtree(attempt_dir)
            elif temporary.exists():
                shutil.rmtree(temporary)
            state_path.write_bytes(original_state)
            if (
                generation_created
                and generation_root.exists()
                and not any(generation_root.iterdir())
            ):
                generation_root.rmdir()
        except OSError as rollback_exc:
            raise GenerationContractError("生成尝试失败，且无法完整回滚") from rollback_exc
        if isinstance(exc, GenerationContractError):
            raise
        raise GenerationContractError("生成尝试失败，已回滚本轮产物") from exc
    return attempt


def record_infrastructure_failure(run_root: str | Path, error: Any) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json(state_path, "运行状态")
    if state.get("state") != "generating":
        raise GenerationContractError("仅 generating 状态可以记录基础设施失败")
    attempt_dir = _current_attempt_dir(root, state)
    _verify_digest(
        attempt_dir / "attempt.json",
        state.get("current_attempt_sha256"),
        "生成尝试",
    )
    target = attempt_dir / "infrastructure_error.json"
    if target.exists():
        raise GenerationContractError("基础设施失败记录已存在，禁止覆盖")
    payload = copy.deepcopy(error) if isinstance(error, dict) else {"error": str(error)}
    original_state = state_path.read_bytes()
    created = False
    try:
        _atomic_write_json(target, payload)
        created = True
        next_state = dict(state)
        next_state["state"] = "ready_to_generate"
        _atomic_write_json(state_path, next_state)
    except Exception as exc:
        try:
            if created and target.exists():
                target.unlink()
            state_path.write_bytes(original_state)
        except OSError as rollback_exc:
            raise GenerationContractError("基础设施失败记录写入失败，且无法完整回滚") from rollback_exc
        if isinstance(exc, GenerationContractError):
            raise
        raise GenerationContractError("基础设施失败记录写入失败，已回滚") from exc
    return next_state


def _validate_aireiter_receipts(
    attempt_dir: Path,
    submit_data: dict[str, Any],
    result_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = _read_json(attempt_dir / "attempt.json", "生成尝试记录")
    try:
        input_items = json.loads(
            (attempt_dir / "input_order.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GenerationContractError("无法读取生成输入顺序") from exc
    if not isinstance(input_items, list):
        raise GenerationContractError("生成输入顺序必须是 JSON 数组")
    if input_items != attempt.get("input_order"):
        raise GenerationContractError("生成输入顺序与 attempt.json 不一致")
    try:
        prompt_text = (attempt_dir / "prompt.txt").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise GenerationContractError("无法读取生成 Prompt") from exc
    if prompt_text != attempt.get("prompt"):
        raise GenerationContractError("生成 Prompt 与 attempt.json 不一致")

    if submit_data.get("schema_version") != 1 or submit_data.get("provider") != "aireiter":
        raise GenerationContractError("AIReiter 提交回执 schema_version/provider 无效")
    if submit_data.get("endpoint") != AIREITER_SUBMIT_ENDPOINT:
        raise GenerationContractError("AIReiter 提交回执 endpoint 无效")
    task_id = submit_data.get("out_task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise GenerationContractError("AIReiter 提交回执缺少 out_task_id")
    task_id = task_id.strip()
    request = submit_data.get("request_contract")
    if not isinstance(request, dict):
        raise GenerationContractError("AIReiter 提交回执缺少 request_contract")
    expected_request = {
        "model": attempt.get("model"),
        "prompt_sha256": sha256_file(attempt_dir / "prompt.txt"),
        "aspect_ratio": attempt.get("aspect_ratio"),
        "resolution": "2K",
        "input_sha256": [item.get("sha256") for item in input_items],
    }
    if request != expected_request:
        raise GenerationContractError("AIReiter 请求契约与生成尝试不一致")

    submit_response = submit_data.get("response")
    if not isinstance(submit_response, dict):
        raise GenerationContractError("AIReiter 提交回执 response 必须是对象")
    status_code = submit_response.get("statusCode")
    if (
        isinstance(status_code, int) and status_code >= 400
    ) or (
        isinstance(status_code, str)
        and status_code.isdigit()
        and int(status_code) >= 400
    ):
        raise GenerationContractError("AIReiter 提交未被接受")
    submit_message = str(
        submit_response.get("message") or submit_response.get("error") or ""
    ).lower()
    if any(
        marker in submit_message
        for marker in (
            "not enough credits",
            "insufficient credit",
            "forbidden",
            "unauthorized",
            "failed",
            "error",
        )
    ):
        raise GenerationContractError("AIReiter 提交未被接受")
    submit_payload = submit_response.get("data")
    if not isinstance(submit_payload, dict):
        raise GenerationContractError("AIReiter 提交回执缺少 data")
    submit_status = str(submit_payload.get("status") or "").lower()
    submit_task_id = str(submit_payload.get("out_task_id") or "").strip()
    if submit_task_id and submit_task_id != task_id:
        raise GenerationContractError("AIReiter 提交任务 ID 与回执不一致")
    if submit_status not in {"pending", "processing", "completed"} and not submit_task_id:
        raise GenerationContractError("AIReiter 提交回执无法证明任务已接受")

    if result_data.get("schema_version") != 1 or result_data.get("provider") != "aireiter":
        raise GenerationContractError("AIReiter 结果回执 schema_version/provider 无效")
    if result_data.get("endpoint") != AIREITER_QUERY_ENDPOINT:
        raise GenerationContractError("AIReiter 结果回执 endpoint 无效")
    if result_data.get("out_task_id") != task_id:
        raise GenerationContractError("AIReiter 提交与结果任务 ID 不一致")
    result_response = result_data.get("response")
    if not isinstance(result_response, dict):
        raise GenerationContractError("AIReiter 结果回执 response 必须是对象")
    result_payload = result_response.get("data")
    if not isinstance(result_payload, dict) or result_payload.get("status") != "completed":
        raise GenerationContractError("AIReiter 任务尚未 completed")
    result_task_id = str(result_payload.get("out_task_id") or "").strip()
    if result_task_id and result_task_id != task_id:
        raise GenerationContractError("AIReiter 查询任务 ID 与回执不一致")
    outputs = result_payload.get("output")
    if not isinstance(outputs, list) or not outputs:
        raise GenerationContractError("AIReiter completed 结果缺少 output")
    output_urls = {
        item.get("url")
        for item in outputs
        if isinstance(item, dict)
        and isinstance(item.get("url"), str)
        and item["url"].strip()
    }
    selected_output_url = result_data.get("selected_output_url")
    if not isinstance(selected_output_url, str) or selected_output_url not in output_urls:
        raise GenerationContractError("AIReiter 结果回执未绑定有效 output URL")
    return copy.deepcopy(submit_data), copy.deepcopy(result_data)


def record_generation_result(
    run_root: str | Path, submit_data: Any, result_data: Any
) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json(state_path, "运行状态")
    if state.get("state") != "generating":
        raise GenerationContractError("仅 generating 状态可以记录生成结果")
    if not isinstance(submit_data, dict) or not isinstance(result_data, dict):
        raise GenerationContractError("提交数据和结果数据必须是 JSON 对象")
    visual_count = state.get("generation_attempts", 0)
    if type(visual_count) is not int or visual_count < 0:
        raise GenerationContractError("视觉结果次数必须是非负整数")
    if max(visual_count, _recorded_visual_results(root)) >= 4:
        raise GenerationContractError("视觉结果已达到 4 次上限，禁止记录更多结果")
    attempt_dir = _current_attempt_dir(root, state)
    _verify_digest(
        attempt_dir / "attempt.json",
        state.get("current_attempt_sha256"),
        "生成尝试",
    )
    normalized_submit, normalized_result = _validate_aireiter_receipts(
        attempt_dir, submit_data, result_data
    )
    selected_output_url = normalized_result["selected_output_url"]
    if not selected_output_url.startswith("https://"):
        raise GenerationContractError("AIReiter output URL 必须使用 HTTPS")
    try:
        request = Request(
            selected_output_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                )
            },
        )
        with urlopen(request, timeout=60) as response:
            status_code = response.getcode()
            if isinstance(status_code, int) and status_code >= 400:
                raise GenerationContractError("AIReiter output URL 下载失败")
            source_bytes = response.read(50 * 1024 * 1024 + 1)
        if not source_bytes:
            raise GenerationContractError("AIReiter output URL 返回空文件")
        if len(source_bytes) > 50 * 1024 * 1024:
            raise GenerationContractError("AIReiter output 图片超过 50MB 上限")
        if (
            len(source_bytes) < 24
            or source_bytes[:8] != b"\x89PNG\r\n\x1a\n"
            or source_bytes[12:16] != b"IHDR"
        ):
            raise GenerationContractError("生成结果必须是真实 PNG 图片，不接受 JPEG/WebP")
        width, height = struct.unpack_from(">II", source_bytes, 16)
        if width <= 0 or height <= 0:
            raise GenerationContractError("生成结果 PNG 图片宽高必须为正整数")
        source_digest = hashlib.sha256(source_bytes).hexdigest()
    except GenerationContractError:
        raise
    except (OSError, ValueError) as exc:
        raise GenerationContractError("无法从 AIReiter output URL 下载生成结果") from exc
    targets = {
        "submit": attempt_dir / "submit.json",
        "result_data": attempt_dir / "result.json",
        "result_image": attempt_dir / "result.png",
    }
    if any(path.exists() for path in targets.values()):
        raise GenerationContractError("当前生成结果产物已存在，禁止覆盖")
    original_state = state_path.read_bytes()
    try:
        temporary = Path(tempfile.mkdtemp(prefix=".result-", dir=attempt_dir))
    except OSError as exc:
        raise GenerationContractError("无法创建生成结果临时目录") from exc
    committed: list[Path] = []
    try:
        _atomic_write_json(temporary / "submit.json", normalized_submit)
        result_document = normalized_result
        result_document["result_sha256"] = source_digest
        _atomic_write_json(temporary / "result.json", result_document)
        (temporary / "result.png").write_bytes(source_bytes)
        if sha256_file(temporary / "result.png") != source_digest:
            raise GenerationContractError("生成结果副本哈希与源文件不一致")
        for name, target in (
            ("submit.json", targets["submit"]),
            ("result.json", targets["result_data"]),
            ("result.png", targets["result_image"]),
        ):
            (temporary / name).replace(target)
            committed.append(target)
        next_state = dict(state)
        next_state["state"] = "awaiting_qc"
        next_state["generation_attempts"] = state.get("generation_attempts", 0) + 1
        next_state["current_submit_sha256"] = sha256_file(targets["submit"])
        next_state["current_result_record_sha256"] = sha256_file(
            targets["result_data"]
        )
        next_state["current_result_sha256"] = sha256_file(targets["result_image"])
        _atomic_write_json(state_path, next_state)
    except Exception as exc:
        try:
            for path in reversed(committed):
                if path.exists():
                    path.unlink()
            state_path.write_bytes(original_state)
        except OSError as rollback_exc:
            raise GenerationContractError("生成结果写入失败，且无法完整回滚") from rollback_exc
        if isinstance(exc, GenerationContractError):
            raise
        raise GenerationContractError("生成结果写入失败，已回滚本轮产物") from exc
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return next_state


def validate_qc_record(
    data: dict[str, Any], fidelity_constraints: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(fidelity_constraints, dict):
        raise GenerationContractError("QC 记录和产品保真约束必须是字典")
    normalized = copy.deepcopy(data)
    if normalized.get("schema_version") != 1 or type(normalized.get("schema_version")) is not int:
        raise GenerationContractError("QC schema_version 必须为 1")
    status = normalized.get("status")
    if not isinstance(status, str) or status not in {"pass", "rerun", "reject"}:
        raise GenerationContractError("QC status 仅允许 pass、rerun 或 reject")

    failure_codes = _string_list(normalized.get("failure_codes"), "failure_codes")
    if len(failure_codes) != len(set(failure_codes)):
        raise GenerationContractError("failure_codes 不得重复")
    allowed_codes = set(REJECT_CODES) | set(RERUN_CODES)
    unknown = sorted(set(failure_codes) - allowed_codes)
    if unknown:
        raise GenerationContractError(f"failure_codes 含未知代码：{unknown}")
    normalized["failure_codes"] = failure_codes

    checklist = normalized.get("checklist")
    if not isinstance(checklist, list):
        raise GenerationContractError("checklist 必须是列表")
    checklist_ids: list[str] = []
    for index, item in enumerate(checklist, start=1):
        if not isinstance(item, dict):
            raise GenerationContractError(f"checklist 第 {index} 项必须是字典")
        check_id = item.get("id")
        if not isinstance(check_id, str) or not check_id:
            raise GenerationContractError(f"checklist 第 {index} 项 id 无效")
        checklist_ids.append(check_id)
        result = item.get("result")
        if not isinstance(result, str) or result not in {"pass", "fail"}:
            raise GenerationContractError(f"checklist {check_id} result 仅允许 pass 或 fail")
        notes = item.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise GenerationContractError(f"checklist {check_id} notes 不能为空")
        item["notes"] = notes.strip()
    if len(checklist_ids) != len(set(checklist_ids)):
        raise GenerationContractError("checklist ID 不得重复")
    if set(checklist_ids) != set(CHECKLIST_CHECK_IDS) or len(checklist_ids) != len(CHECKLIST_CHECK_IDS):
        raise GenerationContractError("checklist ID 必须恰好一次完整覆盖固定检查项")

    try:
        expected_counts = validate_component_counts(
            fidelity_constraints.get("component_counts"),
            fidelity_constraints.get("category"),
        )
    except WorkflowContractError as exc:
        raise GenerationContractError(str(exc)) from exc
    component_count_checks = normalized.get("component_count_checks")
    if not isinstance(component_count_checks, list):
        raise GenerationContractError("component_count_checks 必须是列表")
    actual_counts: list[tuple[str, int]] = []
    for index, item in enumerate(component_count_checks, start=1):
        if not isinstance(item, dict):
            raise GenerationContractError(
                f"component_count_checks 第 {index} 项必须是字典"
            )
        name = item.get("name")
        expected = item.get("expected_physical_count")
        if not isinstance(name, str) or not name.strip():
            raise GenerationContractError("数量检查 name 不能为空")
        if type(expected) is not int or expected <= 0:
            raise GenerationContractError("数量检查 expected_physical_count 必须为正整数")
        name = name.strip()
        actual_counts.append((name, expected))
        item["name"] = name
        for field, label in (
            ("visible_count", "可见数量"),
            ("occluded_count", "遮挡数量"),
        ):
            value = item.get(field)
            if type(value) is not int or value < 0:
                raise GenerationContractError(f"数量检查的{label}必须是非负整数")
        evidence = item.get("occlusion_evidence")
        if not isinstance(evidence, str):
            raise GenerationContractError("数量检查的遮挡证据必须是字符串")
        if item["occluded_count"] > 0 and not evidence.strip():
            raise GenerationContractError("存在遮挡数量时必须提供具体遮挡证据")
        item["occlusion_evidence"] = evidence.strip()
        result = item.get("result")
        if not isinstance(result, str) or result not in {"pass", "fail"}:
            raise GenerationContractError("数量检查 result 仅允许 pass 或 fail")
        notes = item.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise GenerationContractError("数量检查 notes 不能为空")
        item["notes"] = notes.strip()
        if (
            result == "pass"
            and item["visible_count"] + item["occluded_count"] != expected
        ):
            raise GenerationContractError("数量检查通过时，可见数量与遮挡数量之和必须等于实体总数")
    expected_count_pairs = [
        (item["name"], item["physical_count"]) for item in expected_counts
    ]
    if actual_counts != expected_count_pairs:
        raise GenerationContractError(
            "component_count_checks 必须与冻结的组件实体数量按顺序完全一致"
        )

    must_keep = fidelity_constraints.get("must_keep")
    if not isinstance(must_keep, list):
        raise GenerationContractError("产品保真约束 must_keep 必须是列表")
    expected_fidelity: list[tuple[str, str]] = []
    for index, item in enumerate(must_keep, start=1):
        if not isinstance(item, dict):
            raise GenerationContractError(f"must_keep 第 {index} 项必须是字典")
        name = item.get("name")
        question = item.get("qc_question")
        if not isinstance(name, str) or not name.strip() or not isinstance(question, str) or not question.strip():
            raise GenerationContractError("must_keep 的 name 与 qc_question 不能为空")
        expected_fidelity.append((name.strip(), question.strip()))
    if len(expected_fidelity) != len(set(expected_fidelity)):
        raise GenerationContractError("must_keep 的 name+question 不得重复")

    fidelity_checks = normalized.get("fidelity_checks")
    if not isinstance(fidelity_checks, list):
        raise GenerationContractError("fidelity_checks 必须是列表")
    actual_fidelity: list[tuple[str, str]] = []
    for index, item in enumerate(fidelity_checks, start=1):
        if not isinstance(item, dict):
            raise GenerationContractError(f"fidelity_checks 第 {index} 项必须是字典")
        name = item.get("name")
        question = item.get("question")
        if not isinstance(name, str) or not name.strip() or not isinstance(question, str) or not question.strip():
            raise GenerationContractError("fidelity_checks 的 name 与 question 不能为空")
        pair = (name.strip(), question.strip())
        actual_fidelity.append(pair)
        item["name"], item["question"] = pair
        result = item.get("result")
        if not isinstance(result, str) or result not in {"pass", "fail"}:
            raise GenerationContractError(f"fidelity check {pair[0]} result 仅允许 pass 或 fail")
        notes = item.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise GenerationContractError(f"fidelity check {pair[0]} notes 不能为空")
        item["notes"] = notes.strip()
    if len(actual_fidelity) != len(set(actual_fidelity)):
        raise GenerationContractError("fidelity_checks 的 name+question 不得重复")
    if set(actual_fidelity) != set(expected_fidelity) or len(actual_fidelity) != len(expected_fidelity):
        raise GenerationContractError("fidelity_checks 必须与 must_keep 的 name+question 完全一致")

    has_count_failure = any(
        item["result"] == "fail" for item in component_count_checks
    )
    has_failure = (
        any(item["result"] == "fail" for item in checklist)
        or any(item["result"] == "fail" for item in fidelity_checks)
        or has_count_failure
    )
    reject_codes = set(failure_codes) & set(REJECT_CODES)
    rerun_codes = set(failure_codes) & set(RERUN_CODES)
    if has_count_failure != ("component_count_mismatch" in failure_codes):
        raise GenerationContractError(
            "组件数量检查失败必须且只能绑定 component_count_mismatch 数量失败码"
        )
    if status == "pass":
        if has_failure or failure_codes:
            raise GenerationContractError("pass 要求全部检查通过且 failure_codes 为空")
    elif status == "rerun":
        if not has_failure or not rerun_codes or reject_codes:
            raise GenerationContractError("rerun 要求存在失败项和 rerun code，且不得含 reject code")
    elif not has_failure or not reject_codes:
        raise GenerationContractError("reject 要求存在失败项和 reject code")
    return normalized


def finalize_qc(run_root: str | Path, data: dict[str, Any]) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json(state_path, "运行状态")
    if state.get("state") != "awaiting_qc":
        raise GenerationContractError("仅 awaiting_qc 状态可以完成 QC")
    attempt_dir = _current_attempt_dir(root, state)
    attempt_path = attempt_dir / "attempt.json"
    attempt_digest = _verify_digest(
        attempt_path,
        state.get("current_attempt_sha256"),
        "生成尝试",
    )
    submit_path = attempt_dir / "submit.json"
    result_path = attempt_dir / "result.png"
    result_data_path = attempt_dir / "result.json"
    qc_path = attempt_dir / "qc.json"
    if not submit_path.is_file() or not result_path.is_file() or not result_data_path.is_file():
        raise GenerationContractError("当前尝试必须包含 submit.json、result.png 与 result.json")
    if qc_path.exists():
        raise GenerationContractError("当前尝试 qc.json 已存在，禁止重复 finalize")
    visual_count = state.get("generation_attempts")
    if type(visual_count) is not int or not 1 <= visual_count <= 4:
        raise GenerationContractError("generation_attempts 必须为 1 至 4")

    constraints_path = root / "analysis" / "fidelity_constraints.json"
    constraints = _read_json(constraints_path, "产品保真约束")
    normalized = validate_qc_record(data, constraints)
    manifest_path = root / "input" / "input_manifest.json"
    analysis_path = root / "analysis" / "product_analysis.json"
    top3_path = root / "review" / "top3.json"
    decision_path = root / "review" / "decision.json"
    input_digest = _verify_digest(manifest_path, state.get("input_manifest_sha256"), "输入清单")
    analysis_digest = _required_state_and_sidecar_digest(
        state, analysis_path, "product_analysis_sha256", "产品分析"
    )
    constraints_digest = _required_state_and_sidecar_digest(
        state, constraints_path, "fidelity_constraints_sha256", "产品保真约束"
    )
    top3_digest = _verify_digest(top3_path, state.get("top3_sha256"), "Top 3 快照")
    decision_digest = _verify_digest(decision_path, state.get("decision_sha256"), "人工决策")
    submit_digest = _verify_digest(
        submit_path,
        state.get("current_submit_sha256"),
        "AIReiter 提交回执",
    )
    result_record_digest = _verify_digest(
        result_data_path,
        state.get("current_result_record_sha256"),
        "AIReiter 结果回执",
    )
    result_digest = _verify_digest(
        result_path,
        state.get("current_result_sha256"),
        "生成结果",
    )
    submit_data = _read_json(submit_path, "AIReiter 提交回执")
    result_data = _read_json(result_data_path, "生成结果记录")
    normalized_submit, normalized_result = _validate_aireiter_receipts(
        attempt_dir, submit_data, result_data
    )
    if _verify_digest(result_path, result_data.get("result_sha256"), "生成结果") != result_digest:
        raise GenerationContractError("生成结果记录哈希与冻结哈希不一致")
    read_image_size(result_path)
    attempt = _read_json(attempt_path, "生成尝试记录")
    analysis = _read_json(analysis_path, "产品分析")
    decision = _read_json(decision_path, "人工决策")
    selection_evidence = _validated_user_selection_evidence(
        decision, decision.get("selected_rank")
    )
    for field in ("attempt", "model", "aspect_ratio"):
        if field not in attempt:
            raise GenerationContractError(f"生成尝试缺少字段：{field}")

    final_path = root / "final"
    if normalized["status"] == "pass" and final_path.exists():
        raise GenerationContractError("final 目录已存在，禁止覆盖")
    history_path = root / "review" / "decision-history"
    history_target = history_path / f"{attempt_dir.name}.json"
    if normalized["status"] == "reject" and history_target.exists():
        raise GenerationContractError(f"决策历史已存在，禁止覆盖：{history_target}")

    try:
        original_state = state_path.read_bytes()
        temporary = Path(tempfile.mkdtemp(prefix=".qc-", dir=root))
    except OSError as exc:
        raise GenerationContractError("无法创建 QC 临时目录") from exc
    temporary_qc = temporary / "qc.json"
    temporary_final = temporary / "final"
    committed_qc = False
    committed_final = False
    moved_decision = False
    history_created = False
    final_manifest: dict[str, Any] | None = None
    try:
        _atomic_write_json(temporary_qc, normalized)
        qc_digest = sha256_file(temporary_qc)
        if normalized["status"] == "pass":
            temporary_final.mkdir()
            shutil.copyfile(result_path, temporary_final / "result.png")
            if sha256_file(temporary_final / "result.png") != result_digest:
                raise GenerationContractError("最终结果副本哈希与生成结果不一致")
            final_manifest = {
                "schema_version": 1,
                "product_id": analysis.get("product_id"),
                "result": "final/result.png",
                "result_sha256": result_digest,
                "attempt": attempt["attempt"],
                "attempt_sha256": attempt_digest,
                "model": attempt["model"],
                "aspect_ratio": attempt["aspect_ratio"],
                "provider": normalized_submit["provider"],
                "out_task_id": normalized_submit["out_task_id"],
                "selected_output_url": normalized_result["selected_output_url"],
                "submit_receipt": (Path(state["current_attempt"]) / "submit.json").as_posix(),
                "submit_receipt_sha256": submit_digest,
                "result_receipt": (Path(state["current_attempt"]) / "result.json").as_posix(),
                "result_receipt_sha256": result_record_digest,
                "material_id": decision.get("material_id"),
                "record_id": decision.get("record_id"),
                "user_selection_evidence": copy.deepcopy(selection_evidence),
                "input_manifest_sha256": input_digest,
                "product_analysis_sha256": analysis_digest,
                "fidelity_constraints_sha256": constraints_digest,
                "top3_sha256": top3_digest,
                "decision_sha256": decision_digest,
                "qc": (Path(state["current_attempt"]) / "qc.json").as_posix(),
                "qc_sha256": qc_digest,
            }
            _atomic_write_json(temporary_final / "manifest.json", final_manifest)

        next_state = dict(state)
        status = normalized["status"]
        if status == "pass":
            next_state["state"] = "passed"
        else:
            non_pass = state.get("non_pass_attempts", 0)
            if type(non_pass) is not int or non_pass < 0:
                raise GenerationContractError("non_pass_attempts 必须是非负整数")
            next_state["non_pass_attempts"] = non_pass + 1
            if status == "rerun":
                next_state["state"] = "ready_to_generate" if visual_count < 4 else "failed"
            else:
                selected_rank = decision.get("selected_rank")
                if type(selected_rank) is not int or selected_rank not in {1, 2, 3}:
                    raise GenerationContractError("人工决策 selected_rank 无效")
                excluded = state.get("excluded_ranks", [])
                if not isinstance(excluded, list) or any(type(rank) is not int or rank not in {1, 2, 3} for rank in excluded):
                    raise GenerationContractError("excluded_ranks 必须是 rank 1 至 3 的列表")
                excluded = sorted(set(excluded) | {selected_rank})
                next_state["excluded_ranks"] = excluded
                next_state.pop("decision_sha256", None)
                next_state["state"] = (
                    "awaiting_reference_decision"
                    if visual_count < 4 and set(excluded) != {1, 2, 3}
                    else "failed"
                )

        temporary_qc.replace(qc_path)
        committed_qc = True
        if status == "pass":
            temporary_final.replace(final_path)
            committed_final = True
        elif status == "reject":
            history_created = not history_path.exists()
            history_path.mkdir(parents=True, exist_ok=True)
            decision_path.replace(history_target)
            moved_decision = True
        _atomic_write_json(state_path, next_state)
    except Exception as exc:
        try:
            if committed_final and final_path.exists():
                shutil.rmtree(final_path)
            if committed_qc and qc_path.exists():
                qc_path.unlink()
            if moved_decision and history_target.exists():
                history_target.replace(decision_path)
            if history_created and history_path.exists() and not any(history_path.iterdir()):
                history_path.rmdir()
            state_path.write_bytes(original_state)
        except OSError as rollback_exc:
            raise GenerationContractError("QC 提交失败，且无法完整回滚") from rollback_exc
        if isinstance(exc, GenerationContractError):
            raise
        raise GenerationContractError("QC 提交失败，已回滚本轮产物") from exc
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return final_manifest if final_manifest is not None else normalized
