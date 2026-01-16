from alpaca.api.utils import create_api_config
from alpaca.model.utils import create_model_config
from alpaca.pytest.utils import create_pytest_config
from unittest import mock
from alpaca.cli import config_router
import pytest


@pytest.fixture
def restore_routing():
    original = config_router.ROUTING.copy()
    yield
    config_router.ROUTING = original


def test_router_returns_api_config(restore_routing):
    assert config_router.ROUTING["api"] is create_api_config
    config_router.ROUTING["api"] = mock.Mock()
    config_router.create_config_router(["api"])
    config_router.ROUTING["api"].assert_called_once_with()


def test_router_returns_model_config(restore_routing):
    assert config_router.ROUTING["model"] is create_model_config
    config_router.ROUTING["model"] = mock.Mock()
    config_router.create_config_router(["model"])
    config_router.ROUTING["model"].assert_called_once_with()


def test_router_returns_pytest_config(restore_routing):
    assert config_router.ROUTING["pytest"] is create_pytest_config
    config_router.ROUTING["pytest"] = mock.Mock()
    config_router.create_config_router(["pytest"])
    config_router.ROUTING["pytest"].assert_called_once_with()
