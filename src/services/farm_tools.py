import logging
from typing import Any


logger = logging.getLogger(__name__)


def get_farm_readings() -> dict[str, float]:
    logger.info("farm_readings_tool_started")
    return {
        "temperature": 27.4,
        "humidity": 62.0,
        "soil_moisture": 38.5,
        "co2": 510.0,
    }


def get_devices_status() -> dict[str, str]:
    logger.info("devices_status_tool_started")
    return {
        "fans": "on",
        "pumps": "off",
        "lights": "on",
    }


def execute_tool(name: str) -> dict[str, Any]:
    logger.info("tool_execution_requested tool_name=%s", name)
    tools = {
        "get_farm_readings": get_farm_readings,
        "get_devices_status": get_devices_status,
    }

    tool = tools.get(name)
    if tool is None:
        logger.warning("tool_execution_rejected tool_name=%s reason=unavailable", name)
        return {"error": f"Tool '{name}' is not available."}

    result = tool()
    logger.info("tool_execution_completed tool_name=%s result_keys=%s", name, sorted(result.keys()))
    return result
