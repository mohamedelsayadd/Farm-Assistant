import json
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from core.settings import get_settings
from services.processing import (
    format_devices_last_reads_response,
    format_device_ids_response,
    format_sensor_reads_at_time_response,
)

settings = get_settings()
logger = logging.getLogger(__name__)
CAIRO_TIMEZONE = ZoneInfo("Africa/Cairo")


async def get_devices_last_reads(JWT: str) -> list[dict[str, dict[str, dict[str, Any]]]]:
    logger.info("devices_last_reads_tool_started")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.RENILE_DEVICES_API,
            headers={
                "Authorization": f"JWT {JWT}",
            },
            timeout=settings.API_TIMEOUT_SECONDS,
        )

    response.raise_for_status()
    raw_response = response.json()
    logger.info(
        "devices_last_reads_api_response response=%s",
        json.dumps(raw_response, ensure_ascii=False),
    )
    formatted_response = format_devices_last_reads_response(raw_response)
    logger.info(
        "devices_last_reads_tool_processed_response response=%s",
        json.dumps(formatted_response, ensure_ascii=False),
    )
    return formatted_response


async def get_device_id(JWT: str) -> dict[str, str]:
    logger.info("device_id_tool_started")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.RENILE_DEVICES_API,
            headers={
                "Authorization": f"JWT {JWT}",
            },
            timeout=settings.API_TIMEOUT_SECONDS,
        )

    response.raise_for_status()
    raw_response = response.json()
    logger.info(
        "device_id_api_response response=%s",
        json.dumps(raw_response, ensure_ascii=False),
    )
    formatted_response = format_device_ids_response(raw_response)
    logger.info(
        "device_id_tool_processed_response device_count=%s response=%s",
        len(formatted_response),
        json.dumps(formatted_response, ensure_ascii=False),
    )
    return formatted_response


async def get_sensors_reads_at_time(
    JWT: str,
    device_id: str,
    start_time: str,
    end_time: str,
    data_type: str,
) -> dict[str, Any]:
    data_type = _normalize_historical_data_type(start_time, end_time, data_type)
    logger.info(
        "sensor_reads_at_time_tool_started device_id=%s data_type=%s start_time=%s end_time=%s",
        device_id,
        data_type,
        start_time,
        end_time,
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.RENILE_DATA_API,
            headers={
                "Authorization": f"JWT {JWT}",
            },
            params={
                "device_id": device_id,
                "start_time": start_time,
                "data_type": data_type,
            },
            timeout=settings.API_TIMEOUT_SECONDS,
        )

    response.raise_for_status()
    raw_response = response.json()
    logger.info(
        "sensor_reads_at_time_api_response response=%s",
        json.dumps(raw_response, ensure_ascii=False),
    )
    formatted_response = format_sensor_reads_at_time_response(
        raw_response,
        start_time=start_time,
        end_time=end_time,
    )
    logger.info(
        "sensor_reads_at_time_tool_processed_response reading_count=%s response=%s",
        len(formatted_response.get("readings", [])),
        json.dumps(formatted_response, ensure_ascii=False),
    )
    return formatted_response


async def execute_tool(JWT: str, name: str, arguments: dict[str, Any] | None = None) -> Any:
    logger.info("tool_execution_requested tool_name=%s", name)
    tools = {
        "get_devices_last_reads": get_devices_last_reads,
        "get_device_id": get_device_id,
        "get_sensors_reads_at_time": get_sensors_reads_at_time,
    }

    tool = tools.get(name)
    if tool is None:
        logger.warning("tool_execution_rejected tool_name=%s reason=unavailable", name)
        return {"error": f"Tool '{name}' is not available."}

    arguments = arguments or {}
    if name == "get_sensors_reads_at_time":
        required_arguments = ("device_id", "start_time", "end_time", "data_type")
        missing_arguments = [argument for argument in required_arguments if not arguments.get(argument)]
        if missing_arguments:
            return {"error": f"Missing required arguments: {', '.join(missing_arguments)}."}
        if arguments["data_type"] not in {"day", "month"}:
            return {"error": "data_type must be either 'day' or 'month'."}

        result = await tool(
            JWT,
            device_id=arguments["device_id"],
            start_time=arguments["start_time"],
            end_time=arguments["end_time"],
            data_type=arguments["data_type"],
        )
    else:
        result = await tool(JWT)
    logger.info(
        "tool_execution_completed tool_name=%s result_type=%s",
        name,
        type(result).__name__,
    )
    return result


def _normalize_historical_data_type(start_time: str, end_time: str, data_type: str) -> str:
    start_at = _parse_cairo_timestamp(start_time)
    end_at = _parse_cairo_timestamp(end_time)
    if start_at is not None and end_at is not None and end_at - start_at > timedelta(hours=24):
        return "month"
    return data_type


def _parse_cairo_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=CAIRO_TIMEZONE)
    return timestamp.astimezone(CAIRO_TIMEZONE)
