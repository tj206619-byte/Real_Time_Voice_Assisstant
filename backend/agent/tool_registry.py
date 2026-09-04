import json
import logging
from typing import List, Dict, Any, Tuple
from backend.tools.weather_tool import TOOL_DEFINITION as WEATHER_SCHEMA, execute_get_weather
from backend.tools.reminder_tool import TOOL_DEFINITION as REMINDER_SCHEMA, execute_create_reminder
from backend.tools.task_tool import TOOL_DEFINITION as TASK_SCHEMA, execute_create_task

logger = logging.getLogger("voicepilot.tools")

OPENAI_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": WEATHER_SCHEMA
    },
    {
        "type": "function",
        "function": REMINDER_SCHEMA
    },
    {
        "type": "function",
        "function": TASK_SCHEMA
    }
]

async def execute_tool(tool_name: str, arguments_str_or_dict: Any) -> Tuple[bool, Dict[str, Any]]:
    """
    Executes a registered tool by name with provided arguments.
    Returns (success_status, result_dictionary).
    """
    # Parse arguments if passed as JSON string
    if isinstance(arguments_str_or_dict, str):
        try:
            arguments = json.loads(arguments_str_or_dict) if arguments_str_or_dict.strip() else {}
        except Exception as e:
            logger.error(f"Error parsing tool arguments: {e}")
            return False, {"success": False, "error": f"Invalid tool arguments: {str(e)}"}
    else:
        arguments = arguments_str_or_dict or {}

    logger.info(f"Executing tool: '{tool_name}' with args: {arguments}")

    try:
        if tool_name == "get_weather":
            location = arguments.get("location", "")
            res = await execute_get_weather(location)
            return res.get("success", False), res

        elif tool_name == "create_reminder":
            title = arguments.get("title", "")
            datetime_val = arguments.get("datetime", "")
            res = await execute_create_reminder(title, datetime_val)
            return res.get("success", False), res

        elif tool_name == "create_task":
            title = arguments.get("title", "")
            priority = arguments.get("priority", "medium")
            due_date = arguments.get("due_date")
            res = await execute_create_task(title, priority, due_date)
            return res.get("success", False), res

        else:
            return False, {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Exception during tool execution '{tool_name}': {e}", exc_info=True)
        return False, {"success": False, "error": f"Tool execution failed: {str(e)}"}
