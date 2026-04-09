import re
import time
import traceback
from io import BytesIO
from typing import Any

from loguru import logger
from openai import OpenAI
from PIL import Image

from mobile_world.agents.base import BaseAgent
from mobile_world.agents.utils.agent_mapping import UIINS_ACTION_MAP
from mobile_world.agents.utils.helpers import IMAGE_FACTOR, pil_to_base64, smart_resize
from mobile_world.runtime.utils.models import JSONAction


def parsing_response_to_andoid_world_env_action(response, instruction):
    cor_x, cor_y = response[0], response[1]
    if "click" in instruction.lower():
        action_type = UIINS_ACTION_MAP["click"]
    elif "press" in instruction.lower():
        action_type = UIINS_ACTION_MAP["long_press"]
    else:
        raise ValueError(f"Invalid action_type in instruction: {instruction}")

    result = {"action_type": action_type, "x": cor_x, "y": cor_y}
    return result


def parse_coordinates_from_response(raw_string):
    matches = re.findall(r"\[(\d+),(\d+)\]", raw_string)
    matches = [tuple(map(int, match)) for match in matches]
    if len(matches) == 0:
        return -1, -1
    else:
        return tuple(map(int, matches[0]))


class UIINSGroundingAgent(BaseAgent):
    def __init__(
        self,
        llm_base_url: str,
        model_name: str,
        runtime_conf: dict = {
            "temperature": 0.0,
            "max_tokens": 512,
            "min_pixels": 3136,
            "max_pixels": 4096 * 2160,
        },
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.llm_base_url = llm_base_url
        self.model_name = model_name
        # Handle case where runtime_conf is None
        self.runtime_conf = runtime_conf
        self.vlm = OpenAI(
            base_url=self.llm_base_url,
            api_key="empty",
            timeout=60.0,
            max_retries=3,
        )
        self.temperature = self.runtime_conf["temperature"]
        self.max_tokens = self.runtime_conf["max_tokens"]
        self.max_pixels = self.runtime_conf["max_pixels"]
        self.min_pixels = self.runtime_conf["min_pixels"]
        self.instruction = None

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        """Generate the next action based on current observation.

        Args:
            observation: Dictionary containing screenshot and other observation data

        Returns:
            Tuple of (prediction_text, json_action_dict)
        """
        if self.instruction is None:
            raise ValueError("Agent not initialized. Please call initialize(instruction) first.")

        screenshot_data = observation["screenshot"]

        # Handle both bytes and PIL Image input
        if isinstance(screenshot_data, bytes):
            image = Image.open(BytesIO(screenshot_data))
        elif isinstance(screenshot_data, Image.Image):
            image = screenshot_data
        else:
            raise ValueError(f"Unsupported screenshot type: {type(screenshot_data)}")

        if image.mode != "RGB":
            image = image.convert("RGB")

        origin_h, origin_w = image.height, image.width
        resized_h, resized_w = smart_resize(
            origin_h,
            origin_w,
            factor=IMAGE_FACTOR,
            min_pixels=self.min_pixels,
            max_pixels=self.max_pixels,
        )
        image = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

        encoded_string = pil_to_base64(image)

        messages = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "You are a helpful assistant."},
                    {
                        "type": "text",
                        "text": """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. \n\n## Output Format\nReturn a json object with function name and arguments within <tool_call></tool_call> XML tags:\n```\n<tool_call>\n{\"name\": \"grounding\", \"arguments\": <args-json-object>}\n</tool_call>\n```\n\n<args-json-object> represents the following item of the action space:\n\n## Action Space\n{\"action\": \"click\", \"coordinate\": [x, y]}""",
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_string}"},
                    },
                    {
                        "type": "text",
                        "text": self.instruction,
                    },
                ],
            },
        ]

        logger.info("Sending to UIINS Grounding Agent")
        logger.info(f"Description: '{self.instruction}'")

        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.vlm.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    frequency_penalty=0.0,
                    presence_penalty=0.0,
                    extra_body={
                        "repetition_penalty": 1.0,
                    },
                    seed=42,
                )
                prediction = response.choices[0].message.content.strip()
                logger.info(f"Raw response from model: '{prediction}'")

                coordinates = parse_coordinates_from_response(prediction)

                if coordinates is None:
                    error = "Failed to parse coordinates from: '{prediction}'"
                    logger.error(error)
                    return error, None

                json_action_dict = parsing_response_to_andoid_world_env_action(
                    coordinates, self.instruction
                )
                return prediction, JSONAction(**json_action_dict)

            except Exception as e:
                logger.error(f"Error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    error = "All retries failed for UIINS Grounding Agent"
                    logger.error(error)
                    logger.error(traceback.format_exc())
                    return error, None


if __name__ == "__main__":
    from mobile_world.runtime.utils.trajectory_logger import (
        draw_clicks_on_image,
        extract_click_coordinates,
    )

    screenshot_path = "./assets/screenshot_pil.png"
    output_image_path = "./screenshot_with_clicks.png"

    test_image = Image.open(screenshot_path)

    img_byte_arr = BytesIO()
    test_image.save(img_byte_arr, format="PNG")
    image_data = img_byte_arr.getvalue()

    instruction = "click mail app"

    # Create agent instance
    agent = UIINSGroundingAgent(
        llm_base_url="",
        model_name="",
    )

    agent.initialize(instruction)

    obs = {"screenshot": image_data}

    prediction, action = agent.predict(obs)

    action_dict = action.model_dump() if hasattr(action, "model_dump") else action.dict()
    click_coordinates = extract_click_coordinates(action_dict)

    if click_coordinates:
        draw_clicks_on_image(screenshot_path, output_image_path, click_coordinates)
    else:
        logger.error("No click actions found in the provided actions list.")
