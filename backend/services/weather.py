import httpx
from typing import Dict, Any, Optional

WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}

class WeatherService:
    @staticmethod
    async def get_coordinates(location: str) -> Optional[Dict[str, Any]]:
        """Geocode location string to latitude, longitude and resolved name."""
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": location, "count": 1, "language": "en", "format": "json"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(geo_url, params=params)
            if response.status_code != 200:
                return None
            
            data = response.json()
            if not data.get("results"):
                return None
            
            result = data["results"][0]
            return {
                "name": result.get("name"),
                "country": result.get("country", ""),
                "admin1": result.get("admin1", ""),
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude")
            }

    @staticmethod
    async def fetch_weather(location: str) -> Dict[str, Any]:
        """Fetch real-time weather and short-term forecast for a location."""
        try:
            geo = await WeatherService.get_coordinates(location)
            if not geo:
                return {
                    "success": False,
                    "error": f"Could not find coordinates for location '{location}'"
                }

            lat = geo["latitude"]
            lon = geo["longitude"]
            place_name = f"{geo['name']}, {geo['country']}" if geo['country'] else geo['name']

            weather_url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto"
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(weather_url, params=params)
                if res.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Weather API returned status {res.status_code}"
                    }

                data = res.json()
                current = data.get("current", {})
                daily = data.get("daily", {})

                w_code = current.get("weather_code", 0)
                condition = WMO_WEATHER_CODES.get(w_code, "Clear")

                # Daily forecast summary (today & tomorrow)
                tomorrow_condition = "Clear"
                tomorrow_temp_max = None
                tomorrow_temp_min = None
                tomorrow_rain_prob = None
                
                if daily.get("weather_code") and len(daily["weather_code"]) > 1:
                    tomorrow_w_code = daily["weather_code"][1]
                    tomorrow_condition = WMO_WEATHER_CODES.get(tomorrow_w_code, "Clear")
                    tomorrow_temp_max = daily.get("temperature_2m_max", [None, None])[1]
                    tomorrow_temp_min = daily.get("temperature_2m_min", [None, None])[1]
                    tomorrow_rain_prob = daily.get("precipitation_probability_max", [None, None])[1]

                return {
                    "success": True,
                    "location": place_name,
                    "temperature": current.get("temperature_2m"),
                    "unit": "°C",
                    "feels_like": current.get("apparent_temperature"),
                    "humidity": current.get("relative_humidity_2m"),
                    "condition": condition,
                    "wind_speed": f"{current.get('wind_speed_10m')} km/h",
                    "precipitation": current.get("precipitation"),
                    "tomorrow_forecast": {
                        "condition": tomorrow_condition,
                        "temp_max": tomorrow_temp_max,
                        "temp_min": tomorrow_temp_min,
                        "rain_probability": f"{tomorrow_rain_prob}%" if tomorrow_rain_prob is not None else None
                    }
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to retrieve weather data: {str(e)}"
            }
