from services.farm_tools import get_devices_status, get_farm_info


def test_get_farm_info_returns_expected_mock_fields() -> None:
    readings = get_farm_info()

    assert set(readings) == {"temperature", "humidity", "soil_moisture", "co2"}


def test_get_devices_status_returns_expected_mock_fields() -> None:
    status = get_devices_status()

    assert set(status) == {"fans", "pumps", "lights"}
