from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from jewelry_on_hand.generation import GenerationError, run_generation
from jewelry_on_hand.models import ReferenceRow, ReviewDecision, ScoredReference
from jewelry_on_hand.output_roles import (
    OUTPUT_ROLE_FILE_NAME,
    OutputRole,
    normalize_output_role,
    require_scene_replacement_role,
)
from jewelry_on_hand.product_analysis import (
    UnsupportedProductError,
    build_analysis_prompt,
    build_product_fidelity_constraints,
    load_product_analysis,
)
from jewelry_on_hand.product_fidelity import load_product_fidelity_constraints
from jewelry_on_hand.prompt_builder import build_prompt
from jewelry_on_hand.qc import write_qc_result
from jewelry_on_hand.reference_catalog import load_reference_rows
from jewelry_on_hand.reference_composition import build_candidate_snapshot
from jewelry_on_hand.review_decision import (
    ReviewGateError,
    require_generation_decision,
    write_review_decision,
)
from jewelry_on_hand.review_package import (
    _commit_review_packages,
    _discard_staged_review_packages,
    _stage_review_package,
    write_review_package,
)
from jewelry_on_hand.run_paths import RunPaths, create_run_id, read_json, write_json
from jewelry_on_hand.scoring import (
    select_batch_diverse_references,
    select_top_references,
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
    prepare.add_argument("--analysis-json")
    prepare.add_argument("--classification", required=True)
    prepare.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    prepare.add_argument("--run-id")
    prepare.add_argument("--dimensions-json")
    prepare.add_argument("--output-role", choices=[item.value for item in OutputRole])
    prepare.set_defaults(handler=_prepare_review)

    decision = subparsers.add_parser("record-decision", help="记录人工 review 决策。")
    decision.add_argument("--run-root", required=True)
    decision.add_argument("--action", required=True)
    decision.add_argument("--selected-ranks", action="append")
    decision.add_argument("--manual-reference")
    decision.add_argument("--fidelity-confirmed", action="store_true")
    decision.add_argument("--fidelity-notes")
    decision.add_argument("--fidelity-constraints-path")
    decision.add_argument("--output-role", choices=[item.value for item in OutputRole])
    decision.set_defaults(handler=_record_decision)

    generate = subparsers.add_parser("generate", help="通过 review gate 后提交生成任务。")
    generate.add_argument("--run-root", required=True)
    generate.add_argument("--helper-script", default=DEFAULT_HELPER_SCRIPT)
    generate.add_argument("--no-wait", action="store_true")
    generate.set_defaults(handler=_generate)

    rerank_batch = subparsers.add_parser(
        "rerank-batch",
        help="对多个既有 review run 执行批次级多样性重排。",
    )
    rerank_batch.add_argument("--output-root", required=True)
    rerank_batch.add_argument("--run-id", action="append", required=True)
    rerank_batch.set_defaults(handler=_rerank_batch)

    qc = subparsers.add_parser("qc", help="写入单次生成的质检结果。")
    qc.add_argument("--generation-dir", required=True)
    qc.add_argument("--status", required=True)
    qc.add_argument("--passed", action="append")
    qc.add_argument("--failed", action="append")
    qc.add_argument("--notes", default="")
    qc.add_argument("--fidelity-checks-json")
    qc.set_defaults(handler=_qc)

    return parser


def _prepare_review(args: argparse.Namespace) -> int:
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

    product = load_product_analysis(args.analysis_json)
    write_json(paths.analysis_dir / "product_analysis.json", read_json(args.analysis_json))
    constraints = build_product_fidelity_constraints(product)
    write_json(paths.analysis_dir / "product_fidelity_constraints.json", constraints.to_dict())
    rows = load_reference_rows(args.classification)
    write_json(
        paths.analysis_dir / OUTPUT_ROLE_FILE_NAME,
        {"output_role": output_role.value},
    )
    selected, candidates = select_top_references(product, rows, output_role)
    snapshots = tuple(
        build_candidate_snapshot(product, item, output_role)
        for item in selected
    )
    write_review_package(
        paths,
        copied_product,
        selected,
        candidates,
        composition_snapshots=snapshots,
    )
    return 0


def _record_decision(args: argparse.Namespace) -> int:
    paths = _paths_from_run_root(args.run_root)
    data: dict[str, Any] = {"action": args.action}
    _record_output_role(paths, args.output_role, data)
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
    write_review_decision(paths, data)
    return 0


def _generate(args: argparse.Namespace) -> int:
    paths = _paths_from_run_root(args.run_root)
    decision = require_generation_decision(paths)
    output_role = require_scene_replacement_role(
        _load_run_output_role(paths),
        stage="generate",
    )
    decision_output_role = require_scene_replacement_role(
        decision.output_role,
        stage="generate review-decision",
    )
    if decision_output_role != output_role:
        raise ValueError("review_decision.json 的 output_role 与当前 run 不一致")

    product = load_product_analysis(paths.analysis_dir / "product_analysis.json")
    fidelity_constraints = load_product_fidelity_constraints(
        paths.analysis_dir / "product_fidelity_constraints.json"
    )
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
        )
    run_generation(
        paths,
        paths.input_dir / "product-on-hand.jpg",
        prompts_by_rank,
        args.helper_script,
        wait=not args.no_wait,
    )
    return 0


def _rerank_batch(args: argparse.Namespace) -> int:
    run_ids = list(args.run_id)
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("rerank-batch 的 run-id 不能重复")

    paths_list = [
        _existing_batch_run_paths(args.output_root, run_id)
        for run_id in run_ids
    ]
    normalized_roots = [
        os.path.normcase(str(paths.root.resolve()))
        for paths in paths_list
    ]
    if len(normalized_roots) != len(set(normalized_roots)):
        raise ValueError("rerank-batch 的 run-id 解析后不能指向重复运行")
    products = []
    output_roles = []
    candidate_sets = []
    for paths in paths_list:
        decision_path = paths.review_dir / "review_decision.json"
        if decision_path.exists():
            raise ValueError(f"{paths.root} 已存在人工决策，拒绝批量重排")
        products.append(
            load_product_analysis(paths.analysis_dir / "product_analysis.json")
        )
        output_roles.append(
            require_scene_replacement_role(
                _load_run_output_role(paths),
                stage=f"rerank-batch {paths.root.name}",
            )
        )
        candidate_sets.append(
            _load_selected_references(
                paths.analysis_dir / "reference_candidates.json"
            )
        )

    selections = select_batch_diverse_references(
        candidate_sets,
        output_roles,
    )
    snapshots_by_run = [
        tuple(
            build_candidate_snapshot(product, item, output_role)
            for item in selected
        )
        for product, selected, output_role in zip(
            products,
            selections,
            output_roles,
            strict=True,
        )
    ]

    stages = []
    try:
        for paths, selected, candidates, snapshots in zip(
            paths_list,
            selections,
            candidate_sets,
            snapshots_by_run,
            strict=True,
        ):
            stages.append(
                _stage_review_package(
                    paths,
                    paths.input_dir / "product-on-hand.jpg",
                    selected,
                    candidates,
                    composition_snapshots=snapshots,
                )
            )
    except Exception:
        _discard_staged_review_packages(stages)
        raise
    _commit_review_packages(stages)
    return 0


def _existing_batch_run_paths(
    output_root: str | Path,
    run_id: str,
) -> RunPaths:
    root = Path(output_root).resolve()
    run_root = (root / run_id).resolve()
    if not run_root.is_relative_to(root) or run_root.parent != root:
        raise ValueError(f"rerank-batch 包含不安全的 run-id：{run_id!r}")
    if not run_root.is_dir():
        raise FileNotFoundError(run_root)
    return RunPaths(root=run_root)


def _record_output_role(
    paths: RunPaths,
    requested_value: str | None,
    data: dict[str, Any],
) -> None:
    expected_role = require_scene_replacement_role(
        _load_run_output_role(paths),
        stage="record-decision run",
    )
    requested_role = require_scene_replacement_role(
        requested_value,
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
    write_qc_result(
        args.generation_dir,
        args.status,
        _parse_string_list(args.passed),
        _parse_string_list(args.failed),
        args.notes,
        fidelity_checks=_load_optional_fidelity_checks(args.fidelity_checks_json),
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
    row_data.setdefault("purpose_category", metadata.get("用途分类", ""))
    row_data.setdefault("bracelet_applicability", "")
    row_data.setdefault("default_strategy", "")
    row_data.setdefault("style_category", metadata.get("风格分类", ""))
    row_data.setdefault("scene_keywords", metadata.get("场景关键词", ""))
    row_data.setdefault("jewelry_type", metadata.get("饰品类型", ""))
    row_data.setdefault("recommended_usage", metadata.get("推荐使用方式", ""))
    row_data.setdefault("notes", metadata.get("备注", ""))
    row_data.setdefault("confidence", metadata.get("判断置信度", ""))
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
