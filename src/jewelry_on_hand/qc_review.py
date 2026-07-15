from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from jewelry_on_hand.output_roles import require_scene_replacement_role
from jewelry_on_hand.reference_composition import (
    ReferenceCompositionSnapshot,
)
from jewelry_on_hand.run_paths import read_json


REFERENCE_PRESERVATION_QUESTIONS = {
    "framing_preserved": "景别、裁切边界、主体大小和留白是否与参考底图一致",
    "pose_preserved": "身体、手臂、手掌朝向和手指关系是否与参考底图一致",
    "subject_placement_preserved": "人物和目标部位在画面中的位置是否保持",
    "person_preserved": "人物身份、脸、发型和可见身体区域是否保持",
    "clothing_preserved": "服装款式、衣领和遮挡关系是否保持",
    "background_preserved": "背景、道具和环境元素是否保持",
    "lighting_preserved": "光向、明暗、色温和整体色调是否保持",
    "source_jewelry_removed": "参考底图中的全部原首饰是否已清除",
    "replacement_target_preserved": "目标产品是否仅出现在确认的替换位置",
    "single_target_product": "结果中是否只有一件目标产品",
}


def build_reference_preservation_checklist(
    snapshot: ReferenceCompositionSnapshot,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(snapshot, ReferenceCompositionSnapshot):
        raise ValueError("snapshot 必须是 ReferenceCompositionSnapshot")
    return tuple(REFERENCE_PRESERVATION_QUESTIONS.items())


def write_qc_review_page(generation_dir: str | Path) -> Path:
    generation_path = Path(generation_dir)
    scene, product, result, snapshot_path = _review_inputs(generation_path)
    snapshot = ReferenceCompositionSnapshot.from_dict(read_json(snapshot_path))
    page_path = generation_path / "qc-review.html"
    page_path.write_text(
        _review_html(
            scene=scene,
            product=product,
            result=result,
            snapshot=snapshot,
        ),
        encoding="utf-8",
    )
    return page_path


def ensure_qc_review_ready(generation_dir: str | Path) -> None:
    generation_path = Path(generation_dir)
    manifest_path = generation_path / "input-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            "历史离线 QC 仅可只读；现代 qc 写入口要求 input-manifest.json"
        )
    manifest: Any = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("input-manifest.json 必须是 JSON 对象")
    require_scene_replacement_role(manifest.get("output_role"), stage="qc")
    _review_inputs(generation_path)
    _required_file(generation_path / "qc-review.html", "四栏 QC 审核页")


def _review_inputs(generation_path: Path) -> tuple[Path, Path, Path, Path]:
    return (
        _single_file(generation_path, "scene-reference.*", "参考底图"),
        _single_file(generation_path, "product-reference.*", "产品身份图"),
        _required_file(generation_path / "result.png", "生成结果"),
        _required_file(
            generation_path / "reference-composition-snapshot.json",
            "已确认构图快照",
        ),
    )


def _single_file(directory: Path, pattern: str, label: str) -> Path:
    matches = sorted(path for path in directory.glob(pattern) if path.is_file())
    if len(matches) != 1:
        raise ValueError(f"{label}必须是唯一文件，当前找到 {len(matches)} 个")
    return matches[0]


def _required_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"缺少{label}文件：{path}")
    return path


def _review_html(
    *,
    scene: Path,
    product: Path,
    result: Path,
    snapshot: ReferenceCompositionSnapshot,
) -> str:
    snapshot_json = json.dumps(
        snapshot.to_dict(),
        ensure_ascii=False,
        indent=2,
    )
    columns = (
        _image_column("参考底图", scene),
        _image_column("产品身份图", product),
        _image_column("生成结果", result),
        (
            '<section class="qc-column snapshot-column">'
            "<h2>已确认构图快照</h2>"
            f"<pre>{html.escape(snapshot_json)}</pre>"
            "</section>"
        ),
    )
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>人工 QC 审核页</title>
  <style>
    :root { color-scheme: light; font-family: "Microsoft YaHei", sans-serif; }
    body { margin: 0; padding: 24px; background: #ece9e1; color: #171715; }
    main { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
    .qc-column { min-width: 0; padding: 16px; background: #fff; border: 1px solid #c9c4b8; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    img { display: block; width: 100%; height: auto; object-fit: contain; background: #222; }
    pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.5; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 560px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <h1>人工 QC 审核</h1>
  <main>""" + "".join(columns) + """</main>
</body>
</html>
"""


def _image_column(title: str, path: Path) -> str:
    relative_path = html.escape(path.name, quote=True)
    return (
        '<section class="qc-column image-column">'
        f"<h2>{html.escape(title)}</h2>"
        f'<img src="{relative_path}" alt="{html.escape(title)}">'
        "</section>"
    )


__all__ = [
    "REFERENCE_PRESERVATION_QUESTIONS",
    "build_reference_preservation_checklist",
    "ensure_qc_review_ready",
    "write_qc_review_page",
]
