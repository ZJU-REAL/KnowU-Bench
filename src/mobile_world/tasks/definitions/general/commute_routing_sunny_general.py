"""General task: plan a commute route on a sunny day with explicit details."""

from loguru import logger

from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask


class CommuteRoutingSunnyGeneralTask(BaseTask):
    """Plan a cycling route from home to office on a sunny day."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Maps"}
    goal = (
        "今天天气晴朗，请帮我用地图应用规划一条从'浙大紫金港校区'到'杭州市西湖区文三路 478 号浙大科技园'的骑行路线，"
        "给出出行方案就行。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        return True

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        agent_plan = (controller.interaction_cache or "").strip()
        if not agent_plan:
            return 0.0, "No travel plan provided by agent."

        route_keywords = ["骑行", "骑车", "cycling", "bike", "自行车", "路线", "route", "分钟", "min", "公里", "km"]
        plan_lower = agent_plan.lower()
        hits = sum(1 for kw in route_keywords if kw in plan_lower)

        if hits >= 3:
            score = 1.0
        elif hits >= 1:
            score = 0.5
        else:
            score = 0.2

        reason = f"Route plan provided. Keyword hits: {hits}. Score: {score:.1f}. Plan: {agent_plan[:100]}"
        logger.info(f"[Eval] {reason}")
        return score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True
