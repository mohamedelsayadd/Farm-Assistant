from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

CAIRO_TIMEZONE = ZoneInfo("Africa/Cairo")
LATEST_READ_YEAR = 2026


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


def format_farm_info_response(api_response: Any) -> dict[str, Any]:
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


def format_device_ids_response(api_response: Any) -> dict[str, str]:
    raw_devices = api_response if isinstance(api_response, list) else [api_response]

    device_ids: dict[str, str] = {}
    for device in raw_devices:
        if not isinstance(device, dict):
            continue

        name = device.get("name")
        device_id = device.get("id")
        if isinstance(name, str) and isinstance(device_id, str):
            device_ids[name] = device_id

    return device_ids


def format_sensor_reads_at_time_response(
    api_response: Any,
    start_time: str,
    end_time: str,
) -> dict[str, Any]:
    start_at = _parse_cairo_timestamp(start_time)
    end_at = _parse_cairo_timestamp(end_time)
    if start_at is None or end_at is None:
        return {
            "timezone": "Africa/Cairo",
            "readings": [],
            "error": "start_time and end_time must be valid ISO 8601 timestamps.",
        }

    if end_at < start_at:
        return {
            "timezone": "Africa/Cairo",
            "readings": [],
            "error": "end_time must be greater than or equal to start_time.",
        }

    readings_by_time: dict[str, dict[str, Any]] = {}
    if not isinstance(api_response, dict):
        return {"timezone": "Africa/Cairo", "readings": []}

    for sensor_name, sensor_payload in api_response.items():
        if not isinstance(sensor_name, str) or not isinstance(sensor_payload, dict):
            continue

        labels = sensor_payload.get("labels")
        values = sensor_payload.get("data")
        if not isinstance(labels, list) or not isinstance(values, list):
            continue

        for label, value in zip(labels, values, strict=False):
            timestamp = _parse_utc_timestamp(label)
            if timestamp is None:
                continue

            cairo_timestamp = timestamp.astimezone(CAIRO_TIMEZONE)
            if not start_at <= cairo_timestamp <= end_at:
                continue

            time_key = cairo_timestamp.isoformat(timespec="milliseconds")
            readings_by_time.setdefault(time_key, {})[sensor_name] = _normalize_sensor_value(value)

    return {
        "timezone": "Africa/Cairo",
        "readings": [
            {"time": time_key, "sensors": sensors}
            for time_key, sensors in sorted(readings_by_time.items())
        ],
    }


def _build_sensors_metadata(device: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sensors_meta: dict[str, dict[str, Any]] = {}

    for sensor in device.get("sensortypes", []):
        if not isinstance(sensor, dict):
            continue

        sensor_type = (
            sensor.get("sensor_type")
            if isinstance(sensor.get("sensor_type"), dict)
            else {}
        )
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

    latest_readings: dict[str, tuple[dict[str, Any], datetime]] = {}
    for reading in raw_readings:
        if not isinstance(reading, dict):
            continue

        name = reading.get("name")
        if not isinstance(name, str) or not name:
            continue

        created_at = _parse_utc_timestamp(reading.get("createdAt"))
        if created_at is None or created_at.year != LATEST_READ_YEAR:
            continue

        previous = latest_readings.get(name)
        if previous is None or created_at > previous[1]:
            latest_readings[name] = (reading, created_at)

    return [
        _format_reading(reading, created_at, sensors_meta.get(name, {}))
        for name, (reading, created_at) in latest_readings.items()
    ]


def _format_reading(reading: dict[str, Any], created_at: datetime, meta: dict[str, Any]) -> ReadingOut:
    return ReadingOut(
        name=reading.get("name"),
        reading=reading.get("reading"),
        createdAt=_to_cairo_timestamp(created_at),
        unit=meta.get("unit"),
        label_ar=meta.get("label_ar"),
        lower_limit=meta.get("lower_limit"),
        upper_limit=meta.get("upper_limit"),
    )


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized_value)
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _parse_cairo_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized_value)
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=CAIRO_TIMEZONE)
    return timestamp.astimezone(CAIRO_TIMEZONE)


def _normalize_sensor_value(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("$numberDecimal"), str):
        try:
            return float(Decimal(value["$numberDecimal"]))
        except (InvalidOperation, ValueError):
            return value["$numberDecimal"]
    return value


def _to_cairo_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(CAIRO_TIMEZONE).isoformat(timespec="milliseconds")


def _get_nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
