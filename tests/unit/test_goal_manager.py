import pytest
from foundation.event_bus.event_bus import EventBus
from core_ai.goal_manager.goal_manager import GoalManager, LongRunningGoal


def test_goal_manager_creation(tmp_path):
    event_bus = EventBus()
    gm = GoalManager(event_bus=event_bus, data_dir=str(tmp_path))

    goals = gm.list_goals()
    assert len(goals) == 1
    assert goals[0]["title"] == "Evolve HELIX into PAIOS"

    new_g = gm.create_goal("Build Next Feature", "Implement frontend canvas")
    assert new_g.goal_id == "goal-2"
    assert len(gm.list_goals()) == 2
