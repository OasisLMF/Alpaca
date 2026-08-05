from alpaca.api.utils import REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API
from alpaca.model.utils import REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL
from alpaca.pytest.utils import REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST
from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from unittest import mock
from alpaca.cli.config_router import CONFIGS, create_config_router


def test_router_configs():
    assert 'model' in CONFIGS
    assert 'api' in CONFIGS
    assert 'pytest' in CONFIGS
    assert 'benchmark' in CONFIGS
    assert CONFIGS['api'] == (REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API)
    assert CONFIGS['model'] == (REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL)
    assert CONFIGS['pytest'] == (REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST)
    assert CONFIGS['benchmark'] == (REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)


@mock.patch("alpaca.cli.config_router.create_config")
def test_router_api_with_arg_config(mock_create_config):
    create_config_router(["aPI"])
    mock_create_config.assert_called_once_with(REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API)


@mock.patch("alpaca.cli.config_router.create_config")
def test_router_model_with_arg_config(mock_create_config):
    create_config_router(["MODEL"])
    mock_create_config.assert_called_once_with(REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL)


@mock.patch("alpaca.cli.config_router.create_config")
def test_router_pytest_with_arg_config(mock_create_config):
    create_config_router(["pYtEsT"])
    mock_create_config.assert_called_once_with(REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST)


@mock.patch("alpaca.cli.config_router.create_config")
def test_router_benchmark_with_arg_config(mock_create_config):
    create_config_router(["bEnChMaRk"])
    mock_create_config.assert_called_once_with(REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)


@mock.patch("alpaca.cli.config_router.input")
@mock.patch("alpaca.cli.config_router.create_config")
def test_router_with_no_arg_config(mock_create_config, mock_input):
    mock_input.return_value = "API"
    create_config_router([])
    mock_create_config.assert_called_once_with(REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API)

# def test_router_returns_model_config(restore_routing):
#     assert config_router.ROUTING["model"] is create_model_config
#     config_router.ROUTING["model"] = mock.Mock()
#     config_router.create_config_router(["model"])
#     config_router.ROUTING["model"].assert_called_once_with()


# def test_router_returns_pytest_config(restore_routing):
#     assert config_router.ROUTING["pytest"] is create_pytest_config
#     config_router.ROUTING["pytest"] = mock.Mock()
#     config_router.create_config_router(["pytest"])
#     config_router.ROUTING["pytest"].assert_called_once_with()
