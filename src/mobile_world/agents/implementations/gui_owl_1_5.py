import json
import traceback
from typing import Any

from loguru import logger

from mobile_world.agents.base import MCPAgent
from mobile_world.agents.utils.agent_mapping import GUIOWL2AW_ACTION_MAP
from mobile_world.agents.utils.helpers import (
    pil_to_base64, add_period_robustly
)

from mobile_world.runtime.utils.helpers import pretty_print_messages
from mobile_world.runtime.utils.models import ENV_FAIL, MCP, JSONAction

from mobile_world.agents.utils.prompts import (
    GUI_OWL_1_5_SYSTEM_PROMPT_TEMPLATE,
    GUI_OWL_1_5_USER_PROMPT_TEMPLATE,
    GUI_OWL_1_5_USER_PROMPT_WITH_HISTSTEPS_TEMPLATE,
)

SCALE_FACTOR = 999


def parse_tagged_text(text: str) -> dict:
    """
    Parse model output text into structured components.

    Expected format:
        <thinking content>
        Action: "<conclusion>"
        <tool_call>
        {"name": ..., "arguments": ...}
        </tool_call>

    Returns a dict with keys: thinking, conclusion, tool_call.
    """
    result = {"thinking": None, "conclusion": None, "tool_call": None}

    action_parts = text.split("Action:")
    if len(action_parts) > 1:
        result["thinking"] = action_parts[0].strip()
        action_content = action_parts[1]
    else:
        # No "Action:" tag found; treat entire text as action content
        action_content = text

    # Parse conclusion and tool_call from action content
    tool_parts = action_content.split("<tool_call>")
    if len(tool_parts) > 1:
        conclusion_content = tool_parts[0].strip()
        # Strip surrounding quotes if present
        if conclusion_content.startswith('"') and conclusion_content.endswith('"'):
            conclusion_content = conclusion_content[1:-1]
        result["conclusion"] = conclusion_content

        tool_call_raw = tool_parts[1].split("</tool_call>")[0].strip()
        try:
            result["tool_call"] = json.loads(tool_call_raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse tool_call JSON: {e}")

    return result


def parse_action_to_structure_output(text: str) -> dict:
    """
    Parse raw model output into a structured response dict.

    Returns:
        {
            "thinking":     str | None,
            "conclusion":   str | None,
            "action_json":  dict,
            "action_name":  str,
        }
    """
    text = text.strip()

    results = parse_tagged_text(text)
    thinking = results["thinking"]
    conclusion = results["conclusion"]
    tool_call = results["tool_call"]

    if tool_call is None:
        raise ValueError("No <tool_call> block found in model output.")

    action = tool_call["arguments"]
    action_name = tool_call["name"]

    # Normalize 'coordinate' to a 2-element [x, y] list in [0, 1] range
    if "coordinate" in action:
        coordinates = action["coordinate"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError(f"Unexpected coordinate length: {coordinates}")
        action["coordinate"] = [point_x / SCALE_FACTOR, point_y / SCALE_FACTOR]

    # Normalize 'coordinate2' to a 2-element [x, y] list in [0, 1] range
    if "coordinate2" in action:
        coordinates = action["coordinate2"]
        if len(coordinates) == 2:
            point_x, point_y = coordinates
        elif len(coordinates) == 4:
            x1, y1, x2, y2 = coordinates
            point_x = (x1 + x2) / 2
            point_y = (y1 + y2) / 2
        else:
            raise ValueError(f"Unexpected coordinate2 length: {coordinates}")
        action["coordinate2"] = [point_x / SCALE_FACTOR, point_y / SCALE_FACTOR]

    return {
        "thinking": thinking,
        "action_json": action,
        "conclusion": conclusion,
        "action_name": action_name,
    }


def parsing_response_to_andoid_world_env_action(
    structured_response: dict, image_height: int, image_width: int
) -> dict:
    """Convert a structured model response into an AndroidWorld environment action dict."""
    action_json = structured_response.get("action_json")
    action_type = action_json.get("action")

    result = {}

    if action_type == "type":
        result = {
            "action_type": GUIOWL2AW_ACTION_MAP["type"],
            "text": action_json.get("text", ""),
        }

    elif action_type == "swipe":
        start_box = action_json.get("coordinate")
        end_box = action_json.get("coordinate2")
        if start_box and end_box:
            x1, y1 = start_box
            x2, y2 = end_box
            result = {
                "action_type": GUIOWL2AW_ACTION_MAP["swipe"],
                "start_x": round(float(x1) * image_width),
                "start_y": round(float(y1) * image_height),
                "end_x": round(float(x2) * image_width),
                "end_y": round(float(y2) * image_height),
            }
        else:
            raise ValueError("Invalid swipe: missing coordinate or coordinate2.")

    elif action_type in ("click", "long_press"):
        start_box = action_json.get("coordinate")
        if start_box:
            try:
                if len(start_box) == 4:
                    x1, y1, x2, y2 = start_box
                elif len(start_box) == 2:
                    x1, y1 = start_box
                    x2, y2 = x1, y1
                else:
                    raise ValueError(f"Invalid coordinate format: {start_box}")
                x = round(float((x1 + x2) / 2) * image_width)
                y = round(float((y1 + y2) / 2) * image_height)
                result = {
                    "action_type": GUIOWL2AW_ACTION_MAP[action_type],
                    "x": x,
                    "y": y,
                }
            except Exception as e:
                logger.error(f"Error parsing coordinates: {e}")
                raise
        else:
            raise ValueError(f"Missing coordinate for action_type '{action_type}'.")

    elif action_type == "system_button":
        button = action_json.get("button", "").title()
        if button == "Home":
            result = {"action_type": GUIOWL2AW_ACTION_MAP["home"]}
        elif button == "Back":
            result = {"action_type": GUIOWL2AW_ACTION_MAP["back"]}
        elif button == "Enter":
            result = {"action_type": GUIOWL2AW_ACTION_MAP["enter"]}
        else:
            raise ValueError(f"Unsupported system_button: '{button}'.")

    elif action_type == "interact":
        result = {
            "action_type": GUIOWL2AW_ACTION_MAP["interact"],
            "text": action_json.get("text", ""),
        }

    elif action_type == "open":
        # Kept for backward compatibility; current prompt does not emit this action.
        result = {
            "action_type": "open_app",
            "app_name": action_json.get("text", ""),
        }

    elif action_type == "terminate":
        result = {
            "action_type": GUIOWL2AW_ACTION_MAP["terminate"],
            "text": action_json.get("status", ""),
        }

    elif action_type == "answer":
        result = {
            "action_type": GUIOWL2AW_ACTION_MAP["answer"],
            "text": action_json.get("text", ""),
        }

    elif action_type == "wait":
        result = {"action_type": GUIOWL2AW_ACTION_MAP["wait"]}

    else:
        raise ValueError(f"Unknown action_type: '{action_type}'.")

    return result


def _make_image_content(encoded_string: str) -> dict:
    """Return an OpenAI-compatible image_url content block from a base64 string."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{encoded_string}"},
    }


class GUIOWL15AgentMCP(MCPAgent):
    def __init__(
        self,
        model_name: str,
        llm_base_url: str,
        api_key: str = "empty",
        observation_type: str = "screenshot",
        runtime_conf: dict = {
            "history_n": 1,
            "max_tokens": 2048,
            "temperature": 0.0,
            "top_p": 1.0,
        },
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.model_name = model_name
        logger.info(f"Running Task with policy model name: {model_name}")
        self.llm_base_url = llm_base_url
        self.observation_type = observation_type
        self.runtime_conf = runtime_conf
        self.build_openai_client(self.llm_base_url, api_key)

        # Per-task state (reset between tasks)
        self.thoughts: list[str] = []
        self.actions: list[dict] = []
        self.conclusions: list[str] = []
        self.history_images: list[str] = []          # base64-encoded strings
        self.history_responses: list[str] = []       # raw assistant text (excludes current)
        self.history_user_content: list[tuple] = []  # (encoded_string, tool_call, ask_user_response)

        # Frequently used hyper-parameters
        self.temperature = self.runtime_conf.pop("temperature", 0.0)
        self.top_p = self.runtime_conf.pop("top_p", 1.0)
        self.max_tokens = self.runtime_conf.pop("max_tokens", 2048)
        self.history_n = self.runtime_conf.pop("history_n", 1)
        self.is_memory_mode = self.runtime_conf.pop("is_memory_mode", False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_user_message(
        self,
        encoded_string: str,
        tool_call_res: str | None,
        ask_user_response_res: str | None,
    ) -> dict:
        """
        Build an OpenAI user message that wraps a tool response and a screenshot.
        """
        user_content = [
            {"type": "text", "text": "<tool_response>\n"},
        ]

        if tool_call_res is not None:
            user_content.append({"type": "text", "text": str(tool_call_res)})
        elif ask_user_response_res is not None:
            user_content.append(
                {
                    "type": "text",
                    "text": f"(Ask_user_response){ask_user_response_res}",
                }
            )
        else:
            user_content.append({"type": "text", "text": "None"})

        user_content.append(_make_image_content(encoded_string))
        user_content.append({"type": "text", "text": "\n</tool_response>"})

        return {"role": "user", "content": user_content}

    def _format_previous_steps(self, start_idx: int, end_idx: int) -> str:
        """
        Render history steps [start_idx, end_idx) as plain text.

        Each line follows the pattern:
            Step<N>: <conclusion>  Tool response: <tool_response>
        """
        previous_steps = []
        for i in range(start_idx, end_idx):
            step_num = i + 1
            conclusion = add_period_robustly(self.conclusions[i])
            step_info = f"Step{step_num}: {conclusion}"

            tool_call_res = (
                self.history_user_content[i][1]
                if i < len(self.history_user_content)
                else None
            )
            ask_user_res = (
                self.history_user_content[i][2]
                if i < len(self.history_user_content)
                else None
            )

            if tool_call_res is not None:
                step_info += f" Tool response: {tool_call_res}"
            elif ask_user_res is not None:
                step_info += f" Tool response: (Ask_user_response){ask_user_res}"
            else:
                step_info += " Tool response: None"

            previous_steps.append(step_info)

        return "\n".join(previous_steps)

    # ------------------------------------------------------------------
    # Main prediction method
    # ------------------------------------------------------------------

    def predict(
        self, observation: dict[str, Any]
    ) -> tuple[list, str, str, str, str, JSONAction]:
        """Predict the next action based on the current observation."""

        assert len(self.actions) == len(self.thoughts) == len(self.conclusions), (
            "Mismatch between actions, thoughts, and conclusions counts."
        )

        # ── Encode current screenshot ──────────────────────────────────
        obs_image = observation["screenshot"]
        encoded_string: str = pil_to_base64(obs_image)

        tool_call = observation.get("tool_call", None)
        ask_user_response = observation.get("ask_user_response", None)

        # Store current observation (encoded_string, tool_call, ask_user_response)
        self.history_images.append(encoded_string)
        self.history_user_content.append((encoded_string, tool_call, ask_user_response))

        logger.debug(f"History images count:    {len(self.history_images)}")
        logger.debug(f"History responses count: {len(self.history_responses)}")

        assert len(self.history_images) == len(self.history_responses) + 1, (
            "history_images should always be exactly one ahead of history_responses."
        )

        # ── System prompt ──────────────────────────────────────────────
        system_prompt = GUI_OWL_1_5_SYSTEM_PROMPT_TEMPLATE.render(
            tools="\n".join(
                [json.dumps(tool, ensure_ascii=False) for tool in self.tools]
            )
        )

        # ── History windowing ──────────────────────────────────────────
        # total_history_count: number of completed assistant turns (excludes current)
        total_history_count = len(self.history_responses)

        # keep_as_messages: how many recent turns to keep as real user-assistant message pairs
        # history_n includes the current observation, so pairs = history_n - 1
        keep_as_messages = min(self.history_n - 1, total_history_count)

        # text_history_count: older turns that are collapsed into plain text
        text_history_count = total_history_count - keep_as_messages

        # ── Build message list ─────────────────────────────────────────
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        # ── First user message ─────────────────────────────────────────
        first_user_content = []

        if text_history_count > 0:
            # Prepend collapsed history as plain text
            previous_steps_text = self._format_previous_steps(0, text_history_count)
            first_user_content.append(
                {
                    "type": "text",
                    "text": GUI_OWL_1_5_USER_PROMPT_WITH_HISTSTEPS_TEMPLATE.format(
                        instruction=self.instruction,
                        previous_steps=previous_steps_text,
                    ),
                }
            )
        else:
            first_user_content.append(
                {
                    "type": "text",
                    "text": GUI_OWL_1_5_USER_PROMPT_TEMPLATE.format(
                        instruction=self.instruction
                    ),
                }
            )

        # The first screenshot that is kept as an image is at index text_history_count.
        # For the very first turn (text_history_count == 0) this is simply index 0.
        # Note: the first observation in the kept window has no preceding tool response,
        # so we only attach the screenshot here (tool_call / ask_user_response are
        # carried by the *next* user message that follows the assistant reply).
        first_img_encoded, _, _ = self.history_user_content[text_history_count]
        first_user_content.append(_make_image_content(first_img_encoded))

        messages.append({"role": "user", "content": first_user_content})

        # ── Interleaved assistant / user messages ──────────────────────
        # Iterate over the completed turns that we keep as real messages.
        # Index i refers to the i-th completed assistant turn (0-based).
        for i in range(text_history_count, total_history_count):
            # Assistant reply for turn i
            history_resp = self.history_responses[i]
            messages.append(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": history_resp.strip()}],
                }
            )

            # User message for turn i+1 (tool response + screenshot)
            next_img_idx = i + 1
            if next_img_idx < len(self.history_user_content):
                next_encoded, tool_call_res, ask_user_response_res = (
                    self.history_user_content[next_img_idx]
                )
                messages.append(
                    self._get_user_message(
                        next_encoded, tool_call_res, ask_user_response_res
                    )
                )

        logger.debug(
            f"Constructed messages: {keep_as_messages} user-assistant pair(s) "
            f"with images, {text_history_count} text-only history step(s)."
        )
        pretty_print_messages(messages, max_messages=4)
        logger.debug("*" * 100)

        # ── LLM inference with retry ───────────────────────────────────
        origin_h, origin_w = obs_image.height, obs_image.width
        parsed_response = None
        prediction = None
        max_retries = 5

        for attempt in range(1, max_retries + 1):
            prediction = self.openai_chat_completions_create(
                model=self.model_name,
                messages=messages,
                retry_times=3,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                **self.runtime_conf,
            )
            logger.info(f"Raw prediction (attempt {attempt}):\n{prediction}")

            if prediction is None:
                raise RuntimeError("Received None response from the LLM client.")

            try:
                parsed_response = parse_action_to_structure_output(prediction)
                logger.info(f"Parsed response:\n{parsed_response}")
                break
            except Exception:
                logger.error(f"Failed to parse response on attempt {attempt}.")
                logger.error(traceback.format_exc())
                prediction = None
                if attempt == max_retries:
                    logger.error("Max retries reached; giving up on this step.")

        # ── Parse failure fallback ─────────────────────────────────────
        if parsed_response is None:
            return "llm parse error after multiple retries", JSONAction(action_type=ENV_FAIL)
            

        # ── Update state ───────────────────────────────────────────────
        self.history_responses.append(prediction)
        self.thoughts.append(parsed_response["thinking"])
        self.conclusions.append(parsed_response["conclusion"])

        # ── Build and return the env action ───────────────────────────
        if parsed_response["action_name"] == "mobile_use":
            json_action_dict = parsing_response_to_andoid_world_env_action(
                parsed_response,
                origin_h,
                origin_w,
            )
            self.actions.append(json_action_dict)

            return prediction, JSONAction(**json_action_dict),
        else:
            mcp_action = {
                "action_name": parsed_response["action_name"],
                "action_args": parsed_response["action_json"],
            }
            self.actions.append(mcp_action)

            return prediction,JSONAction(
                    action_type=MCP,
                    action_json=parsed_response["action_json"],
                    action_name=parsed_response["action_name"],
                )
               
                

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self):
        """Reset all per-task state so the agent is ready for a new task."""
        self.thoughts = []
        self.actions = []
        self.conclusions = []
        self.history_images = []
        self.history_responses = []
        self.history_user_content = []
