import re

import pytest

from jewelry_on_hand.run_paths import RunPaths, create_run_id, read_json, write_json


def test_run_paths_copy_product_and_write_dimensions(tmp_path):
    source = tmp_path / "product.jpg"; source.write_bytes(b"fake")
    paths = RunPaths.create(tmp_path, create_run_id("demo"))
    copied = paths.copy_product_image(source)
    write_json(paths.input_dir / "product_dimensions.json", {"bead_diameter_mm": 10})
    assert copied.name == "product-on-hand.jpg"
    assert read_json(paths.input_dir / "product_dimensions.json") == {"bead_diameter_mm": 10}


def test_create_run_id_same_prefix_is_unique():
    first = create_run_id("demo")
    second = create_run_id("demo")
    assert first != second
    assert first.startswith("demo-")
    assert second.startswith("demo-")


def test_create_run_id_is_safe_and_accepted_by_run_paths(tmp_path):
    run_id = create_run_id("demo")

    assert re.fullmatch(r"[A-Za-z0-9_-]+-\d{8}-\d{6}-\d{6}-[0-9a-f]{16}", run_id)
    paths = RunPaths.create(tmp_path, run_id)
    assert paths.root.name == run_id


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        ".",
        "/absolute",
        r"C:\absolute",
        "..",
        "../escape",
        r"..\escape",
        "a/b",
        r"a\b",
        "CON",
        "con",
        "CON.txt",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "com9.log",
        "LPT1",
        "lpt9.txt",
        "safe.",
        "...",
    ],
)
def test_run_paths_rejects_unsafe_run_id(tmp_path, run_id):
    with pytest.raises(ValueError):
        RunPaths.create(tmp_path, run_id)


@pytest.mark.parametrize("run_id", ["run-1", "valid_name", "valid.name"])
def test_run_paths_accepts_safe_run_id(tmp_path, run_id):
    paths = RunPaths.create(tmp_path, run_id)
    assert paths.root == tmp_path / run_id


def test_run_paths_creates_all_directories(tmp_path):
    paths = RunPaths.create(tmp_path, "safe-run")

    assert paths.input_dir.is_dir()
    assert paths.analysis_dir.is_dir()
    assert paths.review_dir.is_dir()
    assert paths.generation_dir.is_dir()


def test_copy_product_image_copies_content(tmp_path):
    source = tmp_path / "product.jpg"
    source.write_bytes(b"fake image bytes")
    paths = RunPaths.create(tmp_path, "copy-content")

    copied = paths.copy_product_image(source)

    assert copied.read_bytes() == b"fake image bytes"


def test_copy_product_detail_image_preserves_supported_suffix(tmp_path):
    source = tmp_path / "ring-detail.png"
    source.write_bytes(b"cropped ring")
    paths = RunPaths.create(tmp_path, "ring-detail")

    copied = paths.copy_product_detail_image(source)

    assert copied == paths.input_dir / "product-detail.png"
    assert copied.read_bytes() == b"cropped ring"


def test_copy_product_detail_image_rejects_unsupported_format(tmp_path):
    source = tmp_path / "ring-detail.txt"
    source.write_text("not image", encoding="utf-8")
    paths = RunPaths.create(tmp_path, "ring-detail-invalid")

    with pytest.raises(ValueError, match="jpg/jpeg/png/webp"):
        paths.copy_product_detail_image(source)


@pytest.mark.parametrize("source_name", ["missing.jpg", "directory"])
def test_copy_product_image_rejects_missing_file_or_directory(tmp_path, source_name):
    source = tmp_path / source_name
    if source_name == "directory":
        source.mkdir()
    paths = RunPaths.create(tmp_path, f"reject-{source_name}")

    with pytest.raises(FileNotFoundError):
        paths.copy_product_image(source)


def test_json_roundtrip_preserves_chinese_text(tmp_path):
    path = tmp_path / "nested" / "data.json"
    data = {"材质": "南红玛瑙", "备注": ["上手图", "中文保留"]}

    write_json(path, data)

    assert read_json(path) == data
    assert "南红玛瑙" in path.read_text(encoding="utf-8")
