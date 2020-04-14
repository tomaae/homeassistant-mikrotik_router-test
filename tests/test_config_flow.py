from datetime import timedelta
from unittest.mock import patch

import librouteros
import pytest

from homeassistant import data_entry_flow
from custom_components import mikrotik_router

from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SSL,
)

from . import MOCK_DATA

from tests.common import MockConfigEntry


@pytest.fixture(name="api")
def mock_mikrotik_api():
    """Mock an api."""
    with patch("librouteros.connect"):
        yield


@pytest.fixture(name="auth_error")
def mock_api_authentication_error():
    """Mock an api."""
    with patch(
        "librouteros.connect",
        side_effect=librouteros.exceptions.TrapError("invalid user name or password"),
    ):
        yield


@pytest.fixture(name="conn_error")
def mock_api_connection_error():
    """Mock an api."""
    with patch(
        "librouteros.connect", side_effect=librouteros.exceptions.ConnectionClosed
    ):
        yield


async def test_import(hass, api):
    """Test import step."""
    result = await hass.config_entries.flow.async_init(
        mikrotik_router.DOMAIN, context={"source": "import"}, data=MOCK_DATA
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "Mikrotik"
    assert result["data"][CONF_NAME] == "Mikrotik"
    assert result["data"][CONF_HOST] == "10.0.0.1"
    assert result["data"][CONF_USERNAME] == "admin"
    assert result["data"][CONF_PASSWORD] == "admin"
    assert result["data"][CONF_PORT] == 0
    assert result["data"][CONF_SSL] is False
