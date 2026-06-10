from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.farm_tools import _format_farm_info_response, get_devices_status, get_farm_info


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


@pytest.mark.asyncio
async def test_get_farm_info_returns_structured_farm_data() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = [MOCK_API_RESPONSE]
    with patch("services.farm_tools.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        farm_info = await get_farm_info("test-jwt")

    assert farm_info["farms"][0]["name"] == "ReNile Environmental Station"
    assert farm_info["farms"][0]["project_type"] == "Zayed Environmental Station"
    assert farm_info["farms"][0]["connectivity"] == {
        "type": "Cellular",
        "renew_type": "Manual Renew",
        "manual_renew_date": "2026-05-17T00:00:00.000Z",
        "offline_notification_enabled": True,
        "offline_notification_duration": 2,
    }
    mock_response.raise_for_status.assert_called_once()


def test_format_farm_info_response_merges_sensor_config_with_latest_readings() -> None:
    farm_info = _format_farm_info_response(MOCK_API_RESPONSE)

    sensors = farm_info["farms"][0]["sensors"]
    so2 = sensors[0]
    ambient_temp = sensors[1]

    assert so2 == {
        "name": "SO2",
        "name_ar": "ثاني اكسيد الكبريت",
        "unit": "PPB",
        "current_reading": 9,
        "last_read_at": "2026-06-09T16:25:53.654Z",
        "lower_limit": 0,
        "upper_limit": 2000,
        "historical_min": 0,
        "historical_min_at": "2025-12-30T06:27:06.255Z",
        "historical_max": 428,
        "historical_max_at": "2025-07-17T13:12:54.417Z",
        "status": "normal",
    }
    assert ambient_temp["current_reading"] == 68
    assert ambient_temp["status"] == "above_limit"


def test_format_farm_info_response_omits_internal_and_noisy_fields() -> None:
    farm = _format_farm_info_response(MOCK_API_RESPONSE)["farms"][0]
    sensor = farm["sensors"][0]

    assert "employees" not in farm
    assert "_owner" not in farm
    assert "comment" not in farm
    assert "sendSms" not in sensor
    assert "_id" not in sensor


def test_format_farm_info_response_marks_missing_reading_unavailable() -> None:
    farm_info = _format_farm_info_response(MOCK_API_RESPONSE)

    wind_speed = farm_info["farms"][0]["sensors"][2]

    assert wind_speed["current_reading"] is None
    assert wind_speed["last_read_at"] is None
    assert wind_speed["status"] == "unavailable"


def test_get_devices_status_returns_expected_mock_fields() -> None:
    status = get_devices_status()

    assert set(status) == {"fans", "pumps", "lights"}
