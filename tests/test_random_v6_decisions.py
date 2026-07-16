import importlib.util
from collections import Counter
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "output"
    / "021-20260717-three-role-review-20260713"
    / "select_v6_random_decisions.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("random_v6_decisions", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_choose_low_reuse_ranks_is_reproducible_and_balanced():
    module = _load_module()
    candidates = {
        f"QY{number:03d}-hero": (1, 2, 3)
        for number in range(2, 12)
    }

    first = module.choose_low_reuse_ranks(candidates, seed=20260714)
    second = module.choose_low_reuse_ranks(candidates, seed=20260714)

    assert first == second
    assert set(first) == set(candidates)
    assert all(selected in candidates[run_id] for run_id, selected in first.items())
    usage = Counter(first.values())
    assert max(usage.values()) - min(usage.values()) <= 1
