import json
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


async def get_farm_info(JWT: str) -> dict[str, Any]:
    logger.info("farm_readings_tool_started")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://renile-iot.com/api/users/devices/",
            headers={
                "Authorization": f"JWT {JWT}",
            }
        )

    response.raise_for_status()
    formatted_response = _format_farm_info_response(response.json())
    logger.info(
        "farm_readings_tool_processed_response response=%s",
        json.dumps(formatted_response, ensure_ascii=False),
    )
    return formatted_response


def _format_farm_info_response(api_response: Any) -> dict[str, Any]:
    farms = api_response if isinstance(api_response, list) else [api_response]
    return {
        "farms": [
            _format_farm(farm)
            for farm in farms
            if isinstance(farm, dict)
        ]
    }


def _format_farm(farm: dict[str, Any]) -> dict[str, Any]:
    readings_by_name = {
        reading.get("name"): reading
        for reading in farm.get("lastRead", [])
        if isinstance(reading, dict) and reading.get("name")
    }

    return {
        "id": farm.get("id") or farm.get("_id"),
        "name": farm.get("name"),
        "project_type": _get_nested_value(farm, "_project", "type"),
        "connectivity": {
            "type": farm.get("connectivityType"),
            "renew_type": farm.get("connectivityRenewType"),
            "manual_renew_date": farm.get("connectivityManualRenewDate"),
            "offline_notification_enabled": farm.get("offlineNotificationEnabled"),
            "offline_notification_duration": farm.get("timeDuration"),
        },
        "created_at": farm.get("createdAt"),
        "last_updated_at": farm.get("updatedAt"),
        "sensors": [
            _format_sensor(sensor_config, readings_by_name)
            for sensor_config in farm.get("sensortypes", [])
            if isinstance(sensor_config, dict)
        ],
    }


def _format_sensor(sensor_config: dict[str, Any], readings_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sensor_type = sensor_config.get("sensor_type") if isinstance(sensor_config.get("sensor_type"), dict) else {}
    name = sensor_type.get("type")
    latest_reading = readings_by_name.get(name, {})
    current_reading = latest_reading.get("reading")
    lower_limit = sensor_config.get("lower_limit")
    upper_limit = sensor_config.get("upper_limit")

    return {
        "name": name,
        "name_ar": sensor_type.get("type_ar"),
        "unit": sensor_type.get("measurement_unit"),
        "current_reading": current_reading,
        "last_read_at": latest_reading.get("createdAt"),
        "lower_limit": lower_limit,
        "upper_limit": upper_limit,
        "historical_min": _get_nested_value(latest_reading, "min", "reading"),
        "historical_min_at": _get_nested_value(latest_reading, "min", "createdAt"),
        "historical_max": _get_nested_value(latest_reading, "max", "reading"),
        "historical_max_at": _get_nested_value(latest_reading, "max", "createdAt"),
        "status": _get_sensor_status(current_reading, lower_limit, upper_limit),
    }


def _get_sensor_status(reading: Any, lower_limit: Any, upper_limit: Any) -> str:
    if not isinstance(reading, int | float):
        return "unavailable"
    if not isinstance(lower_limit, int | float) or not isinstance(upper_limit, int | float):
        return "normal"
    if lower_limit > upper_limit:
        return "normal"
    if reading < lower_limit:
        return "below_limit"
    if reading > upper_limit:
        return "above_limit"
    return "normal"


def _get_nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def get_devices_status() -> dict[str, str]:
    logger.info("devices_status_tool_started")
    return {
        "fans": "on",
        "pumps": "off",
        "lights": "on",
    }


async def execute_tool(JWT: str, name: str) -> dict[str, Any]:
    logger.info("tool_execution_requested tool_name=%s", name)
    tools = {
        "get_farm_info": get_farm_info,
        "get_devices_status": get_devices_status,
    }

    tool = tools.get(name)
    if tool is None:
        logger.warning("tool_execution_rejected tool_name=%s reason=unavailable", name)
        return {"error": f"Tool '{name}' is not available."}

    result = await tool(JWT) if name == "get_farm_info" else tool()
    logger.info("tool_execution_completed tool_name=%s result_type=%s",
    name,
    type(result).__name__,
    )
    return result
