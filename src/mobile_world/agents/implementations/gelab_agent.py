"""
Gelab Agent implementation for mobile automation.
Following: https://github.com/stepfun-ai/gelab-zero/blob/main/copilot_tools/parser_0920_summary.py
"""

import re
from typing import Any

from loguru import logger
from PIL import Image

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.utils.helpers import pil_to_base64
from mobile_world.agents.utils.prompts import (
    GELAB_INSTRUCTION_SUFFIX,
    GELAB_SYSTEM_PROMPT,
    GELAB_USER_PROMPT_TEMPLATE,
)
from mobile_world.runtime.utils.helpers import pretty_print_messages
from mobile_world.runtime.utils.models import (
    ANSWER,
    ASK_USER,
    CLICK,
    DRAG,
    FINISHED,
    INPUT_TEXT,
    LONG_PRESS,
    OPEN_APP,
    UNKNOWN,
    WAIT,
    JSONAction,
)

# Gelab uses 0-1000 coordinate system
GELAB_SCALE_FACTOR = 1000


def parse_gelab_response(response: str) -> dict[str, Any]:
    """
    Parse Gelab model response into action dict.

    Expected format:
    <THINK> cot </THINK>
    explain:xxx\taction:xx\tvalue:xxx\tsummary:xxx

    Returns:
        dict with cot, action, and other fields
    """
    response = response.strip()

    # Normalize THINK tags
    response = re.sub(
        r"<\s*/?(?:THINK|think|TINK|tink)\s*>",
        lambda m: "<THINK>" if "/" not in m.group() else "</THINK>",
        response,
    )

    # Extract CoT and key-value parts
    try:
        cot = response.split("<THINK>")[1].split("</THINK>")[0].strip()
        kv_part = response.split("</THINK>")[1].strip()
    except IndexError:
        logger.warning("Missing <THINK> tags, treating entire response as kv")
        kv_part = response
        cot = ""

    action = {"cot": cot}

    # Parse tab-separated key:value pairs
    for kv in kv_part.split("\t"):
        kv = kv.strip()
        if ":" not in kv:
            continue

        key, value = kv.split(":", 1)
        key = key.strip()
        value = value.strip()

        if "point" in key:
            # Parse point format: "x,y" or "x y"
            coords = value.replace(",", " ").split()
            if len(coords) >= 2:
                action[key] = [int(coords[0]), int(coords[1])]
        else:
            action[key] = value

    return action


def transform_gelab_action(action: dict, width: int, height: int) -> dict[str, Any]:
    """
    Transform Gelab action format to Android World environment action format.

    Gelab uses 0-1000 coordinate system, normalized to pixel coordinates.
    """
    action_type = action.get("action")
    if not action_type:
        return {"action_type": UNKNOWN}

    def to_pixels(point: list[int]) -> tuple[float, float]:
        """Convert 0-1000 coordinates to pixel coordinates."""
        x, y = point
        return round(x / GELAB_SCALE_FACTOR * width, 3), round(y / GELAB_SCALE_FACTOR * height, 3)

    if action_type == "CLICK":
        if "point" not in action:
            return {"action_type": UNKNOWN, "text": "CLICK missing point"}
        x, y = to_pixels(action["point"])
        return {"action_type": CLICK, "x": x, "y": y}

    elif action_type == "TYPE":
        result = {"action_type": INPUT_TEXT, "text": action.get("value", "")}
        if "point" in action:
            x, y = to_pixels(action["point"])
            result.update({"x": x, "y": y})
        return result

    elif action_type == "LONGPRESS":
        if "point" not in action:
            return {"action_type": UNKNOWN, "text": "LONGPRESS missing point"}
        x, y = to_pixels(action["point"])
        return {"action_type": LONG_PRESS, "x": x, "y": y}

    elif action_type == "SLIDE":
        if "point1" not in action or "point2" not in action:
            return {"action_type": UNKNOWN, "text": "SLIDE missing points"}
        x1, y1 = to_pixels(action["point1"])
        x2, y2 = to_pixels(action["point2"])
        return {
            "action_type": DRAG,
            "start_x": int(x1),
            "start_y": int(y1),
            "end_x": int(x2),
            "end_y": int(y2),
        }

    elif action_type == "AWAKE":
        return {"action_type": OPEN_APP, "app_name": action.get("value", "")}

    elif action_type == "WAIT":
        result = {"action_type": WAIT}
        try:
            result["duration"] = float(action.get("value", 1))
        except (ValueError, TypeError):
            pass
        return result

    elif action_type == "COMPLETE":
        return {"action_type": ANSWER, "text": action.get("return", "")}

    elif action_type == "INFO":
        return {"action_type": ASK_USER, "text": action.get("value", "")}

    elif action_type == "ABORT":
        return {"action_type": FINISHED, "text": f"ABORT: {action.get('value', 'Task aborted')}"}

    else:
        logger.warning(f"Unknown action type: {action_type}")
        return {"action_type": UNKNOWN}


class GelabAgent(MCPAgent):
    """Gelab Agent implementation following standard MCPAgent interface."""

    def __init__(
        self,
        model_name: str,
        llm_base_url: str,
        api_key: str = "empty",
        observation_type: str = "screenshot",
        runtime_conf: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.model_name = model_name
        self.llm_base_url = llm_base_url
        self.observation_type = observation_type

        # Set default runtime configuration
        default_conf = {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 2048,
        }
        self.runtime_conf = {**default_conf, **(runtime_conf or {})}

        self.build_openai_client(llm_base_url, api_key)

        # Agent state
        self.actions: list[dict] = []
        self.environments: list[dict] = []

    def initialize_hook(self, instruction: str) -> None:
        """Hook for initializing the agent with instruction."""
        logger.info(f"Initializing Gelab agent with instruction: {instruction}")
        self.reset()

    def _build_messages(self, current_env: dict) -> list[dict]:
        """Build messages for LLM API call."""
        # Get summary history from last action
        summary_history = ""
        if self.actions:
            summary_history = self.actions[-1].get("summary", "")

        user_comment = current_env.get("user_comment", "")
        if user_comment:
            history_display = (
                (summary_history + " 用户回复说：" + user_comment)
                if summary_history
                else "暂无历史操作"
            )
        else:
            history_display = summary_history if summary_history else "暂无历史操作"

        user_prompt = GELAB_USER_PROMPT_TEMPLATE.render(
            task=self.instruction,
            history_display=history_display,
        )

        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": GELAB_SYSTEM_PROMPT},
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": current_env["image"]}},
                    {"type": "text", "text": GELAB_INSTRUCTION_SUFFIX},
                ],
            }
        ]

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        """Generate the next action based on current observation."""
        screenshot: Image.Image = observation["screenshot"]
        user_comment = observation.get("ask_user_response", "") or ""

        # Store current environment
        encoded_image = pil_to_base64(screenshot)
        current_env = {
            "image": f"data:image/png;base64,{encoded_image}",
            "user_comment": user_comment,
        }
        self.environments.append(current_env)

        messages = self._build_messages(current_env)
        pretty_print_messages(messages, max_messages=5)

        # Call LLM
        raw_response = self.openai_chat_completions_create(
            model=self.model_name,
            messages=messages,
            retry_times=3,
            max_tokens=self.runtime_conf.get("max_tokens", 2048),
            temperature=self.runtime_conf.get("temperature", 0.0),
            top_p=self.runtime_conf.get("top_p", 1.0),
        )

        if raw_response is None:
            raise ValueError("LLM call failed")

        logger.info(f"Raw LLM response:\n{raw_response}")

        # Parse response
        try:
            action = parse_gelab_response(raw_response)
            logger.info(f"Parsed action: {action}")
        except Exception as e:
            logger.error(f"Error parsing action: {e}")
            return raw_response, JSONAction(action_type=UNKNOWN)

        self.actions.append(action)

        # Transform to Android World format
        try:
            json_action_dict = transform_gelab_action(
                action,
                width=screenshot.width,
                height=screenshot.height,
            )
            logger.info(f"Transformed action: {json_action_dict}")
        except Exception as e:
            logger.error(f"Error transforming action: {e}")
            return raw_response, JSONAction(action_type=UNKNOWN)

        return raw_response, JSONAction(**json_action_dict)

    def reset(self) -> None:
        """Reset agent state for a new task."""
        self.actions = []
        self.environments = []
        logger.debug("Gelab agent reset completed")
