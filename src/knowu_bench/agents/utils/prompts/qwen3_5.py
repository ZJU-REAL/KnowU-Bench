from jinja2 import Template

MOBILE_QWEN3_5_PROMPT_WITH_ASK_USER = Template("""# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{"type": "function", "function": {"name": "mobile_use", "description": "Use a touchscreen to interact with a mobile device, and take screenshots.\\n* This is an interface to a mobile device with touchscreen. You can perform actions like clicking, typing, swiping, etc.\\n* Some applications may take time to start or process actions, so you may need to wait and take successive screenshots to see the results of your actions.\\n* The screen's resolution is 999x999.\\n* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element. Don't click boxes on their edges unless asked.", "parameters": {"properties": {"action": {"description": "The action to perform. The available actions are:\\n* `click`: Click the point on the screen with coordinate (x, y).\\n* `long_press`: Press the point on the screen with coordinate (x, y) for specified seconds.\\n* `swipe`: Swipe from the starting point with coordinate (x, y) to the end point with coordinates2 (x2, y2).\\n* `type`: Input the specified text into the activated input box.\\n* `answer`: CRITICAL: Use this ONLY to report the final result when the task is completely finished. DO NOT use this to ask the user questions.\\n* `ask_user`: CRITICAL: Use this strictly when you need to consult the user, ask for permission, or propose a suggestion (Interactive Execution).\\n* `system_button`: Press the system button.\\n* `wait`: Wait specified seconds for the change to happen.\\n* `terminate`: Terminate the current task and report its completion status.", "enum": ["click", "long_press", "swipe", "type", "answer", "system_button", "wait", "ask_user", "terminate"], "type": "string"}, "coordinate": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=click`, `action=long_press`, and `action=swipe`.", "type": "array"}, "coordinate2": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=swipe`.", "type": "array"}, "text": {"description": "Required only by `action=type`, `action=ask_user` and `action=answer`.", "type": "string"}, "time": {"description": "The seconds to wait. Required only by `action=long_press` and `action=wait`.", "type": "number"}, "button": {"description": "Back means returning to the previous interface, Home means returning to the desktop, Menu means opening the application background menu, and Enter means pressing the enter. Required only by `action=system_button`", "enum": ["Back", "Home", "Menu", "Enter"], "type": "string"}, "status": {"description": "The status of the task. Required only by `action=terminate`.", "type": "string", "enum": ["success", "failure"]}}, "required": ["action"], "type": "object"}}}
{% if tools %}
{{ tools }}
{% endif -%}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags.

# Response format

Response format for every step:
<think>
One concise sentence explaining the next move. Analyze the screen and decide what to do next.
</think>
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>

CRITICAL RULES:
- You MUST put your reasoning strictly inside <think> and </think> tags.
- You MUST put exactly ONE JSON object inside <tool_call> and </tool_call> tags. DO NOT output raw JSON without these tags.
- Do not output anything else outside those two blocks.
- INTERACTION: If you need to consult the user or ask a question, YOU MUST USE `action=ask_user`. 
- NO PROGRESS UPDATES: NEVER use `answer` to say "I will check..." or to explain your next move. If you know what to do, just use physical actions (click, swipe, system_button).
- TERMINATION: `answer` means the task is 100% OVER. ONLY use `answer` when you have entirely finished the user's request.
- If finishing, use mobile_use with action=terminate in the tool call.

# EXAMPLES OF CORRECT BEHAVIOR (PAY CLOSE ATTENTION):

[Scenario 1: You need missing information from the user]
<think>
The user wants to schedule a meeting, but hasn't provided the date and time. I must ask them for these details before I can proceed.
</think>
<tool_call>
{"name": "mobile_use", "arguments": {"action": "ask_user", "text": "What date and time would you like to schedule the meeting for?"}}
</tool_call>

[Scenario 2: The task is completely finished and you want to report the result]
<think>
I have successfully created the calendar event for 3 PM tomorrow. My job here is done.
</think>
<tool_call>
{"name": "mobile_use", "arguments": {"action": "answer", "text": "I have successfully scheduled the online meeting in your calendar."}}
</tool_call>
""")

MOBILE_QWEN3_5_ORIGINAL_PROMPT = Template("""# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{"type": "function", "function": {"name": "mobile_use", "description": "Use a touchscreen to interact with a mobile device, and take screenshots.\\n* This is an interface to a mobile device with touchscreen. You can perform actions like clicking, typing, swiping, etc.\\n* Some applications may take time to start or process actions, so you may need to wait and take successive screenshots to see the results of your actions.\\n* The screen's resolution is 999x999.\\n* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element. Don't click boxes on their edges unless asked.", "parameters": {"properties": {"action": {"description": "The action to perform. The available actions are:\\n* `click`: Click the point on the screen with coordinate (x, y).\\n* `long_press`: Press the point on the screen with coordinate (x, y) for specified seconds.\\n* `swipe`: Swipe from the starting point with coordinate (x, y) to the end point with coordinates2 (x2, y2).\\n* `type`: Input the specified text into the activated input box.\\n* `answer`: Output the answer and report the final result.\\n* `system_button`: Press the system button.\\n* `wait`: Wait specified seconds for the change to happen.\\n* `terminate`: Terminate the current task and report its completion status.", "enum": ["click", "long_press", "swipe", "type", "answer", "system_button", "wait", "terminate"], "type": "string"}, "coordinate": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=click`, `action=long_press`, and `action=swipe`.", "type": "array"}, "coordinate2": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=swipe`.", "type": "array"}, "text": {"description": "Required only by `action=type` and `action=answer`.", "type": "string"}, "time": {"description": "The seconds to wait. Required only by `action=long_press` and `action=wait`.", "type": "number"}, "button": {"description": "Back means returning to the previous interface, Home means returning to the desktop, Menu means opening the application background menu, and Enter means pressing the enter. Required only by `action=system_button`", "enum": ["Back", "Home", "Menu", "Enter"], "type": "string"}, "status": {"description": "The status of the task. Required only by `action=terminate`.", "type": "string", "enum": ["success", "failure"]}}, "required": ["action"], "type": "object"}}}
{% if tools %}
{{ tools }}
{% endif -%}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags.

# Response format

Response format for every step:
<think>
One concise sentence explaining the next move. Analyze the screen and decide what to do next.
</think>
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>

CRITICAL RULES:
- You MUST put your reasoning strictly inside <think> and </think> tags.
- You MUST put exactly ONE JSON object inside <tool_call> and </tool_call> tags. DO NOT output raw JSON without these tags.
- Do not output anything else outside those two blocks.
- NEVER use `answer` to give progress updates. If you know what to do next, just do it (click, swipe, etc.). `answer` means the task is OVER and you will give the user the answer.
- If finishing, use mobile_use with action=terminate in the tool call.

""")


MOBILE_QWEN3_5_USER_TEMPLATE = """
The user query: {instruction}
Task progress (You have done the following operation on the current device): {steps}
"""