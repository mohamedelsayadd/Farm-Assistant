import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from core.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class EmployeeOut(BaseModel):
    user_id: str | None = None
    role: str | None = None

class ReadingOut(BaseModel):
    name: str | None = None
    value: Any = Field(default=None, alias="reading")
    created_at: str | None = Field(default=None, alias="createdAt")
    unit: str | None = None
    label_ar: str | None = None
    lower_limit: float | int | None = None
    upper_limit: float | int | None = None

    model_config = ConfigDict(populate_by_name=True)

class DeviceOut(BaseModel):
    device_id: str | None = None
    device_name: str | None = None
    employees: list[EmployeeOut] = Field(default_factory=list)
    readings: list[ReadingOut] = Field(default_factory=list)

class FarmDevicesOut(BaseModel):
    farm: str | None = None
    devices: list[DeviceOut] = Field(default_factory=list)


async def get_farm_info(JWT: str) -> dict[str, Any]:
    logger.info("farm_readings_tool_started")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.RENILE_DEVICES_API,
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
    raw_devices = api_response if isinstance(api_response, list) else [api_response]
    devices: list[DeviceOut] = []
    farm_name: str | None = None

    for device in raw_devices:
        if not isinstance(device, dict):
            continue

        if farm_name is None:
            farm_name = _get_nested_value(device, "_project", "type")

        sensors_meta = _build_sensors_metadata(device)
        devices.append(
            DeviceOut(
                device_id=device.get("_id") or device.get("id"),
                device_name=device.get("name"),
                employees=_format_employees(device.get("employees", [])),
                readings=_format_readings(device.get("lastRead", []), sensors_meta),
            )
        )

    return FarmDevicesOut(farm=farm_name, devices=devices).model_dump()


def _build_sensors_metadata(device: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sensors_meta: dict[str, dict[str, Any]] = {}

    for sensor in device.get("sensortypes", []):
        if not isinstance(sensor, dict):
            continue

        sensor_type = sensor.get("sensor_type") if isinstance(sensor.get("sensor_type"), dict) else {}
        sensor_name = sensor_type.get("type")
        if not sensor_name:
            continue

        sensors_meta[sensor_name] = {
            "unit": sensor_type.get("measurement_unit"),
            "label_ar": sensor_type.get("type_ar"),
            "lower_limit": sensor.get("lower_limit"),
            "upper_limit": sensor.get("upper_limit"),
        }

    return sensors_meta


def _format_employees(raw_employees: Any) -> list[EmployeeOut]:
    if not isinstance(raw_employees, list):
        return []

    return [
        EmployeeOut(
            user_id=_get_nested_value(employee, "user", "_id"),
            role=employee.get("role"),
        )
        for employee in raw_employees
        if isinstance(employee, dict)
    ]


def _format_readings(raw_readings: Any, sensors_meta: dict[str, dict[str, Any]]) -> list[ReadingOut]:
    if not isinstance(raw_readings, list):
        return []

    readings: list[ReadingOut] = []
    for reading in raw_readings:
        if not isinstance(reading, dict):
            continue

        name = reading.get("name")
        meta = sensors_meta.get(name, {})
        readings.append(
            ReadingOut(
                name=name,
                reading=reading.get("reading"),
                createdAt=reading.get("createdAt"),
                unit=meta.get("unit"),
                label_ar=meta.get("label_ar"),
                lower_limit=meta.get("lower_limit"),
                upper_limit=meta.get("upper_limit"),
            )
        )

    return readings


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
