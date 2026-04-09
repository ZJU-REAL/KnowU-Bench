import json
import time
from typing import Any

from loguru import logger

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.grounding import GROUNDING_MODELS
from mobile_world.agents.utils.helpers import pil_to_base64
from mobile_world.agents.utils.prompts import PLANNER_EXECUTOR_PROMPT_TEMPLATE
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


def normalize_action_type(action_type: str) -> str:
    if not action_type:
        return None
    processed_type = action_type.lower().strip().replace(" ", "_")
    return NORMALIZED_ACTION_MAP.get(processed_type, action_type)


def parse_action(plan_output: str) -> tuple[str, str]:
    """
    Parse the Thought and Action from planner agent output.

    Expected format:
    Thought: [analysis]
    Action: [json_action]

    Args:
        plan_output: Raw output from planner agent

    Returns:
        Tuple of (thought, action)
    """
    try:
        parts = plan_output.split("Action:")

        if len(parts) != 2:
            raise ValueError("Expected exactly one 'Action:' in the output")
        thought_part = parts[0].strip()
        if thought_part.startswith("Thought:"):
            plan_thought = thought_part[8:].strip()  # Remove 'Thought:' prefix
        else:
            plan_thought = thought_part

        plan_action = parts[1].strip()

        return plan_thought, plan_action

    except Exception as e:
        logger.error(f"Error parsing plan output: {e}")
        logger.debug(f"Plan output: {plan_output}")
        raise ValueError(f"Plan-Action prompt output is not in the correct format: {e}")


def parsing_planner_response_to_android_world_env_action(plan_action: str) -> dict:
    """
    Parse the JSON action from planner, normalize it, and convert to Android World format.
    """
    try:
        action_data = parse_json_markdown(plan_action)
        original_action_type = action_data.get("action_type")
        normalized_action_type = normalize_action_type(original_action_type)

        if not normalized_action_type:
            raise ValueError("Action type is missing or empty in the plan.")

        action_data["action_type"] = normalized_action_type
        action_type = normalized_action_type

        if action_type in [
            "open_app",
            "click",
            "double_tap",
            "long_press",
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
        raise ValueError(f"Invalid JSON format in plan_action: {plan_action}")
    except Exception as e:
        logger.error(f"Error parsing plan action: {e}")
        raise ValueError(f"Error parsing plan action: {plan_action}")


class PlannerExecutorAgentMCP(MCPAgent):
    def __init__(
        self,
        model_name: str,
        llm_base_url: str,
        api_key: str = "empty",
        observation_type: str = "screenshot",
        runtime_conf: dict = {},
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Planner parameters (main LLM)
        self.model_name = model_name
        self.llm_base_url = llm_base_url
        self.api_key = api_key
        self.observation_type = observation_type
        self.runtime_conf = runtime_conf

        logger.debug(f"Planner runtime_conf = {self.runtime_conf}")

        self.build_openai_client(self.llm_base_url, self.api_key)
        logger.debug(f"Planner base_url={self.llm_base_url} model={self.model_name}")

        # Executor parameters from kwargs
        executor_agent_class = kwargs.get("executor_agent_class")
        executor_llm_base_url = kwargs.get("executor_llm_base_url")
        executor_model_name = kwargs.get("executor_model_name")
        executor_runtime_conf = kwargs.get(
            "executor_runtime_conf",
            {
                "history_n": 3,
                "temperature": 0.0,
                "max_tokens": 1024,
                "min_pixels": 3136,
                "max_pixels": 4096 * 2160,
            },
        )

        logger.debug(f"Executor runtime_conf = {executor_runtime_conf}")
        logger.debug(f"Executor agent_class = {executor_agent_class}")

        if executor_agent_class:
            self.executor = GROUNDING_MODELS[executor_agent_class](
                llm_base_url=executor_llm_base_url,
                model_name=executor_model_name,
                runtime_conf=executor_runtime_conf,
            )
        else:
            raise ValueError("Executor agent instance creation failed")

        self.history_n_images = self.runtime_conf.pop("history_n_images", 3)
        self.history_images = []
        self.history_responses = []
        self.actions = []
        self.plans = []

    def initialize_hook(self, instruction: str) -> None:
        """Hook for initializing the agent with instruction."""
        logger.info(f"Initializing planner-executor agent with instruction: {instruction}")
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
        Generate natural language UI interaction instructions based on the current observation.

        Args:
            observation: Observation containing screenshot

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
        messages = [
            {
                "role": "system",
                "content": PLANNER_EXECUTOR_PROMPT_TEMPLATE.render(
                    goal=self.instruction,
                    tools="\n".join([json.dumps(tool, ensure_ascii=False) for tool in self.tools]),
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

        pretty_print_messages(messages, max_messages=4)
        logger.debug("*" * 100)

        try_times = 3

        while try_times > 0:
            try:
                plan = self.openai_chat_completions_create(
                    model=self.model_name,
                    messages=messages,
                    retry_times=1,
                    **self.runtime_conf,
                )

                plan_thought, action_str = parse_action(plan)

                logger.info(f"\nRaw LLM response received:\n{plan}")
                break

            except Exception as e:
                logger.warning(
                    f"Error fetching response from planner: {self.model_name}, {self.llm_base_url}, {self.api_key}"
                )

                error_msg = str(e)
                try_times -= 1
                logger.warning(
                    f"Error fetching response from planner: {error_msg}. Retrying... ({try_times} attempts left)"
                )
                if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                    time.sleep(2)

        if plan is None:
            raise ValueError("Planner LLM failed")
        if action_str is None:
            return "Planner LLM failed", JSONAction(
                action_type="unknown", text="Planner LLM failed"
            )

        try:
            json_action_dict = parsing_planner_response_to_android_world_env_action(action_str)
        except Exception as e:
            logger.error(f"Error parsing planner response: {e}")
            return "Planner LLM failed", JSONAction(
                action_type="unknown", text="Planner LLM failed"
            )

        logger.info(f"Parsed planner thought: {plan_thought}")
        logger.info(f"Parsed planner action: {json_action_dict}")

        def get_executor_action(executor_instruction: str) -> dict:
            self.executor.initialize(executor_instruction)
            prediction, exec_action = self.executor.predict(observation)

            if exec_action and exec_action.action_type != "unknown":
                # Convert JSONAction to dict
                exec_action_dict = (
                    exec_action.model_dump(exclude_none=True)
                    if hasattr(exec_action, "model_dump")
                    else exec_action.dict()
                )
                json_action_dict = exec_action_dict
                logger.info(f"Executor succeeded. Using its precise action: {json_action_dict}")
            else:
                logger.warning(f"Executor failed. Using planner's action: {json_action_dict}")
                json_action_dict = {
                    "action_type": "unknown",
                    "text": f"Executor failed for instruction: '{executor_instruction}'. The error of prediction is {prediction}.",
                }
            return json_action_dict

        if (
            json_action_dict["action_type"] in ["click", "long_press", "double_tap", "drag"]
            and self.executor is not None
        ):
            if json_action_dict["action_type"] == "drag":
                logger.debug(f"Executor drag instruction: {json_action_dict}")

                json_action_dict_start = get_executor_action(
                    "Click " + json_action_dict["target_start"]
                )
                json_action_dict_end = get_executor_action(
                    "Click " + json_action_dict["target_end"]
                )

                json_action_dict = {
                    "action_type": "drag",
                    "start_x": json_action_dict_start["x"],
                    "start_y": json_action_dict_start["y"],
                    "end_x": json_action_dict_end["x"],
                    "end_y": json_action_dict_end["y"],
                }

            else:
                action_type_str = json_action_dict["action_type"]
                if action_type_str == "double_tap":
                    action_type_str = "click"
                executor_instruction = action_type_str + " " + json_action_dict["target"]
                logger.debug(f"Executor instruction: {executor_instruction}")
                json_action_dict_executor = get_executor_action(executor_instruction)
                del json_action_dict_executor["action_type"]
                json_action_dict = {
                    "action_type": json_action_dict["action_type"],
                    **json_action_dict_executor,
                }

        self.history_responses.append({"role": "assistant", "content": plan})  # thinking + action
        self.plans.append(plan)
        self.actions.append(json_action_dict)
        logger.debug("Agent state updated for next turn.")

        return plan, JSONAction(**json_action_dict)

    def reset(self):
        """Reset the agent for the next task."""
        self.history_images = []
        self.history_responses = []
        self.actions = []
        self.plans = []
        if self.executor is not None:
            self.executor.reset()
        logger.debug("Agent reset completed")
