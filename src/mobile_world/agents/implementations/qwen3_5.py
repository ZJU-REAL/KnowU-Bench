import json
import traceback
from typing import Any

from loguru import logger

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.utils.agent_mapping import QWENVL2AW_ACTION_MAP
from mobile_world.agents.utils.helpers import (
    pil_to_base64,
)
from mobile_world.agents.utils.prompts import (
    MOBILE_QWEN3_5_PROMPT_WITH_ASK_USER,
    MOBILE_QWEN3_5_USER_TEMPLATE,
)
from mobile_world.runtime.utils.helpers import pretty_print_messages
from mobile_world.runtime.utils.models import ENV_FAIL, MCP, JSONAction

SCALE_FACTOR = 999


def parse_tagged_text(text):
    result = {"thinking": None, "conclusion": None, "tool_call": None}

    # 1. 提取思考过程 (Qwen3.5 的核心变化：使用 </think> 切分)
    parts = text.split("</think>")
    if len(parts) > 1:
        # </think> 前面的是思考过程
        result["thinking"] = parts[0].strip()
        # </think> 后面的是最终输出和动作
        final_output = parts[1].strip()
    else:
        # 万一模型没按套路出牌，就作为容错
        final_output = text.strip()

    # 2. 从最终输出中提取动作 (兼容原有的 <tool_call> 解析逻辑)
    if "Action:" in final_output:
        action_parts = final_output.split("Action:")
        action_tool_part = action_parts[1]
    else:
        action_tool_part = final_output

    if "<tool_call>" in action_tool_part:
        tool_parts = action_tool_part.split("<tool_call>")
        
        # 提取 conclusion
        action_content = tool_parts[0].strip()
        if action_content.startswith('"') and action_content.endswith('"'):
            action_content = action_content[1:-1]
        result["conclusion"] = action_content

        # 提取并解析 tool_call JSON
        tool_call_content = tool_parts[1].split("</tool_call>")[0].strip()
        try:
            result["tool_call"] = json.loads(tool_call_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse tool_call JSON: {e}")
    else:
        # 如果没有触发工具，最终输出就是 conclusion
        result["conclusion"] = final_output

    return result

def parse_action_to_structure_output(text):
    text = text.strip()

    results = parse_tagged_text(text)
    thinking = results["thinking"]
    tool_call = results["tool_call"]
    conclusion = results["conclusion"]

    # ==========================================
    # 🛡️ 新增容错防爆机制：拦截 NoneType
    # ==========================================
    if tool_call is None:
        logger.warning(f"⚠️ Model failed to output <tool_call>! Forcing 'answer' action. Conclusion: {conclusion}")
        # 强行构造一个 answer 动作，避免后续代码崩溃
        action = {
            "action": "answer", 
            "text": conclusion if conclusion else "Error: Model returned empty action."
        }
        action_name = "mobile_use"
    else:
        # 正常解析
        action = tool_call["arguments"]
        action_name = tool_call["name"]
    # ==========================================

    if "coordinate" in action:
        coordinates = action["coordinate"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError("Wrong output format")
        point_x = point_x / SCALE_FACTOR
        point_y = point_y / SCALE_FACTOR
        action["coordinate"] = [point_x, point_y]

    if "coordinate2" in action:
        coordinates = action["coordinate2"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError("Wrong output format")
        point_x = point_x / SCALE_FACTOR
        point_y = point_y / SCALE_FACTOR
        action["coordinate2"] = [point_x, point_y]

    return {
        "thinking": thinking,
        "action_json": action,
        "conclusion": conclusion,
        "action_name": action_name,
    }


def parsing_response_to_andoid_world_env_action(
    structured_response, image_height: int, image_width: int
) -> dict:
    action_json = structured_response.get("action_json")
    action_type = action_json.get("action")

    result = {}

    if action_type == "type":
        result = {
            "action_type": QWENVL2AW_ACTION_MAP["type"],
            "text": action_json.get("text", ""),
        }

    elif action_type in ["swipe"]:
        start_box = action_json.get("coordinate")
        end_box = action_json.get("coordinate2")
        if start_box and end_box:
            (
                x1,
                y1,
            ) = start_box
            (
                x2,
                y2,
            ) = end_box

            result = {
                "action_type": QWENVL2AW_ACTION_MAP["swipe"],
                "start_x": round(float(x1) * image_width),
                "start_y": round(float(y1) * image_height),
                "end_x": round(float(x2) * image_width),
                "end_y": round(float(y2) * image_height),
            }
        else:
            raise ValueError("Invalid scroll box format")

    elif action_type in ["click", "long_press"]:
        start_box = action_json.get("coordinate")
        if start_box:
            try:
                if len(start_box) == 4:
                    x1, y1, x2, y2 = start_box
                elif len(start_box) == 2:
                    x1, y1 = start_box
                    x2, y2 = x1, y1
                else:
                    raise ValueError(f"Invalid box format: {start_box}")

                # Calculate center coordinates
                x = round(float((x1 + x2) / 2) * image_width)
                y = round(float((y1 + y2) / 2) * image_height)
                result = {"action_type": QWENVL2AW_ACTION_MAP[action_type], "x": x, "y": y}
            except Exception as e:
                logger.error(f"Error parsing coordinates from start_box: {e}")
        else:
            raise ValueError(f"Invalid action_type: {action_type}")
    elif action_type in ["system_button"]:
        button = action_json.get("button")
        if button == "Home":
            result = {"action_type": QWENVL2AW_ACTION_MAP["home"]}
        elif button == "Back":
            result = {"action_type": QWENVL2AW_ACTION_MAP["back"]}
        elif button == "Enter":
            result = {"action_type": QWENVL2AW_ACTION_MAP["enter"]}
        else:
            raise ValueError(f"Unsupported button: {button}")
    elif action_type in ["ask_user"]:
        result = {
            "action_type": QWENVL2AW_ACTION_MAP["ask_user"],
            "text": action_json.get("text", ""),
        }
    elif (
        action_type == "open"
    ):  # qwen3 prompt does not support open_app action, only keep for compatibility
        result = {"action_type": "open_app", "app_name": action_json.get("text", "")}

    elif action_type == "terminate":
        status = action_json.get("status", "")
        result = {"action_type": QWENVL2AW_ACTION_MAP["terminate"], "text": status}
    elif action_type == "answer":
        answer_text = action_json.get("text", "")
        result = {"action_type": QWENVL2AW_ACTION_MAP["answer"], "text": answer_text}
    elif action_type == "wait":
        result = {
            "action_type": QWENVL2AW_ACTION_MAP["wait"],
        }

    return result


class Qwen3_5AgentMCP(MCPAgent):
    def __init__(
        self,
        model_name: str,
        llm_base_url: str,
        api_key: str = "empty",
        observation_type="screenshot",
        runtime_conf: dict = {"temperature": 0.0},
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.model_name = model_name
        self.llm_base_url = llm_base_url
        self.observation_type = observation_type
        self.runtime_conf = runtime_conf
        self.build_openai_client(self.llm_base_url, api_key)

        self.thoughts = []
        self.actions = []
        self.conclusions = []
        self.history_images = []
        self.history_responses = []

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        """
        Predict the next action(s) based on the current observation.
        """

        assert len(self.actions) == len(self.thoughts) == len(self.conclusions), (
            "The number of actions, thoughts, and conclusions should be the same."
        )

        screenshot = observation["screenshot"]
        self.history_images.append(screenshot)

        encoded_string = pil_to_base64(screenshot)
        if "tool_call" in observation and observation["tool_call"] is not None:
            self.conclusions[-1] += (
                "; Tool call result: <tool_response>"
                + json.dumps(observation["tool_call"], ensure_ascii=False)
                + "</tool_response>"
            )
        if "ask_user_response" in observation and observation["ask_user_response"] is not None:
            self.conclusions[-1] += f"; Ask user response: {observation['ask_user_response']}"
        steps = ""
        for idx, conclusion in enumerate(self.conclusions):
            steps += (
                "Step "
                + str(idx + 1)
                + ": "
                + str(conclusion.replace("\n", "").replace('"', ""))
                + "; "
            )

        system_prompt = MOBILE_QWEN3_5_PROMPT_WITH_ASK_USER.render(
            tools="\n".join([json.dumps(tool, ensure_ascii=False) for tool in self.tools])
        )
        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
        ]

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": MOBILE_QWEN3_5_USER_TEMPLATE.format(
                            instruction=self.instruction, steps=steps
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_string}"},
                    },
                ],
            }
        )

        pretty_print_messages(messages)

        try_times = 3
        origin_h, origin_w = screenshot.height, screenshot.width
        parsed_response = None

        while True:
            prediction = self.openai_chat_completions_create(
                model=self.model_name,
                messages=messages,
                retry_times=3,
                **self.runtime_conf,
            )

            if prediction is None:
                raise Exception("Error when fetching response from clients")

            try:
                parsed_response = parse_action_to_structure_output(
                    prediction,
                )

                logger.info(f"Parsed response: \n{parsed_response}")
                break
            except Exception:
                if try_times > 0:
                    logger.error("Error when parsing response from clients")
                    logger.error(traceback.format_exc())
                    prediction = None
                    try_times -= 1
                else:
                    raise Exception("Failed to parse response after maximum retries")

        if parsed_response is None:
            return "llm parse error after multiple retries", JSONAction(action_type=ENV_FAIL)

        self.history_responses.append(prediction)
        self.thoughts.append(parsed_response["thinking"])
        self.conclusions.append(parsed_response["conclusion"])

        if parsed_response["action_name"] == "mobile_use":
            json_action_dict = parsing_response_to_andoid_world_env_action(
                parsed_response,
                origin_h,
                origin_w,
            )

            self.actions.append(json_action_dict)

            return prediction, JSONAction(**json_action_dict)
        else:
            self.actions.append(
                {
                    "action_name": parsed_response["action_name"],
                    "action_args": parsed_response["action_json"],
                }
            )
            return prediction, JSONAction(
                action_type=MCP,
                action_json=parsed_response["action_json"],
                action_name=parsed_response["action_name"],
            )

    def reset(self):
        """Reset the agent for the next task."""
        self.thoughts = []
        self.actions = []
        self.history_images = []
        self.history_responses = []
        self.conclusions = []
