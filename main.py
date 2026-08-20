"""Black-box Kaggle entry point for the promoted throughput portfolio.

The implementation lives in ``candidates.throughput_portfolio`` so experimental
policies can be benchmarked against this incumbent without duplicating code.
Keep ``agent`` as the last callable defined in this file: kaggle-environments
loads the last callable from a Python submission file.
"""

from candidates.throughput_portfolio import agent as _promoted_agent


def agent(obs):
    """Return a legal action, falling back safely on malformed observations."""
    try:
        return _promoted_agent(obs)
    except Exception:
        farms = obs.get("farms", []) if hasattr(obs, "get") else []
        try:
            player = int(obs.get("player", 0)) if hasattr(obs, "get") else 0
        except (TypeError, ValueError):
            player = 0
        hands = []
        try:
            if farms and 0 <= player < len(farms):
                hands = [["PASS"] for _ in farms[player].get("hands", [])]
        except (AttributeError, TypeError):
            hands = []
        return {"farmer": ["PASS"], "hands": hands, "market": []}
