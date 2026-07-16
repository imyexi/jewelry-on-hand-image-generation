from __future__ import annotations

import os
import hashlib
import shutil
from html import escape
from urllib.parse import quote
from pathlib import Path
from typing import Sequence

from jewelry_on_hand.category_policies import get_category_policy
from jewelry_on_hand.display_modes import validate_product_mode
from jewelry_on_hand.models import ProductAnalysis, ProductFidelityConstraints, ReferenceRow
from jewelry_on_hand.product_fidelity import CONSTRAINTS_FILE_NAME, load_product_fidelity_constraints
from jewelry_on_hand.models import ScoredReference
from jewelry_on_hand.product_types import ProductType
from jewelry_on_hand.run_paths import RunPaths, read_json, write_json


def write_review_package(
    paths: RunPaths,
    product_image: str | Path,
    selected: Sequence[ScoredReference],
    candidates: Sequence[ScoredReference],
) -> Path:
    selected_items = list(selected)
    candidate_items = list(candidates)
    product_path = _validate_product_image(paths, product_image)
    _validate_selected_targets(paths.review_dir, selected_items)

    write_json(
        paths.analysis_dir / "reference_candidates.json",
        [item.to_dict() for item in candidate_items],
    )

    copied_references = _copy_selected_references(paths.review_dir, selected_items)
    write_json(
        paths.analysis_dir / "selected_references.json",
        [_selected_item_to_dict(item, copied_references[item.rank]) for item in selected_items],
    )

    html_path = paths.review_dir / "review.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        _render_html(paths, product_path, selected_items, candidate_items, copied_references),
        encoding="utf-8",
    )
    return html_path


def _copy_selected_references(
    review_dir: Path,
    selected: Sequence[ScoredReference],
) -> dict[int, Path]:
    review_dir.mkdir(parents=True, exist_ok=True)
    for stale_reference in review_dir.glob("rank-*"):
        if stale_reference.is_file():
            stale_reference.unlink()
    copied: dict[int, Path] = {}
    for item in selected:
        source = item.row.absolute_path
        destination = _reference_destination(review_dir, item)
        shutil.copy2(source, destination)
        copied[item.rank] = destination
    return copied


def _selected_item_to_dict(item: ScoredReference, review_copy: Path) -> dict[str, object]:
    data = item.to_dict()
    source_path = str(item.row.absolute_path.resolve())
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["source_reference"] = source_path
    metadata["source_absolute_path"] = source_path
    metadata["source_relative_path"] = item.row.relative_path
    metadata["source_file_name"] = item.row.file_name
    metadata["source_sha256"] = _file_sha256(item.row.absolute_path)
    metadata["review_sha256"] = _file_sha256(review_copy)
    metadata.setdefault("relative_path", item.row.relative_path)
    metadata.setdefault("相对路径", item.row.relative_path)
    data["metadata"] = metadata
    data["selected_reference"] = str(review_copy.resolve())
    return data


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
) -> str:
    product_src = _html_path(product_image, paths.review_dir)
    selected_cards = "\n".join(
        _render_card(item, paths.review_dir, copied_references.get(item.rank))
        for item in selected
    )
    candidate_cards = "\n".join(
        _render_card(item, paths.review_dir, copied_references.get(item.rank))
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
      <img src="{product_src}" alt="产品图预览">
      <div>
        <p class="badge">产品图预览</p>
        <p>用于确认上手参考图与产品图之间的构图、场景、风险和可忽略的参考图原有饰品。</p>
      </div>
    </section>

    {_render_fidelity_section(_load_optional_fidelity_constraints(paths))}

    {_render_product_confirmation(_load_optional_product_analysis(paths))}

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


def _load_optional_product_analysis(paths: RunPaths) -> ProductAnalysis | None:
    analysis_path = paths.analysis_dir / "product_analysis.json"
    if not analysis_path.is_file():
        return None
    return ProductAnalysis.from_dict(read_json(analysis_path))


def _render_product_confirmation(analysis: ProductAnalysis | None) -> str:
    if analysis is None:
        return ""
    support_status = _analysis_support_status(analysis)
    return f"""<section class="card">
      <h2>产品确认</h2>
      <dl>
        <dt>自动识别品类</dt><dd>{_text(analysis.detected_product_type.value)}</dd>
        <dt>最终确认品类</dt><dd>{_text(analysis.confirmed_product_type.value)}</dd>
        <dt>分类置信度</dt><dd>{_text(analysis.classification_confidence)}</dd>
        <dt>分类证据</dt><dd>{_list(analysis.classification_evidence)}</dd>
        <dt>分类来源</dt><dd>{_text(analysis.classification_source)}</dd>
        <dt>输入图类型</dt><dd>{_text(analysis.source_image_type.value)}</dd>
        <dt>展示模式</dt><dd>{_text(analysis.display_mode.value)}</dd>
        {_render_ring_confirmation_fields(analysis)}
        <dt>层数</dt><dd>{_text(analysis.layer_count)}</dd>
        <dt>长度等级</dt><dd>{_optional_text(analysis.length_category)}</dd>
        <dt>吊坠存在</dt><dd>{_text("是" if analysis.has_pendant else "否")}</dd>
        <dt>吊坠数量</dt><dd>{_text(analysis.pendant_count)}</dd>
        <dt>吊坠所属层</dt><dd>{_optional_text(analysis.pendant_layer)}</dd>
        <dt>吊坠位置</dt><dd>{_optional_text(analysis.pendant_position)}</dd>
        <dt>吊坠朝向</dt><dd>{_optional_text(analysis.pendant_orientation)}</dd>
        <dt>吊坠连接</dt><dd>{_optional_text(analysis.connection_structure)}</dd>
        <dt>多件独立组合</dt><dd>{_text("是" if analysis.is_independent_multi_item else "否")}</dd>
        <dt>遮挡区域</dt><dd>{_list(analysis.occluded_parts)}</dd>
        <dt>不确定细节</dt><dd>{_list(analysis.uncertain_details)}</dd>
        <dt>支持状态</dt><dd>{_text(support_status)}</dd>
      </dl>
    </section>"""


def _render_ring_confirmation_fields(analysis: ProductAnalysis) -> str:
    if analysis.confirmed_product_type is not ProductType.RING:
        return ""
    return (
        f"<dt>戒指数量</dt><dd>{_text(analysis.ring_count)}（仅支持单枚）</dd>"
        f"<dt>左右手</dt><dd>{_text(analysis.hand_side.display_name)}</dd>"
        f"<dt>佩戴手指</dt><dd>{_text(analysis.finger_position.display_name)}</dd>"
        f"<dt>佩戴方式</dt><dd>{_text(analysis.ring_wear_style.display_name)}</dd>"
    )


def _analysis_support_status(analysis: ProductAnalysis) -> str:
    product_type = analysis.confirmed_product_type
    if product_type is ProductType.PENDANT_ONLY:
        return "不支持：当前版本不支持无链独立吊坠，且禁止自动补链"
    if product_type is ProductType.UNKNOWN:
        return "不支持：产品品类无法识别，必须先人工纠正"
    try:
        validate_product_mode(product_type, analysis.display_mode, analysis.source_image_type)
        get_category_policy(product_type).validate_generation(
            layer_count=analysis.layer_count,
            is_independent_multi_item=analysis.is_independent_multi_item,
        )
    except ValueError as exc:
        return f"不支持：{exc}"
    return "支持：完成产品分析与保真确认后可记录生成决策"


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


def _render_card(item: ScoredReference, review_dir: Path, image_path: Path | None) -> str:
    image_html = ""
    if image_path is not None:
        image_html = (
            f'<img class="reference-image" src="{_html_path(image_path, review_dir)}" '
            f'alt="{_text(item.row.file_name)}">'
        )
    return f"""<article class="card">
  {image_html}
  <h3>{_text(item.row.file_name)}</h3>
  <p class="badge">Rank {_text(item.rank)} · Score {_text(item.score)}</p>
  <dl>
    <dt>用途</dt>
    <dd>{_text(item.row.purpose_category)}</dd>
    <dt>风格</dt>
    <dd>{_text(item.row.style_category)}</dd>
    <dt>场景关键词</dt>
    <dd>{_text(item.row.scene_keywords)}</dd>
    <dt>适用品类</dt>
    <dd>{_optional_text(item.row.applicable_product_types)}</dd>
    <dt>适用展示模式</dt>
    <dd>{_optional_text(item.row.applicable_display_modes)}</dd>
    <dt>人物取景</dt>
    <dd>{_optional_text(item.row.framing)}</dd>
    <dt>目标落点/身体区域</dt>
    <dd>{_optional_text(item.row.visible_body_regions)}</dd>
    <dt>预计展示面积</dt>
    <dd>{_optional_text(item.row.product_visibility)}</dd>
    <dt>衣领类型</dt>
    <dd>{_optional_text(item.row.collar_type)}</dd>
    <dt>衣物遮挡风险</dt>
    <dd>{_optional_text(item.row.clothing_occlusion_risk)}</dd>
    <dt>头发遮挡风险</dt>
    <dd>{_optional_text(item.row.hair_occlusion_risk)}</dd>
    <dt>裁切风险</dt>
    <dd>{_optional_text(item.row.crop_risk)}</dd>
    <dt>原有首饰</dt>
    <dd>{_optional_text(item.row.existing_jewelry)}</dd>
    {_render_ring_reference_fields(item.row)}
    <dt>入选理由</dt>
    <dd>{_list(item.reason)}</dd>
    <dt>风险说明</dt>
    <dd>{_list(item.risk)}</dd>
    <dt>需要移除/忽略的首饰</dt>
    <dd>{_list(item.ignored_reference_jewelry)}</dd>
  </dl>
</article>"""


def _render_ring_reference_fields(row: ReferenceRow) -> str:
    fields = (
        ("左右手", getattr(row, "hand_side")),
        ("可见手指", getattr(row, "visible_fingers")),
        ("手部朝向", getattr(row, "hand_orientation")),
        ("戒面可见度", getattr(row, "ring_face_visibility")),
        ("手指分离度", getattr(row, "finger_separation")),
        ("手指遮挡风险", getattr(row, "finger_occlusion_risk")),
    )
    if not any(value for _label, value in fields):
        return ""
    return "".join(
        f"<dt>{_text(label)}</dt><dd>{_optional_text(value)}</dd>"
        for label, value in fields
    )


def _list(items: Sequence[str]) -> str:
    if not items:
        return "<ul><li>无</li></ul>"
    return "<ul>" + "".join(f"<li>{_text(item)}</li>" for item in items) + "</ul>"


def _html_path(path: Path, review_dir: Path) -> str:
    relative = os.path.relpath(path, start=review_dir).replace("\\", "/")
    encoded = quote(relative, safe="/")
    return escape(encoded, quote=True)


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _optional_text(value: object | None) -> str:
    if value is None or value == "":
        return "未确认"
    return _text(value)


__all__ = ["write_review_package"]
