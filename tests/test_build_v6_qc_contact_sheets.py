import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "build_v6_qc_contact_sheets.py"
)


def test_images_for_uses_v6_product_and_three_role_results(tmp_path):
    spec = importlib.util.spec_from_file_location("build_v6_qc_contact_sheets", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for role in module.ROLES:
        path = tmp_path / f"QY002-{role}" / "generation" / "01"
        path.mkdir(parents=True)
        (path / "result.png").write_bytes(b"result")
    latest = tmp_path / "QY002-hero" / "generation" / "02"
    latest.mkdir(parents=True)
    (latest / "result.png").write_bytes(b"latest")
    source = tmp_path / "QY002-hero" / "input"
    source.mkdir(parents=True)
    (source / "product-on-hand.jpg").write_bytes(b"source")

    paths = module.images_for(tmp_path, "QY002")

    assert paths[0] == source / "product-on-hand.jpg"
    assert paths[1] == latest / "result.png"
    assert all(path.name == "result.png" for path in paths[1:])
