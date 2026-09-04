from typing import Dict, Any
from backend.services.weather import WeatherService

TOOL_DEFINITION = {
    "name": "get_weather",
    "description": "Get current weather and short-term forecast for a specific location",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city or location name, e.g. 'Bangalore', 'London', 'San Francisco'"
            }
        },
        "required": ["location"]
    }
}

async def execute_get_weather(location: str) -> Dict[str, Any]:
    """Execute get_weather tool."""
    if not location or not location.strip():
        return {
            "success": False,
            "error": "Location parameter is required."
        }
    
    result = await WeatherService.fetch_weather(location.strip())
    return result
