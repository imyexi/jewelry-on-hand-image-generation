from __future__ import annotations

import os
import shutil
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Sequence
from urllib.parse import quote

from jewelry_on_hand.models import ProductFidelityConstraints, ScoredReference
from jewelry_on_hand.product_fidelity import (
    CONSTRAINTS_FILE_NAME,
    load_product_fidelity_constraints,
)
from jewelry_on_hand.reference_composition import (
    REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME,
    ReferenceCompositionSnapshot,
    validate_snapshot_binding,
)
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


def write_review_package(
    paths: RunPaths,
    product_image: str | Path,
    selected: Sequence[ScoredReference],
    candidates: Sequence[ScoredReference],
    *,
    composition_snapshots: Sequence[ReferenceCompositionSnapshot],
) -> Path:
    selected_items = list(selected)
    candidate_items = list(candidates)
    snapshot_items = list(composition_snapshots)
    product_path = _validate_product_image(paths, product_image)
    _validate_selected_targets(paths.review_dir, selected_items)
    snapshots_by_rank = _validate_composition_snapshots(
        selected_items,
        snapshot_items,
    )

    copied_references = _copy_selected_references(paths.review_dir, selected_items)
    reference_hashes = _validate_copied_reference_hashes(
        selected_items,
        copied_references,
        snapshots_by_rank,
    )
    write_json(
        paths.analysis_dir / "reference_candidates.json",
        [item.to_dict() for item in candidate_items],
    )
    write_json(
        paths.analysis_dir / "selected_references.json",
        [
            _selected_item_to_dict(
                item,
                copied_references[item.rank],
                *reference_hashes[item.rank],
            )
            for item in selected_items
        ],
    )
    write_json(
        paths.analysis_dir / REFERENCE_COMPOSITION_SNAPSHOTS_FILE_NAME,
        [snapshot.to_dict() for snapshot in snapshot_items],
    )

    html_path = paths.review_dir / "review.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        _render_html(
            paths,
            product_path,
            selected_items,
            candidate_items,
            copied_references,
            snapshots_by_rank,
        ),
        encoding="utf-8",
    )
    return html_path


def _copy_selected_references(
    review_dir: Path,
    selected: Sequence[ScoredReference],
) -> dict[int, Path]:
    review_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[int, Path] = {}
    for item in selected:
        source = item.row.absolute_path
        destination = _reference_destination(review_dir, item)
        shutil.copy2(source, destination)
        copied[item.rank] = destination
    return copied


def _selected_item_to_dict(
    item: ScoredReference,
    review_copy: Path,
    source_sha256: str,
    review_sha256: str,
) -> dict[str, object]:
    data = item.to_dict()
    source_path = str(item.row.absolute_path.resolve())
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["source_reference"] = source_path
    metadata["source_absolute_path"] = source_path
    metadata["source_relative_path"] = item.row.relative_path
    metadata["source_file_name"] = item.row.file_name
    metadata["source_sha256"] = source_sha256
    metadata["review_sha256"] = review_sha256
    metadata.setdefault("relative_path", item.row.relative_path)
    metadata.setdefault("相对路径", item.row.relative_path)
    data["metadata"] = metadata
    data["selected_reference"] = str(review_copy.resolve())
    data["source_sha256"] = source_sha256
    data["review_sha256"] = review_sha256
    return data


def _validate_composition_snapshots(
    selected: Sequence[ScoredReference],
    snapshots: Sequence[ReferenceCompositionSnapshot],
) -> dict[int, ReferenceCompositionSnapshot]:
    if any(not isinstance(item, ReferenceCompositionSnapshot) for item in snapshots):
        raise ValueError("composition_snapshots 必须全部是 ReferenceCompositionSnapshot")
    selected_ranks = [item.rank for item in selected]
    snapshot_ranks = [item.rank for item in snapshots]
    if len(snapshot_ranks) != len(set(snapshot_ranks)):
        raise ValueError("候选构图快照中存在重复 rank")
    if set(snapshot_ranks) != set(selected_ranks):
        raise ValueError("候选构图快照 rank 集合必须与 selected rank 集合完全一致")
    roles = {item.output_role for item in snapshots}
    if len(roles) > 1:
        raise ValueError("同一审核包的候选构图快照 output_role 必须一致")

    snapshots_by_rank = {item.rank: item for item in snapshots}
    for reference in selected:
        snapshot = snapshots_by_rank[reference.rank]
        validate_snapshot_binding(
            snapshot,
            reference_file=reference.row.absolute_path,
            output_role=snapshot.output_role,
            expected_rank=reference.rank,
        )
    return snapshots_by_rank


def _validate_copied_reference_hashes(
    selected: Sequence[ScoredReference],
    copied_references: dict[int, Path],
    snapshots_by_rank: dict[int, ReferenceCompositionSnapshot],
) -> dict[int, tuple[str, str]]:
    hashes: dict[int, tuple[str, str]] = {}
    for item in selected:
        source_sha = _file_sha256(item.row.absolute_path)
        review_sha = _file_sha256(copied_references[item.rank])
        if snapshots_by_rank[item.rank].reference_sha256 != source_sha:
            raise ValueError(f"候选构图快照 rank {item.rank} 的源参考图 SHA-256 不一致")
        if source_sha != review_sha:
            raise ValueError(f"参考图 rank {item.rank} 的源文件与审核副本 SHA-256 不一致")
        hashes[item.rank] = (source_sha, review_sha)
    return hashes


def _file_sha256(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _validate_product_image(paths: RunPaths, product_image: str | Path) -> Path:
    product_path = Path(product_image)
    if not product_path.is_file():
        raise FileNotFoundError(product_path)
    root = paths.root.resolve()
    resolved = product_path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("产品图必须位于当前 run 目录内，请先复制到 input/product-on-hand.jpg")
    return product_path


def _validate_selected_targets(
    review_dir: Path, selected: Sequence[ScoredReference]
) -> None:
    seen_ranks: set[int] = set()
    seen_targets: set[Path] = set()
    for item in selected:
        if item.rank in seen_ranks:
            raise ValueError(f"selected 中存在重复 rank: {item.rank}")
        seen_ranks.add(item.rank)
        destination = _reference_destination(review_dir, item)
        if destination in seen_targets:
            raise ValueError(f"selected 参考图复制目标冲突: {destination.name}")
        seen_targets.add(destination)


def _reference_destination(review_dir: Path, item: ScoredReference) -> Path:
    return review_dir / f"rank-{item.rank}-{Path(item.row.file_name).name}"


def _render_html(
    paths: RunPaths,
    product_image: Path,
    selected: Sequence[ScoredReference],
    candidates: Sequence[ScoredReference],
    copied_references: dict[int, Path],
    snapshots_by_rank: dict[int, ReferenceCompositionSnapshot],
) -> str:
    product_src = _html_path(product_image, paths.review_dir)
    selected_cards = "\n".join(
        _render_card(
            item,
            paths.review_dir,
            copied_references.get(item.rank),
            snapshots_by_rank.get(item.rank),
        )
        for item in selected
    )
    candidate_cards = "\n".join(
        _render_card(item, paths.review_dir, copied_references.get(item.rank), None)
        for item in candidates
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>参考图 Review 包</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f1e8;
      --card: #fffaf1;
      --ink: #271c16;
      --muted: #705f50;
      --line: #dfcfbd;
      --accent: #9b3f24;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 12% 8%, #fff6dc 0 16rem, transparent 17rem), var(--bg);
      color: var(--ink);
      font-family: "Noto Serif SC", "Source Han Serif SC", serif;
      line-height: 1.6;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 36px 0 56px;
    }}
    h1, h2, h3 {{
      line-height: 1.15;
    }}
    h1 {{
      margin: 0 0 24px;
      font-size: clamp(2rem, 5vw, 4rem);
      letter-spacing: -0.06em;
    }}
    h2 {{
      margin: 36px 0 16px;
      font-size: clamp(1.5rem, 3vw, 2.2rem);
    }}
    .hero, .card {{
      border: 1px solid var(--line);
      border-radius: 22px;
      background: color-mix(in srgb, var(--card) 92%, white);
      box-shadow: 0 18px 45px rgb(74 47 24 / 12%);
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(220px, 360px) 1fr;
      gap: 24px;
      align-items: center;
      padding: 20px;
    }}
    .hero img, .reference-image {{
      width: 100%;
      max-height: 360px;
      object-fit: contain;
      border-radius: 16px;
      background: #efe4d6;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .card {{
      padding: 18px;
    }}
    .badge {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 12px;
      padding: 5px 10px;
      border-radius: 999px;
      background: #f0d8c7;
      color: var(--accent);
      font-weight: 700;
    }}
    dl {{
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: 8px 12px;
      margin: 12px 0;
    }}
    dt {{
      color: var(--muted);
      font-weight: 700;
    }}
    dd {{
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    ul {{
      margin: 6px 0 0;
      padding-left: 1.2em;
    }}
    @media (max-width: 720px) {{
      .hero {{
        grid-template-columns: 1fr;
      }}
      dl {{
        grid-template-columns: 1fr;
      }}
      dt {{
        margin-top: 8px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>参考图 Review 包</h1>
    <section class="hero">
      <img src="{product_src}" alt="产品身份图">
      <div>
        <p class="badge">产品身份图</p>
        <p>此图只用于锁定产品身份、结构、材质与排列，不提供参考底图的皮肤、姿势或背景。</p>
      </div>
    </section>

    {_render_product_analysis_section(paths)}

    {_render_fidelity_section(_load_optional_fidelity_constraints(paths))}

    <section class="card">
      <h2>人工确认提示</h2>
      <p>逐张核对参考底图和候选构图快照；预计展示面积不足时不要选择，存在阻断性文字或 UI 时不要选择。</p>
    </section>

    <section>
      <h2>Top 3 参考图</h2>
      <div class="grid">
        {selected_cards or '<p>暂无已选参考图。</p>'}
      </div>
    </section>

    <section>
      <h2>全部候选参考图</h2>
      <div class="grid">
        {candidate_cards or '<p>暂无候选参考图。</p>'}
      </div>
    </section>
  </main>
</body>
</html>
"""


def _load_optional_fidelity_constraints(paths: RunPaths) -> ProductFidelityConstraints | None:
    constraints_path = paths.analysis_dir / CONSTRAINTS_FILE_NAME
    if not constraints_path.is_file():
        return None
    return load_product_fidelity_constraints(constraints_path)


def _render_product_analysis_section(paths: RunPaths) -> str:
    analysis_path = paths.analysis_dir / "product_analysis.json"
    if not analysis_path.is_file():
        return ""
    analysis = read_json(analysis_path)
    if not isinstance(analysis, dict):
        raise ValueError(f"{analysis_path} 必须是 JSON 对象")
    fields = (
        ("自动识别品类", "detected_product_type"),
        ("最终确认品类", "confirmed_product_type"),
        ("分类置信度", "classification_confidence"),
        ("分类证据", "classification_evidence"),
        ("分类来源", "classification_source"),
        ("输入图类型", "source_image_type"),
        ("展示模式", "display_mode"),
        ("层数", "layer_count"),
        ("长度等级", "length_category"),
        ("吊坠存在", "has_pendant"),
        ("吊坠数量", "pendant_count"),
        ("吊坠所属层", "pendant_layer"),
        ("吊坠位置", "pendant_position"),
        ("吊坠朝向", "pendant_orientation"),
        ("吊坠连接", "connection_structure"),
        ("遮挡区域", "occluded_parts"),
        ("不确定细节", "uncertain_details"),
    )
    details = "".join(
        f"<dt>{_text(label)}</dt><dd>{_display_value(analysis.get(key))}</dd>"
        for label, key in fields
    )
    unsupported_reason = ""
    if analysis.get("confirmed_product_type") == "pendant_only":
        unsupported_reason = "当前版本不支持无链独立吊坠，且禁止自动补链"
    support_status = unsupported_reason or "当前产品分析可进入人工参考图审核"
    return f"""<section class="card">
      <h2>产品确认</h2>
      <dl>
        {details}
        <dt>支持状态</dt><dd>{_text(support_status)}</dd>
      </dl>
    </section>"""


def _render_fidelity_section(
    constraints: ProductFidelityConstraints | None,
) -> str:
    if constraints is None:
        return ""
    status_label = {
        "pending": "待确认",
        "confirmed": "已确认",
        "corrected": "已修正",
        "not_applicable": "不适用",
    }[constraints.review_status]
    must_keep = "\n".join(_render_must_keep_item(item) for item in constraints.must_keep)
    if not must_keep:
        must_keep = "<p>无额外局部关键识别点；仍需保留产品整体可见外观。</p>"
    return f"""<section class="card">
      <h2>产品保真约束</h2>
      <p class="badge">状态：{_text(status_label)}</p>
      <dl>
        <dt>检测关键词</dt>
        <dd>{_list(constraints.detected_keywords)}</dd>
        <dt>关键识别点</dt>
        <dd>{must_keep}</dd>
        <dt>禁止变化</dt>
        <dd>{_list(constraints.must_not_change)}</dd>
        <dt>局部裁切</dt>
        <dd>{_text("建议" if constraints.detail_crop_recommended else "不需要")}</dd>
      </dl>
    </section>"""


def _render_must_keep_item(item: object) -> str:
    name = getattr(item, "name")
    location = getattr(item, "location")
    visual_shape = getattr(item, "visual_shape")
    relationship = getattr(item, "relationship")
    forbid = getattr(item, "forbid")
    qc_question = getattr(item, "qc_question")
    return (
        "<article>"
        f"<h3>{_text(name)}</h3>"
        "<dl>"
        f"<dt>位置</dt><dd>{_text(location)}</dd>"
        f"<dt>可见形态</dt><dd>{_text(visual_shape)}</dd>"
        f"<dt>相邻关系</dt><dd>{_text(relationship)}</dd>"
        f"<dt>禁止</dt><dd>{_list(forbid)}</dd>"
        f"<dt>QC 问题</dt><dd>{_text(qc_question)}</dd>"
        "</dl>"
        "</article>"
    )


def _render_card(
    item: ScoredReference,
    review_dir: Path,
    image_path: Path | None,
    snapshot: ReferenceCompositionSnapshot | None,
) -> str:
    image_html = ""
    if image_path is not None:
        image_html = (
            f'<img class="reference-image" src="{_html_path(image_path, review_dir)}" '
            f'alt="{_text(item.row.file_name)}">'
        )
    return f"""<article class="card">
  {image_html}
  <h3>{_text(item.row.file_name)}</h3>
  {('<p class="badge">参考底图</p>' if snapshot is not None else '')}
  <p class="badge">Rank {_text(item.rank)} · Score {_text(item.score)}</p>
  <dl>
    <dt>用途分类</dt>
    <dd>{_text(item.row.purpose_category)}</dd>
    <dt>风格分类</dt>
    <dd>{_text(item.row.style_category)}</dd>
    <dt>场景关键词</dt>
    <dd>{_text(item.row.scene_keywords)}</dd>
    <dt>适用品类</dt>
    <dd>{_text(item.row.applicable_product_types)}</dd>
    <dt>适用展示模式</dt>
    <dd>{_text(item.row.applicable_display_modes)}</dd>
    <dt>人物取景</dt>
    <dd>{_text(item.row.framing)}</dd>
    <dt>目标落点/身体区域</dt>
    <dd>{_text(item.row.visible_body_regions)}</dd>
    <dt>预计展示面积</dt>
    <dd>{_text(item.row.product_visibility)}</dd>
    <dt>衣领类型</dt>
    <dd>{_text(item.row.collar_type)}</dd>
    <dt>衣物遮挡风险</dt>
    <dd>{_text(item.row.clothing_occlusion_risk)}</dd>
    <dt>头发遮挡风险</dt>
    <dd>{_text(item.row.hair_occlusion_risk)}</dd>
    <dt>裁切风险</dt>
    <dd>{_text(item.row.crop_risk)}</dd>
    <dt>原有首饰</dt>
    <dd>{_text(item.row.existing_jewelry)}</dd>
    <dt>入选理由</dt>
    <dd>{_list(item.reason)}</dd>
    <dt>风险说明</dt>
    <dd>{_list(item.risk)}</dd>
    <dt>需忽略首饰</dt>
    <dd>{_list(item.ignored_reference_jewelry)}</dd>
  </dl>
  {_render_composition_snapshot(snapshot)}
</article>"""


def _render_composition_snapshot(
    snapshot: ReferenceCompositionSnapshot | None,
) -> str:
    if snapshot is None:
        return ""
    pose = snapshot.pose
    target = snapshot.replacement_target
    risk_label = {
        "none": "无",
        "small_removable": "少量且可移除",
        "blocking": "阻断",
    }[snapshot.text_or_ui_risk]
    visibility = "充足" if snapshot.product_visibility_sufficient else "不足"
    pose_items = (
        f"身体：{pose.body}",
        f"手臂：{pose.arm}",
        f"手部：{pose.hand}",
        f"手侧：{pose.hand_side}",
    )
    return f"""<section class="composition-snapshot">
    <h4>候选构图快照</h4>
    <dl>
      <dt>输出角色</dt><dd>{_text(snapshot.output_role.value)}</dd>
      <dt>源图 SHA-256</dt><dd>{_text(snapshot.reference_sha256)}</dd>
      <dt>景别</dt><dd>{_text(snapshot.framing)}</dd>
      <dt>机位</dt><dd>{_text(snapshot.camera_angle)}</dd>
      <dt>主体位置</dt><dd>{_text(snapshot.subject_placement)}</dd>
      <dt>可见身体区域</dt><dd>{_list(snapshot.visible_body_regions)}</dd>
      <dt>姿势</dt><dd>{_list(pose_items)}</dd>
      <dt>服装</dt><dd>{_text(snapshot.clothing)}</dd>
      <dt>背景</dt><dd>{_text(snapshot.background)}</dd>
      <dt>光线</dt><dd>{_text(snapshot.lighting)}</dd>
      <dt>目标替换位置</dt><dd>{_text(target.body_region)}</dd>
      <dt>待替换原首饰</dt><dd>{_text(target.source_jewelry)}</dd>
      <dt>目标产品数量</dt><dd>{_text(target.target_product_count)}</dd>
      <dt>需移除首饰</dt><dd>{_list(snapshot.other_jewelry_to_remove)}</dd>
      <dt>UI 风险</dt><dd>{_text(risk_label)}</dd>
      <dt>展示面积</dt><dd>{_text(visibility)}</dd>
      <dt>构图签名</dt><dd>{_text(snapshot.composition_signature)}</dd>
    </dl>
  </section>"""


def _list(items: Sequence[str]) -> str:
    if not items:
        return "<ul><li>无</li></ul>"
    return "<ul>" + "".join(f"<li>{_text(item)}</li>" for item in items) + "</ul>"


def _display_value(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return _list(tuple(str(item) for item in value))
    if isinstance(value, bool):
        return _text("是" if value else "否")
    if value is None or value == "":
        return _text("未标注")
    return _text(value)


def _html_path(path: Path, review_dir: Path) -> str:
    relative = os.path.relpath(path, start=review_dir).replace("\\", "/")
    encoded = quote(relative, safe="/")
    return escape(encoded, quote=True)


def _text(value: object) -> str:
    return escape(str(value), quote=True)


__all__ = ["write_review_package"]
