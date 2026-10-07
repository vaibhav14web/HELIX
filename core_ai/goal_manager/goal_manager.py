import os
import json
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from foundation.event_bus.event_bus import EventBus

logger = logging.getLogger("helix.goal_manager")


@dataclass
class GoalTaskNode:
    task_id: str
    title: str
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed | blocked
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LongRunningGoal:
    goal_id: str
    title: str
    description: str
    priority: str = "medium"  # low | medium | high | urgent
    progress_percent: float = 0.0
    tasks: list[GoalTaskNode] = field(default_factory=list)
    status: str = "in_progress"  # in_progress | completed | paused | failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tasks"] = [t.to_dict() if isinstance(t, GoalTaskNode) else t for t in self.tasks]
        return d


class GoalManager:
    def __init__(self, event_bus: EventBus, data_dir: str = "./data/goals"):
        self._event_bus = event_bus
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._goals_file = self._data_dir / "goals.json"
        self._goals: dict[str, LongRunningGoal] = {}
        self._load_goals()

    def _load_goals(self) -> None:
        if not self._goals_file.exists():
            # Seed default goal
            default_goal = LongRunningGoal(
                goal_id="goal-1",
                title="Evolve HELIX into PAIOS",
                description="Transform HELIX into a production-grade Personal AI Operating System.",
                priority="high",
                progress_percent=85.0,
                tasks=[
                    GoalTaskNode("t-1", "Real-Time Streaming Voice Engine", "Implement TTS sentence streaming", "completed"),
                    GoalTaskNode("t-2", "Self & World Model Subsystems", "Add state vector perception", "completed"),
                    GoalTaskNode("t-3", "Application Discovery & Project Registry", "Fuzzy index Windows software & dev workspaces", "completed"),
                    GoalTaskNode("t-4", "Action Verification & Goal Canvas UI", "Validate execution & build goals UI", "in_progress", ["t-1", "t-2", "t-3"]),
                ],
            )
            self._goals[default_goal.goal_id] = default_goal
            self._save_goals()
            return

        try:
            with open(self._goals_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("goals", []):
                    tasks = [GoalTaskNode(**t) for t in item.get("tasks", [])]
                    item["tasks"] = tasks
                    goal = LongRunningGoal(**item)
                    self._goals[goal.goal_id] = goal
        except Exception as e:
            logger.exception("Failed loading goals from %s", self._goals_file)

    def _save_goals(self) -> None:
        try:
            with open(self._goals_file, "w", encoding="utf-8") as f:
                json.dump({"goals": [g.to_dict() for g in self._goals.values()]}, f, indent=2)
        except Exception as e:
            logger.exception("Failed saving goals to %s", self._goals_file)

    def create_goal(self, title: str, description: str, priority: str = "medium", tasks: list[dict] | None = None) -> LongRunningGoal:
        goal_id = f"goal-{len(self._goals) + 1}"
        task_nodes = []
        if tasks:
            for idx, t in enumerate(tasks):
                task_nodes.append(GoalTaskNode(
                    task_id=f"t-{idx+1}",
                    title=t.get("title", f"Task {idx+1}"),
                    description=t.get("description", ""),
                    status=t.get("status", "pending"),
                    depends_on=t.get("depends_on", []),
                ))
        goal = LongRunningGoal(
            goal_id=goal_id,
            title=title,
            description=description,
            priority=priority,
            tasks=task_nodes,
        )
        self._goals[goal_id] = goal
        self._save_goals()
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish_event(
                source="goal_manager",
                event_type="goal.created",
                payload=goal.to_dict(),
            ))
        except RuntimeError:
            pass
        return goal

    def get_goal(self, goal_id: str) -> LongRunningGoal | None:
        return self._goals.get(goal_id)

    def list_goals(self) -> list[dict[str, Any]]:
        return [g.to_dict() for g in self._goals.values()]
