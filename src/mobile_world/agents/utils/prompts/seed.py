from jinja2 import Template

SEED_PROMPT = Template("""## Function Definition

- You have access to the following functions:
{"type": "function", "name": "call_user", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "Message or information displayed to the user to request their input, feedback, or guidance."}}, "required": []}, "description": "This function is used to interact with the user by displaying a message and requesting their input, feedback, or guidance."}
{"type": "function", "name": "click", "parameters": {"type": "object", "properties": {"point": {"type": "string", "description": "Click coordinates. The format is: <point>x y</point>"}}, "required": ["point"]}, "description": "Mouse left single click action."}
{"type": "function", "name": "drag", "parameters": {"type": "object", "properties": {"start_point": {"type": "string", "description": "Drag start point. The format is: <point>x y</point>"}, "end_point": {"type": "string", "description": "Drag end point. The format is: <point>x y</point>"}}, "required": ["start_point", "end_point"]}, "description": "Mouse left button drag action."}
{"type": "function", "name": "finished", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "Provide the final answer or response to complete the task."}}, "required": []}, "description": "This function is used to indicate the completion of a task by providing the final answer or response."}
{"type": "function", "name": "press_home", "parameters": {}, "description": "Press home button."}
{"type": "function", "name": "press_back", "parameters": {}, "description": "Press back button."}
{"type": "function", "name": "left_double", "parameters": {"type": "object", "properties": {"point": {"type": "string", "description": "Click coordinates. The format is: <point>x y</point>"}}, "required": ["point"]}, "description": "Mouse left double click action."}
{"type": "function", "name": "scroll", "parameters": {"type": "object", "properties": {"point": {"type": "string", "description": "Scroll start position. If not specified, default to execute on the current mouse position. The format is: <point>x y</point>"}, "direction": {"type": "string", "description": "Scroll direction.", "enum": ["up", "down", "left", "right"]}}, "required": ["direction", "point"]}, "description": "Scroll action."}
{"type": "function", "name": "type", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "Type content. If you want to submit your input, use \n at the end of content."}}, "required": ["content"]}, "description": "Type content."}
{"type": "function", "name": "wait", "parameters": {"type": "object", "properties": {"time": {"type": "integer", "description": "Wait time in seconds."}}, "required": []}, "description": "Wait for a while."}

{% if tools -%}
## MCP Tools
You are also provided with MCP tools, you can use them to complete the task.
{{ tools }}
{% endif -%}

- To call a function, use the following structure without any suffix:

<think> reasoning process </think>
<tool_call><function=example_function_name><parameter=example_parameter_1>value_1</parameter><parameter=example_parameter_2>
This is the value for the second parameter
that can span
multiple lines
</parameter></function></tool_call>

## Important Notes
- Function calls must begin with <function= and end with </function>.
- All required parameters must be explicitly provided.""")
