from crewai.tools import tool


@tool("get_weather")
def tool(city: str) -> str:
    """
    Get weather information for a city.
    """
    return f"Weather information for {city} is not implemented yet."