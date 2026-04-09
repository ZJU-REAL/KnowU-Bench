import json
import re
import traceback
from typing import Any

from loguru import logger
from PIL import Image

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.utils.helpers import pil_to_base64, reverse_swipe_direction
from mobile_world.agents.utils.prompts import MAI_MOBILE_SYS_PROMPT_ASK_USER_MCP
from mobile_world.runtime.utils.helpers import pretty_print_messages
from mobile_world.runtime.utils.models import (
    ANSWER,
    ASK_USER,
    CLICK,
    DOUBLE_TAP,
    DRAG,
    FINISHED,
    INPUT_TEXT,
    KEYBOARD_ENTER,
    LONG_PRESS,
    MCP,
    NAVIGATE_BACK,
    NAVIGATE_HOME,
    OPEN_APP,
    SCROLL,
    UNKNOWN,
    WAIT,
    JSONAction,
)

SCALE_FACTOR = 999


def parse_tagged_text(text: str) -> dict[str, Any]:
    """Parse text containing XML-style tags to extract thinking and tool_call content."""
    if "</think>" in text and "</thinking>" not in text:
        text = text.replace("</think>", "</thinking>")
        text = "<thinking>" + text

    pattern = r"<thinking>(.*?)</thinking>.*?<tool_call>(.*?)</tool_call>"

    result: dict[str, Any] = {
        "thinking": None,
        "tool_call": None,
    }

    match = re.search(pattern, text, re.DOTALL)
    if match:
        result = {
            "thinking": match.group(1).strip().strip('"'),
            "tool_call": match.group(2).strip().strip('"'),
        }

    if result["tool_call"]:
        try:
            result["tool_call"] = json.loads(result["tool_call"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in tool_call: {e}")

    return result


def parse_action_to_structure_output(text: str) -> dict[str, Any]:
    """Parse model output text into structured action format with normalized coordinates."""
    text = text.strip()

    results = parse_tagged_text(text)
    thinking = results["thinking"]
    tool_call = results["tool_call"]

    # Handle MCP tool calls (non-mobile_use)
    tool_name = tool_call.get("name", "mobile_use")
    if tool_name != "mobile_use":
        return {
            "thinking": thinking,
            "tool_name": tool_name,
            "action_json": tool_call.get("arguments", {}),
        }

    action = tool_call["arguments"]

    for coord_field in ["coordinate", "start_coordinate", "end_coordinate"]:
        if coord_field in action:
            coordinates = action[coord_field]

            if len(coordinates) == 2:
                point_x, point_y = coordinates
            elif len(coordinates) == 4:
                x1, y1, x2, y2 = coordinates
                point_x = (x1 + x2) / 2
                point_y = (y1 + y2) / 2
            else:
                raise ValueError(
                    f"Invalid coordinate format: expected 2 or 4 values, got {len(coordinates)}"
                )

            point_x = point_x / SCALE_FACTOR
            point_y = point_y / SCALE_FACTOR

            action[coord_field] = [point_x, point_y]

    return {
        "thinking": thinking,
        "tool_name": "mobile_use",
        "action_json": action,
    }


class MAIUINaivigationAgent(MCPAgent):
    """Mobile automation agent using vision-language models."""

    def __init__(
        self,
        llm_base_url: str,
        model_name: str,
        api_key: str = "empty",
        runtime_conf: dict[str, Any] | None = {},
        **kwargs,
    ):
        """
        Initialize the MAIUINaivigationAgent.

        Args:
            llm_base_url: Base URL for the LLM API endpoint.
            model_name: Name of the model to use.
            api_key: API key for the LLM service.
            runtime_conf: Optional configuration dictionary.
        """
        super().__init__(**kwargs)

        # Set default configuration
        default_conf = {
            "history_n": 3,
            "temperature": 0.0,
            "top_k": -1,
            "top_p": 1.0,
            "max_tokens": 2048,
        }
        self.runtime_conf = {**default_conf, **runtime_conf}

        self.llm_base_url = llm_base_url
        self.model_name = model_name
        self.api_key = api_key
        self.build_openai_client(self.llm_base_url, self.api_key)

        # Extract frequently used config values
        self.temperature = self.runtime_conf["temperature"]
        self.top_k = self.runtime_conf["top_k"]
        self.top_p = self.runtime_conf["top_p"]
        self.max_tokens = self.runtime_conf["max_tokens"]
        self.history_n = self.runtime_conf["history_n"]

        # History tracking
        self.history_images: list[
            tuple[Any, Any, Any]
        ] = []  # (image, tool_call, ask_user_response)
        self.history_responses: list[dict] = []

    @property
    def system_prompt(self) -> str:
        """Generate the system prompt based on available MCP tools."""
        mcp_tools_str = None
        if self.tools:
            mcp_tools_str = "\n".join([json.dumps(tool, ensure_ascii=False) for tool in self.tools])
        return MAI_MOBILE_SYS_PROMPT_ASK_USER_MCP.render(tools=mcp_tools_str)

    def initialize_hook(self, instruction: str) -> None:
        """Hook for initializing the agent with instruction."""
        logger.info(f"Initializing MAI UI agent with instruction: {instruction}")
        self.reset()

    def _get_user_message(
        self, img_data: Any, tool_call_res: Any, ask_user_response_res: Any
    ) -> dict:
        """Build user message based on available data."""
        if tool_call_res is not None:
            return {
                "role": "user",
                "content": [{"type": "text", "text": f"Tool call result: {tool_call_res}"}],
            }
        elif ask_user_response_res is not None:
            return {
                "role": "user",
                "content": [{"type": "text", "text": ask_user_response_res}],
            }
        else:
            encoded_string = pil_to_base64(img_data)
            return {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_string}"},
                    }
                ],
            }

    def _hide_history_images(self, messages: list[dict]) -> list[dict]:
        """
        Limit the number of images sent to the model by removing older image messages.
        Keep only the most recent history_n images.

        Args:
            messages: List of message dicts

        Returns:
            Modified messages with limited images
        """
        # Collect indices of messages that contain images (from back to front)
        image_message_indices = []
        for i in range(len(messages) - 1, -1, -1):
            if (
                messages[i]["role"] == "user"
                and len(messages[i]["content"]) > 0
                and messages[i]["content"][0]["type"] == "image_url"
            ):
                image_message_indices.append(i)

        indices_to_remove = sorted(image_message_indices[self.history_n :], reverse=True)

        for idx in indices_to_remove:
            del messages[idx]

        return messages

    def _build_messages(self, obs_image: Any, tool_call: Any, ask_user_response: Any) -> list[dict]:
        """Build the message list for the LLM API call."""
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": self.instruction}],
            },
            self._get_user_message(
                self.history_images[0][0], self.history_images[0][1], self.history_images[0][2]
            ),
        ]

        for i, history_resp in enumerate(self.history_responses):
            history_img_data, tool_call_res, ask_user_response_res = self.history_images[i + 1]

            user_message = self._get_user_message(
                history_img_data, tool_call_res, ask_user_response_res
            )

            response_message = {
                "role": "assistant",
                "content": history_resp.get("content", ""),
            }

            messages.append(response_message)
            messages.append(user_message)

        messages = self._hide_history_images(messages)
        return messages

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        """
        Generate the next action based on current observation.

        Args:
            observation: Observation containing screenshot, tool_call, ask_user_response

        Returns:
            Tuple of (raw_response, JSONAction)
        """
        obs_image = observation["screenshot"]
        tool_call = observation.get("tool_call", None)
        ask_user_response = observation.get("ask_user_response", None)

        self.history_images.append((obs_image, tool_call, ask_user_response))

        logger.debug(f"Current history images count: {len(self.history_images)}")
        logger.debug(f"Current history responses count: {len(self.history_responses)}")

        assert len(self.history_images) == len(self.history_responses) + 1

        messages = self._build_messages(obs_image, tool_call, ask_user_response)
        pretty_print_messages(messages, max_messages=10)
        logger.debug("*" * 100)
        prediction = self.openai_chat_completions_create(
            model=self.model_name,
            messages=messages,
            retry_times=3,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )

        if prediction is None:
            raise ValueError("Planner LLM failed")
        logger.info(f"Raw LLM response:\n{prediction}")
        try:
            parsed_response = parse_action_to_structure_output(prediction)
            thinking = parsed_response["thinking"]
            tool_name = parsed_response.get("tool_name", "mobile_use")
            action_json = parsed_response["action_json"]

            logger.info(f"Parsed thinking: {thinking}")
            logger.info(f"Parsed tool_name: {tool_name}")
            logger.info(f"Parsed action: {action_json}")

        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            traceback.print_exc()
            return "Parsing error", JSONAction(action_type=UNKNOWN, text=str(e))
        self.history_responses.append({"role": "assistant", "content": prediction})

        json_action = self._convert_to_json_action(tool_name, action_json, obs_image)

        return prediction, json_action

    def _get_image_size(self, obs_image: Any) -> tuple[int, int]:
        assert isinstance(obs_image, Image.Image)
        return obs_image.size

    def _normalize_coord_to_pixel(self, coord: list[float], obs_image: Any) -> tuple[int, int]:
        width, height = self._get_image_size(obs_image)
        return int(coord[0] * width), int(coord[1] * height)

    def _convert_to_json_action(
        self, tool_name: str, action_json: dict, obs_image: Any
    ) -> JSONAction:
        if tool_name != "mobile_use":
            return JSONAction(
                action_type=MCP,
                action_name=tool_name,
                action_json=action_json,
            )

        action_type = action_json.get("action", UNKNOWN)

        if action_type in ("click", "long_press", "double_click"):
            coordinate = action_json.get("coordinate")
            if not coordinate:
                raise ValueError(f"Missing coordinate for {action_type}")
            x, y = self._normalize_coord_to_pixel(coordinate, obs_image)
            type_map = {"click": CLICK, "long_press": LONG_PRESS, "double_click": DOUBLE_TAP}
            return JSONAction(action_type=type_map[action_type], x=x, y=y)

        if action_type == "swipe":
            direction = reverse_swipe_direction(action_json.get("direction", "up"))
            coordinate = action_json.get("coordinate")
            if coordinate:
                x, y = self._normalize_coord_to_pixel(coordinate, obs_image)
                return JSONAction(action_type=SCROLL, direction=direction, x=x, y=y)
            return JSONAction(action_type=SCROLL, direction=direction)

        if action_type == "drag":
            start_coord = action_json.get("start_coordinate", [0, 0])
            end_coord = action_json.get("end_coordinate", [0, 0])
            start_x, start_y = self._normalize_coord_to_pixel(start_coord, obs_image)
            end_x, end_y = self._normalize_coord_to_pixel(end_coord, obs_image)
            return JSONAction(
                action_type=DRAG,
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
            )

        if action_type == "system_button":
            button = action_json.get("button", "").lower()
            button_map = {"back": NAVIGATE_BACK, "home": NAVIGATE_HOME, "enter": KEYBOARD_ENTER}
            if button in button_map:
                return JSONAction(action_type=button_map[button])
            return JSONAction(action_type=UNKNOWN, text=f"Unknown button: {button}")

        if action_type == "type":
            return JSONAction(action_type=INPUT_TEXT, text=action_json.get("text", ""))

        if action_type == "open":
            return JSONAction(action_type=OPEN_APP, app_name=action_json.get("text", ""))

        if action_type == "terminate":
            return JSONAction(action_type=FINISHED, text=action_json.get("status", "success"))

        if action_type == "answer":
            return JSONAction(action_type=ANSWER, text=action_json.get("text", ""))

        if action_type == "ask_user":
            return JSONAction(action_type=ASK_USER, text=action_json.get("text", ""))

        if action_type == "wait":
            return JSONAction(action_type=WAIT)

        return JSONAction(action_type=UNKNOWN, text=f"Unknown action: {action_type}")

    def reset(self) -> None:
        """Reset the agent for the next task."""
        self.history_images = []
        self.history_responses = []
        logger.debug("MAI UI agent reset completed")
