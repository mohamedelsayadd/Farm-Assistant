from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.farm_tools import get_device_id, get_farm_info, get_sensors_reads_at_time
from services.processing import (
    format_device_ids_response,
    format_farm_info_response,
    format_sensor_reads_at_time_response,
)


MOCK_API_RESPONSE = {
    "connectivityType": "Cellular",
    "connectivityRenewType": "Manual Renew",
    "connectivityManualRenewDate": "2026-05-17T00:00:00.000Z",
    "offlineNotificationEnabled": True,
    "timeDuration": 2,
    "_id": "farm-object-id",
    "employees": [{"role": "Manager", "user": {"_id": "user-id"}}],
    "name": "ReNile Environmental Station",
    "_owner": {"_id": "owner-id"},
    "_project": {
        "_id": "project-id",
        "type": "Zayed Environmental Station",
    },
    "sensortypes": [
        {
            "sendSms": False,
            "_id": "sensor-config-id",
            "sensor_type": {
                "_id": "sensor-type-id",
                "type": "SO2",
                "type_ar": "ثاني اكسيد الكبريت",
                "measurement_unit": "PPB",
            },
            "upper_limit": 2000,
            "lower_limit": 0,
        },
        {
            "sensor_type": {
                "type": "ambient_temp",
                "type_ar": "درجه حراره الجو",
                "measurement_unit": "°C",
            },
            "lower_limit": -40,
            "upper_limit": 60,
        },
        {
            "sensor_type": {
                "type": "Wind_Speed",
                "type_ar": "سرعة الرياح",
                "measurement_unit": "m/s",
            },
            "lower_limit": 0,
            "upper_limit": 60,
        },
    ],
    "lastRead": [
        {
            "min": {
                "reading": 0,
                "createdAt": "2025-12-30T06:27:06.255Z",
            },
            "max": {
                "reading": 428,
                "createdAt": "2025-07-17T13:12:54.417Z",
            },
            "reading": 9,
            "_id": "reading-id",
            "name": "SO2",
            "createdAt": "2026-06-09T16:25:53.654Z",
        },
        {
            "min": {"reading": 10.08, "createdAt": "2025-06-19T03:15:27.152Z"},
            "max": {"reading": 40.9, "createdAt": "2025-07-16T15:32:47.019Z"},
            "reading": 68,
            "name": "ambient_temp",
            "createdAt": "2026-06-09T11:23:23.437Z",
        },
    ],
    "createdAt": "2025-05-04T10:25:54.600Z",
    "updatedAt": "2026-06-09T22:45:01.077Z",
    "comment": "01109253162",
    "id": "farm-id",
}

MOCK_HISTORICAL_READS_RESPONSE = {
    "CO2": {
        "labels": [
            "2026-05-28T22:00:00.000Z",
            "2026-05-28T23:00:00.000Z",
            "2026-05-29T00:00:00.000Z",
        ],
        "data": [
            {"$numberDecimal": "535.0810439560439560439560439560439"},
            {"$numberDecimal": "545.657967032967032967032967032967"},
            {"$numberDecimal": "572.1923076923076923076923076923077"},
        ],
    },
    "ambient_temp": {
        "labels": [
            "2026-05-28T22:00:00.000Z",
            "2026-05-28T23:00:00.000Z",
            "2026-05-29T00:00:00.000Z",
        ],
        "data": [
            {"$numberDecimal": "19.58885989010989010989010989010989"},
            {"$numberDecimal": "19.12501373626373626373626373626374"},
            {"$numberDecimal": "18.45662087912087912087912087912088"},
        ],
    },
}


@pytest.mark.asyncio
async def test_get_farm_info_returns_structured_farm_data() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = [MOCK_API_RESPONSE]
    with patch("services.farm_tools.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        farm_info = await get_farm_info("test-jwt")

    assert farm_info["farm"] == "Zayed Environmental Station"
    assert farm_info["devices"][0]["device_id"] == "farm-object-id"
    assert farm_info["devices"][0]["device_name"] == "ReNile Environmental Station"
    mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_get_device_id_returns_device_name_id_mapping() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = [MOCK_API_RESPONSE]
    with patch("services.farm_tools.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        device_ids = await get_device_id("test-jwt")

    assert device_ids == {"ReNile Environmental Station": "farm-id"}
    mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_get_sensors_reads_at_time_calls_data_api_and_returns_processed_readings() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_HISTORICAL_READS_RESPONSE
    with patch("services.farm_tools.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        readings = await get_sensors_reads_at_time(
            "test-jwt",
            device_id="device-1",
            start_time="2026-05-29T01:00:00+03:00",
            end_time="2026-05-29T02:00:00+03:00",
            data_type="hour",
        )

    mock_get.assert_awaited_once_with(
        "https://renile-iot.com/api/v1/data/",
        headers={"Authorization": "JWT test-jwt"},
        params={
            "device_id": "device-1",
            "start_time": "2026-05-29T01:00:00+03:00",
            "data_type": "hour",
        },
    )
    mock_response.raise_for_status.assert_called_once()
    assert readings == {
        "timezone": "Africa/Cairo",
        "readings": [
            {
                "time": "2026-05-29T01:00:00.000+03:00",
                "sensors": {
                    "CO2": 535.0810439560439,
                    "ambient_temp": 19.58885989010989,
                },
            },
            {
                "time": "2026-05-29T02:00:00.000+03:00",
                "sensors": {
                    "CO2": 545.657967032967,
                    "ambient_temp": 19.125013736263735,
                },
            },
        ],
    }


def test_format_farm_info_response_merges_sensor_metadata_with_latest_readings() -> None:
    farm_info = format_farm_info_response(MOCK_API_RESPONSE)

    readings = farm_info["devices"][0]["readings"]
    so2 = readings[0]
    ambient_temp = readings[1]

    assert so2 == {
        "name": "SO2",
        "value": 9,
        "created_at": "2026-06-09T19:25:53.654+03:00",
        "unit": "PPB",
        "label_ar": "ثاني اكسيد الكبريت",
        "lower_limit": 0,
        "upper_limit": 2000,
    }
    assert ambient_temp["value"] == 68
    assert ambient_temp["created_at"] == "2026-06-09T14:23:23.437+03:00"
    assert ambient_temp["label_ar"] == "درجه حراره الجو"
    assert ambient_temp["lower_limit"] == -40
    assert ambient_temp["upper_limit"] == 60


def test_format_farm_info_response_maps_employees() -> None:
    farm_info = format_farm_info_response(MOCK_API_RESPONSE)

    assert farm_info["devices"][0]["employees"] == [
        {
            "user_id": "user-id",
            "role": "Manager",
        }
    ]


def test_format_farm_info_response_omits_internal_and_noisy_fields() -> None:
    farm_info = format_farm_info_response(MOCK_API_RESPONSE)
    device = farm_info["devices"][0]
    reading = device["readings"][0]

    assert "connectivity" not in farm_info
    assert "_owner" not in device
    assert "comment" not in device
    assert "sensortypes" not in device
    assert "sendSms" not in reading
    assert "_id" not in reading
    assert "min" not in reading
    assert "max" not in reading


def test_format_farm_info_response_omits_configured_sensors_without_readings() -> None:
    farm_info = format_farm_info_response(MOCK_API_RESPONSE)

    reading_names = {reading["name"] for reading in farm_info["devices"][0]["readings"]}

    assert "Wind_Speed" not in reading_names


def test_format_farm_info_response_omits_readings_outside_2026() -> None:
    response = {
        **MOCK_API_RESPONSE,
        "lastRead": [
            {
                "name": "Battery_level",
                "reading": 99,
                "createdAt": "2022-12-13T13:59:55.194Z",
            }
        ],
    }

    readings = format_farm_info_response(response)["devices"][0]["readings"]

    assert readings == []


def test_format_farm_info_response_handles_reading_without_sensor_metadata() -> None:
    response = {
        **MOCK_API_RESPONSE,
        "lastRead": [
            {
                "name": "Battery_level",
                "reading": 99,
                "createdAt": "2026-12-13T13:59:55.194Z",
            }
        ],
    }

    reading = format_farm_info_response(response)["devices"][0]["readings"][0]

    assert reading == {
        "name": "Battery_level",
        "value": 99,
        "created_at": "2026-12-13T15:59:55.194+02:00",
        "unit": None,
        "label_ar": None,
        "lower_limit": None,
        "upper_limit": None,
    }


def test_format_farm_info_response_keeps_latest_2026_reading_per_sensor() -> None:
    response = {
        **MOCK_API_RESPONSE,
        "lastRead": [
            {
                "name": "SO2",
                "reading": 9,
                "createdAt": "2026-06-09T16:25:53.654Z",
            },
            {
                "name": "SO2",
                "reading": 12,
                "createdAt": "2026-06-09T18:25:53.654Z",
            },
            {
                "name": "SO2",
                "reading": 20,
                "createdAt": "2025-06-09T20:25:53.654Z",
            },
            {
                "name": "ambient_temp",
                "reading": 68,
                "createdAt": "2026-06-09T11:23:23.437Z",
            },
        ],
    }

    readings = format_farm_info_response(response)["devices"][0]["readings"]

    assert readings[0]["name"] == "SO2"
    assert readings[0]["value"] == 12
    assert readings[0]["created_at"] == "2026-06-09T21:25:53.654+03:00"
    assert readings[1]["name"] == "ambient_temp"
    assert len(readings) == 2


def test_format_farm_info_response_handles_single_object_and_list_responses() -> None:
    single_response = format_farm_info_response(MOCK_API_RESPONSE)
    list_response = format_farm_info_response([MOCK_API_RESPONSE])

    assert single_response == list_response


def test_format_device_ids_response_maps_device_names_to_ids() -> None:
    device_ids = format_device_ids_response(
        [
            {"name": "Media Monitoring System", "id": "63590cc1d39b8a2f99239130"},
            {"name": "Greenhouse Climate Control", "id": "63951516d034b209322a0fe6"},
            {"name": "Ignored Missing ID"},
            {"id": "ignored-missing-name"},
            "ignored-invalid-device",
        ]
    )

    assert device_ids == {
        "Media Monitoring System": "63590cc1d39b8a2f99239130",
        "Greenhouse Climate Control": "63951516d034b209322a0fe6",
    }


def test_format_sensor_reads_at_time_response_converts_to_cairo_and_clips_by_end_time() -> None:
    readings = format_sensor_reads_at_time_response(
        MOCK_HISTORICAL_READS_RESPONSE,
        start_time="2026-05-29T01:00:00+03:00",
        end_time="2026-05-29T02:00:00+03:00",
    )

    assert readings["timezone"] == "Africa/Cairo"
    assert readings["readings"] == [
        {
            "time": "2026-05-29T01:00:00.000+03:00",
            "sensors": {
                "CO2": 535.0810439560439,
                "ambient_temp": 19.58885989010989,
            },
        },
        {
            "time": "2026-05-29T02:00:00.000+03:00",
            "sensors": {
                "CO2": 545.657967032967,
                "ambient_temp": 19.125013736263735,
            },
        },
    ]


def test_format_sensor_reads_at_time_response_rejects_invalid_time_range() -> None:
    readings = format_sensor_reads_at_time_response(
        MOCK_HISTORICAL_READS_RESPONSE,
        start_time="2026-05-29T03:00:00+03:00",
        end_time="2026-05-29T02:00:00+03:00",
    )

    assert readings == {
        "timezone": "Africa/Cairo",
        "readings": [],
        "error": "end_time must be greater than or equal to start_time.",
    }
