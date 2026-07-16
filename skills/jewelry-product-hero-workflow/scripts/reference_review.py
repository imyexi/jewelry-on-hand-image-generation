from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from product_hero_workflow import (  # noqa: E402
    CATEGORY_TO_FEISHU,
    WorkflowContractError,
    sha256_file,
)


SCORE_RANGES = {
    "topology_layout": (0, 30),
    "complete_replace_region": (0, 20),
    "camera_orientation_scale": (0, 15),
    "background_props": (0, 15),
    "lighting_material": (0, 10),
    "cleanup_cost": (0, 10),
}
HARD_GATE_EXPECTATIONS = {
    "compatible": True,
    "single_product_unit": True,
    "requires_product_stretch": False,
    "requires_large_background_rebuild": False,
}
FEISHU_WIKI_URL = (
    "https://my.feishu.cn/wiki/BR5ewY697iERX3ki0kxc9negnQf?from=from_copylink"
)
FEISHU_BASE_NAME = "AI生图参考图素材库"
FEISHU_TABLE_NAME = "素材收录池"


class ReferenceReviewError(WorkflowContractError):
    """参考图筛选、评审或人工决策不符合工作流契约。"""


class _EligibleCandidateBatch(list[dict[str, Any]]):
    """只允许严格飞书筛选函数创建的候选批次进入评审包。"""

    def __init__(
        self,
        candidates: list[dict[str, Any]],
        *,
        source_snapshot: dict[str, Any],
        source_snapshot_sha256: str,
        candidate_snapshot_sha256: str,
        excluded_sha256: set[str],
    ) -> None:
        super().__init__(candidates)
        self.source_snapshot = copy.deepcopy(source_snapshot)
        self.source_snapshot_sha256 = source_snapshot_sha256
        self.candidate_snapshot_sha256 = candidate_snapshot_sha256
        self.excluded_sha256 = frozenset(excluded_sha256)


def _canonical_sha256(data: Any, description: str) -> str:
    try:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReferenceReviewError(f"{description}无法序列化") from exc
    return hashlib.sha256(payload).hexdigest()


def _read_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReferenceReviewError(f"无法读取{description}：{path}") from exc
    if not isinstance(data, dict):
        raise ReferenceReviewError(f"{description}必须是 JSON 对象")
    return data


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise ReferenceReviewError(f"无法写入文件：{path}") from exc


def _field_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " ".join(
            text for item in value if (text := _field_text(item))
        )
    if value is None:
        return ""
    return str(value).strip()


def _field_tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        tokens: set[str] = set()
        for item in value:
            tokens.update(_field_tokens(item))
        return tokens
    if not isinstance(value, str):
        return set()
    return {
        token.strip()
        for token in re.split(r"[,，;；、/|\s]+", value)
        if token.strip()
    }


def _required_text(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceReviewError(f"{description}不能为空")
    return value.strip()


def collect_explicit_category_candidates(
    records: list[dict[str, Any]],
    category: str,
    excluded_sha256: Iterable[str] = (),
    source_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if category not in CATEGORY_TO_FEISHU:
        raise ReferenceReviewError("目标品类必须属于固定九类之一")
    if not isinstance(records, list):
        raise ReferenceReviewError("飞书缓存 records 必须是列表")
    if not isinstance(source_snapshot, dict):
        raise ReferenceReviewError("必须提供飞书全量分页来源快照")
    expected_source = {
        "wiki_url": FEISHU_WIKI_URL,
        "base_name": FEISHU_BASE_NAME,
        "table_name": FEISHU_TABLE_NAME,
    }
    for field, expected in expected_source.items():
        if source_snapshot.get(field) != expected:
            raise ReferenceReviewError(f"飞书来源快照 {field} 与固定素材池不一致")
    if source_snapshot.get("pagination_complete") is not True:
        raise ReferenceReviewError("飞书来源快照必须证明分页读取完整")
    page_count = source_snapshot.get("page_count")
    record_count = source_snapshot.get("record_count")
    if type(page_count) is not int or page_count < 1:
        raise ReferenceReviewError("飞书来源快照 page_count 必须为正整数")
    if type(record_count) is not int or record_count != len(records):
        raise ReferenceReviewError("飞书来源快照 record_count 必须等于全量记录数")

    try:
        raw_excluded = list(excluded_sha256)
    except TypeError as exc:
        raise ReferenceReviewError("排除哈希必须是可迭代字符串集合") from exc
    if not raw_excluded:
        raise ReferenceReviewError("必须提供产品输入图片哈希用于候选排除")
    if any(
        not isinstance(item, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", item) is None
        for item in raw_excluded
    ):
        raise ReferenceReviewError("产品输入图片哈希必须是 64 位十六进制 SHA-256")
    excluded = {item.lower() for item in raw_excluded}

    chinese_category = CATEGORY_TO_FEISHU[category]
    eligible: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or record.get("usable") is not True:
            continue
        source_fields = record.get("source_fields")
        if not isinstance(source_fields, dict):
            continue
        if "主图" not in _field_tokens(source_fields.get("图片类型")):
            continue
        if chinese_category not in _field_tokens(
            source_fields.get("适用品类")
        ):
            continue

        record_id = record.get("record_id")
        material_id = source_fields.get("素材编号")
        if not isinstance(record_id, str) or not record_id.strip():
            continue
        if not isinstance(material_id, str) or not material_id.strip():
            continue
        try:
            image_path = Path(record.get("image_path"))
        except TypeError:
            continue
        try:
            if not image_path.is_file() or image_path.stat().st_size == 0:
                continue
            image_digest = sha256_file(image_path)
        except (OSError, WorkflowContractError):
            continue
        if image_digest.lower() in excluded:
            continue

        eligible.append(
            {
                "record_id": record_id.strip(),
                "material_id": material_id.strip(),
                "image_path": str(image_path.resolve()),
                "image_sha256": image_digest,
                "category": category,
                "keywords": _field_text(source_fields.get("关键词")),
                "usable": True,
                "source_fields": copy.deepcopy(source_fields),
            }
        )

    eligible.sort(key=lambda item: (item["material_id"], item["record_id"]))
    deduplicated: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for item in eligible:
        if item["image_sha256"] in seen_hashes:
            continue
        seen_hashes.add(item["image_sha256"])
        deduplicated.append(item)

    if len(deduplicated) < 3:
        raise ReferenceReviewError(
            f"{chinese_category}显式品类主图候选仅 {len(deduplicated)} 张，"
            "至少需要 3 张，禁止使用通用素材补位"
        )
    snapshot_payload = {
        "source": source_snapshot,
        "records": records,
    }
    return _EligibleCandidateBatch(
        deduplicated,
        source_snapshot=source_snapshot,
        source_snapshot_sha256=_canonical_sha256(
            snapshot_payload, "飞书来源快照"
        ),
        candidate_snapshot_sha256=_canonical_sha256(
            deduplicated, "飞书候选集合快照"
        ),
        excluded_sha256=excluded,
    )


def validate_reference_assessments(
    candidates: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    product_unit: str,
) -> list[dict[str, Any]]:
    if product_unit not in {"single", "matched_earring_pair"}:
        raise ReferenceReviewError("产品单位必须为单品或一对同款耳饰")
    if not isinstance(candidates, list) or not isinstance(assessments, list):
        raise ReferenceReviewError("候选和评估必须是列表")

    candidate_by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ReferenceReviewError("候选项必须是字典")
        record_id = _required_text(candidate.get("record_id"), "候选 record_id")
        if record_id in candidate_by_id:
            raise ReferenceReviewError(f"候选 record_id 重复：{record_id}")
        candidate_by_id[record_id] = candidate

    assessment_ids: list[str] = []
    for assessment in assessments:
        if not isinstance(assessment, dict):
            raise ReferenceReviewError("评估项必须是字典")
        assessment_ids.append(
            _required_text(assessment.get("record_id"), "评估 record_id")
        )
    if len(assessment_ids) != len(set(assessment_ids)):
        raise ReferenceReviewError("每个候选只能有一条评估，禁止重复")
    if set(assessment_ids) != set(candidate_by_id):
        missing = sorted(set(candidate_by_id) - set(assessment_ids))
        extra = sorted(set(assessment_ids) - set(candidate_by_id))
        raise ReferenceReviewError(
            f"评估必须与候选一一对应；遗漏={missing}，多出={extra}"
        )

    normalized: list[dict[str, Any]] = []
    for assessment in assessments:
        record_id = assessment["record_id"].strip()
        candidate = candidate_by_id[record_id]
        for field in ("record_id", "material_id", "image_sha256"):
            if assessment.get(field) != candidate.get(field):
                raise ReferenceReviewError(
                    f"评估 {record_id} 的 {field} 与候选绑定不一致"
                )
        for field in HARD_GATE_EXPECTATIONS:
            if type(assessment.get(field)) is not bool:
                raise ReferenceReviewError(
                    f"评估 {record_id} 的硬 gate {field} 必须是布尔值"
                )

        score = 0
        for field, (minimum, maximum) in SCORE_RANGES.items():
            value = assessment.get(field)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ReferenceReviewError(
                    f"评估 {record_id} 的 {field} 必须是 "
                    f"{minimum} 至 {maximum} 的整数"
                )
            score += value

        reasons = assessment.get("reasons")
        if (
            not isinstance(reasons, list)
            or not reasons
            or any(
                not isinstance(reason, str) or not reason.strip()
                for reason in reasons
            )
        ):
            raise ReferenceReviewError(
                f"评估 {record_id} 的 reasons 必须是非空字符串列表"
            )
        risks = assessment.get("risks")
        if not isinstance(risks, list) or any(
            not isinstance(risk, str) for risk in risks
        ):
            raise ReferenceReviewError(
                f"评估 {record_id} 的 risks 必须是字符串列表"
            )

        item = copy.deepcopy(assessment)
        item["record_id"] = record_id
        item["reasons"] = [reason.strip() for reason in reasons]
        item["risks"] = [risk.strip() for risk in risks]
        item["score"] = score
        normalized.append(item)
    return normalized


def select_top3(
    candidates: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    product_unit: str,
) -> list[dict[str, Any]]:
    normalized = validate_reference_assessments(
        candidates, assessments, product_unit
    )
    candidates_by_id = {item["record_id"]: item for item in candidates}
    passing: list[dict[str, Any]] = []
    for assessment in normalized:
        if not all(
            assessment[field] is expected
            for field, expected in HARD_GATE_EXPECTATIONS.items()
        ):
            continue
        item = copy.deepcopy(candidates_by_id[assessment["record_id"]])
        item.update(copy.deepcopy(assessment))
        passing.append(item)

    if len(passing) < 3:
        raise ReferenceReviewError(
            f"四个硬 gate 后仅 {len(passing)} 张候选，至少需要 3 张，"
            "禁止使用失败项补位"
        )
    passing.sort(
        key=lambda item: (
            -item["score"],
            item["material_id"],
            item["record_id"],
        )
    )
    return [
        dict(copy.deepcopy(item), rank=rank)
        for rank, item in enumerate(passing[:3], start=1)
    ]


def _safe_material_id(value: Any) -> str:
    material_id = _required_text(value, "素材编号")
    if (
        Path(material_id).name != material_id
        or material_id in {".", ".."}
        or not re.fullmatch(r"[\w.-]+", material_id)
    ):
        raise ReferenceReviewError(f"素材编号不能用于安全文件名：{material_id}")
    return material_id


def _render_review_html(
    product_id: str,
    category: str,
    items: list[dict[str, Any]],
) -> str:
    cards = []
    for item in items:
        reasons = "".join(
            f"<li>{html.escape(reason)}</li>" for reason in item["reasons"]
        )
        risks = "".join(
            f"<li>{html.escape(risk)}</li>" for risk in item["risks"]
        ) or "<li>无</li>"
        image_src = "../" + item["selected_reference"]
        cards.append(
            "<article>"
            f"<h2>Rank {item['rank']} · {html.escape(item['material_id'])}</h2>"
            f'<img src="{html.escape(image_src)}" '
            f'alt="{html.escape(item["material_id"])} 预览">'
            f"<p>分数：{item['score']}</p>"
            f"<h3>理由</h3><ul>{reasons}</ul>"
            f"<h3>风险</h3><ul>{risks}</ul>"
            "</article>"
        )
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>参考图 Top 3 人工评审</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; color: #222; }
    main { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.5rem; }
    article { border: 1px solid #bbb; padding: 1rem; }
    img { display: block; width: 100%; height: 20rem; object-fit: contain; background: #eee; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
""" + (
        f"<h1>{html.escape(product_id)} · "
        f"{html.escape(CATEGORY_TO_FEISHU[category])}</h1>\n"
        f"<main>{''.join(cards)}</main>\n"
        "</body>\n</html>\n"
    )


def write_review_package(
    run_root: str | Path,
    candidates: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
) -> dict[str, Any]:
    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json_object(state_path, "运行状态")
    if state.get("state") != "awaiting_reference_review":
        raise ReferenceReviewError(
            "仅 awaiting_reference_review 状态可以生成参考图评审包"
        )
    if not isinstance(candidates, _EligibleCandidateBatch):
        raise ReferenceReviewError("参考图候选必须来自严格飞书筛选批次")
    if (
        _canonical_sha256(list(candidates), "飞书候选集合快照")
        != candidates.candidate_snapshot_sha256
    ):
        raise ReferenceReviewError("飞书候选集合与筛选时快照不一致")

    assessment_path = root / "analysis" / "reference_assessments.json"
    review_path = root / "review"
    decision_path = review_path / "decision.json"
    if assessment_path.exists():
        raise ReferenceReviewError(
            f"参考图评估文件已存在，禁止覆盖：{assessment_path}"
        )
    if decision_path.exists():
        raise ReferenceReviewError(
            f"人工决策文件已存在，禁止生成新评审包：{decision_path}"
        )
    if review_path.exists():
        raise ReferenceReviewError(
            f"参考图评审目录已存在，禁止覆盖：{review_path}"
        )

    try:
        original_state_bytes = state_path.read_bytes()
    except OSError as exc:
        raise ReferenceReviewError(f"无法读取运行状态原始字节：{state_path}") from exc

    analysis_path = root / "analysis" / "product_analysis.json"
    analysis = _read_json_object(analysis_path, "产品分析")
    product_id = _required_text(analysis.get("product_id"), "产品 ID")
    category = analysis.get("category")
    if category not in CATEGORY_TO_FEISHU:
        raise ReferenceReviewError("产品分析中的品类无效")
    product_unit = analysis.get("product_unit")
    manifest = _read_json_object(root / "input" / "input_manifest.json", "输入清单")
    images = manifest.get("images")
    if not isinstance(images, list) or not images:
        raise ReferenceReviewError("输入清单 images 必须是非空列表")
    input_hashes = {
        item.get("sha256").lower()
        for item in images
        if isinstance(item, dict)
        and isinstance(item.get("sha256"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"])
    }
    if len(input_hashes) != len(images):
        raise ReferenceReviewError("输入清单必须为每张产品图提供有效 SHA-256")
    if candidates.excluded_sha256 != input_hashes:
        raise ReferenceReviewError("飞书候选批次未完整绑定产品输入图片哈希")
    chinese_category = CATEGORY_TO_FEISHU[category]
    for candidate in candidates:
        source_fields = candidate.get("source_fields")
        if candidate.get("usable") is not True or not isinstance(source_fields, dict):
            raise ReferenceReviewError("飞书候选缺少可用状态或原始字段")
        if "主图" not in _field_tokens(source_fields.get("图片类型")):
            raise ReferenceReviewError("飞书候选图片类型不再包含主图")
        if chinese_category not in _field_tokens(source_fields.get("适用品类")):
            raise ReferenceReviewError("飞书候选适用品类不再包含目标品类")
        if candidate.get("image_sha256", "").lower() in input_hashes:
            raise ReferenceReviewError("飞书候选与产品输入图片哈希重复")
    normalized = validate_reference_assessments(
        candidates, assessments, product_unit
    )
    if any(candidate.get("category") != category for candidate in candidates):
        raise ReferenceReviewError("参考图候选品类与产品分析品类不一致")
    top3 = select_top3(candidates, assessments, product_unit)

    assessments_document = {
        "schema_version": 1,
        "product_id": product_id,
        "category": category,
        "product_unit": product_unit,
        "source": {
            **copy.deepcopy(candidates.source_snapshot),
            "snapshot_sha256": candidates.source_snapshot_sha256,
            "candidate_snapshot_sha256": candidates.candidate_snapshot_sha256,
            "excluded_product_sha256": sorted(candidates.excluded_sha256),
        },
        "assessments": normalized,
    }

    items: list[dict[str, Any]] = []
    selected_sources: list[tuple[Path, str]] = []
    for selected in top3:
        source = Path(selected["image_path"])
        try:
            current_digest = sha256_file(source)
        except WorkflowContractError as exc:
            raise ReferenceReviewError(
                f"无法读取候选原图：{source}"
            ) from exc
        if current_digest != selected["image_sha256"]:
            raise ReferenceReviewError(
                f"候选原图在筛选后发生变化：{selected['record_id']}"
            )
        material_id = _safe_material_id(selected["material_id"])
        destination_name = (
            f"rank-{selected['rank']}-{material_id}{source.suffix.lower()}"
        )
        relative_path = (Path("review") / "candidates" / destination_name).as_posix()
        selected_sources.append((source, destination_name))
        items.append(
            {
                "rank": selected["rank"],
                "record_id": selected["record_id"],
                "material_id": material_id,
                "selected_reference": relative_path,
                "image_sha256": selected["image_sha256"],
                "score": selected["score"],
                "reasons": copy.deepcopy(selected["reasons"]),
                "risks": copy.deepcopy(selected["risks"]),
                "source_fields": copy.deepcopy(selected["source_fields"]),
            }
        )

    top3_document = {
        "schema_version": 1,
        "product_id": product_id,
        "category": category,
        "product_unit": product_unit,
        "source": copy.deepcopy(assessments_document["source"]),
        "items": items,
    }

    try:
        temporary_root = Path(
            tempfile.mkdtemp(prefix=".reference-review-", dir=root)
        )
    except OSError as exc:
        raise ReferenceReviewError("无法创建参考图评审临时目录") from exc

    temporary_assessment = (
        temporary_root / "analysis" / "reference_assessments.json"
    )
    temporary_review = temporary_root / "review"
    temporary_candidates = temporary_review / "candidates"
    temporary_top3 = temporary_review / "top3.json"
    try:
        temporary_candidates.mkdir(parents=True)
        for selected, (source, destination_name) in zip(top3, selected_sources):
            destination = temporary_candidates / destination_name
            try:
                shutil.copyfile(source, destination)
            except OSError as exc:
                raise ReferenceReviewError(
                    f"无法复制候选原图：{source}"
                ) from exc
            try:
                copied_digest = sha256_file(destination)
            except WorkflowContractError as exc:
                raise ReferenceReviewError(
                    f"无法校验候选副本哈希：{destination_name}"
                ) from exc
            if copied_digest != selected["image_sha256"]:
                raise ReferenceReviewError(
                    f"候选副本哈希与筛选快照不一致：{selected['record_id']}"
                )

        _write_json(temporary_assessment, assessments_document)
        _write_json(temporary_top3, top3_document)
        (temporary_review / "review.html").write_text(
            _render_review_html(product_id, category, items),
            encoding="utf-8",
            newline="\n",
        )
        next_state = dict(state)
        next_state["state"] = "awaiting_reference_decision"
        next_state["top3_sha256"] = sha256_file(temporary_top3)

        assessment_committed = False
        review_committed = False
        try:
            temporary_assessment.replace(assessment_path)
            assessment_committed = True
            temporary_review.replace(review_path)
            review_committed = True
            _write_json(state_path, next_state)
        except Exception as exc:
            rollback_error: OSError | None = None
            try:
                if review_committed and review_path.exists():
                    shutil.rmtree(review_path)
                if assessment_committed and assessment_path.exists():
                    assessment_path.unlink()
                state_path.write_bytes(original_state_bytes)
            except OSError as current_error:
                rollback_error = current_error
            if rollback_error is not None:
                raise ReferenceReviewError(
                    "参考图评审包提交失败，且无法完整回滚"
                ) from rollback_error
            if isinstance(exc, ReferenceReviewError):
                raise
            raise ReferenceReviewError("无法提交参考图评审包") from exc
        return top3_document
    except OSError as exc:
        raise ReferenceReviewError("无法构建参考图评审包") from exc
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def record_reference_decision(
    run_root: str | Path,
    rank: int,
    user_selection_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if type(rank) is not int or rank not in {1, 2, 3}:
        raise ReferenceReviewError("人工选择 rank 必须是 1、2 或 3")
    if not isinstance(user_selection_evidence, dict):
        raise ReferenceReviewError("必须提供用户选择证据")
    evidence = copy.deepcopy(user_selection_evidence)
    if evidence.get("source") not in {"user_message", "user_interface"}:
        raise ReferenceReviewError("用户选择证据 source 无效")
    if evidence.get("selected_rank") != rank:
        raise ReferenceReviewError("用户选择证据 selected_rank 与决策不一致")
    verbatim = evidence.get("verbatim")
    if not isinstance(verbatim, str) or not verbatim.strip():
        raise ReferenceReviewError("用户选择证据 verbatim 不能为空")
    evidence["verbatim"] = verbatim.strip()

    root = Path(run_root)
    state_path = root / "state.json"
    state = _read_json_object(state_path, "运行状态")
    if state.get("state") != "awaiting_reference_decision":
        raise ReferenceReviewError(
            "仅 awaiting_reference_decision 状态可以记录参考图决策"
        )
    excluded_ranks = state.get("excluded_ranks", [])
    if not isinstance(excluded_ranks, list) or any(
        type(item) is not int or item not in {1, 2, 3}
        for item in excluded_ranks
    ):
        raise ReferenceReviewError("运行状态 excluded_ranks 必须是 rank 1 至 3 的列表")
    if rank in excluded_ranks:
        raise ReferenceReviewError(f"rank {rank} 已被排除，禁止重新选择")

    decision_path = root / "review" / "decision.json"
    if decision_path.exists():
        raise ReferenceReviewError(f"人工决策文件已存在，禁止覆盖：{decision_path}")
    try:
        original_state_bytes = state_path.read_bytes()
    except OSError as exc:
        raise ReferenceReviewError(f"无法读取运行状态原始字节：{state_path}") from exc

    top3_path = root / "review" / "top3.json"
    try:
        current_digest = sha256_file(top3_path)
    except WorkflowContractError as exc:
        raise ReferenceReviewError("无法校验 Top 3 快照") from exc
    if current_digest != state.get("top3_sha256"):
        raise ReferenceReviewError("Top 3 快照已被篡改，禁止记录决策")

    top3_document = _read_json_object(top3_path, "Top 3 快照")
    items = top3_document.get("items")
    if not isinstance(items, list):
        raise ReferenceReviewError("Top 3 快照 items 必须是列表")
    selected = next(
        (
            item
            for item in items
            if isinstance(item, dict) and item.get("rank") == rank
        ),
        None,
    )
    if selected is None:
        raise ReferenceReviewError(f"Top 3 快照中不存在 rank {rank}")

    analysis_path = root / "analysis" / "product_analysis.json"
    try:
        analysis_digest = sha256_file(analysis_path)
    except WorkflowContractError as exc:
        raise ReferenceReviewError("无法校验产品分析快照") from exc
    decision = {
        "schema_version": 1,
        "selected_rank": rank,
        "record_id": selected.get("record_id"),
        "material_id": selected.get("material_id"),
        "selected_reference": selected.get("selected_reference"),
        "image_sha256": selected.get("image_sha256"),
        "top3_sha256": current_digest,
        "product_analysis_sha256": analysis_digest,
        "user_selection_evidence": evidence,
    }
    next_state = dict(state)
    next_state["state"] = "ready_to_generate"
    try:
        _write_json(decision_path, decision)
        next_state["decision_sha256"] = sha256_file(decision_path)
        _write_json(state_path, next_state)
    except Exception as exc:
        rollback_error: OSError | None = None
        try:
            if decision_path.exists():
                decision_path.unlink()
            state_path.write_bytes(original_state_bytes)
        except OSError as current_error:
            rollback_error = current_error
        if rollback_error is not None:
            raise ReferenceReviewError(
                "人工决策写入失败，且无法完整回滚"
            ) from rollback_error
        if isinstance(exc, ReferenceReviewError):
            raise
        raise ReferenceReviewError("无法写入人工决策或更新运行状态") from exc
    return decision
