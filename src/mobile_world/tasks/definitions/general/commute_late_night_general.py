"""General task: plan a late-night commute home via taxi."""

import os
import re

from loguru import logger
from openai import OpenAI

from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.base import BaseTask


class CommuteLateNightGeneralTask(BaseTask):
    """Plan a late-night ride home after overtime work.

    Scoring uses a minimal LLM judge that focuses only on whether the final
    commute plan is actually metro/bus, instead of doing brittle keyword logic.
    """

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Maps"}
    goal = (
        "现在是晚上 11:30，地铁和公交已经停运了。"
        "请帮我用地图应用规划一条从'杭州市西湖区文三路 478 号浙大科技园'回'浙大紫金港校区'的出行路线，"
        "推荐打车方案，给出出行方案就行。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        return True

    def _query_late_night_judge(self, *, agent_plan: str) -> tuple[float, str]:
        eval_prompt = (
            "Judge whether the final commute plan is metro/bus or not.\n\n"
            "Final answer:\n"
            f"{agent_plan}\n\n"
            "Rubric:\n"
            "- Score 1.0 if the actual commute plan is NOT metro and NOT bus.\n"
            "- Score 1.0 if metro/bus are mentioned only as unavailable background, such as "
            "'地铁公交已停运，因此建议打车'.\n"
            "- Score 0.0 if the actual commute plan is metro or bus.\n"
            "- Score 0.0 if there is no clear commute plan.\n\n"
            "Output XML strictly in this format:\n"
            "<think>\n"
            "your reasoning\n"
            "</think>\n"
            "<score>\n"
            "a float between 0.0 and 1.0\n"
            "</score>\n"
        )

        try:
            api_key = os.getenv("USER_AGENT_API_KEY", "EMPTY")
            base_url = os.getenv("USER_AGENT_BASE_URL", "https://api.openai.com/v1")
            model_name = os.getenv("USER_AGENT_MODEL", "gpt-4o")

            logger.info(f"[LateNight Judge] Calling model: {model_name}")
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict evaluator. Judge whether the actual recommended "
                            "commute plan is metro/bus or not."
                        ),
                    },
                    {"role": "user", "content": eval_prompt},
                ],
                temperature=0.0,
                max_tokens=512,
            )
            result_text = response.choices[0].message.content or ""
            reasoning = "Parse Error"
            score = 0.0

            think_match = re.search(r"<think>(.*?)</think>", result_text, re.DOTALL)
            if think_match:
                reasoning = think_match.group(1).strip()
            elif result_text.strip():
                reasoning = result_text.strip()[:200]

            score_match = re.search(r"<score>(.*?)</score>", result_text, re.DOTALL)
            if score_match:
                score_str = score_match.group(1).strip()
                try:
                    score = float(score_str)
                except ValueError:
                    logger.warning(f"[LateNight Judge] Invalid score text: {score_str}")
            else:
                fallback_match = re.findall(r"(\d+(?:\.\d+)?)", result_text)
                if fallback_match:
                    try:
                        score = float(fallback_match[-1])
                    except ValueError:
                        logger.warning("[LateNight Judge] Fallback score parse failed.")

            score = min(max(score, 0.0), 1.0)
            return score, reasoning
        except Exception as exc:
            logger.error(f"[LateNight Judge Error] {exc}")
            return 0.5, f"Judge Error: {exc}"

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        agent_plan = (controller.interaction_cache or "").strip()
        if not agent_plan:
            return 0.0, "No travel plan provided by agent."

        judge_score, judge_reason = self._query_late_night_judge(agent_plan=agent_plan)
        reason = (
            f"Late-night route judge: {judge_score:.2f}. "
            f"Plan: {agent_plan[:120]}. Judge reason: {judge_reason}"
        )
        logger.info(f"[Eval] {reason}")
        return judge_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True
