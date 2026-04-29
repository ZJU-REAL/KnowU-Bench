"""General task: plan a commute route on a rainy day with sheltered transport."""

import os
import re

from loguru import logger
from openai import OpenAI

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.tasks.base import BaseTask


class CommuteRoutingBadWeatherGeneralTask(BaseTask):
    """Plan a sheltered commute route on a rainy day.

    Scoring uses a minimal LLM judge that focuses only on whether the final
    commute plan is actually an outdoor-heavy walking/cycling plan.
    """

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Maps"}
    goal = (
        "外面在下雨，请帮我用地图应用规划一条从'浙大紫金港校区'到'杭州市西湖区文三路 478 号浙大科技园'的出行路线，"
        "要求尽量减少淋雨，给出出行方案就行。"
    )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        return True

    def _query_bad_weather_judge(self, *, agent_plan: str) -> tuple[float, str]:
        eval_prompt = (
            "Judge whether the final rainy-day commute plan is an outdoor walking/cycling "
            "plan or not.\n\n"
            "Final answer:\n"
            f"{agent_plan}\n\n"
            "Rubric:\n"
            "- Score 1.0 if the actual main commute plan is NOT walking and NOT cycling.\n"
            "- Score 1.0 if the main plan is sheltered transport such as metro, bus, or taxi, "
            "even if it includes short access walking to a station or pickup point.\n"
            "- Score 1.0 if walking/cycling are mentioned only as rejected options or bad "
            "weather background, such as '下雨别骑车，建议坐地铁'.\n"
            "- Score 0.0 if the actual main commute plan is walking or cycling in the rain.\n"
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

            logger.info(f"[BadWeather Judge] Calling model: {model_name}")
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict evaluator. Judge whether the actual recommended "
                            "rainy-day commute plan is mainly walking/cycling or not."
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
                    logger.warning(f"[BadWeather Judge] Invalid score text: {score_str}")
            else:
                fallback_match = re.findall(r"(\d+(?:\.\d+)?)", result_text)
                if fallback_match:
                    try:
                        score = float(fallback_match[-1])
                    except ValueError:
                        logger.warning("[BadWeather Judge] Fallback score parse failed.")

            score = min(max(score, 0.0), 1.0)
            return score, reasoning
        except Exception as exc:
            logger.error(f"[BadWeather Judge Error] {exc}")
            return 0.5, f"Judge Error: {exc}"

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()

        agent_plan = (controller.interaction_cache or "").strip()
        if not agent_plan:
            return 0.0, "No travel plan provided by agent."

        judge_score, judge_reason = self._query_bad_weather_judge(agent_plan=agent_plan)
        reason = (
            f"Bad-weather route judge: {judge_score:.2f}. "
            f"Plan: {agent_plan[:120]}. Judge reason: {judge_reason}"
        )
        logger.info(f"[Eval] {reason}")
        return judge_score, reason

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        return True
