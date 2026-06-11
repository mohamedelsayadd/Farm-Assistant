import json
import logging
from typing import Any

import httpx

from core.settings import get_settings
from services.processing import format_device_ids_response, format_farm_info_response

settings = get_settings()
logger = logging.getLogger(__name__)


async def get_farm_info(JWT: str) -> dict[str, Any]:
    logger.info("farm_readings_tool_started")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.RENILE_DEVICES_API,
            headers={
                "Authorization": f"JWT {JWT}",
            },
        )

    response.raise_for_status()
    formatted_response = format_farm_info_response(response.json())
    logger.info(
        "farm_readings_tool_processed_response response=%s",
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
        )

    response.raise_for_status()
    formatted_response = format_device_ids_response(response.json())
    logger.info("device_id_tool_processed_response device_count=%s", len(formatted_response))
    return formatted_response


async def execute_tool(JWT: str, name: str) -> dict[str, Any]:
    logger.info("tool_execution_requested tool_name=%s", name)
    tools = {
        "get_farm_info": get_farm_info,
        "get_device_id": get_device_id,
    }

    tool = tools.get(name)
    if tool is None:
        logger.warning("tool_execution_rejected tool_name=%s reason=unavailable", name)
        return {"error": f"Tool '{name}' is not available."}

    result = await tool(JWT)
    logger.info(
        "tool_execution_completed tool_name=%s result_type=%s",
        name,
        type(result).__name__,
    )
    return result
