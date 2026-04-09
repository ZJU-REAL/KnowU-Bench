import json
import os
import time
from typing import Any

from loguru import logger

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.utils.helpers import pil_to_base64
from mobile_world.agents.utils.prompts import GENERAL_E2E_PROMPT_TEMPLATE
from mobile_world.runtime.utils.helpers import pretty_print_messages
from mobile_world.runtime.utils.models import JSONAction
from mobile_world.runtime.utils.parsers import parse_json_markdown

ACTION_ALIASES = {
    "click": ["tap", "press", "touch"],
    "long_press": ["long tap", "long press", "hold"],
    "input_text": ["type", "enter_text", "write", "enter"],
    "scroll": ["swipe", "fling"],
    "keyboard_enter": ["enter"],
}
NORMALIZED_ACTION_MAP = {}
for standard_action, aliases in ACTION_ALIASES.items():
    NORMALIZED_ACTION_MAP[standard_action] = standard_action
    for alias in aliases:
        NORMALIZED_ACTION_MAP[alias.replace(" ", "_")] = standard_action
        NORMALIZED_ACTION_MAP[alias] = standard_action

CLAUDE_IMAGE_SIZE = (1280, 720)


def normalize_action_type(action_type: str) -> str:
    if not action_type:
        return None
    processed_type = action_type.lower().strip().replace(" ", "_")
    return NORMALIZED_ACTION_MAP.get(processed_type, action_type)


def parse_action(plan_output: str) -> tuple[str, str]:
    """
    Parse the Thought and Action from agent output.

    Expected format:
    Thought: [analysis]
    Action: [json_action]

    Args:
        plan_output: Raw output from agent

    Returns:
        Tuple of (thought, action)
    """
    try:
        parts = plan_output.split("Action:")

        if len(parts) != 2:
            raise ValueError("Expected exactly one 'Action:' in the output")
        thought_part = parts[0].strip()
        if thought_part.startswith("Thought:"):
            thought = thought_part[8:].strip()  # Remove 'Thought:' prefix
        else:
            thought = thought_part

        action = parts[1].strip()

        return thought, action

    except Exception as e:
        logger.error(f"Error parsing output: {e}")
        logger.debug(f"Output: {plan_output}")
        raise ValueError(f"Output is not in the correct format: {e}")


def parse_response_to_action(
    action_str: str,
    image_width: int,
    image_height: int,
    scale_factor: int | tuple[int, int] = 1000,
) -> dict:
    """
    Parse the JSON action from response and normalize it.
    Convert relative coordinates (0-999) to absolute coordinates based on image size.

    Args:
        action_str: JSON action string from model
        image_width: Width of the screenshot image
        image_height: Height of the screenshot image
        scale_factor: Scale factor for the coordinates
    Returns:
        Dictionary with action type and absolute coordinates
    """
    try:
        action_data = parse_json_markdown(action_str)
        original_action_type = action_data.get("action_type")
        normalized_action_type = normalize_action_type(original_action_type)

        if not normalized_action_type:
            raise ValueError("Action type is missing or empty.")

        action_data["action_type"] = normalized_action_type
        action_type = normalized_action_type
        scale_factor_x, scale_factor_y = (
            [scale_factor, scale_factor] if isinstance(scale_factor, int) else scale_factor
        )

        # Handle coordinate-based actions
        if action_type in ["click", "double_tap", "long_press"]:
            # Ensure coordinate is present
            if "coordinate" in action_data:
                coord = action_data["coordinate"]
                if isinstance(coord, list) and len(coord) == 2:
                    # Convert relative coordinates (0-999) to absolute coordinates
                    relative_x, relative_y = coord[0], coord[1]

                    absolute_x = int(relative_x * image_width / scale_factor_x)
                    absolute_y = int(relative_y * image_height / scale_factor_y)

                    logger.debug(
                        f"Coordinate conversion: relative ({relative_x}, {relative_y}) -> absolute ({absolute_x}, {absolute_y})"
                    )

                    return {
                        "action_type": action_type,
                        "x": absolute_x,
                        "y": absolute_y,
                    }
                else:
                    raise ValueError(f"Invalid coordinate format: {coord}")
            else:
                raise ValueError(f"Missing coordinate for action type: {action_type}")

        # Handle drag action
        elif action_type == "drag":
            if "start_coordinate" in action_data and "end_coordinate" in action_data:
                start_coord = action_data["start_coordinate"]
                end_coord = action_data["end_coordinate"]
                if (
                    isinstance(start_coord, list)
                    and len(start_coord) == 2
                    and isinstance(end_coord, list)
                    and len(end_coord) == 2
                ):
                    # Convert relative coordinates (0-999) to absolute coordinates
                    relative_start_x, relative_start_y = start_coord[0], start_coord[1]
                    relative_end_x, relative_end_y = end_coord[0], end_coord[1]

                    absolute_start_x = int(relative_start_x * image_width / scale_factor_x)
                    absolute_start_y = int(relative_start_y * image_height / scale_factor_y)
                    absolute_end_x = int(relative_end_x * image_width / scale_factor_x)
                    absolute_end_y = int(relative_end_y * image_height / scale_factor_y)

                    logger.debug(
                        f"Drag coordinate conversion: relative ({relative_start_x}, {relative_start_y}) -> ({relative_end_x}, {relative_end_y}) | absolute ({absolute_start_x}, {absolute_start_y}) -> ({absolute_end_x}, {absolute_end_y})"
                    )

                    return {
                        "action_type": "drag",
                        "start_x": absolute_start_x,
                        "start_y": absolute_start_y,
                        "end_x": absolute_end_x,
                        "end_y": absolute_end_y,
                    }
                else:
                    raise ValueError(f"Invalid drag coordinates: {start_coord}, {end_coord}")
            else:
                raise ValueError("Missing coordinates for drag action")

        # Handle other action types
        elif action_type in [
            "open_app",
            "answer",
            "navigate_home",
            "navigate_back",
            "scroll",
            "wait",
            "ask_user",
            "keyboard_enter",
        ]:
            return action_data
        elif action_type == "input_text":
            return {
                "action_type": "input_text",
                "text": action_data.get("text", ""),
            }
        elif action_type == "status":
            return {
                "action_type": "answer",
                "text": "task finished"
                if action_data.get("goal_status") == "complete"
                else "task failed",
            }
        else:
            return action_data

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON action: {e}")
        raise ValueError(f"Invalid JSON format in action: {action_str}")
    except Exception as e:
        logger.error(f"Error parsing action: {e}")
        raise ValueError(f"Error parsing action: {action_str}")


class GeneralE2EAgentMCP(MCPAgent):
    def __init__(
        self,
        model_name: str,
        llm_base_url: str,
        api_key: str = "empty",
        observation_type: str = "screenshot",
        runtime_conf: dict = {
            "history_n_images": 3,
            "temperature": 0.0,
            "max_tokens": 2048,
        },
        tools: list[dict] = [],
        scale_factor: int = 1000,
        **kwargs,
    ):
        super().__init__(tools=tools, **kwargs)

        # Agent parameters
        self.model_name = model_name
        self.llm_base_url = llm_base_url
        self.api_key = api_key
        self.observation_type = observation_type
        self.runtime_conf = runtime_conf
        self.scale_factor = scale_factor
        if "claude" in self.model_name.lower():
            self.scale_factor = CLAUDE_IMAGE_SIZE
        if "k2.5" in self.model_name.lower():
            self.scale_factor = 1

        logger.debug(f"Agent runtime_conf = {self.runtime_conf}")
        logger.debug(f"Agent scale_factor = {self.scale_factor}")

        self.build_openai_client(self.llm_base_url, self.api_key)
        logger.debug(f"Agent base_url={self.llm_base_url} model={self.model_name}")

        self.history_n_images = self.runtime_conf.pop("history_n_images", 3)
        if os.getenv("HISTORY_N_IMAGES") is not None:
            self.history_n_images = int(os.getenv("HISTORY_N_IMAGES"))

        self.history_images = []
        self.history_responses = []
        self.actions = []

    def initialize_hook(self, instruction: str) -> None:
        """Hook for initializing the agent with instruction."""
        logger.info(f"Initializing general E2E agent with instruction: {instruction}")
        # Reset history when initializing with new instruction
        self.reset()

    def _get_user_message(self, img_data, tool_call_res, ask_user_response_res) -> dict:
        user_message = None
        if tool_call_res is not None:
            user_message = {
                "role": "user",
                "content": [{"type": "text", "text": f"Tool call result: {tool_call_res}"}],
            }
        elif ask_user_response_res is not None:
            user_message = {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": ask_user_response_res,
                    }
                ],
            }
        else:
            user_message = {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": img_data,
                    }
                ],
            }
        return user_message

    def _hide_history_images(self, messages) -> list[dict]:
        num_images_used = 0
        for i in range(len(messages)):
            reverse_i = len(messages) - i - 1
            if (
                messages[reverse_i]["role"] == "user"
                and messages[reverse_i]["content"][0]["type"] == "image_url"
            ):
                if num_images_used < self.history_n_images:
                    encoded_string = pil_to_base64(messages[reverse_i]["content"][0]["image_url"])
                    messages[reverse_i]["content"][0]["image_url"] = {
                        "url": f"data:image/png;base64,{encoded_string}"
                    }
                    num_images_used += 1
                else:
                    messages[reverse_i]["content"] = [
                        {"type": "text", "text": "(Previous turn, screen not shown)"}
                    ]
        return messages

    def predict(
        self,
        observation: dict[str, Any],
    ) -> tuple[str, JSONAction]:
        """
        Generate action with coordinates based on the current observation.

        Args:
            observation: Observation containing screenshot

        Returns:
            Tuple of (raw_response, JSONAction)
        """

        # resize for claude
        orig_width, orig_height = observation["screenshot"].size
        if "claude" in self.model_name.lower():
            obs_image = observation["screenshot"].resize(CLAUDE_IMAGE_SIZE)
        else:
            obs_image = observation["screenshot"]
        tool_call = observation.get("tool_call", None)
        ask_user_response = observation.get("ask_user_response", None)

        self.history_images.append((obs_image, tool_call, ask_user_response))

        logger.debug(f"Current history images count: {len(self.history_images)}")
        logger.debug(f"Current history responses count: {len(self.history_responses)}")

        assert len(self.history_images) == len(self.history_responses) + 1
        messages = [
            {
                "role": "system",
                "content": GENERAL_E2E_PROMPT_TEMPLATE.render(
                    goal=self.instruction,
                    tools="\n".join([json.dumps(tool, ensure_ascii=False) for tool in self.tools]),
                    scale_factor=self.scale_factor,
                ),
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
                "content": [{"type": "text", "text": history_resp.get("content", "")}],
            }

            messages.append(response_message)
            messages.append(user_message)

        logger.debug(f"Constructed {len(messages) // 2} history turns.")
        messages = self._hide_history_images(messages)

        pretty_print_messages(messages, max_messages=6)
        logger.debug("*" * 100)

        try_times = 3
        response = None
        thought = None
        action_str = None

        while try_times > 0:
            try:
                response = self.openai_chat_completions_create(
                    model=self.model_name,
                    messages=messages,
                    retry_times=1,
                    **self.runtime_conf,
                )
                logger.info(f"\nRaw LLM response received:\n{response}")

                thought, action_str = parse_action(response)

                break

            except Exception as e:
                logger.warning(
                    f"Error fetching response from agent: {self.model_name}, {self.llm_base_url}, {self.api_key}"
                )

                error_msg = str(e)
                try_times -= 1
                logger.warning(
                    f"Error fetching response from agent: {error_msg}. Retrying... ({try_times} attempts left)"
                )
                if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                    time.sleep(2)

        if response is None:
            raise ValueError("Agent LLM failed")
        if action_str is None:
            return "Agent LLM failed", JSONAction(action_type="unknown", text="Agent LLM failed")

        logger.debug(f"Image size: {orig_width}x{orig_height}")

        try:
            json_action_dict = parse_response_to_action(
                action_str, orig_width, orig_height, self.scale_factor
            )

        except Exception as e:
            logger.error(f"Error parsing agent response: {e}")
            return "Agent LLM failed", JSONAction(action_type="unknown", text="Agent LLM failed")

        logger.info(f"Parsed thought: {thought}")
        logger.info(f"Parsed action: {json_action_dict}")

        self.history_responses.append({"role": "assistant", "content": response})
        self.actions.append(json_action_dict)
        logger.debug("Agent state updated for next turn.")

        return response, JSONAction(**json_action_dict)

    def reset(self):
        """Reset the agent for the next task."""
        self.history_images = []
        self.history_responses = []
        self.actions = []
        logger.debug("Agent reset completed")
