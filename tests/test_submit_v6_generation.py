import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "submit_v6_generation.py"
)


def test_build_generate_command_submits_without_waiting():
    spec = importlib.util.spec_from_file_location("submit_v6_generation", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    command = module.build_generate_command(Path("output/v6/QY002-hero"))

    assert command[:3] == [module.sys.executable, "-m", "jewelry_on_hand.cli"]
    assert command[-1] == "--no-wait"
    assert "--helper-script" in command
