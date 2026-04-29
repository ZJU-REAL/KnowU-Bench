"""
UI Venus Agent implementation for mobile automation.
"""

import re
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any

from loguru import logger
from PIL import Image

from knowu_bench.agents.base import BaseAgent
from knowu_bench.agents.utils.helpers import pil_to_base64
from knowu_bench.agents.utils.prompts.ui_venus import UI_VENUS_15_PROMPT_CN
from knowu_bench.runtime.utils.helpers import pretty_print_messages
from knowu_bench.runtime.utils.models import (
    ANSWER,
    CLICK,
    DRAG,
    FINISHED,
    INPUT_TEXT,
    KEYBOARD_ENTER,
    LONG_PRESS,
    NAVIGATE_BACK,
    NAVIGATE_HOME,
    OPEN_APP,
    UNKNOWN,
    WAIT,
    JSONAction,
)

SCALE = 1000


def parse_coordinates(coord_str: str) -> tuple[float | None, float | None]:
    """Parse coordinate string like '(x, y)' into a tuple of floats."""
    if not coord_str:
        return None, None

    coord_str_clean = coord_str.replace(" ", "")
    match = re.match(r"\(([\d.]+),([\d.]+)\)", coord_str_clean)
    if match:
        return float(match.group(1)) / SCALE, float(match.group(2)) / SCALE

    match = re.match(r"\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)", coord_str)
    if match:
        return float(match.group(1)) / SCALE, float(match.group(2)) / SCALE

    return None, None


def _split_parameters(params_str: str) -> list[str]:
    """Split function parameters respecting quotes and brackets."""
    param_parts = []
    current_part = ""

    in_quotes = False
    quote_char = None
    bracket_level = 0

    for char in params_str:
        if char in ['"', "'"] and not in_quotes:
            in_quotes = True
            quote_char = char
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
        elif not in_quotes:
            if char == "(":
                bracket_level += 1
            elif char == ")":
                bracket_level -= 1
            elif char == "," and bracket_level == 0:
                param_parts.append(current_part.strip())
                current_part = ""
                continue

        current_part += char

    if current_part.strip():
        param_parts.append(current_part.strip())

    return param_parts


def parse_answer(action_str: str) -> tuple[str, dict]:
    """Parse a Venus-style action string like 'Click(box=(x, y))' into (action_name, params)."""
    pattern = r"^(\w+)\((.*)\)$"
    match = re.match(pattern, action_str.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"Invalid action_str format: {action_str}")

    action_type = match.group(1)
    params_str = match.group(2).strip()
    params = {}

    if params_str:
        try:
            param_pairs = _split_parameters(params_str)
            for pair in param_pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    value = value.strip("'").strip()
                    params[key.strip()] = value
                else:
                    params[pair.strip()] = None
        except Exception as e:
            logger.debug(f"Answer parse error: {e}")

    if action_type == "Click":
        p_x, p_y = parse_coordinates(params.get("box", ""))
        if p_x is not None and p_y is not None:
            return "Click", {"box": (p_x, p_y)}
        raise ValueError(f"action {action_type} Unknown click params: {repr(params)}")

    elif action_type == "LongPress":
        p_x, p_y = parse_coordinates(params.get("box", ""))
        if p_x is not None and p_y is not None:
            return "LongPress", {"box": (p_x, p_y)}
        raise ValueError(f"action {action_type} Unknown long press params: {repr(params)}")

    elif action_type == "Drag":
        p_x, p_y = parse_coordinates(params.get("start", ""))
        e_x, e_y = parse_coordinates(params.get("end", ""))
        if p_x is not None and p_y is not None and e_x is not None and e_y is not None:
            return "Drag", {"start": (p_x, p_y), "end": (e_x, e_y)}
        raise ValueError(f"action {action_type} Unknown drag params: {repr(params)}")

    elif action_type == "Scroll":
        p_x, p_y = parse_coordinates(params.get("start", ""))
        e_x, e_y = parse_coordinates(params.get("end", ""))
        if p_x is not None and p_y is not None and e_x is not None and e_y is not None:
            return "Scroll", {"start": (p_x, p_y), "end": (e_x, e_y)}

        raise ValueError(f"action {action_type} Unknown scroll params: {repr(params)}")

    elif action_type == "Type":
        type_text = params.get("content")
        if type_text is not None:
            return "Type", {"content": type_text}
        raise ValueError(f"action {action_type} Unknown type params: {repr(params)}")

    elif action_type == "CallUser":
        call_text = params.get("content")
        if call_text is not None:
            return "CallUser", {"content": call_text}
        raise ValueError(f"action {action_type} Unknown call user params: {repr(params)}")

    elif action_type == "Launch":
        app = params.get("app", "")
        url = params.get("url", "")
        if app is not None:
            return "Launch", {"app": app, "url": url}
        raise ValueError(f"action {action_type} Unknown launch params: {repr(params)}")

    elif action_type == "Finished":
        return "Finished", {"content": params.get("content", "")}

    elif action_type in ["Wait", "PressBack", "PressHome", "PressEnter", "PressRecent"]:
        return action_type, {}

    else:
        raise ValueError(f"action {action_type} Unknown action: {repr(params)}")


def convert_venus_action_to_json_action(
    action_name: str, action_params: dict, origin_h: int, origin_w: int
) -> dict:
    """Convert parsed Venus action to JSONAction-compatible dict."""
    if action_name == "Click":
        return {
            "action_type": CLICK,
            "x": int(action_params["box"][0] * origin_w),
            "y": int(action_params["box"][1] * origin_h),
        }
    elif action_name == "LongPress":
        return {
            "action_type": LONG_PRESS,
            "x": int(action_params["box"][0] * origin_w),
            "y": int(action_params["box"][1] * origin_h),
        }
    elif action_name == "Scroll":
        return {
            "action_type": DRAG,
            "start_x": int(action_params["start"][0] * origin_w),
            "start_y": int(action_params["start"][1] * origin_h),
            "end_x": int(action_params.get("end", (0, 0))[0] * origin_w),
            "end_y": int(action_params.get("end", (0, 0))[1] * origin_h),
        }
    elif action_name == "Type":
        return {"action_type": INPUT_TEXT, "text": action_params.get("content", "")}
    elif action_name == "Launch":
        return {"action_type": OPEN_APP, "app_name": action_params.get("app", "")}
    elif action_name == "Wait":
        return {"action_type": WAIT}
    elif action_name == "Finished":
        return {"action_type": FINISHED, "text": action_params.get("content", "")}
    elif action_name == "PressBack":
        return {"action_type": NAVIGATE_BACK}
    elif action_name == "PressHome":
        return {"action_type": NAVIGATE_HOME}
    elif action_name == "PressEnter":
        return {"action_type": KEYBOARD_ENTER}
    elif action_name == "CallUser":
        return {"action_type": ANSWER, "text": action_params.get("content", "")}
    elif action_name == "Drag":
        return {
            "action_type": DRAG,
            "start_x": int(action_params["start"][0] * origin_w),
            "start_y": int(action_params["start"][1] * origin_h),
            "end_x": int(action_params["end"][0] * origin_w),
            "end_y": int(action_params["end"][1] * origin_h),
        }
    else:
        raise ValueError(f"Unknown action type: {action_name}")


@dataclass
class StepData:
    """Data for a single agent step."""

    raw_screenshot: Image.Image
    query: str
    generated_text: str
    think: str
    action: str
    conclusion: str
    status: str = "success"

    def to_dict(self, include_screenshot: bool = False) -> dict:
        data = asdict(self)
        data["raw_screenshot"] = None
        if include_screenshot and self.raw_screenshot is not None:
            import base64

            buffer = BytesIO()
            self.raw_screenshot.save(buffer, format="PNG")
            data["raw_screenshot_base64"] = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return data


class VenusNaviAgent(BaseAgent):
    """UI Venus navigation agent using vision-language models."""

    def __init__(
        self,
        llm_base_url: str,
        model_name: str,
        api_key: str = "empty",
        model_config: dict | None = None,
        history_length: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        default_config = {
            "min_pixels": 830000,
            "max_pixels": 937664,
            "max_tokens": 4096,
            "temperature": 0.0,
            "top_p": 1.0,
        }
        config = {**default_config, **(model_config or {})}

        self.llm_base_url = llm_base_url
        self.model_name = model_name
        self.min_pixels = config["min_pixels"]
        self.max_pixels = config["max_pixels"]
        self.max_tokens = config["max_tokens"]
        self.temperature = config["temperature"]
        self.top_p = config["top_p"]
        self.history: list[StepData] = []
        self.history_length = max(0, history_length)

        self.build_openai_client(self.llm_base_url, api_key)

    def initialize_hook(self, instruction: str) -> None:
        """Hook for initializing the agent with instruction."""
        logger.info(f"Initializing VenusNaviAgent with instruction: {instruction}")
        self.reset()

    def reset(self) -> None:
        """Reset the agent history for the next task."""
        logger.info("VenusNaviAgent reset")
        self.history = []

    def _build_query(self, goal: str) -> str:
        """Build the user query with history."""
        if len(self.history) == 0:
            history_str = ""
        else:
            recent_history = self.history[-self.history_length :]
            history_entries = [
                f"Step {i}: <think>{step.think}</think><action>{step.action}</action>"
                for i, step in enumerate(recent_history)
            ]
            history_str = "\n".join(history_entries)

        return UI_VENUS_15_PROMPT_CN.format(user_task=goal, previous_actions=history_str)

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        """Generate the next action based on current observation.

        Args:
            observation: Dictionary containing 'screenshot' key with PIL Image or bytes.

        Returns:
            Tuple of (generated_text, JSONAction)
        """
        if self.instruction is None:
            raise ValueError("Agent not initialized. Call initialize() first.")

        # Handle both PIL Image and bytes
        screenshot_data = observation["screenshot"]
        if isinstance(screenshot_data, Image.Image):
            raw_screenshot = screenshot_data
        else:
            raw_screenshot = Image.open(BytesIO(screenshot_data))

        screenshot = raw_screenshot.convert("RGB")
        origin_h, origin_w = screenshot.height, screenshot.width

        user_query = self._build_query(self.instruction)
        encoded_string = pil_to_base64(screenshot)

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_query},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_string}"},
                    },
                ],
            },
        ]

        pretty_print_messages(messages, max_messages=10)

        generated_text = self.openai_chat_completions_create(
            model=self.model_name,
            messages=messages,
            retry_times=3,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )

        if generated_text is None:
            raise ValueError("LLM call failed after retries.")

        logger.info(f"Goal: {self.instruction}")
        logger.info(f"Response: {repr(generated_text)}")

        # Parse think/action/conclusion tags
        try:
            think_text = generated_text.split("<think>")[1].split("</think>")[0].strip("\n")
        except (IndexError, ValueError):
            think_text = ""
        try:
            answer_text = generated_text.split("<action>")[1].split("</action>")[0].strip("\n")
        except (IndexError, ValueError):
            answer_text = ""
        try:
            conclusion_text = (
                generated_text.split("<conclusion>")[1].split("</conclusion>")[0].strip("\n")
            )
        except (IndexError, ValueError):
            conclusion_text = ""

        # Parse the action
        try:
            action_name, action_params = parse_answer(answer_text)
            action_json = {"action": action_name, "params": action_params}
        except Exception as e:
            logger.warning(f"Failed to parse_answer: {e}")
            step_data = StepData(
                raw_screenshot=raw_screenshot,
                query=user_query,
                generated_text=generated_text,
                think=think_text,
                action=answer_text,
                conclusion=conclusion_text,
                status="failed",
            )
            self.history.append(step_data)
            return generated_text, JSONAction(action_type=UNKNOWN, text=str(e))

        step_data = StepData(
            raw_screenshot=raw_screenshot,
            query=user_query,
            generated_text=generated_text,
            think=think_text,
            action=answer_text,
            conclusion=conclusion_text,
            status="success",
        )
        self.history.append(step_data)

        # Convert to JSONAction
        aw_action_dict = convert_venus_action_to_json_action(
            action_json["action"], action_json["params"], origin_h, origin_w
        )

        logger.info(f"Action: {repr(action_json)}")
        logger.info(f"AW Action: {repr(aw_action_dict)}")

        return generated_text, JSONAction(**aw_action_dict)
