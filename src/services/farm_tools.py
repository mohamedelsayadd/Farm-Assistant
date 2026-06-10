import logging
from typing import Any

import requests


logger = logging.getLogger(__name__)


def get_farm_info(JWT: str) -> dict[str, float]:
    logger.info("farm_readings_tool_started")

    response = requests.get(
        "https://renile-iot.com/api/users/devices/",
        headers={
            "Authorization": f"JWT {JWT}",
        }
    )

    return response.json()


def get_devices_status() -> dict[str, str]:
    logger.info("devices_status_tool_started")
    return {
        "fans": "on",
        "pumps": "off",
        "lights": "on",
    }


def execute_tool(JWT: str, name: str) -> dict[str, Any]:
    logger.info("tool_execution_requested tool_name=%s", name)
    tools = {
        "get_farm_info": get_farm_info,
        "get_devices_status": get_devices_status,
    }

    tool = tools.get(name)
    if tool is None:
        logger.warning("tool_execution_rejected tool_name=%s reason=unavailable", name)
        return {"error": f"Tool '{name}' is not available."}

    result = tool(JWT) if name == "get_farm_info" else tool()
    logger.info("tool_execution_completed tool_name=%s result_type=%s",
    name,
    type(result).__name__,
    )
    return result
