from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from jewelry_on_hand.feishu_reference_source import (
    FeishuReferenceConfig,
    FeishuReferenceError,
    FeishuReferenceSync,
    PendingEnrichmentError,
    audit_enrichment_readback,
    build_reference_source_snapshot,
    ensure_enrichment_fields,
    import_enrichment_results,
    sync_and_load_reference_rows,
)
from jewelry_on_hand.generation import (
    GenerationError,
    run_generation,
    validate_necklace_reference_selection,
)
from jewelry_on_hand.models import (
    ProductAnalysis,
    ProductConfirmationSnapshot,
    ReferenceRow,
    ReviewDecision,
    ScoredReference,
)
from jewelry_on_hand.output_roles import (
    OUTPUT_ROLE_FILE_NAME,
    OutputRole,
    normalize_output_role,
    require_scene_replacement_role,
)
from jewelry_on_hand.product_types import ProductType, normalize_product_type
from jewelry_on_hand.product_analysis import (
    UnsupportedProductError,
    build_analysis_prompt,
    build_product_fidelity_constraints,
    load_product_analysis,
)
from jewelry_on_hand.product_fidelity import (
    load_product_fidelity_constraints,
    validate_product_fidelity_constraints,
)
from jewelry_on_hand.prompt_builder import build_prompt
from jewelry_on_hand.qc import write_qc_result
from jewelry_on_hand.qc_review import ensure_qc_review_ready
from jewelry_on_hand.reference_catalog import load_reference_rows
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME,
    build_candidate_snapshot,
    load_reference_composition_snapshot,
)
from jewelry_on_hand.ring_attributes import FingerPosition, HandSide, RingWearStyle
from jewelry_on_hand.review_decision import (
    ReviewGateError,
    require_generation_decision,
    validate_confirmed_analysis,
    validate_decision_against_analysis,
    write_review_bundle,
)
from jewelry_on_hand.review_package import write_review_package
from jewelry_on_hand.run_paths import RunPaths, create_run_id, read_json, write_json
from jewelry_on_hand.scoring import (
    require_three_review_candidates,
    select_batch_diverse_references,
    select_reference_candidates,
)


DEFAULT_OUTPUT_ROOT = "outputs/auto_reference_runs"
DEFAULT_HELPER_SCRIPT = "skills/aireiter-image-generation/scripts/aireiter_image_helper.py"
EXPECTED_ERRORS = (
    ValueError,
    FileNotFoundError,
    KeyError,
    GenerationError,
    ReviewGateError,
    UnsupportedProductError,
    FeishuReferenceError,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except EXPECTED_ERRORS as exc:
        print(f"错误：{_error_text(exc)}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jewelry-on-hand",
        description="珠宝上手图自动参考图工作流 CLI。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-review", help="生成候选参考图 review 包。")
    prepare.add_argument("--product-image", required=True)
    prepare.add_argument(
        "--product-detail-image",
        help="戒指可选：已确认的产品主体细节图，仅用于 review、结构分析、canonical 约束和人工 QC，不进入模型。",
    )
    prepare.add_argument("--analysis-json")
    prepare.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    prepare.add_argument("--run-id")
    prepare.add_argument("--dimensions-json")
    prepare.add_argument("--output-role", choices=[item.value for item in OutputRole])
    prepare.add_argument(
        "--confirmed-product-type",
        choices=[item.value for item in ProductType],
    )
    prepare.add_argument(
        "--source-image-type",
        choices=["worn_source", "hand_held_source", "flat_lay_source", "unknown_source"],
    )
    prepare.add_argument("--display-mode", choices=["worn", "hand_held"])
    prepare.add_argument("--layer-count", type=int)
    prepare.add_argument("--length-category")
    prepare.add_argument(
        "--has-pendant",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    prepare.add_argument("--pendant-count", type=int)
    prepare.add_argument("--pendant-layer")
    prepare.add_argument("--pendant-position")
    prepare.add_argument("--pendant-orientation")
    prepare.add_argument("--connection-structure")
    prepare.add_argument(
        "--independent-multi-item",
        dest="is_independent_multi_item",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    prepare.add_argument(
        "--classification",
        help="历史兼容：从本地分类 Excel 读取参考图库；提供时优先于飞书参考源。",
    )
    prepare.add_argument(
        "--ignore-pending-enrichment",
        action="store_true",
        help="完整同步线上参考图库后，显式排除尚待 AI 补齐的素材并写入来源审计。",
    )
    _add_reference_source_arguments(prepare)
    prepare.set_defaults(handler=_prepare_review)

    rerank_batch = subparsers.add_parser(
        "rerank-batch", help="对多个既有 review run 执行批次级多样性重排。"
    )
    rerank_batch.add_argument("--output-root", required=True)
    rerank_batch.add_argument("--run-id", action="append", required=True)
    rerank_batch.set_defaults(handler=_rerank_batch)
    sync = subparsers.add_parser("reference-sync", help="同步飞书参考图库并输出待补齐清单。")
    _add_reference_source_arguments(sync)
    sync.set_defaults(handler=_reference_sync)

    ensure_fields_help = "补齐飞书参考图库缺失的 AI 字段。"
    ensure_fields = subparsers.add_parser(
        "reference-ensure-fields",
        help=ensure_fields_help,
        description=ensure_fields_help,
    )
    _add_reference_source_arguments(ensure_fields)
    ensure_fields.set_defaults(handler=_reference_ensure_fields)

    enrichment = subparsers.add_parser("reference-import-enrichment", help="导入 AI 补齐结果并回填飞书。")
    enrichment.add_argument("--input-json", required=True)
    _add_reference_source_arguments(enrichment)
    enrichment.set_defaults(handler=_reference_import_enrichment)

    audit = subparsers.add_parser(
        "reference-audit-enrichment",
        help="逐条复读飞书补齐字段并输出当前状态审计。",
    )
    _add_reference_source_arguments(audit)
    audit.set_defaults(handler=_reference_audit_enrichment)

    decision = subparsers.add_parser("record-decision", help="记录人工 review 决策。")
    decision.add_argument("--run-root", required=True)
    decision.add_argument("--action", required=True)
    decision.add_argument("--selected-ranks", action="append")
    decision.add_argument("--manual-reference")
    decision.add_argument("--fidelity-confirmed", action="store_true")
    decision.add_argument("--fidelity-notes")
    decision.add_argument("--fidelity-constraints-path")
    decision.add_argument("--output-role", choices=[item.value for item in OutputRole])
    decision.add_argument(
        "--confirmed-product-type",
        choices=[item.value for item in ProductType],
    )
    decision.add_argument(
        "--source-image-type",
        choices=["worn_source", "hand_held_source", "flat_lay_source", "unknown_source"],
    )
    decision.add_argument("--display-mode", choices=["worn", "hand_held"])
    decision.add_argument("--layer-count", type=int)
    decision.add_argument("--length-category")
    decision.add_argument(
        "--has-pendant",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    decision.add_argument("--pendant-count", type=int)
    decision.add_argument("--pendant-layer")
    decision.add_argument("--pendant-position")
    decision.add_argument("--pendant-orientation")
    decision.add_argument("--connection-structure")
    decision.add_argument("--ring-count", type=int)
    decision.add_argument(
        "--hand-side",
        choices=[item.value for item in HandSide],
    )
    decision.add_argument(
        "--finger-position",
        choices=[item.value for item in FingerPosition],
    )
    decision.add_argument(
        "--ring-wear-style",
        choices=[item.value for item in RingWearStyle],
    )
    decision.add_argument(
        "--independent-multi-item",
        dest="is_independent_multi_item",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    decision.set_defaults(handler=_record_decision)

    generate = subparsers.add_parser("generate", help="通过 review gate 后提交生成任务。")
    generate.add_argument("--run-root", required=True)
    generate.add_argument("--helper-script", default=DEFAULT_HELPER_SCRIPT)
    generate.add_argument("--no-wait", action="store_true")
    generate.set_defaults(handler=_generate)

    qc = subparsers.add_parser("qc", help="写入单次生成的质检结果。")
    qc.add_argument("--generation-dir", required=True)
    qc.add_argument("--status", required=True)
    qc.add_argument("--passed", action="append")
    qc.add_argument("--failed", action="append")
    qc.add_argument("--notes", default="")
    qc.add_argument("--fidelity-checks-json", required=True)
    qc.add_argument("--checklist-checks-json", required=True)
    qc.add_argument("--reference-preservation-checks-json", required=True)
    qc.add_argument(
        "--critical-failures",
        action="append",
        nargs="?",
        const="",
        help="关键失败代码，可重复传入或使用逗号分隔。存在关键失败时不得标记 pass。",
    )
    qc.set_defaults(handler=_qc)

    return parser


def _prepare_review(args: argparse.Namespace) -> int:
    if args.classification and args.ignore_pending_enrichment:
        raise ValueError(
            "--ignore-pending-enrichment 仅适用于线上飞书参考图库，"
            "不能与 --classification 同时使用"
        )
    output_role = require_scene_replacement_role(
        args.output_role,
        stage="prepare-review",
    )
    run_id = args.run_id or create_run_id()
    _ensure_prepare_run_is_empty(args.output_root, run_id)
    paths = RunPaths.create(args.output_root, run_id)

    copied_product = paths.copy_product_image(args.product_image)
    dimensions = _load_optional_dimensions(args.dimensions_json)
    if dimensions is not None:
        write_json(paths.input_dir / "product_dimensions.json", dimensions)

    prompt = build_analysis_prompt(copied_product, dimensions)
    (paths.analysis_dir / "product_analysis_prompt.txt").write_text(prompt, encoding="utf-8")

    if not args.analysis_json:
        print(
            "缺少 --analysis-json：已生成 analysis/product_analysis_prompt.txt，请先完成产品分析 JSON。",
            file=sys.stderr,
        )
        return 1

    analysis_data, product = _prepare_review_analysis(args)
    write_json(paths.analysis_dir / "product_analysis.json", analysis_data)
    product_identity = copied_product
    if args.product_detail_image:
        if product.confirmed_product_type is not ProductType.RING:
            raise ValueError("--product-detail-image 仅支持戒指产品")
        product_identity = paths.copy_product_detail_image(args.product_detail_image)
    constraints = build_product_fidelity_constraints(
        product,
        product_image=product_identity.relative_to(paths.root).as_posix(),
    )
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", constraints.to_dict())
    rows = _load_prepare_reference_rows(args)
    if args.ignore_pending_enrichment:
        write_json(
            paths.analysis_dir / "reference_source_snapshot.json",
            build_reference_source_snapshot(
                _reference_config(args).cache_root,
                ignore_pending_enrichment=True,
            ),
        )
    write_json(
        paths.analysis_dir / OUTPUT_ROLE_FILE_NAME,
        {"output_role": output_role.value},
    )
    selection = select_reference_candidates(
        product,
        rows,
        output_role=output_role,
    )
    write_json(
        paths.analysis_dir / "reference_snapshot_readiness.json",
        selection.readiness_audit(),
    )
    require_three_review_candidates(selection)
    selected = list(selection.selected)
    candidates = list(selection.candidates)
    composition_snapshots = [
        build_candidate_snapshot(product, item, output_role) for item in selected
    ]
    write_review_package(
        paths,
        product_identity,
        selected,
        candidates,
        composition_snapshots=composition_snapshots,
    )
    return 0


def _rerank_batch(args: argparse.Namespace) -> int:
    output_root = Path(args.output_root)
    paths_list = [RunPaths(root=output_root / run_id) for run_id in args.run_id]
    output_roles = [
        require_scene_replacement_role(
            _load_run_output_role(paths),
            stage="rerank-batch",
        )
        for paths in paths_list
    ]
    products = [
        load_product_analysis(paths.analysis_dir / "product_analysis.json")
        for paths in paths_list
    ]
    candidate_sets = [
        _load_selected_references(paths.analysis_dir / "reference_candidates.json")
        for paths in paths_list
    ]
    selections = select_batch_diverse_references(
        candidate_sets,
        output_roles,
        limit=3,
    )
    for paths, product, output_role, selected, candidates in zip(
        paths_list,
        products,
        output_roles,
        selections,
        candidate_sets,
        strict=True,
    ):
        product_image = paths.input_dir / "product-on-hand.jpg"
        composition_snapshots = [
            build_candidate_snapshot(product, item, output_role) for item in selected
        ]
        write_review_package(
            paths,
            product_image,
            selected,
            candidates,
            composition_snapshots=composition_snapshots,
        )
    return 0


def _prepare_review_analysis(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], ProductAnalysis]:
    source_data = read_json(args.analysis_json)
    if not isinstance(source_data, dict):
        raise ValueError("--analysis-json 必须包含 JSON 对象")
    overrides = _decision_analysis_overrides(args)
    if not overrides:
        return source_data, load_product_analysis(args.analysis_json)

    current = ProductAnalysis.from_dict(source_data)
    corrected_data = dict(source_data)
    corrected_data.update(
        {
            "detected_product_type": current.detected_product_type.value,
            "confirmed_product_type": current.confirmed_product_type.value,
            "classification_confidence": current.classification_confidence,
            "classification_evidence": list(current.classification_evidence),
            "classification_source": "manual_override",
            "display_mode": current.display_mode.value,
            "source_image_type": current.source_image_type.value,
        }
    )
    corrected_data.update(overrides)
    corrected = ProductAnalysis.from_dict(corrected_data)
    validate_confirmed_analysis(corrected)
    return corrected_data, corrected


def _load_prepare_reference_rows(args: argparse.Namespace) -> list[ReferenceRow]:
    if args.classification:
        return load_reference_rows(args.classification)
    if getattr(args, "ignore_pending_enrichment", False):
        return sync_and_load_reference_rows(
            _reference_config(args),
            ignore_pending_enrichment=True,
        )
    return sync_and_load_reference_rows(_reference_config(args))


def _add_reference_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reference-wiki-url")
    parser.add_argument("--reference-table-name")
    parser.add_argument("--reference-cache-root")


def _reference_config(args: argparse.Namespace) -> FeishuReferenceConfig:
    return FeishuReferenceConfig.from_env(
        cache_root=getattr(args, "reference_cache_root", None),
        wiki_url=getattr(args, "reference_wiki_url", None),
        table_name=getattr(args, "reference_table_name", None),
    )


def _reference_sync(args: argparse.Namespace) -> int:
    result = FeishuReferenceSync(_reference_config(args)).sync()
    print(
        f"飞书参考图库同步完成：总计 {result.total_records} 条，可用 {result.usable_records} 条，"
        f"下载 {result.downloaded_count} 张。"
    )
    if result.pending_count:
        print(
            f"仍有 {result.pending_count} 条等待 AI 补齐：{result.pending_path}",
            file=sys.stderr,
        )
        return 2
    return 0


def _reference_ensure_fields(args: argparse.Namespace) -> int:
    created = ensure_enrichment_fields(_reference_config(args))
    if created:
        print(f"已创建 AI 补齐字段：{'、'.join(created)}")
    else:
        print("飞书参考图库已包含全部 AI 补齐字段。")
    return 0


def _reference_import_enrichment(args: argparse.Namespace) -> int:
    result = import_enrichment_results(
        _reference_config(args),
        args.input_json,
    )
    print(
        f"已回填 {result.updated_records} 条素材；剩余待补齐 {result.remaining_pending} 条。"
    )
    return 0 if result.remaining_pending == 0 else 2


def _reference_audit_enrichment(args: argparse.Namespace) -> int:
    result = audit_enrichment_readback(_reference_config(args))
    print(
        f"补齐复读审计完成：已核验 {result.verified_records} 条，"
        f"失败 {result.failed_records} 条。"
    )
    return 0 if result.failed_records == 0 else 2


def _record_decision(args: argparse.Namespace) -> int:
    paths = _paths_from_run_root(args.run_root)
    data: dict[str, Any] = {"action": args.action}
    _record_output_role(paths, args, data)
    ranks = _parse_int_list(args.selected_ranks)
    _ensure_unique_ranks(ranks)
    if ranks:
        data["selected_ranks"] = ranks
    if args.manual_reference:
        data["manual_reference"] = args.manual_reference
    if args.fidelity_confirmed:
        data["fidelity_confirmed"] = True
    if args.fidelity_notes:
        data["fidelity_notes"] = args.fidelity_notes
    if args.fidelity_constraints_path:
        data["fidelity_constraints_path"] = args.fidelity_constraints_path
    has_analysis_corrections = bool(_decision_analysis_overrides(args))
    analysis_data, analysis = _prepare_decision_analysis(paths, args)
    if analysis is not None:
        data["confirmation_snapshot"] = ProductConfirmationSnapshot.from_analysis(
            analysis
        ).to_dict()
        if has_analysis_corrections:
            validate_confirmed_analysis(analysis)
        validate_decision_against_analysis(ReviewDecision.from_dict(data), analysis)
    write_review_bundle(paths, data, analysis_data=analysis_data)
    return 0


def _prepare_decision_analysis(
    paths: RunPaths,
    args: argparse.Namespace,
) -> tuple[dict[str, Any] | None, ProductAnalysis | None]:
    analysis_path = paths.analysis_dir / "product_analysis.json"
    overrides = _decision_analysis_overrides(args)
    if not analysis_path.is_file():
        if overrides:
            raise FileNotFoundError(f"缺少待纠正的产品分析文件：{analysis_path}")
        return None, None

    current_data = read_json(analysis_path)
    if not isinstance(current_data, dict):
        raise ValueError(f"{analysis_path} 必须是 JSON 对象")
    current_analysis = ProductAnalysis.from_dict(current_data)
    if not overrides:
        return None, current_analysis

    corrected_data = dict(current_data)
    corrected_data.update(
        {
            "detected_product_type": current_analysis.detected_product_type.value,
            "confirmed_product_type": current_analysis.confirmed_product_type.value,
            "classification_confidence": current_analysis.classification_confidence,
            "classification_evidence": list(current_analysis.classification_evidence),
            "classification_source": "manual_override",
            "display_mode": current_analysis.display_mode.value,
            "source_image_type": current_analysis.source_image_type.value,
        }
    )
    corrected_data.update(overrides)
    corrected_type = normalize_product_type(corrected_data["confirmed_product_type"])
    if corrected_type is ProductType.UNKNOWN:
        raise UnsupportedProductError("产品品类无法识别，必须先人工纠正")
    if corrected_type is ProductType.PENDANT_ONLY:
        raise UnsupportedProductError("当前版本不支持无链独立吊坠，且禁止自动补链")
    corrected_analysis = ProductAnalysis.from_dict(corrected_data)
    changed_fields = [
        field_name
        for field_name in overrides
        if getattr(corrected_analysis, field_name) != getattr(current_analysis, field_name)
    ]
    if changed_fields and (
        current_analysis.confirmed_product_type
        in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}
        or corrected_analysis.confirmed_product_type
        in {ProductType.NECKLACE, ProductType.PENDANT_NECKLACE}
    ):
        raise ReviewGateError(
            "人工纠正字段会改变项链参考图适配，旧 Top 3 与旧决策均不得沿用："
            f"{'、'.join(changed_fields)}；请新建 run，并在评分前重新执行 prepare-review"
        )
    if not changed_fields:
        return None, current_analysis
    return corrected_data, corrected_analysis


def _decision_analysis_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    direct_fields = (
        "confirmed_product_type",
        "source_image_type",
        "display_mode",
        "layer_count",
        "has_pendant",
        "pendant_count",
        "is_independent_multi_item",
        "ring_count",
        "hand_side",
        "finger_position",
        "ring_wear_style",
    )
    for field_name in direct_fields:
        value = getattr(args, field_name, None)
        if value is not None:
            overrides[field_name] = value
    for field_name in (
        "length_category",
        "pendant_position",
        "pendant_orientation",
        "connection_structure",
    ):
        value = getattr(args, field_name, None)
        if value is not None:
            overrides[field_name] = _parse_nullable_text(value, field_name)
    pendant_layer = getattr(args, "pendant_layer", None)
    if pendant_layer is not None:
        overrides["pendant_layer"] = _parse_nullable_integer(
            pendant_layer, "pendant_layer"
        )
    return overrides


def _parse_nullable_text(value: str, field_name: str) -> str | None:
    text = value.strip()
    if text.lower() in {"none", "null"}:
        return None
    if not text:
        raise ValueError(f"{field_name} 必须是非空字符串或 none/null")
    return text


def _parse_nullable_integer(value: str, field_name: str) -> int | None:
    text = value.strip()
    if text.lower() in {"none", "null"}:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是整数或 none/null") from exc


def _generate(args: argparse.Namespace) -> int:
    paths = _paths_from_run_root(args.run_root)
    output_role = require_scene_replacement_role(
        _load_run_output_role(paths),
        stage="generate",
    )
    decision = require_generation_decision(paths)
    decision_output_role = require_scene_replacement_role(
        decision.output_role,
        stage="generate review-decision",
    )
    if decision_output_role != output_role:
        raise ValueError("review_decision.json 的 output_role 与当前 run 不一致")

    analysis_path = paths.analysis_dir / "product_analysis.json"
    canonical_path = paths.analysis_dir / "product_fidelity_constraints.json"
    snapshot_path = paths.review_dir / REFERENCE_COMPOSITION_SNAPSHOT_FILE_NAME
    product = load_product_analysis(analysis_path)
    fidelity_constraints = load_product_fidelity_constraints(canonical_path)
    reference_snapshot = load_reference_composition_snapshot(snapshot_path)
    validate_product_fidelity_constraints(product, fidelity_constraints)
    validate_necklace_reference_selection(paths, product, decision)
    selected_references = _load_selected_references(paths.analysis_dir / "selected_references.json")
    references_by_rank = _references_by_rank(selected_references)
    prompts_by_rank = {}
    for rank in _generation_ranks(decision):
        if rank not in references_by_rank:
            raise KeyError(f"人工决策选择的 rank {rank} 不在 selected_references.json 中")
        prompts_by_rank[rank] = build_prompt(
            product,
            references_by_rank[rank],
            fidelity_constraints,
            output_role=output_role,
            reference_snapshot=reference_snapshot,
        )
    run_generation(
        paths,
        paths.input_dir / "product-on-hand.jpg",
        prompts_by_rank,
        args.helper_script,
        wait=not args.no_wait,
        reference_snapshot=reference_snapshot,
        product_analysis_path=analysis_path,
        fidelity_constraints_path=canonical_path,
    )
    return 0


def _record_output_role(
    paths: RunPaths,
    args: argparse.Namespace,
    data: dict[str, Any],
) -> None:
    expected_role = require_scene_replacement_role(
        _load_run_output_role(paths),
        stage="record-decision run",
    )
    requested_role = require_scene_replacement_role(
        args.output_role,
        stage="record-decision",
    )
    if requested_role is not expected_role:
        raise ValueError("record-decision 的 output_role 与当前 run 不一致")
    data["output_role"] = requested_role.value


def _load_run_output_role(paths: RunPaths) -> OutputRole | None:
    role_path = paths.analysis_dir / OUTPUT_ROLE_FILE_NAME
    if not role_path.is_file():
        return None
    data = read_json(role_path)
    if not isinstance(data, dict):
        raise ValueError(f"{role_path} 必须是 JSON 对象")
    return normalize_output_role(data.get("output_role"))


def _qc(args: argparse.Namespace) -> int:
    fidelity_checks = _load_optional_fidelity_checks(args.fidelity_checks_json)
    checklist_checks = _load_optional_checklist_checks(args.checklist_checks_json)
    reference_checks = _load_optional_reference_preservation_checks(
        args.reference_preservation_checks_json
    )
    critical_failures = _parse_critical_failures(args.critical_failures)
    ensure_qc_review_ready(args.generation_dir)
    write_qc_result(
        args.generation_dir,
        args.status,
        _parse_string_list(args.passed),
        _parse_string_list(args.failed),
        args.notes,
        fidelity_checks=fidelity_checks,
        checklist_checks=checklist_checks,
        reference_preservation_checks=reference_checks,
        critical_failures=critical_failures,
    )
    return 0


def _paths_from_run_root(run_root: str | Path) -> RunPaths:
    return RunPaths(root=Path(run_root))


def _ensure_prepare_run_is_empty(output_root: str | Path, run_id: str) -> None:
    run_root = Path(output_root) / run_id
    if not run_root.exists():
        return
    if not run_root.is_dir():
        raise ValueError(f"目标 run 路径已存在且不是目录：{run_root}")
    if any(run_root.iterdir()):
        raise ValueError(f"目标 run 目录已存在且非空，拒绝复用：{run_root}")


def _load_optional_dimensions(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError("--dimensions-json 必须是 JSON 对象")
    return data


def _load_optional_fidelity_checks(path: str | None) -> list[Any]:
    if not path:
        return []
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError("--fidelity-checks-json 必须是 JSON 数组")
    return data


def _load_optional_checklist_checks(path: str | None) -> list[Any]:
    if not path:
        return []
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError("--checklist-checks-json 必须是 JSON 数组")
    return data


def _load_optional_reference_preservation_checks(
    path: str | None,
) -> list[Any]:
    if not path:
        return []
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(
            "--reference-preservation-checks-json 必须是 JSON 数组"
        )
    return data


def _parse_int_list(values: list[str] | None) -> list[int]:
    ranks: list[int] = []
    for item in _split_csv_values(values):
        try:
            ranks.append(int(item))
        except ValueError as exc:
            raise ValueError(f"selected_ranks 包含无效 rank: {item!r}") from exc
    return ranks


def _ensure_unique_ranks(ranks: list[int]) -> None:
    if len(ranks) != len(set(ranks)):
        raise ValueError("selected_ranks 不能包含重复 rank")


def _parse_string_list(values: list[str] | None) -> list[str]:
    return _split_csv_values(values)


def _parse_critical_failures(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    result: list[str] = []
    for value in values:
        parts = value.split(",")
        if any(not part.strip() for part in parts):
            raise ValueError("--critical-failures 不能包含空值或空的逗号分段")
        result.extend(part.strip() for part in parts)
    return result


def _split_csv_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def _load_selected_references(path: Path) -> list[ScoredReference]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"{path} 必须是列表")
    return [_scored_reference_from_dict(item, path) for item in data]


def _references_by_rank(references: list[ScoredReference]) -> dict[int, ScoredReference]:
    references_by_rank: dict[int, ScoredReference] = {}
    for reference in references:
        if reference.rank in references_by_rank:
            raise ValueError(f"selected_references.json 中存在重复 rank: {reference.rank}")
        references_by_rank[reference.rank] = reference
    return references_by_rank


def _generation_ranks(decision: ReviewDecision) -> list[int]:
    if decision.action == "generate_rank_1":
        return [1]
    if decision.selected_ranks:
        return list(decision.selected_ranks)
    return [1]


def _scored_reference_from_dict(item: Any, path: Path) -> ScoredReference:
    if not isinstance(item, dict):
        raise ValueError(f"{path} 中的 selected reference 必须是对象")
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    reference_path = item.get("selected_reference")
    if not isinstance(reference_path, str) or not reference_path.strip():
        raise ValueError(f"{path} 中缺少 selected_reference")
    score = _required_int(item.get("score"), "score")
    rank = _required_int(item.get("rank"), "rank")

    row_data = dict(metadata)
    if "index" not in row_data and "序号" not in row_data:
        row_data["index"] = rank
    row_data["absolute_path"] = reference_path
    if "relative_path" not in row_data and "相对路径" in metadata:
        row_data["relative_path"] = metadata["相对路径"]
    row_data.setdefault("relative_path", Path(reference_path).name)
    row_data.setdefault(
        "file_name",
        metadata.get("file_name") or metadata.get("文件名") or Path(reference_path).name,
    )
    row_data.setdefault("purpose_category", "")
    row_data.setdefault("bracelet_applicability", "")
    row_data.setdefault("default_strategy", "")
    row_data.setdefault("style_category", "")
    row_data.setdefault("scene_keywords", "")
    row_data.setdefault("jewelry_type", "")
    row_data.setdefault("recommended_usage", "")
    row_data.setdefault("notes", "")
    row_data.setdefault("confidence", "")
    row_data.setdefault("file_exists", Path(reference_path).is_file())

    row = ReferenceRow.from_dict(row_data)
    return ScoredReference(
        row=row,
        score=score,
        rank=rank,
        reason=tuple(_string_items(item.get("reason"), "reason")),
        risk=tuple(_string_items(item.get("risk"), "risk")),
        ignored_reference_jewelry=tuple(
            _string_items(item.get("ignored_reference_jewelry"), "ignored_reference_jewelry")
        ),
    )


def _required_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 必须是整数")
    return value


def _string_items(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} 必须是字符串列表")
    return value


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


if __name__ == "__main__":
    raise SystemExit(main())
