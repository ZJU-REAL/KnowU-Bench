"""
Seed Agent implementation for MobileWorld benchmark.
**Note that the GUI capability of seed-1.8 is not officially supported**, we implement it based on the implementation in https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/seed_agent.py
"""

import json
import os
import re
from typing import Any

from loguru import logger
from PIL import Image

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.utils.helpers import pil_to_base64
from mobile_world.agents.utils.prompts import SEED_PROMPT
from mobile_world.runtime.utils.helpers import pretty_print_messages
from mobile_world.runtime.utils.models import (
    ANSWER,
    ASK_USER,
    CLICK,
    DOUBLE_TAP,
    DRAG,
    INPUT_TEXT,
    MCP,
    NAVIGATE_BACK,
    NAVIGATE_HOME,
    SCROLL,
    UNKNOWN,
    WAIT,
    JSONAction,
)

# Special action words
FINISH_WORD = "finished"
WAIT_WORD = "wait"
CALL_USER = "call_user"

# Thinking token used by Seed model
THINK_TOKEN = "think"


def _extract_parameters(func_content: str) -> dict:
    """
    Extract parameters from function content, handling cases where </parameter> may be missing.

    Handles both:
    - <parameter=point>500 300</parameter>
    - <parameter=point><point>486 500</point><parameter=direction>down</parameter>
    """
    params = {}
    # Match parameter opening tags and capture content until </parameter> or next <parameter= or end
    param_pattern = r"<parameter=(\w+)>(.*?)(?:</parameter>|(?=<parameter=)|$)"
    param_matches = re.findall(param_pattern, func_content, re.DOTALL)

    for param_name, param_value in param_matches:
        # Clean up value - extract from inner tags like <point>...</point> if present
        inner_tag_match = re.search(r"<\w+>(.*?)</\w+>", param_value, re.DOTALL)
        if inner_tag_match:
            param_value = inner_tag_match.group(1)
        params[param_name] = param_value.strip()

    return params


def parse_seed_xml_action(response_text: str) -> list[dict]:
    """
    Parse Seed model's XML-style action format.

    Example format:
    <tool_call>
    <function=click>
    <parameter=point>500 300</parameter>
    </function>
    </tool_call>
    """
    parsed_actions = []

    # Find tool call blocks
    tool_call_pattern = r"<tool_call[^>]*>(.*?)</tool_call[^>]*>"
    tool_call_matches = re.findall(tool_call_pattern, response_text, re.DOTALL)

    if not tool_call_matches:
        # Try alternative pattern without prefix
        tool_call_pattern = r"<function=(\w+)>(.*?)</function>"
        function_matches = re.findall(tool_call_pattern, response_text, re.DOTALL)

        for func_name, func_content in function_matches:
            params = _extract_parameters(func_content)
            parsed_actions.append({"function": func_name, "parameters": params})
    else:
        for tool_call_content in tool_call_matches:
            # Find function blocks within tool call
            function_pattern = r"<function=(\w+)>(.*?)</function>"
            function_matches = re.findall(function_pattern, tool_call_content, re.DOTALL)

            for func_name, func_content in function_matches:
                params = _extract_parameters(func_content)
                parsed_actions.append({"function": func_name, "parameters": params})

    return parsed_actions


def parse_point_string(point_str: str) -> tuple[int, int]:
    """
    Parse point string in format '<point>x y</point>' or 'x y'.
    Returns (x, y) coordinates.
    """
    # Remove <point> tags if present
    point_str = re.sub(r"</?point>", "", point_str).strip()

    # Split by space or comma
    parts = re.split(r"[\s,]+", point_str)
    if len(parts) >= 2:
        return int(float(parts[0])), int(float(parts[1]))
    raise ValueError(f"Invalid point format: {point_str}")


class SeedAgent(MCPAgent):
    """
    Seed Agent for MobileWorld using Seed1.5-VL model.
    Uses Volcengine Ark SDK for inference with thinking capabilities.
    """

    def __init__(
        self,
        model_name: str,
        llm_base_url: str | None = None,
        api_key: str | None = None,
        runtime_conf: dict[str, Any] | None = None,
        **kwargs,
    ):
        """
        Initialize Seed Agent.

        Args:
            model_name: Model name/endpoint ID
            llm_base_url: Base URL for Ark API (uses DOUBAO_API_URL env var if not provided)
            api_key: API key (uses DOUBAO_API_KEY env var if not provided)
            runtime_conf: Runtime configuration dict
        """
        super().__init__(**kwargs)

        # Default configuration
        default_conf = {
            "history_n": 3,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 4096,
            "reasoning_effort": "high",
            "use_thinking": True,
            "resize_image": False,
            "resized_image_width": 1080,
            "resized_image_height": 2400,
        }
        self.runtime_conf = {**default_conf, **(runtime_conf or {})}

        self.model_name = model_name
        self.api_key = api_key or os.environ.get("DOUBAO_API_KEY")
        self.base_url = llm_base_url or os.environ.get("DOUBAO_API_URL")

        if not self.api_key:
            raise ValueError("DOUBAO_API_KEY environment variable or api_key parameter required")
        if not self.base_url:
            raise ValueError(
                "DOUBAO_API_URL environment variable or llm_base_url parameter required"
            )

        self.build_openai_client(base_url=self.base_url, api_key=self.api_key)

        # Extract config values
        self.history_n = self.runtime_conf.get("history_n", 3)
        self.temperature = self.runtime_conf["temperature"]
        self.top_p = self.runtime_conf["top_p"]
        self.max_tokens = self.runtime_conf["max_tokens"]
        self.reasoning_effort = self.runtime_conf["reasoning_effort"]
        self.use_thinking = self.runtime_conf["use_thinking"]
        self.resize_image = self.runtime_conf["resize_image"]
        self.resized_width = self.runtime_conf["resized_image_width"]
        self.resized_height = self.runtime_conf["resized_image_height"]

        # History tracking: list of tuples (image_b64, tool_call_result, ask_user_response)
        self.history_images: list[tuple[str, Any, Any]] = []
        self.history_responses: list[str] = []

        self.system_prompt = "You are provided with a task description, a history of previous actions, and corresponding screenshots. Your goal is to perform the next action to complete the task. Please note that if performing the same action multiple times results in a static screen with no changes, you should attempt a modified or alternative action."

    def initialize_hook(self, instruction: str) -> None:
        """Hook for initializing the agent with instruction."""
        logger.info(f"Initializing Seed agent with instruction: {instruction}")
        self.reset()

    def _inference_with_thinking(self, messages: list[dict]) -> str:
        """
        Call Ark API with thinking/reasoning enabled.
        Returns the full response including thinking and content.
        """
        completion = self.openai_chat_completions_create(
            model=self.model_name,
            stream=True,
            reasoning_effort=self.reasoning_effort,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )

        reasoning_content = ""
        content = ""
        added_think_token = False

        for chunk in completion:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_content += delta.reasoning_content
                if hasattr(delta, "content") and delta.content:
                    if not added_think_token:
                        added_think_token = True
                    content += delta.content

        # Combine reasoning and content with special tokens
        prediction = f"<{THINK_TOKEN}>{reasoning_content}</{THINK_TOKEN}>{content}"

        return prediction

    def _prepare_image(self, screenshot: Image.Image) -> str:
        """Prepare image for API call, optionally resizing."""
        if self.resize_image:
            screenshot = screenshot.resize((self.resized_width, self.resized_height))
        return pil_to_base64(screenshot)

    def _get_user_message(
        self, img_b64: str, tool_call_res: Any, ask_user_response_res: Any
    ) -> dict:
        """Build user message based on available data (image, tool call result, or ask user response)."""
        if tool_call_res is not None:
            tool_call_str = (
                json.dumps(tool_call_res, ensure_ascii=False)
                if isinstance(tool_call_res, (dict, list))
                else str(tool_call_res)
            )
            return {
                "role": "user",
                "content": [{"type": "text", "text": f"Tool call result: {tool_call_str}"}],
            }
        elif ask_user_response_res is not None:
            return {
                "role": "user",
                "content": [{"type": "text", "text": ask_user_response_res}],
            }
        else:
            return {
                "role": "tool",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    }
                ],
                "tool_call_id": "1",
            }

    def _build_messages(
        self, obs_image: Image.Image, tool_call: Any, ask_user_response: Any
    ) -> list[dict]:
        """Build message list for API call."""
        current_image_b64 = self._prepare_image(obs_image)
        # Store tuple of (image_b64, tool_call_result, ask_user_response)
        self.history_images.append((current_image_b64, tool_call, ask_user_response))

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": SEED_PROMPT.render(tools=self.tools)},
            {"role": "user", "content": self.instruction},
        ]

        # Add first observation
        first_img_b64, first_tool_call, first_ask_user = self.history_images[0]
        messages.append(self._get_user_message(first_img_b64, first_tool_call, first_ask_user))

        # Add history responses with their corresponding observations
        for i, hist_response in enumerate(self.history_responses):
            # Extract content after thinking token
            content_parts = hist_response.split(f"</{THINK_TOKEN}>")
            content = content_parts[-1] if len(content_parts) > 1 else hist_response
            reasoning = (
                content_parts[0].replace(f"<{THINK_TOKEN}>", "") if len(content_parts) > 1 else ""
            )

            messages.append(
                {"role": "assistant", "content": content, "reasoning_content": reasoning}
            )

            # Add the next observation if available
            if i + 1 < len(self.history_images):
                img_b64, tool_call_res, ask_user_res = self.history_images[i + 1]
                messages.append(self._get_user_message(img_b64, tool_call_res, ask_user_res))
        messages_with_limited_images = []
        image_count = 0
        for msg in messages[::-1]:
            if msg["role"] == "tool" and msg["content"][0]["type"] == "image_url":
                image_count += 1
                if image_count > self.history_n:
                    continue
            messages_with_limited_images.append(msg)
        messages_with_limited_images = messages_with_limited_images[::-1]

        return messages_with_limited_images

    def _convert_to_json_action(
        self, parsed_action: dict, image_width: int, image_height: int
    ) -> JSONAction:
        """Convert parsed Seed action to JSONAction."""
        func_name = parsed_action["function"]
        params = parsed_action["parameters"]

        # Handle terminal actions
        if func_name == FINISH_WORD:
            return JSONAction(action_type=ANSWER, text=params.get("content", "success"))

        if func_name == WAIT_WORD:
            return JSONAction(action_type=WAIT)

        if func_name == CALL_USER:
            return JSONAction(action_type=ASK_USER, text=params.get("content", ""))

        # Handle click action
        if func_name == "click":
            point_str = params.get("point", "0 0")
            x, y = parse_point_string(point_str)
            # Coordinates are in 1000-scale, convert to actual pixels
            x = int(x * image_width / 1000)
            y = int(y * image_height / 1000)
            return JSONAction(action_type=CLICK, x=x, y=y)

        # Handle double click
        if func_name == "left_double":
            point_str = params.get("point", "0 0")
            x, y = parse_point_string(point_str)
            x = int(x * image_width / 1000)
            y = int(y * image_height / 1000)
            return JSONAction(action_type=DOUBLE_TAP, x=x, y=y)
        # Handle drag/swipe

        if func_name == "drag":
            start_str = params.get("start_point", "0 0")
            end_str = params.get("end_point", "0 0")
            start_x, start_y = parse_point_string(start_str)
            end_x, end_y = parse_point_string(end_str)

            start_x = int(start_x * image_width / 1000)
            start_y = int(start_y * image_height / 1000)
            end_x = int(end_x * image_width / 1000)
            end_y = int(end_y * image_height / 1000)

            return JSONAction(
                action_type=DRAG, start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y
            )

        # Handle scroll
        if func_name == "scroll":
            direction = params.get("direction", "down")
            point_str = params.get("point", "500 500")
            x, y = parse_point_string(point_str)
            x = int(x * image_width / 1000)
            y = int(y * image_height / 1000)
            return JSONAction(action_type=SCROLL, direction=direction, x=x, y=y)

        # Handle type/input
        if func_name == "type":
            content = params.get("content", "")
            return JSONAction(action_type=INPUT_TEXT, text=content)

        # Handle press
        if func_name == "press_home":
            return JSONAction(action_type=NAVIGATE_HOME)
        if func_name == "press_back":
            return JSONAction(action_type=NAVIGATE_BACK)

        if self.tools:
            return JSONAction(action_type=MCP, action_json=params, action_name=func_name)
        else:
            return JSONAction(action_type=UNKNOWN, text=f"Unknown action: {func_name}")

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        """
        Generate the next action based on current observation.

        Args:
            observation: Dict containing 'screenshot' (PIL Image) and optional fields
                - tool_call: Result from previous MCP tool call
                - ask_user_response: Response from user when agent asked for input

        Returns:
            Tuple of (raw_response, JSONAction)
        """
        obs_image = observation["screenshot"]
        tool_call = observation.get("tool_call", None)
        ask_user_response = observation.get("ask_user_response", None)

        if not isinstance(obs_image, Image.Image):
            raise ValueError("Screenshot must be a PIL Image")

        image_width, image_height = obs_image.size

        logger.debug(f"Current history images count: {len(self.history_images)}")
        logger.debug(f"Current history responses count: {len(self.history_responses)}")

        messages = self._build_messages(obs_image, tool_call, ask_user_response)
        pretty_print_messages(messages, max_messages=5)

        # Call API with retries
        retry_times = 3
        prediction = None

        while retry_times > 0:
            try:
                prediction = self._inference_with_thinking(messages)
                break
            except Exception as e:
                logger.warning(f"Error calling LLM: {e}")
                retry_times -= 1
                if retry_times == 0:
                    raise ValueError(f"Failed to get response from LLM after retries: {e}")

        logger.info(f"Raw LLM response:\n{prediction}")
        self.history_responses.append(prediction)

        # Parse the response
        try:
            # Check if it's a simple text response without tool call
            if "tool_call" not in prediction and "function" not in prediction:
                # Model returned text without action - treat as answer
                content = prediction.split(f"</{THINK_TOKEN}>")[-1].strip()
                return prediction, JSONAction(action_type=ANSWER, text=content)

            parsed_actions = parse_seed_xml_action(prediction)

            if not parsed_actions:
                raise ValueError("No actions parsed from response")

            # Take the first action
            first_action = parsed_actions[0]
            logger.info(f"Parsed action: {first_action}")

            json_action = self._convert_to_json_action(first_action, image_width, image_height)
            logger.info(f"Converted to JSONAction: {json_action}")

            return prediction, json_action

        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            # Return the raw response as answer on parse error
            content = prediction.split(f"</{THINK_TOKEN}>")[-1].strip() if prediction else str(e)
            return prediction or str(e), JSONAction(action_type=UNKNOWN, text=content)

    def reset(self) -> None:
        """Reset the agent for the next task."""
        self.history_images: list[tuple[str, Any, Any]] = []
        self.history_responses: list[str] = []
        logger.debug("Seed agent reset completed")
