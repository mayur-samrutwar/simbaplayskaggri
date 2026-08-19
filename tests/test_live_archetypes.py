from __future__ import annotations

import copy
from pathlib import Path

import pytest
from kaggle_environments import make

from candidates.live_archetypes import POLICIES, agent_for


ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = (
    ROOT / "candidates" / "live_melon_strawberry.py",
    ROOT / "candidates" / "live_strawberry.py",
    ROOT / "candidates" / "live_milk.py",
    ROOT / "candidates" / "live_tomato_goose.py",
)


def test_live_archetypes_do_not_import_hybrid_core():
    source = (ROOT / "candidates" / "live_archetypes.py").read_text(encoding="utf-8")
    assert "from candidates.hybrid_core" not in source
    assert "import candidates.hybrid_core" not in source


@pytest.mark.parametrize("name", sorted(POLICIES))
def test_live_archetype_initial_action_is_deterministic_and_legal_shape(name):
    env = make("kaggriculture", configuration={"episodeSteps": 8, "seed": 31}, debug=True)
    observation = env.steps[0][0].observation
    first = agent_for(copy.deepcopy(observation), name)
    second = agent_for(copy.deepcopy(observation), name)
    assert first == second
    assert set(first) == {"farmer", "hands", "market"}
    assert isinstance(first["farmer"], list)
    assert first["hands"] == []
    assert len(first["market"]) <= 10


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda path: path.stem)
def test_live_archetype_wrapper_loads_and_finishes_short_game(wrapper):
    env = make("kaggriculture", configuration={"episodeSteps": 72, "seed": 32}, debug=True)
    env.run([str(wrapper), "pass"])
    final = env.steps[-1][0]
    assert final.status == "DONE"
    assert final.reward is not None
